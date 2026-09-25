# Automação: Notas do iPhone → Planilha de Gastos (OneDrive)

> ⚠️ **Versão anterior (Gmail + Power Automate).** A automação em uso hoje é a do
> Azure Function, documentada em `output/setup_guide.md` (inclui conversão automática
> de moeda estrangeira). Este arquivo fica como referência do fluxo antigo.

## O que esta automação faz

Você escreve seus gastos no Notes do iPhone exatamente como faz hoje (com pequena adição de `[categoria]`). Quando quiser sincronizar, toca em **Compartilhar → Log Expenses**. A automação envia o texto por email, um fluxo no Power Automate lê o email, interpreta cada linha e adiciona as linhas na aba correta da planilha.

---

## Pré-requisito obrigatório: mover o arquivo para fora do Cofre Pessoal

O OneDrive **Cofre Pessoal** bloqueia acesso automático por design. O Power Automate não consegue ler nem escrever em arquivos que estão lá.

**Passos:**
1. Acesse [onedrive.live.com](https://onedrive.live.com) no computador
2. Clique em **Cofre Pessoal** e autentique (PIN ou biometria)
3. Localize `Finanças 2026 - Belo Horizonte.xlsx`
4. Clique com o botão direito → **Mover para** → escolha `Finanças > Gastos > 2026`
5. Confirme a movimentação

O arquivo continua privado na sua conta — só perde a camada extra de bloqueio do cofre.

---

## Formato das notas (atualizado)

O padrão de cada linha de gasto é:

```
24/02
açaí compras do dia [comida]: 15 Nubank (Pix)
evento womens day [saida]: 56,10 Nubank
27/02
sorvetes almoço na Milena [saida]: 21,16 Nubank
Beats [saida]: 8 dinheiro
01/03
carnaval ballroom [saida]: 22,35 Nubank
uber moto [transporte]: 12,32 Nubank
```

**Regras:**
- Data sozinha na linha: `DD/MM`
- Um gasto por linha: `destino infos extra [categoria]: valor banco (forma)`
  - **primeira palavra** antes de `[categoria]` → coluna B (Destino)
  - **palavras seguintes** antes de `[categoria]` → coluna G (Infos Extra); cópia do Destino se só houver uma palavra
- `[categoria]` — obrigatório para preencher a coluna MOTIVO; aceita maiúsculas, plural e pequenos erros de digitação
- `(Pix)` — só escreva quando for Pix; se omitido, o padrão é Cartão de Crédito
- `dinheiro` no lugar do banco = pagamento em espécie (sem banco, forma = Dinheiro)

**Tags de categoria disponíveis:**

| Tag | MOTIVO na planilha |
|---|---|
| `[comida]` | Comida - dia a dia |
| `[saida]` | Saída entre amigos |
| `[viagem]` | Passagens de Viagem |
| `[acomodacao]` | Acomodação em Viagem |
| `[higiene]` | Higiene / Skin Care |
| `[transporte]` | Transporte |
| `[roupas]` | Roupas / Bolsas / Joias / Sapatos / Make / Glitter |
| `[lazer]` | Lazer / Experiências |
| `[fitness]` | Vida Fitness / Saúde |
| `[estudos]` | Estudos |
| `[burocracia]` | Burocracias |
| `[telefone]` | Telefone / Eletrônicos |
| `[presentes]` | Presentes |
| `[investimentos]` | Investimentos |

---

## Parte 1: Criar o Atalho no iPhone (iOS Shortcuts)

**Tempo estimado: 10 minutos**

1. Abra o app **Atalhos** (Shortcuts) no iPhone
2. Toque em **+** no canto superior direito
3. Toque no campo de nome (topo) e escreva: `Log Expenses`
4. Toque em **Adicionar Ação**
5. Busque por **"Receber entrada"** (Receive Input) → selecione
   - Toque na ação → altere o tipo para **Texto**
   - Ative a opção **"Mostrar em Compartilhar"** (Show in Share Sheet)
6. Toque novamente em **Adicionar Ação**
7. Busque por **"Enviar email"** (Send Email) → selecione
   - **Para:** `cacagrandini@gmail.com`
   - **Assunto:** `EXPENSES`
   - **Corpo:** toque no campo → toque no ícone de variável (círculo azul com x) → selecione **Entrada do Atalho** (Shortcut Input)
8. Toque em **OK** / **Concluído**

**Testar o atalho:**
1. Abra o app **Notas**
2. Toque e segure em uma linha de texto → arraste para selecionar algumas linhas
3. No menu de seleção, toque em **Compartilhar**
4. Role para baixo na lista e toque em **Log Expenses**
5. Confirme se um email chegou em cacagrandini@gmail.com com assunto `EXPENSES` e **apenas o texto selecionado** no corpo

---

## Parte 2: Criar o fluxo no Power Automate

**Tempo estimado: 60 minutos**

Acesse [make.powerautomate.com](https://make.powerautomate.com) e faça login com sua conta Microsoft (a mesma do OneDrive).

### 2.1 — Criar o fluxo

1. Clique em **+ Novo fluxo** → **Fluxo de nuvem automatizado**
2. Nome: `Gastos - Notas para Planilha`
3. Em "Escolher o gatilho do fluxo", busque **Gmail** → selecione **"Quando um novo email chegar"**
4. Clique em **Criar**
5. Quando solicitado, conecte sua conta Gmail (cacagrandini@gmail.com)

### 2.2 — Configurar o gatilho Gmail

No bloco **"Quando um novo email chegar":**
- **Incluir Anexos:** Não
- **Assunto do filtro:** `EXPENSES`
- Deixe os outros campos em branco

> ⚠️ O gatilho Gmail retorna `snippet` (prévia curta do email). Para garantir que o texto completo seja lido, siga o próximo passo.

### 2.3 — Buscar o conteúdo completo do email

1. Clique em **+ Novo passo**
2. Busque **Gmail** → **"Obter email"** (Get email)
3. **ID da Mensagem:** clique no campo → selecione o token dinâmico **Id** (do gatilho)

### 2.4 — Inicializar variáveis

Adicione 3 ações **"Inicializar variável"** (Initialize variable):

| Nome | Tipo | Valor inicial |
|---|---|---|
| `DataAtual` | Cadeia de caracteres (String) | *(vazio)* |
| `NomeTabela` | Cadeia de caracteres (String) | *(vazio)* |
| `Banco` | Cadeia de caracteres (String) | *(vazio)* |

### 2.5 — Dividir o email em linhas

1. Clique em **+ Novo passo**
2. **Controle** → **Aplicar a cada um** (Apply to each)
3. **Selecionar saída das etapas anteriores:** clique no campo → na barra de expressões (fx), cole:
   ```
   split(body('Obter_email')?['Body'], '\n')
   ```
4. Clique em **OK**

### 2.6 — Detectar linha de data vs. linha de gasto

Dentro do "Aplicar a cada um", adicione uma ação **Condição**:

**Condição A — É uma linha de data?**

Expressão: 
```
equals(length(trim(items('Aplicar_a_cada_um'))), 5)
```
E também:
```
equals(substring(trim(items('Aplicar_a_cada_um')), 2, 1), '/')
```

**Se SIM (linha de data):**
- Ação **Definir variável** → `DataAtual` = expressão:
  ```
  concat(trim(items('Aplicar_a_cada_um')), '/2026')
  ```
- Ação **Definir variável** → `NomeTabela` = expressão Switch:
  ```
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '01'), 'janeiro',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '02'), 'fevereiro',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '03'), 'março',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '04'), 'abril',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '05'), 'maio',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '06'), 'junho',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '07'), 'julho',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '08'), 'agosto',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '09'), 'setembro',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '10'), 'outubro',
  if(equals(substring(trim(items('Aplicar_a_cada_um')), 3, 2), '11'), 'novembro',
  'dezembro')))))))))))
  ```

**Se NÃO — adicione outra Condição B — É uma linha de gasto?**

Expressão:
```
contains(items('Aplicar_a_cada_um'), ':')
```

**Se SIM (linha de gasto):** siga para o passo 2.7.

### 2.7 — Parsear a linha de gasto

Ainda dentro do bloco "Se SIM" da Condição B, adicione variáveis locais com **Compor** (Compose) para cada parte:

**Compor — NomeETag** (tudo antes de `:`)
```
substring(items('Aplicar_a_cada_um'), 0, indexOf(items('Aplicar_a_cada_um'), ':'))
```

**Compor — Resto** (tudo depois de `:`, sem espaços)
```
trim(substring(items('Aplicar_a_cada_um'), add(indexOf(items('Aplicar_a_cada_um'), ':'), 1)))
```

**Compor — TemmTag** (verificar se tem `[`)
```
contains(outputs('Compor_NomeETag'), '[')
```

**Compor — NomeLoja**
```
if(outputs('Compor_TemmTag'),
  trim(first(split(outputs('Compor_NomeETag'), '['))),
  trim(outputs('Compor_NomeETag'))
)
```

**Compor — TagBruta** (categoria)
```
if(outputs('Compor_TemmTag'),
  first(split(last(split(outputs('Compor_NomeETag'), '[')), ']')),
  ''
)
```

**Compor — TemPix** (verificar se tem `(`)
```
contains(outputs('Compor_Resto'), '(')
```

**Compor — FormaBruta**
```
if(outputs('Compor_TemPix'),
  first(split(last(split(outputs('Compor_Resto'), '(')), ')')),
  ''
)
```

**Compor — RestroSemPix**
```
if(outputs('Compor_TemPix'),
  trim(first(split(outputs('Compor_Resto'), '('))),
  trim(outputs('Compor_Resto'))
)
```

**Compor — Palavras**
```
split(outputs('Compor_RestroSemPix'), ' ')
```

**Compor — Valor**
```
first(outputs('Compor_Palavras'))
```

**Compor — BancoBruto**
```
toLower(join(skip(outputs('Compor_Palavras'), 1), ' '))
```

### 2.8 — Normalizar banco

Adicione **Compor — BancoFinal**:
```
if(or(equals(outputs('Compor_BancoBruto'), 'nubank'), equals(outputs('Compor_BancoBruto'), 'nu bank')), 'Nubank',
if(equals(outputs('Compor_BancoBruto'), 'inter'), 'Inter',
if(or(equals(outputs('Compor_BancoBruto'), 'ifood'), equals(outputs('Compor_BancoBruto'), 'ifood benefícios')), 'Ifood Benefícios',
if(equals(outputs('Compor_BancoBruto'), 'alelo'), 'Alelo',
if(equals(outputs('Compor_BancoBruto'), 'wise'), 'Wise',
if(equals(outputs('Compor_BancoBruto'), 'dinheiro'), '',
outputs('Compor_BancoBruto')))))))
```

### 2.9 — Normalizar forma de pagamento

Adicione **Compor — FormaFinal**:
```
if(equals(outputs('Compor_BancoBruto'), 'dinheiro'), 'Dinheiro',
if(equals(toLower(outputs('Compor_FormaBruta')), 'pix'), 'Pix',
'Cartão de Crédito'))
```

### 2.10 — Normalizar motivo (categoria)

Adicione **Compor — MotivoFinal**:
```
if(equals(outputs('Compor_TagBruta'), 'comida'), 'Comida - dia a dia',
if(equals(outputs('Compor_TagBruta'), 'saida'), 'Saída entre amigos',
if(equals(outputs('Compor_TagBruta'), 'viagem'), 'Passagens de Viagem',
if(equals(outputs('Compor_TagBruta'), 'acomodacao'), 'Acomodação em Viagem',
if(equals(outputs('Compor_TagBruta'), 'higiene'), 'Higiene / Skin Care',
if(equals(outputs('Compor_TagBruta'), 'transporte'), 'Transporte',
if(equals(outputs('Compor_TagBruta'), 'roupas'), 'Roupas / Bolsas / Joias / Sapatos / Make / Glitter',
if(equals(outputs('Compor_TagBruta'), 'lazer'), 'Lazer / Experiências',
if(equals(outputs('Compor_TagBruta'), 'fitness'), 'Vida Fitness / Saúde',
if(equals(outputs('Compor_TagBruta'), 'estudos'), 'Estudos',
if(equals(outputs('Compor_TagBruta'), 'burocracia'), 'Burocracias',
if(equals(outputs('Compor_TagBruta'), 'telefone'), 'Telefone / Eletrônicos',
if(equals(outputs('Compor_TagBruta'), 'presentes'), 'Presentes',
if(equals(outputs('Compor_TagBruta'), 'investimentos'), 'Investimentos',
''))))))))))))))
```

### 2.11 — Calcular valor negativo

Adicione **Compor — ValorNegativo**:
```
mul(float(replace(outputs('Compor_Valor'), ',', '.')), -1)
```

### 2.12 — Adicionar linha na tabela do Excel

1. Clique em **+ Adicionar ação** (ainda dentro do "Se SIM" da Condição B)
2. Busque **Excel Online (Business)** → **"Adicionar uma linha em uma tabela"**
3. Configure:
   - **Local:** OneDrive for Business
   - **Biblioteca de Documentos:** OneDrive
   - **Arquivo:** navegue até `Finanças > Gastos > 2026 > Finanças 2026 - Belo Horizonte.xlsx`
   - **Tabela:** clique no campo → expressão:
     ```
     variables('NomeTabela')
     ```
4. Mapeie as colunas que aparecem:

| Coluna na planilha | Valor |
|---|---|
| DESTINO | `first(split(outputs('Compor_NomeETag'), ' '))` *(primeira palavra)* |
| DATA | `variables('DataAtual')` |
| MOTIVO | `outputs('Compor_MotivoFinal')` |
| BANCO USADO | `outputs('Compor_BancoFinal')` |
| MODO DE PAGAMENTO | `outputs('Compor_FormaFinal')` |
| INFOS EXTRA | expressão: resto após a primeira palavra (ver nota abaixo) |
| VALOR | `outputs('Compor_ValorNegativo')` |

5. Clique em **Salvar** (canto superior direito)

---

## Parte 3: Testar a automação completa

1. No iPhone, abra o **Notes** e escreva uma nota de teste:
   ```
   27/05
   teste automacao mercado [comida]: 1,00 Nubank (Pix)
   ```
2. Toque em **Compartilhar** → **Log Expenses**
3. Aguarde alguns segundos e verifique se o email chegou em cacagrandini@gmail.com com assunto `EXPENSES`
4. Acesse [make.powerautomate.com](https://make.powerautomate.com) → **Meus fluxos** → clique no fluxo → veja **Histórico de execuções de 28 dias**
5. A execução mais recente deve aparecer como **Bem-sucedida** (verde)
6. Abra a planilha no Excel Online → aba **maio** → a linha de teste deve estar lá

---

## Uso diário

> **Importante — evitar duplicatas:** Nunca compartilhe a nota inteira, senão todas as linhas serão inseridas novamente na planilha. Sempre **selecione apenas os novos gastos** antes de compartilhar.

**Passo a passo para sincronizar:**

1. Abra a nota no iPhone
2. Toque e segure na primeira linha que ainda não foi sincronizada (long press)
3. Arraste para selecionar até a última linha nova — só as linhas que você quer enviar
4. Com o texto selecionado, toque em **Compartilhar** (pode aparecer no menu de seleção)
5. Role e toque em **Log Expenses**
6. A planilha é atualizada em segundos

**Dica:** Para saber onde parou a última sincronização, você pode adicionar um símbolo (ex: `✓`) ao final da última linha já sincronizada na nota.

---

## Solução de problemas

| Problema | Causa provável | Solução |
|---|---|---|
| Email não chega no Gmail | Atalho não configurado corretamente | Reabra o Atalho e verifique o endereço e assunto |
| Fluxo não dispara | Filtro de assunto errado | Verifique se o email chegou com assunto exatamente `EXPENSES` |
| Fluxo dispara mas falha | Expressão com erro | Abra o histórico de execuções, clique na execução e veja qual passo falhou |
| Linha vai para a aba errada | Data com formato diferente | Confirme que a data na nota está no formato `DD/MM` (ex: `07/03`) |
| Planilha não encontrada | Arquivo ainda no Cofre Pessoal | Mova o arquivo para fora do Cofre Pessoal (ver pré-requisito) |
| Tabela não encontrada | Nome da tabela diferente | Abra o Excel → clique na tabela → veja o nome em Ferramentas de Tabela |
