# Expenses Spreadsheet Automation

Seleciono o texto de um gasto no Bloco de Notas do iPhone, toco em **Compartilhar**, e
ele cai sozinho como uma nova linha na minha planilha de gastos — já com categoria,
banco e valor identificados, sem digitar nada na planilha.

## O que o workflow faz

1. **Eu** seleciono uma ou mais linhas de gasto já escritas na nota e compartilho com o Shortcut.
2. O **Shortcut** só pega esse texto selecionado e envia para a automação — nenhuma lógica fica nele.
3. A **Azure Function** interpreta cada linha (data, destino, categoria, banco, forma de
   pagamento) e converte moeda estrangeira para BRL quando necessário.
4. Via **Microsoft Graph API**, cada gasto é escrito na primeira linha vazia da aba do
   mês certo, na minha planilha de Finanças no OneDrive.

```
iPhone (Bloco de Notas) → Shortcut "Compartilhar" → Azure Function → Graph API → Planilha
```

Toda a lógica de interpretação (parsing), categorização e conversão de moeda vive no
Azure Function (`output/azure_function/function_app.py`).

## Formato das notas

```
04/06
açaí compras do dia [comida]: 15 Nubank (Pix)
uber ida trabalho [transporte]: 12,32 Nubank
beats [saida]: 8 dinheiro
jantar paris [saida]: 50 euro Wise (Pix)
```

- Linha de data sozinha: `DD/MM`
- Linha de gasto: `destino infos extra [categoria]: valor banco (forma)`
- `[categoria]` aceita maiúsculas, plural e pequenos erros de digitação
- `(Pix)` só quando for Pix; se omitido, o padrão é Cartão de Crédito
- `dinheiro` no lugar do banco = pagamento em espécie

Guia completo de sintaxe: [`resources/note-format-reference.md`](resources/note-format-reference.md).

## Categorias disponíveis

| Tag | Planilha |
|---|---|
| `[comida]` | Comida - dia a dia |
| `[saida]` | Saída entre amigos |
| `[viagem]` | Passagens de Viagem |
| `[acomodacao]` | Acomodação em Viagem |
| `[higiene]` | Higiene / Skin Care |
| `[transporte]` | Transporte |
| `[roupas]` | Roupas / Bolsas / Joias / Sapatos |
| `[lazer]` | Lazer / Experiências |
| `[fitness]` | Vida Fitness / Saúde |
| `[estudos]` | Estudos |
| `[burocracia]` / `[trabalho]` | Burocracias / Trabalho |
| `[telefone]` | Telefone / Eletrônicos |
| `[presentes]` | Presentes |
| `[investimentos]` | Investimentos |
| `[casa]` | Coisas para Casa |
| `[faixaazul]` | Faixa Azul |

## Conversão automática de moeda

Gastos em euro, dólar ou lira turca são convertidos automaticamente para reais.
Basta escrever a moeda como uma palavra logo após o valor:

```
compras turquia [roupas]: 200 lira Nubank
mercado ny [comida]: 30 dolar Inter
```

A conversão usa a cotação do dia via [Frankfurter.app](https://www.frankfurter.app/)
(API gratuita, câmbio oficial do Banco Central Europeu). O valor já convertido em
BRL é o que vai para a planilha; o valor original fica registrado entre parênteses
na coluna "Infos Extra" (ex: `paris (50.00 EUR)`).

Palavras de moeda reconhecidas: `real`/`reais` (padrão, sem conversão),
`euro`/`euros`/`eur`, `dolar`/`dólar`/`dolares`/`dólares`/`dol`/`usd`,
`lira`/`liras`/`try`.

## Estrutura do projeto

```
workflows/   → recipes em português das automações (fluxo antigo via Power Automate)
resources/   → referência rápida do formato das notas
output/      → código da Azure Function, guia de setup e scripts de teste
```

## Setup e manutenção

Guia passo a passo (registro no Azure, deploy da Function, Apple Shortcut):
[`output/setup_guide.md`](output/setup_guide.md).

Para adicionar uma nova categoria ou banco, edite `CATEGORY_MAP` / `BANK_MAP` em
`output/azure_function/function_app.py` e faça o redeploy.
