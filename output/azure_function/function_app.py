import json
import re
import os
import difflib
import requests
import azure.functions as func
from collections import defaultdict
from datetime import date
from azure.storage.blob import BlobServiceClient, BlobClient

app = func.FunctionApp()

CLIENT_ID  = os.environ["CLIENT_ID"]
FILE_PATH  = os.environ["FILE_PATH"]
BLOB_CONN  = os.environ["AzureWebJobsStorage"]

BLOB_CONTAINER = "gastos-tokens"
BLOB_NAME      = "tokens.json"
AUTHORITY      = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
GRAPH          = "https://graph.microsoft.com/v1.0"

MONTHS_PT = {
    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}

CATEGORY_MAP = {
    "comida":       "Comida - dia a dia",
    "saida":        "Saída entre amigos",
    "saida amigos":        "Saída entre amigos",
    "viagem passagem":       "Passagens de Viagem",
    "viagem acomodacao":   "Acomodação em Viagem",
    "acomodacao":   "Acomodação em Viagem",
    "higiene":      "Higiene / Skin Care",
    "skincare":      "Higiene / Skin Care",
    "transporte":   "Transporte",
    "roupas":       "Roupas / Bolsas / Joias / Sapatos",
    "roupa":       "Roupas / Bolsas / Joias / Sapatos",
    "bolsa":       "Roupas / Bolsas / Joias / Sapatos",
    "joias":       "Roupas / Bolsas / Joias / Sapatos",
    "make":       "Roupas / Bolsas / Joias / Sapatos",
    "lazer":        "Lazer / Experiências",
    "fitness":      "Vida Fitness / Saúde",
    "saude":      "Vida Fitness / Saúde",
    "estudos":      "Estudos",
    "estudo":      "Estudos",
    "burocracia":   "Burocracias / Trabalho",
    "burocracias":   "Burocracias / Trabalho",
    "trabalho":   "Burocracias / Trabalho",
    "telefone":     "Telefone / Eletrônicos",
    "presentes":    "Presentes",
    "presente":    "Presentes",
    "investimentos":"Investimentos",
    "investimento":"Investimentos",
    "casa":         "Coisas para Casa",
    "coisas para casa": "Coisas para Casa",
    "faixaazul":    "Faixa Azul",
    "faixa azul":   "Faixa Azul",
}

# Words that mark a value as a foreign currency instead of BRL (Reais).
# The recognised words are entered in full or abbreviated, in Portuguese.
CURRENCY_MAP = {
    "real":     "BRL", "reais":    "BRL",
    "euro":     "EUR", "euros":    "EUR", "eur": "EUR",
    "dolar":    "USD", "dólar":    "USD",
    "dolares":  "USD", "dólares":  "USD", "dol": "USD", "usd": "USD",
    "lira":     "TRY", "liras":    "TRY", "try": "TRY",
}

FRANKFURTER_URL = "https://api.frankfurter.app/latest"


def _convert_to_brl(valor: float, currency: str) -> float:
    """Converts `valor` from `currency` (ISO code) to BRL using the free Frankfurter API (ECB rates)."""
    if currency == "BRL":
        return valor
    r = requests.get(
        FRANKFURTER_URL,
        params={"amount": valor, "from": currency, "to": "BRL"},
        timeout=10,
    )
    r.raise_for_status()
    return round(r.json()["rates"]["BRL"], 2)

def _lookup_category(tag: str) -> str:
    """Resolves a category tag with tolerance for case, plurals, and small typos."""
    if not tag:
        return tag
    lower = tag.strip().lower()
    if lower in CATEGORY_MAP:
        return CATEGORY_MAP[lower]
    singular = lower[:-1] if lower.endswith("s") else lower
    if singular in CATEGORY_MAP:
        return CATEGORY_MAP[singular]
    matches = difflib.get_close_matches(lower, CATEGORY_MAP.keys(), n=1, cutoff=0.75)
    return CATEGORY_MAP[matches[0]] if matches else tag


BANK_MAP = {
    "nubank":   "Nubank",
    "nu bank":  "Nubank",
    "inter":    "Inter",
    "ifood":    "Ifood Benefícios",
    "alelo":    "Alelo",
    "wise":     "Wise",
}

# Payment keywords that appear INLINE after the bank name (no parentheses needed)
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
        description [category]: value bank (payment)

    Returns a list of expense dicts ready to write to the spreadsheet.
    """
    if year is None:
        year = date.today().year

    expenses = []
    current_date = date.today().strftime(f"{year}-%m-%d")

    for raw_line in note_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Date line: exactly DD/MM
        if re.match(r"^\d{2}/\d{2}$", line):
            day, month = line.split("/")
            current_date = f"{year}-{month}-{day}"
            continue

        # Expense line: must contain ':'
        if ":" not in line:
            continue

        before_colon, after_colon = line.split(":", 1)
        after_colon = after_colon.strip()

        # Extract [category] tag
        tag_match = re.search(r"\[([^\]]+)\]", before_colon)
        category_tag = tag_match.group(1).strip() if tag_match else ""
        text_without_tag = re.sub(r"\s*\[[^\]]*\]", "", before_colon).strip()

        # First word → Destino (col B); remainder → Infos Extra (col G)
        parts_before = text_without_tag.split(None, 1)
        destino     = parts_before[0] if parts_before else ""
        infos_extra = parts_before[1].strip() if len(parts_before) > 1 else destino

        # Strip (payment) parentheses form if present
        paren_match = re.search(r"\(([^)]+)\)", after_colon)
        after_colon_clean = re.sub(r"\([^)]+\)", "", after_colon).strip()

        # Split into tokens: first is the value, rest is "bank [payment_keyword]"
        parts = after_colon_clean.split()
        if not parts:
            continue

        try:
            valor = float(parts[0].replace(",", "."))
        except ValueError:
            continue

        rest = parts[1:]  # everything after the value

        # Detect a currency word right after the value (e.g. "50 euro Wise")
        moeda = "BRL"
        valor_original = None
        if rest and rest[0].lower() in CURRENCY_MAP:
            moeda = CURRENCY_MAP[rest[0].lower()]
            rest = rest[1:]

        if moeda != "BRL":
            valor_original = valor
            valor = _convert_to_brl(valor, moeda)

        # Check if the last word is an inline payment keyword (e.g. "pix", "crédito")
        if rest and rest[-1].lower() in PAYMENT_INLINE:
            pagamento = PAYMENT_INLINE[rest[-1].lower()]
            banco_bruto = " ".join(rest[:-1]).lower().strip()
        elif paren_match:
            # Fallback: (Pix) style
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

        # Values in the spreadsheet are always negative
        if valor > 0:
            valor = -valor

        # Foreign-currency expenses: show the original amount/currency in the description
        if valor_original is not None:
            infos_extra = f"{infos_extra} ({valor_original:.2f} {moeda})"

        expenses.append({
            "destino":     destino,
            "data":        current_date,
            "motivo":      _lookup_category(category_tag),
            "banco":       banco,
            "pagamento":   pagamento,
            "infos_extra": infos_extra,
            "valor":       valor,
        })

    return expenses


# ── Token storage ─────────────────────────────────────────────────────────────

def _blob() -> BlobClient:
    svc = BlobServiceClient.from_connection_string(BLOB_CONN)
    try:
        svc.create_container(BLOB_CONTAINER)
    except Exception:
        pass
    return svc.get_blob_client(BLOB_CONTAINER, BLOB_NAME)


def load_tokens() -> dict:
    return json.loads(_blob().download_blob().readall())


def save_tokens(tokens: dict):
    _blob().upload_blob(json.dumps(tokens), overwrite=True)


def get_access_token() -> str:
    tokens = load_tokens()
    r = requests.post(f"{AUTHORITY}/token", data={
        "client_id":     CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "scope":         "Files.ReadWrite offline_access",
    })
    r.raise_for_status()
    fresh = r.json()
    if "refresh_token" in fresh:
        tokens["refresh_token"] = fresh["refresh_token"]
    tokens["access_token"] = fresh["access_token"]
    save_tokens(tokens)
    return fresh["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_file_id(token: str) -> str:
    r = requests.get(f"{GRAPH}/me/drive/root:{FILE_PATH}", headers=_h(token))
    r.raise_for_status()
    return r.json()["id"]


def get_used_range(token: str, file_id: str, sheet: str) -> dict:
    r = requests.get(
        f"{GRAPH}/me/drive/items/{file_id}/workbook/worksheets/{sheet}/usedRange",
        headers=_h(token),
    )
    r.raise_for_status()
    return r.json()


def get_motivo_colors(token: str, file_id: str, sheet: str) -> dict:
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

def _range_start_row(address: str) -> int:
    """'Junho!B3:M50' -> 3"""
    part = address.split("!")[-1].split(":")[0]
    m = re.match(r"[A-Z]+(\d+)", part)
    return int(m.group(1)) if m else 1


def _range_start_col(address: str) -> int:
    """'Junho!B3:M50' -> 1  (B = index 1, 0-based)"""
    m = re.match(r"(?:[^!]+!)?([A-Z]+)\d+", address)
    if not m:
        return 0
    col_str = m.group(1)
    result = 0
    for ch in col_str.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def find_first_empty_row(values: list, address: str) -> int:
    """
    Scans the used range and returns the Excel row number of the first empty row
    in column B (Destino) that sits below the column-header row.

    Column B is always Excel column index 1 (0-based). Its position in the
    values array = 1 - start_col_excel (where start_col_excel comes from the
    range address, e.g. 'Junho!A1:L50' -> 0, 'Junho!B3:L50' -> 1).
    """
    start_row = _range_start_row(address)
    start_col = _range_start_col(address)
    b_in_array = 1 - start_col  # array index that corresponds to Excel column B

    if b_in_array < 0:
        raise ValueError(
            f"Used range starts at column {_col_to_letter(start_col)} "
            f"(after column B). Cannot locate the Destino column."
        )

    # Find the column-header row (contains at least 3 recognisable headers)
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
            "Column header row not found. "
            "Expected a row with at least 3 of: Destino, Data, Motivo, "
            "Banco Usado, Modo de Pagamento, Infos Extra, Valor/Value."
        )

    data_start = headers_idx + 1

    # First row where column B (Destino) is empty
    for i in range(data_start, len(values)):
        row  = values[i]
        cell = row[b_in_array] if len(row) > b_in_array else None
        if cell in (None, ""):
            return start_row + i

    return start_row + len(values)


def write_expenses_to_sheet(token: str, file_id: str, sheet: str,
                             first_row: int, expenses: list,
                             color_map: dict = None) -> list:
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
    today = date.today().strftime("%Y-%m-%d")
    written = []

    for offset, expense in enumerate(expenses):
        excel_row = first_row + offset

        valor = expense.get("valor", 0)
        if isinstance(valor, str):
            valor = float(valor.replace(",", ".").replace("R$", "").strip())
        if valor > 0:
            valor = -valor

        destino     = expense.get("destino", "")
        motivo      = expense.get("motivo", "")
        infos_extra = expense.get("infos_extra", destino)

        row_data = [
            destino,                          # B — Destino
            expense.get("data", today),       # C — Data
            motivo,                           # D — Motivo
            expense.get("banco", ""),         # E — Banco Usado
            expense.get("pagamento", ""),     # F — Modo de Pagamento
            infos_extra,                      # G — Infos Extra
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

    return written


# ── HTTP Trigger ──────────────────────────────────────────────────────────────

@app.route(route="add_expenses", auth_level=func.AuthLevel.FUNCTION)
def add_expenses(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body must be valid JSON"}),
            status_code=400, mimetype="application/json",
        )

    note_text = body.get("note", "").strip()
    if not note_text:
        return func.HttpResponse(
            json.dumps({"error": "Field 'note' is required and must not be empty"}),
            status_code=400, mimetype="application/json",
        )

    try:
        expenses = parse_note(note_text)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"Failed to parse note: {e}"}),
            status_code=400, mimetype="application/json",
        )

    if not expenses:
        return func.HttpResponse(
            json.dumps({"error": "No valid expense lines found in the note"}),
            status_code=400, mimetype="application/json",
        )

    try:
        token   = get_access_token()
        file_id = get_file_id(token)

        # Group expenses by month sheet
        by_sheet = defaultdict(list)
        for exp in expenses:
            month_num = int(exp["data"].split("-")[1])
            by_sheet[MONTHS_PT[month_num]].append(exp)

        # Build color map once from the first sheet (colors are the same across all sheets)
        first_sheet = next(iter(by_sheet))
        color_map   = get_motivo_colors(token, file_id, first_sheet)

        results = []
        for sheet, sheet_expenses in by_sheet.items():
            used      = get_used_range(token, file_id, sheet)
            first_row = find_first_empty_row(used["values"], used["address"])
            written   = write_expenses_to_sheet(token, file_id, sheet, first_row, sheet_expenses, color_map)
            results.extend({"sheet": sheet, "cell": c} for c in written)

        return func.HttpResponse(
            json.dumps({"ok": True, "rows_written": len(results), "details": results}),
            status_code=200, mimetype="application/json",
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500, mimetype="application/json",
        )
