# Automação de Adiantamento Salarial no ERP ADMSIS

Este documento consolida o funcionamento do módulo especializado de **Lançamento de Adiantamento Salarial em Lote** no ERP ADMSIS (tela `0103070100` - Financeiro / Títulos a Pagar), espelhado na robustez e no motor comprovado do VR.

---

## 1. Formatos de Documentos Suportados

O parser inteligente (`src/pdf_parser.py` -> `AdiantamentoParser`) é capaz de processar dois formatos distintos de documento:

### Formato A: Relação Geral dos Líquidos (Sintético)
- **Exemplos:** `adiantamento_601.pdf`, `adiantamento_nevine.pdf`
- **Estrutura:** Documento de página única gerado pelo sistema de folha contábil (Phator).
- **Dados extraídos:**
  - **Empresa e CNPJ:** No cabeçalho (ex: `CNPJ: 52.803.025/0001-27` -> Filial 601 | `CNPJ: 71.883.656/0001-48` -> Filial Nevine).
  - **Competência:** `Competência: MM/AAAA` (ex: `08/2026`).
  - **Vencimento:** Padrão dia 20 do mês (se cair em sábado ou domingo, retrocede para a sexta-feira útil anterior).
  - **Tabela de Empregados:** Linhas contendo `Código | Nome do Empregado | CPF | Valor Líquido`.

### Formato B: Recibos Analíticos de Pagamento (Holerite Tradicional)
- **Exemplos:** `Recibo de Pagamento ADIANTAMENTO_601- JULHO.pdf`, `Recibo de Pagamento ADIANTAMENTO_NEVINE- JULHO.pdf`
- **Estrutura:** Múltiplas páginas contendo os recibos individuais dos funcionários com discriminação de proventos/descontos.
- **Dados extraídos:**
  - Código, Nome do Funcionário, CNPJ da Filial, Vencimento (dia 20) e Valor Líquido.

---

## 2. Blindagem de Filiais por CNPJ

Para impedir que títulos sejam cadastrados na filial errada ou que a filial seja alterada indevidamente durante a troca de funcionário, o sistema aplica uma **tripla camada de segurança**:

| Filial | Código ERP (`#ttp_filial_id`) | CNPJ Matriz / Filial | Identificação |
|---|---|---|---|
| **601** | `216` | `52.803.025/0001-27` | 601 COMERCIO, SERVICOS E CONFECCOES LTDA |
| **Nevine** | `293` | `71.883.656/0001-48` | NEVINE COMERCIO E SERVICOS LTDA |
| **429** | `155` | `05.393.606/0001-58` | RELEVO GUARDANAPOS IND COM LTDA (429) |
| **302** | `253` | — | Filial 302 |
| **551** | `161` | — | Filial 551 |
| **Relevo** | `154` | — | Relevo Matriz |

### As 3 Camadas de Blindagem:
1. **Identificação Primária por CNPJ:** O parser lê o CNPJ do cabeçalho do documento e mapeia diretamente para o ID interno da filial.
2. **Seleção Forçada no DOM:** Durante o formulário de edição/cópia, o robô dispara `select_option("#ttp_filial_id", value=val_filial)` e emite evento `change`.
3. **Validação Pré-Gravação:** Antes de submeter o formulário (`#AlterarI`), o robô lê o `<select>` via JavaScript e verifica se o valor e o texto batem com a filial exigida.

---

## 3. Fluxo de Execução no ERP ADMSIS (`src/adiantamento_launcher.py`)

1. **Login & Navegação:** Acessa `0103070100` (Títulos a Pagar).
2. **Filtro de Adiantamentos:**
   - `#ttp_favorecido_tp_id` = `3` (Funcionário).
   - `#ttp_referencia` = `"Adiantamento"`.
   - Clica em `#ConfirmaFiltroS`.
   - *Benefício crucial:* Garante que todos os títulos listados pertencem à conta contábil correta de **Adiantamento Salarial** (não confunde com Vale Refeição ou Fornecedores).
3. **Identificação do Título Base:**
   - O robô checa se já existe um título do próprio colaborador no grid (ex: Arnaldo Acerbi, Fernando Felipe, etc.).
   - Se existir: abre direto o título dele. Ao clicar em **Copiar**, não precisa alterar o colaborador.
   - Se não existir: abre o título base daquela filial (`btnEd_4` para 601, `btnEd_1` para Nevine, `btnEd_11` para 429), abre o lookup `#btnLookupJanela_ttp_funcionario_id`, pesquisa pelo nome e seleciona o colaborador no frame `EngAjaxLookup`.
4. **Cópia do Título:**
   - Dispara `#Copiar` (`f_Copiar()` via submissão com ação `103070105`).
5. **Preenchimento dos Campos:**
   - **Filial:** Forçada para o código correto da filial.
   - **Valor:** `#ttp_valor_titulo` preenchido com o valor líquido em formato brasileiro (`1.720,00`).
   - **Vencimento:** `#ttp_data_vencimento` preenchido com `DDMMAAAA` (dia 20 da competência, com eventos de digitação e blur).
   - **Referência / Nota / Histórico:** `Adiantamento de Salário - MM/AAAA`.
6. **Gravação:**
   - Clica em `#AlterarI` / `EngNavegacao.alterar()`.
   - Aguarda gravação e retorna para a grade principal para o próximo colaborador.
7. **Regra de GED:**
   - Conforme regra contábil de RH, recibos e holerites não devem inflar o GED anexando o PDF a cada título individual. O script pula o upload e conclui o registro diretamente.

---

## 4. Formas de Execução

### Via Linha de Comando (CLI):
```bash
# Executa um arquivo específico (Relação de Líquidos ou Recibo de Pagamento):
python run_adiantamento.py "adiantamento_601.pdf"
python run_adiantamento.py "adiantamento_nevine.pdf"
python run_adiantamento.py "Recibo de Pagamento ADIANTAMENTO_601- JULHO.pdf"

# Execução padrão (processa adiantamento_601.pdf):
python run_adiantamento.py
```

### Via Assistente Discord (SofIA):
1. **Comando de Texto:**
   - `@SofIA lance o adiantamento da filial 601`
   - `@SofIA lance adiantamento nevine`
   - `@SofIA adiantamento agosto`
2. **Envio de Arquivo PDF no Chat:**
   - Basta arrastar e soltar qualquer PDF de adiantamento (relação de líquidos ou recibo de pagamento). A SofIA detecta automaticamente o tipo `Adiantamento`, extrai os colaboradores, exibe o progresso e retorna o Embed verde com o resumo consolidado da folha lançada no ERP.
