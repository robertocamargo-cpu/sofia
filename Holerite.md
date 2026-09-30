# Automação de Pagamento de Salários (Folha Mensal) no ERP ADMSIS

Este documento consolida o funcionamento do módulo especializado de **Lançamento de Folha de Pagamento de Salários em Lote** no ERP ADMSIS (tela `0103070100` - Financeiro / Títulos a Pagar), seguindo a mesma arquitetura de segurança, cópia de títulos e blindagem de filial utilizada no Adiantamento e no VR.

---

## 1. Documentos e Formato Suportado

O parser inteligente (`src/pdf_parser.py` -> `PagamentoParser`) processa a **Relação Geral dos Líquidos** da Folha Mensal:
- **Exemplos:** `PAGAMENTO_601.pdf`, `PAGAMENTO_429.pdf`, `PAGAMENTO_NEVINE.pdf`.
- **Cabeçalho:**
  - **Empresa & CNPJ:** Ex: `52.803.025/0001-27` $\rightarrow$ Filial **601** | `05.393.606/0001-58` $\rightarrow$ Filial **429** | `71.883.656/0001-48` $\rightarrow$ Filial **NEVINE**.
  - **Tipo de Cálculo:** `Cálculo: Folha Mensal`.
  - **Competência:** `Competência: MM/AAAA` (ex: `06/2026`).
  - **Vencimento:** Extraído da data de emissão no documento (ex: `03/07/2026`, 5º dia útil) ou calculado automaticamente.
- **Categorias Extraídas:**
  - Extrai tanto a tabela de **Empregados** (CLT) quanto de **Contribuintes** (Pró-labore / Autônomos).
  - Campos: Código, Nome do Colaborador, CPF e Valor Líquido.

---

## 2. Blindagem de Filiais por CNPJ

Para garantir que cada título seja vinculado à filial correta:

| Filial | Código ERP (`#ttp_filial_id`) | CNPJ Matriz / Filial | Identificação |
|---|---|---|---|
| **601** | `216` | `52.803.025/0001-27` | 601 COMERCIO, SERVICOS E CONFECCOES LTDA |
| **429** | `155` | `05.393.606/0001-58` | RELEVO GUARDANAPOS IND COM LTDA (429) |
| **Nevine** | `293` | `71.883.656/0001-48` | NEVINE COMERCIO E SERVICOS LTDA |

### As 3 Camadas de Blindagem:
1. **Identificação por CNPJ:** Mapeamento direto do CNPJ para o ID interno do ERP.
2. **Forçamento no DOM:** Disparo de `select_option("#ttp_filial_id", value=val_filial)` e evento `change`.
3. **Validação Pré-Gravação:** Verificação via asserção antes de salvar com `#AlterarI`.

---

## 3. Fluxo de Execução no ERP (`src/pagamento_launcher.py`)

1. **Login & Navegação:** Acessa `0103070100` (Títulos a Pagar).
2. **Filtro de Salários:**
   - `#ttp_favorecido_tp_id` = `3` (Funcionário).
   - `#ttp_referencia` = `"Salario"`.
   - Clica em `#ConfirmaFiltroS`.
   - *Benefício crucial:* Garante que todos os títulos clonados herdam a conta contábil de **Salários / Folha Mensal** (sem misturar com adiantamento salarial ou despesas de alimentação).
3. **Identificação do Título Base:**
   - O robô verifica se já existe título do próprio colaborador no grid (ex: Ana Helena, Fernando Felipe, Helena Eufrasio, Paulo Vinicius).
   - Se existir: abre e clica em **Copiar** diretamente (sem abrir lookup).
   - Se não existir: abre o título base daquela filial (`btnEd_1` para 601, `btnEd_8` para 429), aciona `#Copiar`, abre o lookup `#btnLookupJanela_ttp_funcionario_id`, pesquisa pelo primeiro nome no frame `EngAjaxLookup` e seleciona o colaborador.
4. **Cópia do Título:** Ação `103070105` (`f_Copiar()`).
5. **Preenchimento dos Campos:**
   - **Filial:** Forçada para o código correto (`216` para 601).
   - **Valor:** `#ttp_valor_titulo` preenchido com o valor líquido em padrão brasileiro (`3.350,73`).
   - **Vencimento:** `#ttp_data_vencimento` preenchido com `03072026` com eventos de digitação e blur.
   - **Referência / Nota / Histórico:** `Salário - MM/AAAA`.
6. **Gravação:** `#AlterarI` / `EngNavegacao.alterar()`.
7. **Regra de GED:** Pula o upload de documentos no GED para não inflar o banco e acelerar o processamento.
8. **Retorno à Grade:** Retorna ao grid de títulos para processar o próximo colaborador de forma resiliente.

---

## 4. Formas de Execução

### Via Linha de Comando (CLI):
```bash
# Executar a folha de pagamento da filial 601:
python run_pagamento.py "PAGAMENTO_601.pdf"

# Executar as demais filiais:
python run_pagamento.py "PAGAMENTO_429.pdf"
python run_pagamento.py "PAGAMENTO_NEVINE.pdf"

# Execução padrão (processa PAGAMENTO_601.pdf):
python run_pagamento.py
```

### Via Assistente Discord (SofIA):
1. **Comando de Texto:**
   - `@SofIA lance o pagamento da filial 601`
   - `@SofIA folha de pagamento 601`
   - `@SofIA salario nevine`
2. **Envio de Arquivo PDF no Chat:**
   - Basta arrastar e soltar `PAGAMENTO_601.pdf` (ou qualquer PDF de pagamento). A SofIA detecta o tipo `Pagamento`, lança todos os colaboradores no ERP e responde com a **tabela preenchida e formatada** com todos os dados lançados (sem enviar documentos aleatórios em anexo).

---

## 5. Histórico de Lançamentos Realizados

### Filial 601 — Competência 06/2026 (Processado com Sucesso ✅)
* **Arquivo:** `PAGAMENTO_601.pdf`
* **Vencimento:** `03/07/2026`
* **Plano de Contas:** `SALÁRIOS / FOLHA DE PAGAMENTO`
* **Filial ERP:** `601` (value `216`)

| # | Colaborador | Categoria | CPF | Valor Líquido | Status ERP |
|---|---|---|---|---|---|
| 1 | ANA HELENA ALBUQUERQUE ROCES | Empregado | 268.938.088-95 | R$ 3.350,73 | Gravado ✅ |
| 2 | ARNALDO CESAR ACERBI | Empregado | 044.673.748-84 | R$ 1.574,45 | Gravado ✅ |
| 3 | AURORA LENIRDA DUTRA | Empregado | 402.997.326-49 | R$ 1.504,30 | Gravado ✅ |
| 4 | FERNANDO FELIPE | Empregado | 249.085.898-01 | R$ 2.544,25 | Gravado ✅ |
| 5 | HELENA EUFRASIO | Empregado | 251.612.848-70 | R$ 610,31 | Gravado ✅ |
| 6 | JULIANA SANCHES OLIVEIRA DE PAULA | Empregado | 372.901.728-41 | R$ 2.418,06 | Gravado ✅ |
| 7 | PAULO VINICIUS RODRIGUES FERNANDES | Empregado | 426.201.318-98 | R$ 1.656,79 | Gravado ✅ |
| 8 | ANA PAULA SOEIRO GOMES | Contribuinte | 291.270.328-09 | R$ 1.442,69 | Gravado ✅ |

**Total Lançado:** **R$ 15.101,58** (8 colaboradores) ✅

