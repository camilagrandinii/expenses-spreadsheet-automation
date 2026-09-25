"""
Teste e validação da integração com Microsoft Graph API.

Uso:
    pip install requests msal
    python test_graph_api.py

Fluxo:
    1. Na primeira execução, autentica via Device Code (browser)
    2. Salva tokens.json localmente (você vai fazer upload para o Azure Blob Storage)
    3. inspect_sheet() mostra a estrutura detectada e o mapeamento de colunas
    4. test_add_expenses() insere linhas de teste para confirmar que tudo está correto
"""

import json
import re
import requests
from collections import defaultdict
from datetime import date
from msal import PublicClientApplication, SerializableTokenCache

# ── Configuração ──────────────────────────────────────────────────────────────
CLIENT_ID  = "9b36dc52-ac95-42cd-98ad-4102933c4e81"
FILE_PATH  = "/Finanças 2026 - Belo Horizonte.xlsx"
TOKEN_FILE = "tokens.json"
SCOPES     = ["Files.ReadWrite"]
# ─────────────────────────────────────────────────────────────────────────────

GRAPH = "https://graph.microsoft.com/v1.0"

MONTHS_PT = {
    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}

CATEGORY_MAP = {
    "comida":       "Comida - dia a dia",
    "saida":        "Saída entre amigos",
    "viagem":       "Passagens de Viagem",
    "acomodacao":   "Acomodação em Viagem",
    "higiene":      "Higiene / Skin Care",
    "transporte":   "Transporte",
    "roupas":       "Roupas / Bolsas / Joias / Sapatos / Make / Glitter",
    "lazer":        "Lazer / Experiências",
    "fitness":      "Vida Fitness / Saúde",
    "estudos":      "Estudos",
    "burocracia":   "Burocracias",
    "telefone":     "Telefone / Eletrônicos",
    "presentes":    "Presentes",
    "investimentos":"Investimentos",
}

BANK_MAP = {
    "nubank":   "Nubank",
    "nu bank":  "Nubank",
    "inter":    "Inter",
    "ifood":    "Ifood Benefícios",
    "alelo":    "Alelo",
    "wise":     "Wise",
}

PAYMENT_INLINE = {
    "pix":     "Pix",
    "crédito": "Cartão de Crédito",
    "credito": "Cartão de Crédito",
    "débito":  "Cartão de Débito",
    "debito":  "Cartão de Débito",
}


# ── Note parsing ──────────────────────────────────────────────────────────────

def parse_note(note_text: str, year: int = None) -> list:
    """
    Parses note text in the format:
        DD/MM
        description [category]: value bank payment_keyword

    payment_keyword can appear without parentheses (e.g. "pix", "crédito")
    or in the old (Pix) form — both are handled.

    Returns a list of expense dicts ready to write to the spreadsheet.
    """
    if year is None:
        year = date.today().year

    expenses = []
    current_date = date.today().strftime(f"%d/%m/{year}")

    for raw_line in note_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"^\d{2}/\d{2}$", line):
            day, month = line.split("/")
            current_date = f"{day}/{month}/{year}"
            continue

        if ":" not in line:
            continue

        before_colon, after_colon = line.split(":", 1)
        after_colon = after_colon.strip()

        tag_match = re.search(r"\[([^\]]+)\]", before_colon)
        category_tag = tag_match.group(1).strip() if tag_match else ""
        destino = re.sub(r"\s*\[[^\]]*\]", "", before_colon).strip()

        # Strip (payment) parentheses form if present
        paren_match = re.search(r"\(([^)]+)\)", after_colon)
        after_colon_clean = re.sub(r"\([^)]+\)", "", after_colon).strip()

        parts = after_colon_clean.split()
        if not parts:
            continue

        try:
            valor = float(parts[0].replace(",", "."))
        except ValueError:
            continue

        rest = parts[1:]

        # Check if the last word is an inline payment keyword
        if rest and rest[-1].lower() in PAYMENT_INLINE:
            pagamento = PAYMENT_INLINE[rest[-1].lower()]
            banco_bruto = " ".join(rest[:-1]).lower().strip()
        elif paren_match:
            pagamento = PAYMENT_INLINE.get(paren_match.group(1).strip().lower(), "Cartão de Crédito")
            banco_bruto = " ".join(rest).lower().strip()
        else:
            pagamento = "Cartão de Crédito"
            banco_bruto = " ".join(rest).lower().strip()

        if banco_bruto == "dinheiro":
            banco = ""
            pagamento = "Dinheiro"
        else:
            banco = BANK_MAP.get(banco_bruto, banco_bruto.title() if banco_bruto else "")

        if valor > 0:
            valor = -valor

        expenses.append({
            "destino":     destino,
            "data":        current_date,
            "motivo":      CATEGORY_MAP.get(category_tag, category_tag),
            "banco":       banco,
            "pagamento":   pagamento,
            "infos_extra": destino,   # G = same description as written
            "valor":       valor,
        })

    return expenses


# ── Auth (via MSAL) ───────────────────────────────────────────────────────────

MSAL_CACHE_FILE = "msal_cache.json"  # MSAL internal cache — local only, not uploaded


def _make_msal_app(cache):
    return PublicClientApplication(
        CLIENT_ID,
        authority="https://login.microsoftonline.com/consumers",
        token_cache=cache,
    )


def _load_cache():
    cache = SerializableTokenCache()
    try:
        with open(MSAL_CACHE_FILE) as f:
            cache.deserialize(f.read())
    except FileNotFoundError:
        pass
    return cache


def _save_cache(cache):
    if cache.has_state_changed:
        with open(MSAL_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def _save_azure_tokens(cache, access_token: str):
    """
    Saves tokens.json in the flat format the Azure Function expects:
        {"refresh_token": "...", "access_token": "..."}

    The refresh token is extracted from MSAL's internal cache structure.
    This file is what gets uploaded to Azure Blob Storage.
    """
    cache_data = json.loads(cache.serialize())
    rt_entries = cache_data.get("RefreshToken", {})
    if not rt_entries:
        raise RuntimeError("Refresh token não encontrado no cache MSAL.")
    refresh_token = next(iter(rt_entries.values()))["secret"]
    with open(TOKEN_FILE, "w") as f:
        json.dump({"refresh_token": refresh_token, "access_token": access_token}, f, indent=2)
    print(f"  {TOKEN_FILE} salvo no formato correto para o Azure Function ✓")


def get_access_token() -> str:
    cache    = _load_cache()
    msal_app = _make_msal_app(cache)

    accounts = msal_app.get_accounts()
    if accounts:
        result = msal_app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            _save_azure_tokens(cache, result["access_token"])
            return result["access_token"]

    flow = msal_app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Erro ao iniciar device flow: {flow}")

    print("\n" + "=" * 60)
    print(flow["message"])
    print("=" * 60 + "\n")

    result = msal_app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Falha na autenticação: {result.get('error_description', result)}")

    _save_cache(cache)
    _save_azure_tokens(cache, result["access_token"])
    print("  Autenticado!\n")
    return result["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def list_folder(token, path="/"):
    """
    Lists files and folders at a given OneDrive path.
    Use path="/" for root, path="/Documents" for the Documents folder, etc.
    """
    if path in ("/", ""):
        url = f"{GRAPH}/me/drive/root/children"
    else:
        url = f"{GRAPH}/me/drive/root:{path}:/children"

    r = requests.get(url, headers=_h(token))
    if r.status_code == 404:
        print(f"  Pasta não encontrada: {path}")
        return []
    r.raise_for_status()
    items = r.json().get("value", [])
    for item in items:
        kind = "📁" if "folder" in item else "📄"
        print(f"    {kind} {item['name']}")
    return items


def browse_drive(token):
    """
    Interactively walks the OneDrive folder tree so you can find the correct
    FILE_PATH to put in the config above.
    """
    print("\n=== Navegador do OneDrive ===")
    print("Use isso para encontrar o caminho correto até o arquivo .xlsx\n")

    path = ""
    while True:
        display = path if path else "/ (raiz)"
        print(f"\nConteúdo de: {display}")
        items = list_folder(token, path if path else "/")

        if not items:
            print("  (pasta vazia ou não encontrada)")

        print("\nOpções:")
        print("  [número] Entrar na pasta")
        print("  [v] Voltar um nível")
        print("  [q] Sair e mostrar o caminho atual")

        choice = input("Escolha: ").strip().lower()

        if choice == "q":
            print(f"\nCaminho atual: {path}/")
            print("Para usar um arquivo .xlsx nessa pasta, defina FILE_PATH como:")
            print(f'  FILE_PATH = "{path}/NomeDoArquivo.xlsx"')
            break
        elif choice == "v":
            path = "/".join(path.split("/")[:-1])
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    item = items[idx]
                    if "folder" in item:
                        path = f"{path}/{item['name']}"
                    else:
                        full_path = f"{path}/{item['name']}"
                        print(f"\nArquivo selecionado. Use este FILE_PATH:")
                        print(f'  FILE_PATH = "{full_path}"')
                        return full_path
                else:
                    print("  Número inválido.")
            except ValueError:
                print("  Opção não reconhecida.")

    return None


def get_file_id(token):
    r = requests.get(f"{GRAPH}/me/drive/root:{FILE_PATH}", headers=_h(token))
    if r.status_code == 404:
        print(f"\n  ERRO 404: arquivo não encontrado no caminho:")
        print(f"    {FILE_PATH}")
        print("\n  Execute browse_drive() para encontrar o caminho correto.")
        print("  No terminal, responda 's' quando perguntado se deseja navegar.")
        raise FileNotFoundError(f"FILE_PATH não encontrado: {FILE_PATH}")
    r.raise_for_status()
    info = r.json()
    print(f"  Arquivo: {info['name']}")
    print(f"  File ID: {info['id']}\n")
    return info["id"]


def get_used_range(token, file_id, sheet):
    r = requests.get(
        f"{GRAPH}/me/drive/items/{file_id}/workbook/worksheets/{sheet}/usedRange",
        headers=_h(token),
    )
    r.raise_for_status()
    return r.json()


def list_worksheets(token, file_id):
    r = requests.get(
        f"{GRAPH}/me/drive/items/{file_id}/workbook/worksheets",
        headers=_h(token),
    )
    r.raise_for_status()
    sheets = r.json().get("value", [])
    print("  Abas encontradas:")
    for s in sheets:
        print(f"    - {s['name']}")
    return [s["name"] for s in sheets]


def get_motivo_colors(token, file_id, sheet):
    """
    Reads the Motivos Disponíveis column (L2:L16) and returns a map of
    {motivo_text: "#RRGGBB"} by reading the fill color of each cell.
    """
    r = requests.get(
        f"{GRAPH}/me/drive/items/{file_id}/workbook/worksheets/{sheet}/range(address='L2:L16')",
        headers=_h(token),
    )
    r.raise_for_status()
    values = r.json().get("values", [])

    color_map = {}
    for i, row in enumerate(values):
        motivo = str(row[0]).strip() if row and row[0] not in (None, "") else None
        if not motivo:
            continue
        excel_row = i + 2
        r2 = requests.get(
            f"{GRAPH}/me/drive/items/{file_id}"
            f"/workbook/worksheets/{sheet}/range(address='L{excel_row}')/format/fill",
            headers=_h(token),
        )
        if r2.status_code == 200:
            color = r2.json().get("color", "")
            if color:
                color_map[motivo] = color

    return color_map


# ── Spreadsheet navigation ────────────────────────────────────────────────────

def _range_start_row(address):
    part = address.split("!")[-1].split(":")[0]
    m = re.match(r"[A-Z]+(\d+)", part)
    return int(m.group(1)) if m else 1


def _range_start_col(address):
    m = re.match(r"(?:[^!]+!)?([A-Z]+)\d+", address)
    if not m:
        return 0
    col_str = m.group(1)
    result = 0
    for ch in col_str.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _col_to_letter(idx):
    letters = ""
    while idx >= 0:
        letters = chr(65 + idx % 26) + letters
        idx = idx // 26 - 1
    return letters


def find_first_empty_row(values, address):
    """
    Returns the Excel row number of the first empty row in column B (Destino)
    that sits below the column-header row.
    """
    start_row = _range_start_row(address)
    start_col = _range_start_col(address)
    b_in_array = 1 - start_col  # array index corresponding to Excel column B

    HEADER_INDICATORS = {
        "destino", "data", "motivo", "banco usado", "modo de pagamento",
        "infos extra", "valor", "value",
    }
    headers_idx = None
    for i, row in enumerate(values):
        normalized = {str(c).strip().lower() for c in row if c not in (None, "")}
        if len(normalized & HEADER_INDICATORS) >= 3:
            headers_idx = i
            break

    if headers_idx is None:
        raise ValueError(
            "Linha de cabeçalho não encontrada. "
            "Esperado: linha com ao menos 3 de: Destino, Data, Motivo, "
            "Banco Usado, Modo de Pagamento, Infos Extra, Valor."
        )

    data_start = headers_idx + 1
    for i in range(data_start, len(values)):
        row  = values[i]
        cell = row[b_in_array] if len(row) > b_in_array else None
        if cell in (None, ""):
            return start_row + i

    return start_row + len(values)


def write_expenses_to_sheet(token, file_id, sheet, first_row, expenses, color_map=None):
    """
    Writes each expense to B:H on consecutive rows starting at first_row.
    If color_map is provided, also colors cell D (Motivo) with the category color.

    Fixed column layout:
      B  Destino           — description as written
      C  Data              — DD/MM/YYYY
      D  Motivo            — expanded category  ← colored per category
      E  Banco Usado       — normalised bank name
      F  Modo de Pagamento — Pix / Cartão de Crédito / Cartão de Débito / Dinheiro
      G  Infos Extra       — same description as B
      H  Valor             — negative number
    """
    today = date.today().strftime("%d/%m/%Y")
    written = []

    for offset, expense in enumerate(expenses):
        excel_row = first_row + offset

        valor = expense.get("valor", 0)
        if isinstance(valor, str):
            valor = float(valor.replace(",", ".").replace("R$", "").strip())
        if valor > 0:
            valor = -valor

        destino = expense.get("destino", "")
        motivo  = expense.get("motivo", "")

        row_data = [
            destino,                          # B — Destino
            expense.get("data", today),       # C — Data
            motivo,                           # D — Motivo
            expense.get("banco", ""),         # E — Banco Usado
            expense.get("pagamento", ""),     # F — Modo de Pagamento
            destino,                          # G — Infos Extra (same as B)
            valor,                            # H — Valor
        ]

        cell_address = f"B{excel_row}:H{excel_row}"
        url = (
            f"{GRAPH}/me/drive/items/{file_id}"
            f"/workbook/worksheets/{sheet}/range(address='{cell_address}')"
        )
        r = requests.patch(url, headers=_h(token), json={"values": [row_data]})
        r.raise_for_status()

        # Apply category color to cell D (Motivo)
        if color_map and motivo in color_map:
            fill_url = (
                f"{GRAPH}/me/drive/items/{file_id}"
                f"/workbook/worksheets/{sheet}/range(address='D{excel_row}')/format/fill"
            )
            requests.patch(fill_url, headers=_h(token), json={"color": color_map[motivo]})

        written.append(cell_address)
        print(f"    ✓ {sheet}!{cell_address}  {destino} / {motivo} / {valor}")

    return written


# ── Diagnóstico ───────────────────────────────────────────────────────────────

def inspect_sheet(token, file_id, sheet):
    """
    Mostra a estrutura detectada na planilha para uma aba específica.
    Rode isso antes de test_add_expenses() para confirmar que as colunas estão corretas.
    """
    print(f"\n=== Inspecionando aba: {sheet} ===")
    used    = get_used_range(token, file_id, sheet)
    values  = used["values"]
    address = used["address"]
    start_row = _range_start_row(address)

    print(f"  Intervalo usado: {address}")
    print(f"  Total de linhas: {len(values)}\n")

    print("  Primeiras 20 linhas:")
    for i, row in enumerate(values[:20]):
        excel_row = start_row + i
        preview   = [str(c)[:22] if c not in (None, "") else "—" for c in row[:9]]
        print(f"    Excel {excel_row:3d} (arr {i:2d}): {preview}")

    print()
    try:
        target_row = find_first_empty_row(values, address)
        print("  Cabeçalhos detectados ✓")
        print(f"  Próxima linha disponível: Excel row {target_row}")
    except ValueError as e:
        print(f"  ERRO na detecção: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

TEST_NOTE = """\
04/06
açaí TESTE - pode deletar [comida]: 1,00 nu bank pix
uber TESTE - pode deletar [transporte]: 2,50 nu bank crédito
"""


if __name__ == "__main__":
    print("Obtendo token de acesso...")
    token = get_access_token()

    # Try to get the file; if 404, offer to browse the drive
    try:
        file_id = get_file_id(token)
    except FileNotFoundError:
        nav = input("\nDeseja navegar pelo OneDrive para encontrar o arquivo? (s/n): ").strip().lower()
        if nav == "s":
            browse_drive(token)
        print("\nAtualize FILE_PATH no topo deste script e execute novamente.")
        exit(1)

    print("Listando abas:")
    list_worksheets(token, file_id)

    sheet = MONTHS_PT[date.today().month]
    print(f"\nAba do mês atual: {sheet}")

    inspect_sheet(token, file_id, sheet)

    print(f"\nNota de teste que será usada:\n{TEST_NOTE}")
    resposta = input("Deseja inserir as linhas de teste? (s/n): ").strip().lower()
    if resposta == "s":
        expenses = parse_note(TEST_NOTE)
        print(f"\nGastos parseados ({len(expenses)}):")
        for e in expenses:
            print(f"  {e}")

        # Group by sheet (in case the note has multiple dates/months)
        by_sheet = defaultdict(list)
        for exp in expenses:
            month_num = int(exp["data"].split("/")[1])
            by_sheet[MONTHS_PT[month_num]].append(exp)

        print("\nLendo cores dos motivos...")
        first_sheet = next(iter(by_sheet))
        color_map   = get_motivo_colors(token, file_id, first_sheet)
        print(f"  {len(color_map)} cores encontradas: {list(color_map.keys())}")

        print("\nEscrevendo na planilha...")
        for sh, sh_expenses in by_sheet.items():
            used      = get_used_range(token, file_id, sh)
            first_row = find_first_empty_row(used["values"], used["address"])
            write_expenses_to_sheet(token, file_id, sh, first_row, sh_expenses, color_map)

        print("\nAbra o Excel e verifique se as linhas de teste apareceram no lugar certo.")
        print("Depois, delete essas linhas manualmente.")

    print(f"\nArquivo {TOKEN_FILE} pronto. Faça upload para o Azure Blob Storage (Passo 4.4 do setup_guide.md).")
