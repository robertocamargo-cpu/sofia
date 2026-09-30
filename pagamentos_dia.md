# 📊 Fluxo de Automação: Contas a Pagar do Dia (Relatório 2015)

Este documento descreve detalhadamente o fluxo de extração e envio automatizado do **Relatório de Contas a Pagar / Títulos a Pagar** emitido diretamente do ERP ADMSIS e entregue no Discord com o PDF oficial em anexo.

---

## 🎯 1. Visão Geral

- **Objetivo:** Consultar o ERP ADMSIS, gerar o relatório oficial de títulos a pagar para o dia solicitado (ou intervalo/filial desejada), baixar o documento PDF emitido pelo sistema e devolvê-lo diretamente no Discord com um resumo executivo dos valores.
- **Tela no ERP:** `0117030100` (`Relatórios / Relatórios Financeiros`)
- **Código do Relatório:** `2015` (`2015-Relatório de Títulos a Pagar`)
- **Módulos do Sistema:**
  - [`src/relatorio_launcher.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/src/relatorio_launcher.py)
  - [`run_relatorio.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/run_relatorio.py)
  - [`sofia_bot.py`](file:///c:/Users/finan/OneDrive/Área%20de%20Trabalho/automacao%20contas%20a%20pagar/sofia_bot.py)

---

## 🖥️ 2. Mapeamento de Elementos no ERP ADMSIS

| Campo / Ação | Seletor HTML | Descrição / Valor |
| :--- | :--- | :--- |
| **URL da Tela** | `https://erp.admsis.com/Home?eng_tela=0117030100` | Tela de Relatórios Financeiros |
| **Tipo de Relatório** | `<select id="relatorio">` | Seleciona `value="2015"` (Relatório de Títulos a Pagar) |
| **Data Vencimento Inicial** | `<input id="data_vencimento_i">` | Preenchimento de 8 dígitos (`DDMMAAAA`) com disparo de `change` e `blur` |
| **Data Vencimento Final** | `<input id="data_vencimento_f">` | Preenchimento de 8 dígitos (`DDMMAAAA`) com disparo de `change` e `blur` |
| **Filial (Opcional)** | `<select id="filial" multiple>` | Seleção opcional de filiais (`302`, `429`, `551`, `601`, `Nevine`, `Relevo`) |
| **Botão Gerar PDF** | `<button id="btRelatorioPDF">` | Dispara a função JavaScript `f_btRelatorioPDF()` |

---

## ⚡ 3. Arquitetura de Download do PDF (Melhoria Técnica)

No navegador Chrome tradicional, a geração do relatório abre uma nova aba no visualizador interno de PDF do Chromium com o botão "Transferir" (`<cr-icon-button id="save">` em shadow-root).

### 💡 Solução Robusta de Alta Performance Implementada:
Em vez de depender de cliques frágeis dentro da camada de sombra (*Shadow DOM*) do leitor de PDF do navegador, nossa automação:
1. **Intercepta a requisição do ERP:** Monitora as respostas de rede e captura a URL direta do relatório:
   ```text
   https://erp.admsis.com/EngRelatorio/Pdf/2015?requestID=<UUID>
   ```
2. **Download Nativo via Sessão Autenticada:** O Playwright realiza o download direto em bytes utilizando os cookies da sessão já autenticada (`context.request.get(pdf_url)`).
3. **Vantagens:**
   - 100% de estabilidade mesmo em modo *headless* (segundo plano).
   - Sem travamentos com visualizadores de terceiros ou extensões de navegador.
   - Velocidade instantânea de salvamento em disco.

---

## 🚀 4. Sugestões de Melhoria Implementadas

1. **Interpretação Flexível de Datas no Discord:**
   - Reconhece datas específicas digitadas no chat: `03/07/2026`, `03/07/26`, `3/7/2026`.
   - Reconhece termos relativos: `hoje`, `amanhã`, `ontem`.
   - Se nenhuma data for informada, assume automaticamente a data atual (`hoje`).
2. **Resumo Executivo Instantâneo no Embed:**
   - A SofIA inspeciona o PDF baixado via `pdfplumber` e extrai métricas cruciais:
     - **Valor Total a Pagar (R$)**
     - **Quantidade de Títulos no Dia**
     - **Desdobramento de Valores por Filial** (ex: quanto vence na 429, 601, Nevine, etc.)
   - Dessa forma, quem estiver no Discord obtém um panorama financeiro imediato sem precisar abrir o arquivo.
3. **Entrega Oficial do Arquivo:**
   - O documento PDF oficial gerado pelo ERP é anexado diretamente à resposta da mensagem no Discord.
4. **Filtro Opcional por Filial:**
   - O usuário pode pedir o relatório consolidado de todas as empresas ou filtrar apenas uma filial (ex: `@SofIA contas a pagar filial 601`).

---

## 💬 5. Exemplos de Uso no Discord

| O que você digita | Ação da SofIA |
| :--- | :--- |
| `@SofIA contas a pagar de hoje` | Gera o relatório de hoje de todas as filiais e anexa o PDF |
| `@SofIA o que tem para pagar hoje?` | Gera o relatório do dia e anexa o PDF |
| `@SofIA contas a pagar 03/07/2026` | Gera o relatório específico da data `03/07/2026` e anexa o PDF |
| `@SofIA pagamentos do dia filial 601` | Gera o relatório filtrando apenas a filial 601 |
| `@SofIA titulos a pagar amanhã` | Gera a previsão de pagamentos para o dia seguinte |

---

## 💻 6. Execução via Terminal (CLI)

Você também pode gerar o relatório a qualquer momento sem abrir o Discord:

```bash
# Relatório de hoje (todas as filiais)
python run_relatorio.py

# Relatório de data específica
python run_relatorio.py 03/07/2026

# Relatório de data específica filtrando filial
python run_relatorio.py 03/07/2026 601
```

### Exemplo de Saída no Terminal:
```text
=== GERADOR DE RELATÓRIO DE CONTAS A PAGAR ===
Data: 03/07/2026
[Relatório] Realizando login...
Login OK
[Relatório] Navegando para tela https://erp.admsis.com/Home?eng_tela=0117030100...
[Relatório] Selecionando Relatório 2015 (Títulos a Pagar)...
[Relatório] Preenchendo data vencimento: 03/07/2026 até 03/07/2026...
[Relatório] Clicando em #btRelatorioPDF...
[Relatório] URL interceptada: https://erp.admsis.com/EngRelatorio/Pdf/2015?requestID=...
[Relatório] PDF obtido com sucesso (126.901 bytes)!

==============================================
  RELATÓRIO GERADO COM SUCESSO!
==============================================
Arquivo PDF: logs/contas_a_pagar_03072026_03072026_20260929_143258.pdf
Período: 03/07/2026 até 03/07/2026
Quantidade de Títulos: 20
Valor Total a Pagar: R$ 33.200,00

Totais por Filial:
  - Filial 302: R$ 2.930,37
  - Filial 429: R$ 4.852,68
  - Filial 551: R$ 1.200,00
  - Filial 601: R$ 3.357,80
  - Filial Nevine: R$ 14.759,15
==============================================
```
