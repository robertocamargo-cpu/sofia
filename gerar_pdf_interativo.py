"""
Script para geração de PDF Interativo e Estilizado do Portfólio de Jobs da SofIA.
Utiliza Playwright / Chromium headless para renderizar HTML/CSS moderno em PDF A4 com links clicáveis.
"""

import os
import asyncio
from playwright.async_api import async_playwright

OUTPUT_PDF = os.path.join(os.path.dirname(__file__), "Manual_Interativo_SofIA.pdf")

HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Manual Interativo de Automações - SofIA ERP ADMSIS</title>
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
      font-size: 13px;
    }

    .page {
      padding: 30px;
      max-width: 1000px;
      margin: 0 auto;
      background: white;
    }

    /* HEADER */
    .header {
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
      color: white;
      padding: 35px 30px;
      border-radius: 16px;
      margin-bottom: 25px;
      box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.2);
      position: relative;
    }

    .header-badge {
      display: inline-block;
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(8px);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 12px;
    }

    .header h1 {
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.5px;
      margin-bottom: 8px;
    }

    .header p {
      color: #cbd5e1;
      font-size: 14px;
      max-width: 650px;
    }

    .rule-callout {
      background: #fef3c7;
      border-left: 4px solid var(--warning);
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 25px;
      font-size: 12px;
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
      padding: 20px;
      margin-bottom: 30px;
    }

    .toc-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--primary-dark);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .toc-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px 16px;
    }

    .toc-link {
      display: flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      color: #1e40af;
      font-weight: 500;
      font-size: 12px;
      padding: 6px 10px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid #dbeafe;
      transition: all 0.2s;
    }

    .toc-num {
      background: var(--primary);
      color: white;
      font-size: 10px;
      font-weight: 700;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    /* JOB CARDS */
    .job-section {
      margin-bottom: 25px;
      page-break-inside: avoid;
    }

    .job-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }

    .job-header {
      background: #f1f5f9;
      border-bottom: 1px solid var(--border);
      padding: 12px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .job-title-group {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .job-icon {
      font-size: 20px;
    }

    .job-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--dark);
    }

    .job-badges {
      display: flex;
      gap: 6px;
    }

    .badge {
      font-size: 10px;
      font-weight: 600;
      padding: 3px 8px;
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

    .badge-req {
      background: #fee2e2;
      color: #991b1b;
    }

    .job-body {
      padding: 16px 18px;
    }

    .job-desc {
      font-size: 12.5px;
      color: var(--text);
      margin-bottom: 12px;
    }

    .rules-list {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 14px;
      font-size: 11.5px;
    }

    .rules-list strong {
      color: #1e293b;
    }

    .rules-list ul {
      margin-left: 18px;
      margin-top: 4px;
    }

    .rules-list li {
      margin-bottom: 3px;
    }

    /* COMMAND BOX */
    .command-box {
      background: var(--code-bg);
      border-radius: 8px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .command-label {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #94a3b8;
    }

    .command-code {
      font-family: 'JetBrains Mono', monospace;
      color: #38bdf8;
      font-size: 11.5px;
      word-break: break-all;
    }

    .command-note {
      font-size: 10.5px;
      color: #64748b;
      margin-top: 2px;
      font-style: italic;
    }

    .back-to-top {
      display: inline-block;
      margin-top: 10px;
      font-size: 11px;
      color: var(--primary);
      text-decoration: none;
      font-weight: 600;
    }

    .footer {
      text-align: center;
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 30px;
      padding-top: 15px;
      border-top: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <div class="page">
    
    <!-- HEADER -->
    <div class="header" id="topo">
      <div class="header-badge">Automação Financeira • ADMSIS ERP</div>
      <h1>Manual Interativo de Jobs & Comandos da SofIA</h1>
      <p>Guia operacional completo de automações de Contas a Pagar e Receber via Discord e terminal, com regras de negócio, parametrizações contábeis e comandos.</p>
    </div>

    <!-- REGRA GERAL -->
    <div class="rule-callout">
      <span style="font-size: 18px;">💡</span>
      <div>
        <strong>Regra de Acionamento da SofIA:</strong> A assistente opera em silêncio no canal e <u>só responde quando for chamada diretamente</u> por menção (<code>@SofIA</code>), pelo nome (<code>sofia ...</code>), mensagem direta (DM) ou reply a uma mensagem dela.
      </div>
    </div>

    <!-- ÍNDICE INTERATIVO -->
    <div class="toc-card">
      <div class="toc-title">
        <span>📑</span> Índice Rápido de Jobs (Clique para navegar)
      </div>
      <div class="toc-grid">
        <a class="toc-link" href="#job-1"><span class="toc-num">1</span> 01. Lançamento de Boletos e Faturas (PDF)</a>
        <a class="toc-link" href="#job-2"><span class="toc-num">2</span> 02. Lançamento de Guias GNRE</a>
        <a class="toc-link" href="#job-3"><span class="toc-num">3</span> 03. Vale Refeição em Lote (VR)</a>
        <a class="toc-link" href="#job-4"><span class="toc-num">4</span> 04. Adiantamento Salarial em Lote</a>
        <a class="toc-link" href="#job-5"><span class="toc-num">5</span> 05. Folha de Pagamento (Resumo Líquido)</a>
        <a class="toc-link" href="#job-6"><span class="toc-num">6</span> 06. Pagamento Avulso (PIX / TED)</a>
        <a class="toc-link" href="#job-7"><span class="toc-num">7</span> 07. Alteração de Título Individual</a>
        <a class="toc-link" href="#job-8"><span class="toc-num">8</span> 08. Alteração de Vencimento em Lote</a>
        <a class="toc-link" href="#job-9"><span class="toc-num">9</span> 09. Relatório Oficial Contas a Pagar (2015)</a>
        <a class="toc-link" href="#job-10"><span class="toc-num">10</span> 10. Relatório Oficial Contas a Receber (2004)</a>
        <a class="toc-link" href="#job-11"><span class="toc-num">11</span> 11. Consulta de Histórico de Lotes</a>
        <a class="toc-link" href="#job-12"><span class="toc-num">12</span> 12. Incentivo / Prêmio de Vendas (Nevine)</a>
      </div>
    </div>

    <!-- 1. BOLETOS -->
    <div class="job-section" id="job-1">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📄</span>
            <span class="job-title">01. Lançamento de Boletos e Faturas (PDF)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Auto-GED</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lê linha digitável, favorecido, valor e data de vencimento. Localiza o fornecedor no ERP via lookup, clica em <i>Copiar Título</i>, anexa o PDF no GED e faz download da Autorização de Pagamento Oficial.</p>
          <div class="rules-list">
            <strong>⚙️ Regras de Negócio Aplicadas:</strong>
            <ul>
              <li><strong>Vencimento D-1:</strong> O vencimento gravado no ERP é sempre 1 dia antes da data do boleto (com antecipação automática para sexta se cair no fim de semana).</li>
              <li><strong>Referência Inteligente:</strong> Herda a referência do título clonado e avança automaticamente o mês (ex: <i>Setembro/2026</i> &rarr; <i>Outubro/2026</i>).</li>
            </ul>
          </div>
          <div class="command-box">
            <span class="command-label">Comando no Discord (Anexar PDF)</span>
            <span class="command-code">@SofIA lance este pagamento</span>
            <span class="command-note">Ou: "sofia lance o boleto" (anexando o PDF do boleto/fatura)</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 2. GNRE -->
    <div class="job-section" id="job-2">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏛️</span>
            <span class="job-title">02. Lançamento de Guias GNRE (Tributos Estaduais)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Impostos</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Processa guias GNRE em PDF, identifica o Estado (UF Favorecida), receita tributária, documento de origem (NF), valor e vencimento, clonando o histórico fiscal correspondente e anexando o comprovante.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord (Anexar Guia)</span>
            <span class="command-code">@SofIA lance a GNRE</span>
            <span class="command-note">Identifica automaticamente o Estado (ex: Sefaz Bahia, Pernambuco, etc.)</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 3. VR -->
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
          <p class="job-desc">Lê a aba do mês solicitado na <code>Planilha VR.xlsx</code>, calcula dias trabalhados descontando férias e faltas, e lança no ERP os títulos de cada colaborador rateados nas filiais 429, 601 e Nevine.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA faça o VR de outubro</span>
            <span class="command-note">Ou: "sofia lance o vale refeição de setembro" (sem necessidade de anexo)</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 4. ADIANTAMENTO -->
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
          <p class="job-desc">Processa a relação de adiantamentos quinzenais por filial, localiza os colaboradores na tela de funcionários do ERP e lança os valores líquidos com plano de contas de adiantamento.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA lance adiantamento filial 601</span>
            <span class="command-note">Também aceita filial 429 ou Nevine</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 5. FOLHA DE PAGAMENTO -->
    <div class="job-section" id="job-5">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">👥</span>
            <span class="job-title">05. Folha de Pagamento / Salários (Mensal)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-req">PDF Obrigatório</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lança o salário líquido mensal de todos os colaboradores da filial selecionada a partir do relatório em PDF da <strong>Relação Geral dos Líquidos</strong>.</p>
          <div class="rules-list">
            <strong>⚠️ Regra de Envio Obrigatória:</strong>
            <ul>
              <li><strong>Anexo Mandatório:</strong> É <u>obrigatório anexar o arquivo PDF com o Resumo de Líquido</u> junto ao comando. Sem o anexo, a SofIA não executa e orienta o envio do arquivo.</li>
            </ul>
          </div>
          <div class="command-box">
            <span class="command-label">Comando no Discord (Obrigatoriamente Anexando PDF)</span>
            <span class="command-code">@SofIA lance folha de pagamento filial 601</span>
            <span class="command-note">Ou: "sofia lance pagamento filial nevine" (anexando o PDF com a relação dos líquidos)</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 6. AVULSO -->
    <div class="job-section" id="job-6">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">💸</span>
            <span class="job-title">06. Pagamento Avulso (PIX / TED sem Boleto)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Clonagem Inteligente</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Lança despesas avulsas clonando o último título pendente do favorecido no ERP (herdando plano de contas, rateio e impostos), atualizando valor, filial e data de pagamento.</p>
          <div class="rules-list">
            <strong>⚙️ Regras de Referência e Validação:</strong>
            <ul>
              <li><strong>Referência Opcional:</strong> Se não for informada no comando, a SofIA herda a referência do título anterior e avança o mês automaticamente.</li>
              <li><strong>Campos Obrigatórios:</strong> Favorecido, Valor e Vencimento (se faltar algum, ela pausa e solicita no chat).</li>
            </ul>
          </div>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA lance o pagamento avulso para EDUARDO LAURINDO, valor 760, filial 429, vencimento hoje</span>
            <span class="command-note">Com referência personalizada: "... ref MANUTENÇÃO PREDIAL, vencimento 05/10/2026"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 7. ALTERACAO INDIVIDUAL -->
    <div class="job-section" id="job-7">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">✏️</span>
            <span class="job-title">07. Alteração de Título Individual</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">NLP</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Altera dados específicos do último título pendente de um fornecedor diretamente no formulário do ERP ADMSIS interpretando comandos em linguagem natural.</p>
          <div class="command-box">
            <span class="command-label">Exemplos de Comandos no Discord</span>
            <span class="command-code">@SofIA altere o plano de contas do favorecido Eduardo Laurindo para 41038</span>
            <span class="command-code" style="margin-top: 4px;">@SofIA altere a data de vencimento do favorecido Eduardo Laurindo para 01/10/2026</span>
            <span class="command-note">Suporta também alteração de Filial, Referência, Observação e Valor</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 8. ALTERACAO EM LOTE -->
    <div class="job-section" id="job-8">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🔄</span>
            <span class="job-title">08. Alteração de Vencimento em Lote (Prorrogação)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0103070100</span>
            <span class="badge badge-auto">Lote Geral</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Localiza <strong>todos os títulos pendentes</strong> com vencimento na data de origem especificada e altera em massa o vencimento de cada um para a nova data informada.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA altere a data de vencimento de TODOS os favorecidos de HOJE para 01/10/2026</span>
            <span class="command-note">Ou: "sofia prorrogar todos os titulos de 30/09/2026 para 05/10/2026"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 9. RELATORIO 2015 -->
    <div class="job-section" id="job-9">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📊</span>
            <span class="job-title">09. Relatório Oficial de Contas a Pagar (Cód. 2015)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0117030100</span>
            <span class="badge badge-auto">Emissão Oficial</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Emite o Relatório Oficial 2015 no módulo de relatórios do ERP, intercepta e faz o download do PDF gerado pelo sistema e envia no chat junto a um resumo de despesas por filial.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA contas a pagar de hoje</span>
            <span class="command-note">Ou: "sofia o que tem para pagar hoje?", "@SofIA contas a pagar 03/07/2026 filial 601"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 10. RELATORIO 2004 -->
    <div class="job-section" id="job-10">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📥</span>
            <span class="job-title">10. Relatório Oficial de Contas a Receber (Cód. 2004)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Tela 0117030100</span>
            <span class="badge badge-auto">Emissão Oficial</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Emite o Relatório Oficial 2004 de títulos a receber em aberto, faz download do PDF gerado pelo ADMSIS e envia no Discord destacando montante total e principais devedores.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA contas a receber de hoje</span>
            <span class="command-note">Ou: "sofia recebimentos do dia", "@SofIA titulos a receber de amanha"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 11. HISTORICO -->
    <div class="job-section" id="job-11">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">📜</span>
            <span class="job-title">11. Consulta de Histórico de Lotes Executados</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-auto">Auditoria</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Consulta o arquivo estruturado <code>data/batch_history.json</code> e retorna no chat uma tabela formatada dos últimos lotes processados, títulos lançados, valores e falhas.</p>
          <div class="command-box">
            <span class="command-label">Comando no Discord</span>
            <span class="command-code">@SofIA historico</span>
            <span class="command-note">Ou: "sofia histórico de lotes"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- 12. PREMIO DE VENDAS -->
    <div class="job-section" id="job-12">
      <div class="job-card">
        <div class="job-header">
          <div class="job-title-group">
            <span class="job-icon">🏆</span>
            <span class="job-title">12. Apuração de Incentivo / Prêmio de Vendas (Nevine)</span>
          </div>
          <div class="job-badges">
            <span class="badge badge-tela">Google Sheets</span>
            <span class="badge badge-auto">Relatório PDF</span>
          </div>
        </div>
        <div class="job-body">
          <p class="job-desc">Conecta à base oficial de vendas no Google Sheets, filtra pedidos elegíveis excluindo status reprovados/cancelados e calcula a premiação comercial consolidando regras F1 (Cliente Novo) e F2 (Espaço Nevine), gerando ranking e relatório em PDF.</p>
          <div class="rules-list">
            <strong>⚙️ Critérios de Bonificação Aplicados:</strong>
            <ul>
              <li><strong>F1 (Cliente Novo):</strong> <code>ind_cliente_novo == "CLIENTE NOVO"</code> e <code>ope_descricao == "* VENDA"</code>.</li>
              <li><strong>F2 (Espaço Nevine):</strong> Cliente recorrente e <code>ope_descricao</code> contendo <code>"ESPAÇO NEVINE"</code>.</li>
              <li><strong>Desconsidera:</strong> Status <code>APROVACAO</code>, <code>ANALISE DE CREDITO</code>, <code>VENDEDOR</code>, <code>FATURAMENTO DENEGADO</code> e <code>CANCELADO</code>.</li>
            </ul>
          </div>
          <div class="command-box">
            <span class="command-label">Comandos no Discord</span>
            <span class="command-code">@SofIA calcule o prêmio de setembro</span>
            <span class="command-note">Ou: "@SofIA apurar incentivo", "@SofIA prêmio deste mês", "@SofIA comissão de agosto"</span>
          </div>
          <a class="back-to-top" href="#topo">↑ Voltar ao Índice</a>
        </div>
      </div>
    </div>

    <!-- FOOTER -->
    <div class="footer">
      Automação Contas a Pagar & Receber • ERP ADMSIS • Assistente SofIA<br>
      Documento gerado em 01/10/2026 • Todos os direitos reservados.
    </div>

  </div>
</body>
</html>
"""

async def main():
    print("Iniciando geração do PDF interativo...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Carrega o HTML com os links interativos
        await page.set_content(HTML_CONTENT, wait_until="networkidle")
        
        # Gera o PDF A4 com formatação profissional e links navegáveis preservados
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
        
    print(f"PDF interativo gerado com sucesso em:\n{OUTPUT_PDF}")

if __name__ == "__main__":
    asyncio.run(main())
