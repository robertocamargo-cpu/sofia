# Automação Contas a Pagar - ERP ADMSIS & Assistente SofIA

## Visão Geral
Sistema automatizado em Python que realiza a captura de documentos financeiros (Boletos, GNREs, Holerites), extrai dados em memória, valida a legibilidade e unicidade, lança o título no ERP **ADMSIS**, anexa o documento no **GED**, gera a **Autorização de Pagamento oficial em PDF** e devolve o comprovante para o usuário (via Discord ou CLI).

---

## Fluxo Completo de Lançamento (Closed-Loop)

1. **Recepção do Documento**: Via Discord (`@SofIA lance este pagamento` com anexo) ou linha de comando (`run_sofia.py`).
2. **Validação & Idempotência (Fail-Fast)**:
   - Checagem de hash SHA-256 em `data/processed_hashes.json` para impedir duplicidades no financeiro.
   - Extração rápida de fornecedor, valor e vencimento.
3. **Login no ERP ADMSIS**: Autenticação com sessão gerenciada via Playwright.
4. **Navegação no Grid**: Acessa a tela `0103070100` e filtra pelo tipo de favorecido (`FORNECEDOR` ou `FUNCIONARIO`).
5. **Lookup de Fornecedor / Favorecido**:
   - Clica no botão de lookup correspondente (`#btnLookupJanela_ttp_fornecedor_id`).
   - Aguarda o iframe `EngAjaxLookup` com `#txtPesquisa`.
   - Digita o termo de busca (ex: UF ou nome) e pesquisa (`#btEnviar`).
   - Seleciona o checkbox `.eng-lookup-multi-chk` da linha correspondente e clica em `#btConfirmarSelecao` (ou chama `Selecionar(codigo)`).
6. **Filtrar Grid**: Clica em `#ConfirmaFiltroS` para listar os títulos do fornecedor.
7. **Copiar Título Base**: Localiza um título (preferencialmente da filial desejada, ex: `429`), clica em editar (`a[id^='btnEd_']`) e em seguida em `#Copiar` (confirmando "Sim").
8. **Preenchimento dos Campos**:
   - **Valor**: formato `1200,00` via `#ttp_valor_titulo`.
   - **Vencimento**: digitação numérica sem barras `28092026` com delay de 50ms via `#ttp_data_vencimento` (respeita o componente `eng-campo-data`).
   - **Referência / Nota Fiscal / Observação**: preenchimento padronizado (`REF-{tipo} {doc}`).
   - **Filial**: seleção segura via `#ttp_filial_id`.
9. **Gravação ("Alterar")**: Clica em `button:has-text("Alterar")` e confirma o salvamento ("Sim").
10. **Anexação no GED (Documentos)**:
    - Sem fechar o título recém-salvo, clica na aba **Documentos** (`#tab_btn_0`).
    - Clica em `#btNovo` no iframe `EngGedList`.
    - No iframe `EngGedNovo`, seleciona o arquivo PDF original e clica em `#btNovo` (Carregar Arquivo).
    - Valida o anexo listado no grid do GED.
11. **Emissão da Autorização de Pagamento (#ImprAutPagto)**:
    - Clica no botão `<button id="ImprAutPagto" onclick="f_ImprAutPagto()">`.
    - Intercepta a requisição do relatório oficial `EngRelatorio/Pdf/840`.
    - Faz o download do PDF autenticado e salva em `logs/autorizacao_pagamento_{doc}_{timestamp}.pdf`.
12. **Fechamento e Retorno**:
    - Fecha o modal do título no ERP.
    - O bot do Discord responde na mensagem original com o resumo do lançamento (Embed) e **o PDF da Autorização de Pagamento anexado**.

---

## Pontos Críticos e Técnicos

### 1. Autorização de Pagamento (`f_ImprAutPagto`)
O botão `#ImprAutPagto` submete o formulário com a action `EngRelatorio/Pdf/840?requestID=...`. A captura é feita monitorando o evento de resposta no contexto do navegador (`page.context.on('response', ...)`), capturando a URL e baixando o PDF autenticado via `context.request.get(url)`.

### 2. Lookup de Fornecedor
O iframe `EngAjaxLookup` utiliza checkboxes com classe `.eng-lookup-multi-chk` e confirmação no botão `#btConfirmarSelecao`, disparando `ConfirmarSelecaoMultipla()`. Essa abordagem é 100% resiliente em relação a links dinâmicos e paginação.

### 3. Vencimento
**NÃO** usar `.fill("28/09/2026")` — o componente `eng-campo-data` rejeita caracteres com barras. Deve-se limpar o campo, digitar apenas os 8 dígitos numéricos com delay (`28092026`) e disparar os eventos `change` e `blur`.

### 4. Upload de Arquivos no GED
O `input[type="file"]` (`#eng_arquivo`) fica oculto pelo uploadifive. A automação aciona o file chooser clicando no elemento visível e, como fallback, atribui os arquivos diretamente via `set_input_files`.

### 5. Idempotência / Anti-Duplicidade
O sistema calcula o hash SHA-256 do arquivo recebido e salva em `data/processed_hashes.json`. Se o mesmo arquivo for postado repetidas vezes, a execução é interrompida em 1 segundo com aviso amigável, sem abrir o ERP nem duplicar despesas.

---

## Estrutura de Arquivos

| Arquivo | Função |
| :--- | :--- |
| `sofia_bot.py` | Bot do Discord (recebe `@SofIA lance este pagamento` + anexo, orquestra e devolve o PDF) |
| `src/sofia_core.py` | Orquestrador central: validação Fail-Fast, hash SHA-256, classificação e despacho |
| `src/erp_launcher.py` | Motor Playwright do ERP ADMSIS (login, cópia, preenchimento, GED, `#ImprAutPagto`) |
| `src/run_gnre.py` | Fluxo especializado para GNRE com mapeamento das 27 UFs e lookup da SEFAZ |
| `src/pdf_parser.py` | Parser de PDFs (Boletos, GNREs, DAS, Holerites com desduplicação de caracteres) |
| `src/vr_launcher.py` | Motor de lançamento de Vale Refeição (cópia de títulos, lookup de funcionários, gravação) |
| `src/vr_parser.py` | Leitor e extrator da `Planilha VR.xlsx` com mapeamento de filiais por CNPJ |
| `run_vr.py` | Executador CLI para lote de VR por competência |
| `VR.md` | Documentação técnica e operacional completa do processo de VR |
| `src/adiantamento_launcher.py` | Motor de lançamento de Adiantamento Salarial em lote com blindagem de filial |
| `run_adiantamento.py` | Executador CLI para lançamento de Adiantamento (Relação de Líquidos e Recibos) |
| `ADIANTAMENTO.md` | Documentação técnica e operacional completa do processo de Adiantamento Salarial |
| `src/pagamento_launcher.py` | Motor de lançamento de Folha de Pagamento de Salários com blindagem de filial |
| `run_pagamento.py` | Executador CLI para lançamento de Folha de Pagamento de Salários |
| `Holerite.md` | Documentação técnica e operacional completa do processo de Folha de Salários |
| `src/relatorio_launcher.py` | Motor de extração de Relatórios Financeiros (Pagar Cód. 2015 / Receber Cód. 2004) |
| `run_relatorio.py` | Executador CLI para extração de Contas a Pagar do Dia / Relatório 2015 |
| `pagamentos_dia.md` | Documentação técnica e operacional completa do Relatório de Contas a Pagar do Dia |
| `run_recebimento.py` | Executador CLI para extração de Contas a Receber do Dia / Relatório 2004 |
| `recebimento_dia.md` | Documentação técnica e operacional completa do Relatório de Contas a Receber do Dia |
| `src/batch_logger.py` | Gravador e consultor do histórico estruturado de execuções em lote (`batch_history.json`) |
| `data/batch_history.json` | Log estruturado de auditoria de lotes (VR, Adiantamento, Salários) com métricas financeiras |
| `.env` | Credenciais do ERP, filial padrão e token do Discord (`DISCORD_BOT_TOKEN`) |
| `data/processed_hashes.json` | Banco de hashes para controle de duplicidades individuais |
| `logs/` | Armazena screenshots de diagnóstico e os PDFs das Autorizações de Pagamento emitidas |

---

## 🔒 Concorrência & Fila de Sessão ERP
O bot do Discord gerencia o acesso ao ERP ADMSIS através de um `asyncio.Lock()` global. 
* Se múltiplos usuários emitirem relatórios ou anexarem documentos simultaneamente, as requisições não colidem no ERP nem derrubam a sessão Playwright.
* O bot notifica o usuário instantaneamente: `⏳ Em fila: O ERP ADMSIS está sendo utilizado por outra operação...`, liberando e processando a tarefa de forma ordenada e serializada.

## 📊 Auditoria Estruturada de Lotes (`data/batch_history.json`)
Todas as execuções de VR, Adiantamento Salarial e Pagamento de Salários gravam automaticamente um registro com:
* Tipo do Lote, Competência, Filial, Vencimento.
* Total de colaboradores processados vs. com sucesso.
* Total financeiro lançado (R$).
* Detalhamento de cada colaborador e eventuais falhas.
* Consulta rápida no Discord via `@SofIA historico`.


