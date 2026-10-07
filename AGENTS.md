# AGENTS.md - Super SofIA (Administrativo)

## 1. Identidade e Escopo Exclusivo do Projeto
* **Nome do Projeto**: **Super SofIA - Administrativo**
* **Diretório Raiz**: `c:\Users\finan\OneDrive\Área de Trabalho\automacao contas a pagar`
* **Assistente Responsável**: **SofIA** (Assistente de Operações Administrativas, Financeiras, Fiscais e DP)
* **Status**: Sistema unificado com 20 jobs automatizados, monitoramento de métricas (`http://localhost:8080/metricas`) e bot integrado ao Discord.

---

## 2. 🛑 TRAVA DE ISOLAMENTO: NÃO CONFUNDIR COM NATALIA (COMERCIAL)
* **Projeto NatalIA (Comercial)**: Fica na pasta `c:\Users\finan\OneDrive\Área de Trabalho\assistente` e é atendido em outra janela do Antigravity.
* **Fronteira Absoluta**:
  1. **NÃO ACESSAR NEM EXECUTAR NADA NA PASTA `assistente`**: Qualquer IA atuando neste repositório está **estritamente proibida** de ler, criar, editar ou executar scripts, testes ou comandos git na pasta `assistente`.
  2. **USUÁRIO ERP EXCLUSIVO**: A SofIA possui credenciais próprias no Admsis ERP (definidas no `.env` local). Nunca altere para as credenciais da NatalIA, evitando derrubar sessões de vendas ativas.
  3. **CANAIS DISCORD EXCLUSIVOS**: A SofIA opera com seu próprio token de bot e canais dedicados (Administrativo, Financeiro, Fiscal, GNRE e Logs). Não misturar com os canais comerciais da NatalIA.
  4. **NÃO IMPORTAR REGRAS COMERCIAIS**: Regras de orçamentos, pedidos de venda, cálculo de frete, SKUs ou tabelas de preço pertencem exclusivamente à NatalIA.

---

## 3. Escopo Funcional da Super SofIA
A SofIA gerencia com exclusividade os 4 pilares administrativos:

1. **Financeiro**:
   - Contas a Pagar: Leitura OCR de boletos, tributos e avulsos, lançamento com prevenção de duplicidade (SHA-256), upload no GED do Admsis e emissão da Autorização de Pagamento em PDF.
   - Contas a Receber: Monitoramento de cobranças e baixas.
   - Previsão Financeira: Varredura diária das contas do dia e alertas.
   - Relatórios Gerenciais: Relatório 2015 (Pagar) e Relatório 2004 (Receber).

2. **Fiscal & Faturamento**:
   - Faturamento & NF-e: Varredura e emissão automática horária conforme planilhas de expedição.
   - Emissão de GNREs: Processamento no Portal Sefaz estadual, anexo do comprovante e baixa automática.
   - Fechamento Mensal Fiscal: Consolidação e empacotamento de XMLs e PDFs de NF-e para contabilidade.

3. **Departamento Pessoal (DP)**:
   - Folha de Pagamento de Salários (Relatórios e Lançamentos).
   - Adiantamentos Salariais quinzenais.
   - Vale Refeição (VR) com rateio e lançamento de créditos.
   - Premiações e Registro de Ponto de colaboradores.

4. **Operação e Estabilidade**:
   - Trava de Concorrência: Todos os módulos que acessam o ERP devem respeitar a trava assíncrona `erp_lock`.
   - Monitoramento: Servidor de Métricas ativo em segundo plano na porta `8080`.
   - Inicialização no Windows: Através dos scripts `iniciar_super_sofia.bat` e `iniciar_super_sofia_invisivel.vbs`.
