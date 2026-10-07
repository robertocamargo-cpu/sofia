# Super SofIA - Administrativo (ADMSIS ERP)

Sistema unificado de automação RPA para operações administrativas, financeiras, fiscais e departamento pessoal (Boletos, Faturamento/NF-e, GNRE Sefaz, Fechamento Fiscal, Folha, VR, Adiantamentos, Ponto e Previsão Financeira), integrado com o ERP **ADMSIS**, **GED** e bot no **Discord**.

> ℹ️ **Nota de Escopo**: Este repositório é exclusivo da **Super SofIA (Administrativo)**. As operações comerciais (orçamentos, pedidos de venda e frete) são de responsabilidade exclusiva da **NatalIA** no projeto separado `assistente`.

---

## Modos de Operação

### 1. Via Discord Bot (SofIA)
A assistente atua de forma conversacional e assíncrona no canal do Discord:
1. O usuário anexa o PDF e envia:
   > `@SofIA lance este pagamento`
2. A SofIA valida os dados, impede duplicidades (via hash SHA-256), lança o título no ERP, anexa o PDF ao GED e clica em `Impr. Aut. Pagto`.
3. A SofIA responde no chat com o resumo formatado (Embed) e **devolve o PDF da Autorização de Pagamento** pronto para aprovação/assinatura bancária.

**Como iniciar o bot:**
```bash
python sofia_bot.py
```

---

### 2. Via Linha de Comando (CLI / Teste Local)
Você pode executar o fluxo de lançamento diretamente pelo terminal:
```bash
# Executar qualquer documento através da Sofia:
python run_sofia.py "GNRE NF 54949.pdf"

# Lançamento em lote de Vale Refeição (VR):
python run_vr.py "outubro 2026"

# Lançamento em lote de Adiantamento Salarial:
python run_adiantamento.py "adiantamento_601.pdf"
python run_adiantamento.py "adiantamento_nevine.pdf"

# Lançamento em lote de Folha de Pagamento de Salários:
python run_pagamento.py "PAGAMENTO_601.pdf"
python run_pagamento.py "PAGAMENTO_429.pdf"
python run_pagamento.py "PAGAMENTO_NEVINE.pdf"

# Consulta de Contas a Pagar do Dia (Relatório 2015):
python run_relatorio.py
python run_relatorio.py 03/07/2026
python run_relatorio.py 03/07/2026 601

# Consulta de Contas a Receber do Dia (Relatório 2004):
python run_recebimento.py
python run_recebimento.py 03/07/2026
python run_recebimento.py 03/07/2026 relevo

# Lançamento de Pagamento Avulso (PIX / Transferência sem boleto):
python run_avulso.py "EDUARDO LAURINDO" 760 429 "MANUTENCAO" 30/09/2026

# Ou através dos scripts dedicados:
python run_gnre.py "GNRE NF 54949.pdf"
python run_relevo.py
python run_nevine.py
```

---

## Tecnologias

* **Python 3.11+**
* **Playwright** (Chromium / Camoufox)
* **discord.py** (integração do bot)
* **pdfplumber** & **Pillow** (extração e parsing de PDFs/imagens)
* **python-dotenv** (gerenciamento de credenciais e tokens)

---

## Configuração (`.env`)

Crie ou edite o arquivo `.env` com os seguintes parâmetros:
```env
ERP_URL=https://erp.admsis.com/Home?eng_tela=0103070100
ERP_USERNAME=seu_usuario
ERP_PASSWORD=sua_senha
FILIAL_PADRAO=429
USE_CAMOUFOX=False
PDF_PASSWORD=05393

# Bot Discord SofIA
DISCORD_BOT_TOKEN=seu_discord_bot_token_aqui
```

---

## Documentação Detalhada
Consulte os guias específicos para cada tipo de lançamento:
* [VR.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/VR.md) — Lançamento mensal de Vale Refeição (VR) por colaborador via planilha e ERP.
* [AUTOMACAO.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/AUTOMACAO.md) — Fluxo geral, seletores, regras de negócio e GED.
* [GNRE.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/GNRE.md) — Mapeamento completo das 27 UFs e particularidades de guias estaduais.
* [RELEVO.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/RELEVO.md) — Boletos protegidos por senha e regras de antecipação.
* [Holerite.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/Holerite.md) & [ADIANTAMENTO.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/ADIANTAMENTO.md) — Lançamentos em lote por funcionário.
* [avulso.md](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/avulso.md) — Pagamentos avulsos via PIX/transferência com duplicação do último título.


