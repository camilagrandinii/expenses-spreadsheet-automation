# Guia de Configuração: Gastos direto do iPhone para Excel

## Arquitetura

```
iPhone (Apple Shortcuts)
        │ seleciona texto na nota e toca "Log Expenses"
        ↓ POST { "note": "texto bruto da nota" }
Azure Function (Python, free tier)
        │ interpreta cada linha, detecta colunas, agrupa por mês
        ↓
Microsoft Graph API
        │ escreve cada gasto na primeira linha vazia da aba correta
        ↓
Finanças 2026 - Belo Horizonte.xlsx (OneDrive)
```

O Shortcut apenas captura o texto selecionado e envia. Toda a lógica de parsing,
detecção de aba e localização da primeira linha vazia fica no Azure Function.

---

## Formato das notas

```
04/06
açaí compras do dia [comida]: 15 Nubank (Pix)
uber ida trabalho [transporte]: 12,32 Nubank
beats [saida]: 8 dinheiro
protetor solar farmácia [higiene]: 38,90 Nubank
```

**Regras:**

- Linha de data: `DD/MM` sozinha (ex: `04/06`)
- Linha de gasto: `destino infos extra [categoria]: valor banco (forma)`
  - **primeira palavra** antes de `[categoria]` → coluna B (Destino)
  - **palavras seguintes** antes de `[categoria]` → coluna G (Infos Extra)
  - se houver só uma palavra, Infos Extra copia o Destino automaticamente
- `[categoria]` é obrigatório — preenche a coluna MOTIVO; aceita maiúsculas, plural e pequenos erros de digitação
- `(Pix)` só quando for Pix; omitir = Cartão de Crédito
- `dinheiro` no lugar do banco = pagamento em espécie

**Categorias disponíveis:** `[comida]` `[saida]` `[viagem]` `[acomodacao]` `[higiene]`
`[transporte]` `[roupas]` `[lazer]` `[fitness]` `[estudos]` `[burocracia]`/`[trabalho]`
`[telefone]` `[presentes]` `[investimentos]` `[casa]` `[faixaazul]`

**Gastos em outra moeda:** escreva `euro`/`eur`, `dolar`/`dol`/`usd` ou `lira`/`try` logo
após o valor (ex: `50 euro Wise`). O Function converte para BRL automaticamente via
[Frankfurter.app](https://www.frankfurter.app/) (API gratuita, cotação do BCE) e guarda
o valor original entre parênteses em Infos Extra.

---

## Estrutura da planilha

O Azure Function detecta automaticamente as colunas pelo nome do cabeçalho.
A estrutura esperada em cada aba mensal é:

| Coluna | Cabeçalho esperado   | O que é preenchido                                                                     |
| ------ | --------------------- | --------------------------------------------------------------------------------------- |
| B      | Destino               | Primeira palavra da linha (ex: `açaí`)                                                                             |
| C      | Data                  | Data no formato DD/MM/AAAA                                                                                            |
| D      | `Motivo`            | Categoria expandida (ex: "Comida - dia a dia"), vem da coluna L os motivos disponíveis                               |
| E      | `Banco Usado`       | Banco normalizado (ex: "Nubank")                                                                                      |
| F      | `Modo de Pagamento` | "Cartão de Crédito", "Cartão de Débito", "Pix", "Dinheiro"                                                        |
| G      | `Infos Extra`       | Palavras seguintes antes de `[categoria]` (ex: `compras do dia`); cópia do Destino se só houver uma palavra         |
| H      | Valor                 | Valor negativo (ex: -15,00)                                                                                           |
| I+     | Saldo Total           | Fórmulas — não tocadas                                                                                                |

**O Function encontra a primeira linha vazia na coluna B** (abaixo dos cabeçalhos)
e escreve ali. Valores são sempre armazenados como negativos.

A aba é determinada pela **data de cada gasto na nota** — gastos de junho vão
para a aba `Junho`, gastos de julho para `Julho`, etc.

---

## Passo 1 — Verificar a planilha (5 min)

Confirme que cada aba mensal:

- Tem o nome do mês em português (ex: `Junho`, `Julho`)
- Tem uma linha de cabeçalho com todas essas palavras:
  `Destino`, `Data`, `Motivo`, `Banco Usado`, `Modo de Pagamento`, `Infos Extra`, `Valor`
- Tem pelo menos uma linha vazia abaixo dos gastos já registrados

Nenhuma alteração no formato da planilha é necessária.

---

## Passo 2 — Registrar o App no Azure (15 min)

1. Acesse **portal.azure.com** (login com a mesma conta Microsoft do OneDrive)
2. Pesquise por **"Registros de aplicativo"** → **+ Novo registro**
   - **Nome:** `GastosShortcut`
   - **Tipos de conta:** *Contas Microsoft pessoais apenas*
   - **URI de redirecionamento:** deixe em branco
3. Após criar, copie o **ID do aplicativo (cliente)** — você usará em todos os passos
4. Em **Autenticação** (menu lateral):
   - Em *Fluxos de cliente público avançados* → habilite **Sim** → Salvar
5. Em **Permissões de API** → **+ Adicionar uma permissão** → **Microsoft Graph**
   → **Permissões delegadas** → selecione `Files.ReadWrite` → **Adicionar permissões**

---

## Passo 3 — Testar autenticação e detecção de colunas (10 min)

### 3.1 Instalar dependências

```bash
pip install requests msal
```

### 3.2 Configurar o script

Abra `output/test_graph_api.py` e substitua na linha 16:

```python
CLIENT_ID = "SEU_APP_ID_DO_AZURE"
```

pelo App ID copiado no Passo 2.

### 3.3 Executar

```bash
python output/test_graph_api.py
```

**Na primeira vez**, o script vai pedir para você:

1. Abrir `https://microsoft.com/devicelogin` no navegador
2. Digitar o código exibido no terminal
3. Fazer login com a conta Microsoft que tem o arquivo no OneDrive

### 3.4 O que o script faz

1. **Confirma que encontrou o arquivo** — imprime o nome e o File ID
2. **Lista as abas** — confirma que existem abas com nome de mês em português
3. **Inspeciona a aba do mês atual** — imprime as primeiras 20 linhas e o mapeamento
   de colunas detectado, e mostra qual linha está disponível para escrita
4. **Insere linhas de teste** (opcional) — pede confirmação antes de escrever

### 3.5 Verificar o resultado

Depois de inserir as linhas de teste:

- Abra a planilha no OneDrive
- Confirme que as duas linhas (`açaí TESTE` e `uber TESTE`) apareceram na aba
  do mês atual, na seção correta, nas primeiras linhas vazias
- Delete essas linhas manualmente

### 3.6 Salvar o tokens.json

O arquivo `tokens.json` gerado nesse passo precisa ser enviado para o Azure
Blob Storage mais adiante (Passo 4.4).

---

## Passo 4 — Criar o Azure Function App e fazer o deploy (30 min)

### 4.1 Criar o Function App

1. No portal Azure → **Criar um recurso** → buscar **Function App**
2. Preencha:
   - **Assinatura:** sua assinatura (pode ser Pay-as-you-go free tier)
   - **Grupo de recursos:** criar novo, ex: `gastos-rg`
   - **Nome:** ex: `gastos-camila` (deve ser único globalmente)
   - **Plano:** Flex Consumption  ← suporta Python no Linux; Consumption (Windows) não suporta Python
   - **Runtime:** Python 3.11
   - **Região:** Brazil South ou East US
3. Clique em **Revisar + criar** → **Criar**
4. Aguarde ~2 min para o recurso ser criado

### 4.2 Fazer o deploy do código

Instale as ferramentas necessárias uma vez:

```bash
# Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Azure CLI — Windows: baixe o instalador MSI em https://learn.microsoft.com/azure/azure-cli
```

Deploy direto da pasta `azure_function/`:

```bash
cd "output/azure_function"
func azure functionapp publish gastos-camila --python
```

### 4.3 Configurar variáveis de ambiente

No portal Azure → seu Function App → **Configurações** → **Variáveis de ambiente** → **+ Adicionar**:

| Nome          | Valor                                               |
| ------------- | --------------------------------------------------- |
| `CLIENT_ID` | App ID do Passo 2                                   |
| `FILE_PATH` | `/Finanças 2026 - Belo Horizonte.xlsx` |

Clique em **Salvar** após adicionar.

> `AzureWebJobsStorage` já existe automaticamente — aponta para o Storage Account
> criado junto com o Function App.

### 4.4 Fazer upload do tokens.json

1. No portal Azure → busque **Storage accounts** → clique na storage account do
   seu Function App (nome parecido com `gastoscamilaXXXX`)
2. Em **Contêineres** → **+ Contêiner** → nome: `gastos-tokens` → acesso: **Privado** → Criar
3. Abra o contêiner `gastos-tokens` → **Carregar** → selecione o `tokens.json` local

---

## Passo 5 — Obter a URL e chave do Function (5 min)

1. No portal Azure → seu Function App → **Funções** → `add_expenses`
2. Clique em **Obter URL da função** → copie a URL completa (já inclui `code=` no final)

A URL terá este formato:

```
https://gastos-camila.azurewebsites.net/api/add_expenses?code=XXXXXXXXXXXXXXXX
```

Guarde essa URL — ela vai no Shortcut.

---

## Passo 6 — Criar o Apple Shortcut

O Shortcut captura o texto selecionado na nota e envia para o Function.
São apenas 3 ações.

### Ações do Shortcut

| # | Ação                                    | Configuração                                                                                   |
| - | ----------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1 | **Receber entrada** (Receive Input) | Tipo:**Texto** · Ativar **"Mostrar em Compartilhar"**                               |
| 2 | **Dicionário**                     | Adicione uma chave:`note` → Tipo: **Texto** → Valor: `[variável Entrada do Atalho]` |
| 3 | **Obter conteúdo do URL**          | Veja configuração abaixo                                                                       |
| 4 | **Se** + **Mostrar alerta**   | Se `ok` = `true` → "Gastos registrados!" / Senão → mostrar `error`                      |

**Ação 3 — configuração do POST:**

- **Método:** POST
- **URL:** `https://gastos-camila.azurewebsites.net/api/add_expenses?code=SEU_CODE`
- **Cabeçalhos:** `Content-Type` = `application/json`
- **Corpo:** JSON → selecione a variável `Dicionário` (da ação 2)

### Adicionar à tela inicial

Segure o Shortcut → **Compartilhar** → **Adicionar à Tela de Início** → escolha ícone e nome (ex: "Gastos")

---

## Uso diário

1. Abra o app **Notas** no iPhone
2. Selecione apenas as linhas ainda não sincronizadas (long press → arrastar)
3. Toque em **Compartilhar** no menu de seleção
4. Toque em **Gastos**
5. Aguarde o alerta de confirmação

> **Dica:** marque com um `✓` a última linha sincronizada na nota para saber
> onde parou na próxima vez.

---

## Teste final

1. Escreva uma nota de teste:
   ```
   04/06
   teste azul mercado [comida]: 1,00 Nubank (Pix)
   ```
2. Selecione o texto, toque em **Compartilhar** → **Gastos**
3. Abra a planilha no OneDrive → aba `Junho` → confirme que a linha apareceu
   na primeira linha vazia da seção, com valor `-1,00`
4. Delete a linha de teste manualmente

---

## Manutenção

| Situação                                                | O que fazer                                                                                                              |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Function retorna erro 500 com "refresh_token" na mensagem | Token expirou (90 dias sem uso). Rode `test_graph_api.py` novamente e faça upload do novo `tokens.json` para o blob |
| Categoria ainda não reconhecida após tentativas (maiúscula, plural, typo) | Adicione a tag em `CATEGORY_MAP` no `function_app.py` e faça redeploy                          |
| Banco não reconhecido                                    | Adicione o mapeamento em `BANK_MAP` no `function_app.py` e faça redeploy                                            |
| Virou o ano (2027)                                        | Atualize `FILE_PATH` nas variáveis do Function App para apontar para o novo arquivo                                   |
| Cabeçalho de coluna diferente                            | O Function detecta pelo nome — se renomear uma coluna na planilha, atualize `detect_columns()` no código             |
