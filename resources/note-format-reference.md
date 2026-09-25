# Referência Rápida: Formato das Notas de Gastos

## Estrutura

```
DD/MM
destino infos extra [categoria]: valor banco (forma de pagamento)
```

- **destino** → primeira palavra; vai para a coluna B (Destino)
- **infos extra** → tudo após a primeira palavra e antes de `[categoria]`; vai para a coluna G (Infos Extra)
- Se houver apenas uma palavra antes de `[categoria]`, Infos Extra copia o Destino automaticamente

## Exemplos

```
24/02
açaí compras do dia [comida]: 15 Nubank (Pix)
uber ida trabalho [transporte]: 12,32 Nubank
beats [saida]: 8 dinheiro
evento womens day [saida]: 56,10 Nubank
faixa azul ginástica [transporte]: 4,95 Inter (Pix)
protetor solar farmácia [higiene]: 38,90 Nubank
```

| Coluna | açaí (1ª linha) | uber (2ª linha) | beats (3ª linha) |
|---|---|---|---|
| B — Destino | `açaí` | `uber` | `beats` |
| G — Infos Extra | `compras do dia` | `ida trabalho` | `beats` *(cópia)* |

## Regras rápidas

- **Data** → linha sozinha, formato `DD/MM`
- **`[categoria]`** → obrigatório (para preencher MOTIVO na planilha); tolerante a maiúsculas, plural e pequenos erros de digitação
- **`(Pix)`** → só escreva quando for Pix; omitir = Cartão de Crédito
- **`dinheiro`** no lugar do banco = pagamento em espécie
- Valor pode ser inteiro (`15`) ou decimal com vírgula (`56,10`)
- Banco não é case-sensitive (`nubank` = `Nubank`)

## Tags de categoria

A tag aceita variações de maiúsculas, plural e pequenos erros (`[Comida]`, `[comidas]`, `[comdia]` → todas resolvem para `Comida - dia a dia`).

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
| `[burocracia]` ou `[trabalho]` | Burocracias / Trabalho |
| `[telefone]` | Telefone / Eletrônicos |
| `[presentes]` | Presentes |
| `[investimentos]` | Investimentos |
| `[casa]` | Coisas para Casa |
| `[faixaazul]` | Faixa Azul |

## Bancos disponíveis

`Nubank` · `Inter` · `Ifood` · `Alelo` · `Wise` · `dinheiro`

## Formas de pagamento

| Na nota | Na planilha |
|---|---|
| `(Pix)` | Pix |
| `dinheiro` (banco) | Dinheiro |
| *(omitido)* | Cartão de Crédito |

## Gastos em outra moeda (conversão automática para BRL)

Se o gasto foi feito em euro, dólar ou lira, escreva a moeda como uma palavra logo depois do valor (antes do banco). A automação converte automaticamente para reais usando a cotação do dia (API gratuita [Frankfurter.app](https://www.frankfurter.app/), câmbio oficial do Banco Central Europeu) e grava o valor **já em BRL** na coluna Valor. O valor original fica registrado entre parênteses na coluna Infos Extra.

```
jantar paris [saida]: 50 euro Wise (Pix)
compras turquia [roupas]: 200 lira Nubank
mercado ny [comida]: 30 dolar Inter
```

**Palavras de moeda reconhecidas:**

| Escreva | Moeda |
|---|---|
| `real` / `reais` *(padrão, pode omitir)* | Reais (BRL) — sem conversão |
| `euro` / `euros` / `eur` | Euro (EUR) |
| `dolar` / `dólar` / `dolares` / `dólares` / `dol` / `usd` | Dólar (USD) |
| `lira` / `liras` / `try` | Lira turca (TRY) |
