"""
Script para geração de PDF Interativo e Estilizado do Portfólio de Jobs da Super SofIA.
Cada Job possui estritamente UM comando oficial no Discord, conforme solicitado.
Renderiza HTML/CSS moderno via Playwright em PDF A4 com links internos navegáveis.
"""

import os
import asyncio
from playwright.async_api import async_playwright

OUTPUT_PDF = os.path.join(os.path.dirname(__file__), "Manual_Interativo_SofIA.pdf")

HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Manual Interativo de Automações - Super SofIA</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

    :root {
      --primary: #2563eb;
      --primary-dark: #1d4ed8;
      --primary-light: #eff6ff;
      --accent: #0ea5e9;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --dark: #0f172a;
      --text: #334155;
      --text-muted: #64748b;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --code-bg: #1e293b;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      background-color: var(--bg);
      line-height: 1.5;
      font-size: 12.5px;
    }

    .page {
      padding: 24px;
      max-width: 960px;
      margin: 0 auto;
      background: white;
    }

    /* HEADER */
    .header {
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
      color: white;
      padding: 28px 24px;
      border-radius: 14px;
      margin-bottom: 20px;
      box-shadow: 0 8px 20px -4px rgba(15, 23, 42, 0.2);
    }

    .header-badge {
      display: inline-block;
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(8px);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 10.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 10px;
    }

    .header h1 {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      margin-bottom: 6px;
    }

    .header p {
      color: #cbd5e1;
      font-size: 13px;
      max-width: 750px;
    }

    .rule-callout {
      background: #fef3c7;
      border-left: 4px solid var(--warning);
      padding: 10px 14px;
      border-radius: 6px;
      margin-bottom: 20px;
      font-size: 11.5px;
      color: #92400e;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    /* ÍNDICE / SUMÁRIO */
    .toc-card {
      background: var(--primary-light);
      border: 1px solid #bfdbfe;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }

    .toc-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--primary-dark);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .toc-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 6px 12px;
    }

    .toc-link {
      display: flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      color: #1e40af;
      font-weight: 500;
      font-size: 11.5px;
      padding: 5px 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid #dbeafe;
      transition: all 0.2s;
    }

    .toc-num {
      background: var(--primary);
      color: white;
      font-size: 9.5px;
      font-weight: 700;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    /* JOB CARDS */
    .job-section {
      margin-bottom: 16px;
      page-break-inside: avoid;
    }

    .job-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
    }

    .job-header {
      background: #f1f5f9;
      border-bottom: 1px solid var(--border);
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .job-title-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .job-icon {
      font-size: 18px;
    }

    .job-title {
      font-size: 13.5px;
      font-weight: 700;
      color: var(--dark);
    }

    .job-badges {
      display: flex;
      gap: 6px;
    }

    .badge {
      font-size: 9.5px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .badge-tela {
      background: #e0e7ff;
      color: #3730a3;
    }

    .badge-auto {
      background: #dcfce7;
      color: #166534;
    }

    .job-body {
      padding: 12px 14px;
    }

    .job-desc {
      font-size: 12px;
      color: var(--text);
      margin-bottom: 10px;
    }

    /* COMMAND BOX (EXATAMENTE UM COMANDO) */
    .command-box {
      background: var(--code-bg);
      border-radius: 6px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .command-label {
      font-size: 9.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #94a3b8;
      white-space: nowrap;
    }

    .command-code {
      font-family: 'JetBrains Mono', monospace;
      color: #38bdf8;
      font-size: 11.5px;
      font-weight: 600;
      word-break: break-all;
    }

    .back-to-top {
      display: inline-block;
      margin-top: 8px;
      font-size: 10.5px;
      color: var(--primary);
      text-decoration: none;
      font-weight: 600;
    }

    .footer {
      text-align: center;
      font-size: 10.5px;
      color: var(--text-muted);
      margin-top: 25px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <div class="page">
    
    <!-- HEADER -->
    <div class="header" id="topo">
      <div class="header-badge">Super SofIA • Automação Unificada ERP ADMSIS</div>
      <h1>Manual de Jobs & Comandos Oficiais da SofIA</h1>
      <p>Catálogo operacional completo da Super SofIA. Para cada job cadastrado na plataforma, é exibido estritamente o seu comando oficial único de acionamento no Discord.</p>
    </div>

    <!-- REGRA GERAL -->
    <div class="rule-callout">
      <span style="font-size: 16px;">💡</span>
      <div>
        <strong>Regra de Acionamento:</strong> A SofIA responde no canal quando mencionada (<code>@SofIA</code>), pelo nome (<code>sofia ...</code>), mensagem direta (DM) ou reply.
      </div>
    </div>

    <!-- ÍNDICE INTERATIVO -->
    <div class="toc-card">
      <div class="toc-title">
        <span>📑</span> Índice Rápido de Jobs (Clique para navegar)
      </div>
      <div class="toc-grid">
        <a class="toc-link" href="#job-1"><span class="toc-num">1</span> 01. Boletos e Faturas (PDF)</a>
        <a class="toc-link" href="#job-2"><span class="toc-num">2</span> 02. Lançamento de Guias GNRE</a>
        <a class="toc-link" href="#job-3"><span class="toc-num">3</span> 03. Vale Refeição em Lote (VR)</a>
        <a class="toc-link" href="#job-4"><span class="toc-num">4</span> 04. Adiantamento Salarial em Lote</a>
        <a class="toc-link" href="#job-5"><span class="toc-num">5</span> 05. Folha de Pagamento (Salários)</a>
        <a class="toc-link" href="#job-6"><span class="toc-num">6</span> 06. Pagamento Avulso (PIX / TED)</a>
        <a class="toc-link" href="#job-7"><span class="toc-num">7</span> 07. Alteração de Título Individual</a>
        <a class="toc-link" href="#job-8"><span class="toc-num">8</span> 08. Alteração de Vencimento em Lote</a>
        <a class="toc-link" href="#job-9"><span class="toc-num">9</span> 09. Relatório Contas a Pagar (2015)</a>
        <a class="toc-link" href="#job-10"><span class="toc-num">10</span> 10. Relatório Contas a Receber (2004)</a>
        <a class="toc-link" href="#job-11"><span class="toc-num">11</span> 11. Consulta de Histórico de Lotes</a>
        <a class="toc-link" href="#job-12"><span class="toc-num">12</span> 12. Prêmio de Vendas (Nevine)</a>
        <a class="toc-link" href="#job-13"><span class="toc-num">13</span> 13. Faturamento & Emissão de NF-e</a>
        <a class="toc-link" href="#job-14"><span class="toc-num">14</span> 14. Consulta de DANFE / XML</a>
        <a class="toc-link" href="#job-15"><span class="toc-num">15</span> 15. Ordem de Produção (OP)</a>
        <a class="toc-link" href="#job-16"><span class="toc-num">16</span> 16. Emissão de Guia GNRE Sefaz</a>
        <a class="toc-link" href="#job-17"><span class="toc-num">17</span> 17. Previsão Financeira / Caixa</a>
        <a class="toc-link" href="#job-18"><span class="toc-num">18</span> 18. Fechamento Fiscal Mensal XML</a>
        <a class="toc-link" href="#job-19"><span class="toc-num">19</span> 19. Espelho de Ponto REP Henry</a>
        <a class="toc-link" href="#job-20"><span class="toc-num">20</span> 20. Dashboard de Métricas (8080)</a>
        <a class="toc-link" href="#job-21"><span class="toc-num">21</span> 21. Cronograma de Tarefas (Cron)</a>
      </div>
    </div>

    <!-- 01. BOLETOS -->
    <div class="job-section" id="job-1">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📄</span>
            <span class="job-title">01. Lançamento de Boletos e Faturas (PDF)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Auto-GED / D-1</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lê linha digitável, favorecido, valor e vencimento do PDF. Clona o título no ERP aplicando D-1, anexa o documento no GED e faz download da Autorização de Pagamento.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA lance este pagamento</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 02. GNRE ERP -->
    <div class="job-section" id="job-2">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏛️</span>
            <span class="job-title">02. Lançamento de Guias GNRE no ERP</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Vencimento Original</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lança guias estaduais GNRE no Contas a Pagar do ADMSIS, respeitando estritamente o vencimento original impresso na guia (sem D-1) e anexando o comprovante.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA lance a GNRE</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 03. VR -->
    <div class="job-section" id="job-3">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🍽️</span>
            <span class="job-title">03. Vale Refeição em Lote (VR)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Planilha Excel</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lê a planilha oficial de VR da competência informada, desconta férias e faltas, e lança no ERP os títulos de todos os colaboradores rateados nas filiais 429, 601 e Nevine.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA faça o VR de outubro</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 04. ADIANTAMENTO -->
    <div class="job-section" id="job-4">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">💵</span>
            <span class="job-title">04. Adiantamento Salarial em Lote</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Holerites</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lê a relação de adiantamentos quinzenais em PDF, localiza colaboradores no cadastro do ERP e lança os títulos individuais com plano de contas de Adiantamento Salarial.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA lance adiantamento filial 601</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 05. FOLHA DE PAGAMENTO -->
    <div class="job-section" id="job-5">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">💼</span>
            <span class="job-title">05. Folha de Pagamento (Salários)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Resumo Líquido</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Processa o PDF oficial de Resumo de Líquido da Folha de Pagamento e grava os salários líquidos mensais de todos os colaboradores no ERP ADMSIS.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA lance pagamento filial 601</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 06. AVULSO -->
    <div class="job-section" id="job-6">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">💸</span>
            <span class="job-title">06. Pagamento Avulso (PIX / TED)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Sem Boleto</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lança pagamentos pontuais sem código de barras (PIX, TED, prestadores de serviço), clonando o histórico do favorecido e atualizando valor, vencimento e descrição.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA lance pagamento avulso para EDUARDO LAURINDO, valor 760, filial 429, ref MANUTENÇÃO, vencimento hoje</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 07. ALTERAÇÃO INDIVIDUAL -->
    <div class="job-section" id="job-7">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">✏️</span>
            <span class="job-title">07. Alteração de Título Individual</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Prorrogação / Plano</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Localiza o último título pendente do fornecedor no ADMSIS e altera dinamicamente data de vencimento, plano de contas, valor, filial ou observação.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA altere a data de vencimento do favorecido EDUARDO LAURINDO para 15/10/2026</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 08. ALTERAÇÃO EM LOTE -->
    <div class="job-section" id="job-8">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🔄</span>
            <span class="job-title">08. Alteração de Vencimento em Lote</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Massa / Lote</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Filtra todos os títulos pendentes de uma data de origem e prorroga o vencimento de todos simultaneamente para a nova data informada.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA altere a data de vencimento de TODOS os favorecidos de HOJE para 15/10/2026</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 09. RELATÓRIO 2015 -->
    <div class="job-section" id="job-9">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📊</span>
            <span class="job-title">09. Relatório Oficial de Contas a Pagar (Cód. 2015)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0117030100</span>
            <span class="badge badge-auto">PDF Oficial</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Emite o Relatório Oficial 2015 no ERP ADMSIS para a data especificada, calcula o somatório por filial e envia o PDF oficial gerado como anexo no chat.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA contas a pagar de hoje</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 10. RELATÓRIO 2004 -->
    <div class="job-section" id="job-10">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📥</span>
            <span class="job-title">10. Relatório Oficial de Contas a Receber (Cód. 2004)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0117030100</span>
            <span class="badge badge-auto">PDF Oficial</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Emite o Relatório Oficial 2004 de títulos a receber em aberto no ERP ADMSIS, destacando os principais devedores e enviando o PDF completo no Discord.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA contas a receber de hoje</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 11. HISTÓRICO -->
    <div class="job-section" id="job-11">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📜</span>
            <span class="job-title">11. Consulta de Histórico de Lotes Executados</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Base Local JSON</span>
            <span class="badge badge-auto">Auditoria</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Exibe a tabela dos últimos lotes processados pela SofIA (VR, Salários, Adiantamentos), indicando data, competência, filial, colaboradores e valor total lançado.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA historico</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 12. PRÊMIO DE VENDAS -->
    <div class="job-section" id="job-12">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏆</span>
            <span class="job-title">12. Incentivo / Prêmio de Vendas (Nevine)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Google Sheets</span>
            <span class="badge badge-auto">Ranking Comercial</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Conecta à base de vendas, consolida os bônus comerciais por vendedor aplicando regras F1 (Cliente Novo) e F2 (Espaço Nevine), e gera o ranking em PDF.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA calcule o prêmio de setembro</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 13. NFE FATURAMENTO -->
    <div class="job-section" id="job-13">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏭</span>
            <span class="job-title">13. Faturamento & Emissão de NF-e</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103030100</span>
            <span class="badge badge-auto">Emissão + Boleto</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Localiza o pedido na grade de faturamento do ADMSIS, dispara a autorização da NF-e e, caso a forma de pagamento seja boleto, gera os boletos bancários automaticamente.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA faturar pedido 1585</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 14. DANFE / XML -->
    <div class="job-section" id="job-14">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🔍</span>
            <span class="job-title">14. Consulta de DANFE e Baixa de XML de NF-e</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103050100</span>
            <span class="badge badge-auto">Download PDF/XML</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Acessa a tela de consulta de notas pelo número do pedido, extrai o DANFE em PDF e o arquivo XML original, enviando ambos diretamente no chat.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA danfe 1585</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 15. OP -->
    <div class="job-section" id="job-15">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">⚙️</span>
            <span class="job-title">15. Conclusão de Ordem de Produção (OP)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0102080100</span>
            <span class="badge badge-auto">Produção</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Filtra a Ordem de Produção pelo número do pedido, seleciona os componentes no grid interno e confirma a conclusão formal do lote de fabricação no ERP.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA avançar op 1585</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 16. GNRE SEFAZ -->
    <div class="job-section" id="job-16">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏛️</span>
            <span class="job-title">16. Emissão de Guia GNRE (Portal Sefaz Nacional)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Portal GNRE</span>
            <span class="badge badge-auto">ICMS-ST / FCP</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Extrai impostos interestaduais no ERP (ICMS-ST, FCP, IE, Chave DFe), acessa o Portal Nacional da GNRE via Camoufox, preenche os formulários e baixa o PDF oficial.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA crie a GNRE do pedido 1760</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 17. PREVISÃO FINANCEIRA -->
    <div class="job-section" id="job-17">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📈</span>
            <span class="job-title">17. Previsão Financeira & Fluxo de Caixa</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Telas 2004/2015</span>
            <span class="badge badge-auto">Google Sheets</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Baixa relatórios 2004 e 2015 no ERP, aplica regras de compensação bancária e feriados por filial (302, 429, 551, 601, Nevine) e preenche as 50 células no Google Sheets.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA gerar previsão</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 18. FECHAMENTO FISCAL XML -->
    <div class="job-section" id="job-18">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📦</span>
            <span class="job-title">18. Fechamento Fiscal Mensal de XMLs</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">0104040100 / 0117020100</span>
            <span class="badge badge-auto">ZIPs + XLSX</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Baixa os pacotes ZIP com todos os XMLs de notas fiscais emitidas no mês e gera o Relatório 2001 em XLSX para todas as 5 filiais da empresa.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA fechamento fiscal 09/2026</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 19. PONTO ELETRÔNICO -->
    <div class="job-section" id="job-19">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">⏱️</span>
            <span class="job-title">19. Espelho de Ponto Eletrônico (REP Henry)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">REP 601 + Nevine</span>
            <span class="badge badge-auto">HTML Interativo</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Consolida os registros AFD dos relógios 601 e Nevine, calcula carga horária CLT (tolerância de 10 min, horas extras e atrasos) e gera o espelho interativo HTML.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA espelho de ponto</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 20. MÉTRICAS -->
    <div class="job-section" id="job-20">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📊</span>
            <span class="job-title">20. Dashboard de Métricas Operacionais</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Porta 8080</span>
            <span class="badge badge-auto">API REST</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Apresenta o painel de notas emitidas, boletos gerados e guias GNRE em produção, com servidor HTTP ativo na porta 8080 (<code>/metricas</code>).</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA metricas</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 21. CRONOGRAMA -->
    <div class="job-section" id="job-21">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">⏰</span>
            <span class="job-title">21. Cronograma de Tarefas Automáticas (Cron)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Loop Assíncrono</span>
            <span class="badge badge-auto">Fila erp_lock</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Exibe o status do agendador interno em segundo plano, horários programados (NF-e de hora em hora, GNRE às 09h/11h/14h/16h e Previsão às 09h30) e horários da última rodada.</p>
          <div class="command-box">
            <span class="command-label">Comando:</span>
            <span class="command-code">@SofIA agendamentos</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- FOOTER -->
    <div class="footer">
      Super SofIA • Central Unificada de Automações ERP ADMSIS & Financeiro<br>
      Manual atualizado em Outubro/2026 • 21 Jobs com Comando Único Oficial.
    </div>

  </div>
</body>
</html>
"""

async def main():
    print("Iniciando geração do PDF interativo oficial com comando único por job...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.set_content(HTML_CONTENT, wait_until="networkidle")
        
        await page.pdf(
            path=OUTPUT_PDF,
            format="A4",
            print_background=True,
            margin={
                "top": "12mm",
                "bottom": "12mm",
                "left": "12mm",
                "right": "12mm"
            }
        )
        await browser.close()
        
    print(f"[OK] PDF interativo gerado com sucesso em:\n{OUTPUT_PDF}")

if __name__ == "__main__":
    asyncio.run(main())
