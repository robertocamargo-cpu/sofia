"""
====================================================================
  MÓDULO DE APURAÇÃO DE INCENTIVO / PRÊMIO DE VENDAS (NEVINE)
====================================================================
Fluxo automatizado para apuração de bônus e incentivos comerciais:
  1. Conecta e baixa os dados atualizados da planilha oficial do Google Sheets.
  2. Filtra o período selecionado (mês anterior completo, mês atual ou datas customizadas).
  3. Aplica exclusão global de status não faturados/cancelados.
  4. Processa os critérios de bonificação:
     - Filtro 1: Cliente Novo + Venda (ind_cliente_novo == "CLIENTE NOVO" e ope_descricao == "* VENDA")
     - Filtro 2: Sem cliente novo + Venda Espaço Nevine (ind_cliente_novo vazio e ope_descricao contém "ESPAÇO NEVINE")
  5. Agrupa por vendedor, calcula vendas e premiação total.
  6. Gera relatório analítico em HTML e PDF oficial.
  7. Registra no histórico estruturado (data/batch_history.json).
"""

import os
import re
import csv
import io
import asyncio
import urllib.request
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict
from typing import Optional, Dict, Any, Tuple, List

from dotenv import load_dotenv

load_dotenv()

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

GOOGLE_SHEETS_CSV_URL = os.getenv(
    "PREMIO_SHEETS_URL",
    "https://docs.google.com/spreadsheets/d/19NV3k-0H4-rw49K4pwrND8owsaWkFOSeHTkscqGcsZQ/export?format=csv&gid=827221464"
)

STATUS_EXCLUIDOS = {
    "APROVACAO",
    "ANALISE DE CREDITO",
    "VENDEDOR",
    "FATURAMENTO DENEGADO",
    "CANCELADO"
}

MESES_NOMES = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

def parse_decimal_br(val: Any) -> Decimal:
    """Converte valores textuais com formato brasileiro para Decimal."""
    if not val:
        return Decimal("0")
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")

def formatar_moeda_br(val: Any) -> str:
    """Formata Decimal/float para padrão monetário brasileiro R$ 0.000,00."""
    try:
        d = Decimal(str(val))
        return f"R$ {d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def determinar_periodo_premio(texto: str = "") -> Tuple[date, date, str]:
    """
    Identifica as datas de início e fim da apuração a partir de comando textual.
    Padrão se omitido: mês anterior completo.
    """
    t = texto.lower().strip()
    hoje = date.today()

    # 1. Período explícito DD/MM/AAAA a DD/MM/AAAA
    m_range = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\s*(?:a|ate|até|-)\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", t)
    if m_range:
        d1, m1, y1, d2, m2, y2 = m_range.groups()
        if len(y1) == 2: y1 = f"20{y1}"
        if len(y2) == 2: y2 = f"20{y2}"
        dt_ini = date(int(y1), int(m1), int(d1))
        dt_fim = date(int(y2), int(m2), int(d2))
        label = f"{dt_ini.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')}"
        return dt_ini, dt_fim, label

    # 2. Mês específico por nome (ex: "premio de setembro", "agosto")
    for idx, m_nome in enumerate(MESES_NOMES):
        if idx > 0 and (m_nome in t or (m_nome == "março" and "marco" in t)):
            ano = hoje.year
            # Se o mês solicitado for maior que o mês atual, refere-se ao ano passado
            if idx > hoje.month:
                ano -= 1
            dt_ini = date(ano, idx, 1)
            # Último dia do mês
            if idx == 12:
                dt_fim = date(ano, 12, 31)
            else:
                dt_fim = date(ano, idx + 1, 1) - timedelta(days=1)
            label = f"{m_nome.capitalize()}/{ano}"
            return dt_ini, dt_fim, label

    # 3. Mês atual até hoje (ex: "premio do mes", "este mes")
    if any(k in t for k in ["este mes", "este mês", "mes atual", "mês atual", "do mes", "do mês"]):
        dt_ini = date(hoje.year, hoje.month, 1)
        dt_fim = hoje
        label = f"Mês Atual ({dt_ini.strftime('%d/%m')} a {dt_fim.strftime('%d/%m/%Y')})"
        return dt_ini, dt_fim, label

    # 4. Padrão: Mês anterior completo
    primeiro_dia_mes_atual = date(hoje.year, hoje.month, 1)
    dt_fim = primeiro_dia_mes_atual - timedelta(days=1)
    dt_ini = date(dt_fim.year, dt_fim.month, 1)
    nome_mes_ant = MESES_NOMES[dt_fim.month].capitalize()
    label = f"{nome_mes_ant}/{dt_fim.year}"
    return dt_ini, dt_fim, label

import time

CACHE_CSV_PATH = os.path.join(LOG_DIR, "planilha_google_cache.csv")

def baixar_planilha_csv(forcar_download: bool = False) -> List[Dict[str, str]]:
    """Baixa o CSV oficial diretamente do Google Sheets com retry e cache local de alta velocidade."""
    # Se o cache tiver menos de 10 minutos e não for forçado, usa o cache local instantâneo
    if not forcar_download and os.path.isfile(CACHE_CSV_PATH):
        try:
            idade_segundos = time.time() - os.path.getmtime(CACHE_CSV_PATH)
            if idade_segundos < 600:
                print(f"  [Prêmio] Usando cache recente da planilha ({idade_segundos:.0f}s atrás)...", flush=True)
                with open(CACHE_CSV_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if len(rows) > 100:
                        return rows
        except Exception as e:
            print(f"  [Prêmio] Aviso ao ler cache: {e}", flush=True)

    print("  [Prêmio] Baixando planilha oficial do Google Sheets...", flush=True)
    req = urllib.request.Request(GOOGLE_SHEETS_CSV_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    
    ultimo_erro = None
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                if len(content) > 1000 and "id_unico" in content:
                    # Salva no cache local
                    try:
                        with open(CACHE_CSV_PATH, "w", encoding="utf-8", errors="ignore") as f_cache:
                            f_cache.write(content)
                    except Exception:
                        pass
                    reader = csv.DictReader(io.StringIO(content))
                    rows = list(reader)
                    print(f"  [Prêmio] Download concluído com sucesso: {len(rows)} linhas recebidas.", flush=True)
                    return rows
                else:
                    print(f"  [Prêmio] Tentativa {tentativa+1}: resposta com formato inesperado.", flush=True)
        except Exception as e:
            ultimo_erro = e
            print(f"  [Prêmio] Tentativa {tentativa+1} falhou: {e}", flush=True)
            time.sleep(1)

    # Fallback para o cache local se o download online falhar
    if os.path.isfile(CACHE_CSV_PATH):
        print("  [Prêmio] Aviso: Utilizando último cache local disponível devido a instabilidade na conexão.", flush=True)
        with open(CACHE_CSV_PATH, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            return list(reader)

    raise RuntimeError(f"Não foi possível baixar os dados da planilha do Google Sheets: {ultimo_erro}")

async def apurar_premio_vendas(
    texto_comando: str = "",
    dt_inicio: Optional[date] = None,
    dt_fim: Optional[date] = None
) -> Dict[str, Any]:
    """
    Executa a apuração completa de incentivo de vendas para a equipe comercial da Nevine:
      - Baixa os dados
      - Filtra período e status
      - Processa regras F1 e F2
      - Gera ranking consolidado
      - Gera relatório HTML e PDF
    """
    if dt_inicio and dt_fim:
        periodo_label = f"{dt_inicio.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')}"
    else:
        dt_inicio, dt_fim, periodo_label = determinar_periodo_premio(texto_comando)

    dt_ini_str = dt_inicio.strftime("%Y-%m-%d")
    dt_fim_str = dt_fim.strftime("%Y-%m-%d")

    print(f"\n{'='*70}")
    print(f"  INICIANDO APURAÇÃO DE INCENTIVO DE VENDAS (NEVINE)")
    print(f"  Período : {periodo_label} ({dt_ini_str} a {dt_fim_str})")
    print(f"{'='*70}\n")

    # 1. Download
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, baixar_planilha_csv)

    f1_rows = []
    f2_rows = []

    # 2. Filtragem
    for r in rows:
        vda_data = (r.get("vda_data") or "").strip()
        if not (dt_ini_str <= vda_data <= dt_fim_str):
            continue

        siv = (r.get("siv_descricao") or "").strip().upper()
        if siv in STATUS_EXCLUIDOS:
            continue

        cli_novo = (r.get("ind_cliente_novo") or "").strip().upper()
        ope = (r.get("ope_descricao") or "").strip().upper()

        # Critério Filtro 1: CLIENTE NOVO + * VENDA
        if cli_novo == "CLIENTE NOVO" and ope == "* VENDA":
            f1_rows.append(r)
        # Critério Filtro 2: Sem cliente novo + ESPAÇO NEVINE
        elif not cli_novo and ("ESPAÇO NEVINE" in ope or "ESPA?O NEVINE" in ope):
            f2_rows.append(r)

    # 3. Consolidação por Vendedor
    ranking_map = defaultdict(lambda: {
        "nome": "",
        "qtd_f1": 0,
        "vendas_f1": Decimal("0"),
        "premio_f1": Decimal("0"),
        "qtd_f2": 0,
        "vendas_f2": Decimal("0"),
        "premio_f2": Decimal("0"),
        "total_vendas": Decimal("0"),
        "total_premio": Decimal("0"),
        "total_pedidos": 0
    })

    for r in f1_rows:
        ven = (r.get("ven_nome") or "Não Identificado").strip()
        p = parse_decimal_br(r.get("PREMIO"))
        v = parse_decimal_br(r.get("valor_total"))
        ranking_map[ven]["nome"] = ven
        ranking_map[ven]["qtd_f1"] += 1
        ranking_map[ven]["vendas_f1"] += v
        ranking_map[ven]["premio_f1"] += p
        ranking_map[ven]["total_vendas"] += v
        ranking_map[ven]["total_premio"] += p
        ranking_map[ven]["total_pedidos"] += 1

    for r in f2_rows:
        ven = (r.get("ven_nome") or "Não Identificado").strip()
        p = parse_decimal_br(r.get("PREMIO"))
        v = parse_decimal_br(r.get("valor_total"))
        ranking_map[ven]["nome"] = ven
        ranking_map[ven]["qtd_f2"] += 1
        ranking_map[ven]["vendas_f2"] += v
        ranking_map[ven]["premio_f2"] += p
        ranking_map[ven]["total_vendas"] += v
        ranking_map[ven]["total_premio"] += p
        ranking_map[ven]["total_pedidos"] += 1

    # Ordena o ranking pelo maior valor de prêmio
    ranking = sorted(ranking_map.values(), key=lambda x: x["total_premio"], reverse=True)

    # Totais gerais
    total_pedidos_f1 = len(f1_rows)
    total_vendas_f1 = sum(parse_decimal_br(r.get("valor_total")) for r in f1_rows)
    total_premio_f1 = sum(parse_decimal_br(r.get("PREMIO")) for r in f1_rows)

    total_pedidos_f2 = len(f2_rows)
    total_vendas_f2 = sum(parse_decimal_br(r.get("valor_total")) for r in f2_rows)
    total_premio_f2 = sum(parse_decimal_br(r.get("PREMIO")) for r in f2_rows)

    total_pedidos_geral = total_pedidos_f1 + total_pedidos_f2
    total_vendas_geral = total_vendas_f1 + total_vendas_f2
    total_premio_geral = total_premio_f1 + total_premio_f2

    # 4. Geração do Relatório HTML
    safe_periodo = periodo_label.replace("/", "-").replace(" ", "_")
    html_filename = f"relatorio_premio_{safe_periodo}.html"
    html_path = os.path.join(LOG_DIR, html_filename)
    pdf_filename = f"relatorio_premio_{safe_periodo}.pdf"
    pdf_path = os.path.join(LOG_DIR, pdf_filename)

    gerar_relatorio_html_premio(
        caminho_html=html_path,
        periodo_label=periodo_label,
        dt_inicio=dt_inicio,
        dt_fim=dt_fim,
        ranking=ranking,
        total_pedidos_geral=total_pedidos_geral,
        total_vendas_geral=total_vendas_geral,
        total_premio_geral=total_premio_geral,
        total_pedidos_f1=total_pedidos_f1,
        total_vendas_f1=total_vendas_f1,
        total_premio_f1=total_premio_f1,
        total_pedidos_f2=total_pedidos_f2,
        total_vendas_f2=total_vendas_f2,
        total_premio_f2=total_premio_f2
    )

    # 5. Geração do PDF Analítico via Playwright
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await b.new_page()
            await page.goto(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}", wait_until="networkidle")
            await page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
            await b.close()
            print(f"  [Prêmio] Relatório PDF gerado com sucesso: {pdf_path}", flush=True)
    except Exception as e_pdf:
        print(f"  [Prêmio] Aviso ao exportar PDF: {e_pdf}", flush=True)

    # 6. Grava no Histórico de Lotes
    resumo_execucao = {
        "competencia": periodo_label,
        "total_colaboradores": len(ranking),
        "total_sucesso": len(ranking),
        "total_falhas": 0,
        "valor_total_lancado": float(total_premio_geral),
        "total_vendas_geral": float(total_vendas_geral),
        "total_pedidos": total_pedidos_geral,
        "ranking": [
            {
                "vendedor": item["nome"],
                "pedidos": item["total_pedidos"],
                "vendas": float(item["total_vendas"]),
                "premio": float(item["total_premio"]),
                "premio_f1": float(item["premio_f1"]),
                "premio_f2": float(item["premio_f2"])
            }
            for item in ranking
        ]
    }

    try:
        from batch_logger import salvar_historico_lote
        salvar_historico_lote("PREMIO_VENDAS", resumo_execucao, arquivo=f"Google Sheets / {periodo_label}")
    except Exception as e_hist:
        print(f"  [Prêmio] Erro ao gravar histórico: {e_hist}", flush=True)

    return {
        "sucesso": True,
        "periodo_label": periodo_label,
        "dt_inicio": dt_inicio.strftime("%d/%m/%Y"),
        "dt_fim": dt_fim.strftime("%d/%m/%Y"),
        "total_pedidos": total_pedidos_geral,
        "total_vendas": float(total_vendas_geral),
        "total_vendas_str": formatar_moeda_br(total_vendas_geral),
        "total_premio": float(total_premio_geral),
        "total_premio_str": formatar_moeda_br(total_premio_geral),
        "subtotal_f1": {
            "pedidos": total_pedidos_f1,
            "vendas_str": formatar_moeda_br(total_vendas_f1),
            "premio_str": formatar_moeda_br(total_premio_f1)
        },
        "subtotal_f2": {
            "pedidos": total_pedidos_f2,
            "vendas_str": formatar_moeda_br(total_vendas_f2),
            "premio_str": formatar_moeda_br(total_premio_f2)
        },
        "ranking": ranking,
        "html_path": html_path,
        "pdf_path": pdf_path if os.path.exists(pdf_path) else None
    }

def formatar_tabela_ranking_discord(ranking: List[Dict[str, Any]]) -> str:
    """Formata tabela de ranking em bloco de texto monoespaçado para o Discord."""
    linhas = [
        "```text",
        f"{'Pos':<4} | {'Vendedor':<18} | {'Pedidos':<7} | {'Prêmio Total'}",
        "-" * 46
    ]
    for i, item in enumerate(ranking, 1):
        pos_txt = f"{i}º"
        v_nome = item["nome"][:18]
        p_str = formatar_moeda_br(item["total_premio"])
        linhas.append(f"{pos_txt:<4} | {v_nome:<18} | {item['total_pedidos']:<7} | {p_str}")
    linhas.append("```")
    return "\n".join(linhas)

def gerar_relatorio_html_premio(
    caminho_html: str,
    periodo_label: str,
    dt_inicio: date,
    dt_fim: date,
    ranking: list,
    total_pedidos_geral: int,
    total_vendas_geral: Decimal,
    total_premio_geral: Decimal,
    total_pedidos_f1: int,
    total_vendas_f1: Decimal,
    total_premio_f1: Decimal,
    total_pedidos_f2: int,
    total_vendas_f2: Decimal,
    total_premio_f2: Decimal
):
    """Gera o arquivo HTML com estética dark-mode premium inspirado no relatório analítico."""
    linhas_tabela = []
    for i, item in enumerate(ranking, 1):
        medal_cls = f"rank-{i}" if i <= 3 else ""
        medal_txt = f"{i}º"
        vendas_f1_fmt = formatar_moeda_br(item["vendas_f1"])
        premio_f1_fmt = formatar_moeda_br(item["premio_f1"])
        vendas_f2_fmt = formatar_moeda_br(item["vendas_f2"])
        premio_f2_fmt = formatar_moeda_br(item["premio_f2"])
        vendas_tot_fmt = formatar_moeda_br(item["total_vendas"])
        premio_tot_fmt = formatar_moeda_br(item["total_premio"])

        linhas_tabela.append(f"""
        <tr>
          <td class="col-rank"><span class="rank-badge {medal_cls}">{medal_txt}</span></td>
          <td>
            <div class="nome-destaque">{item['nome']}</div>
            <div class="sub-pedidos">{item['total_pedidos']} pedidos bonificados</div>
          </td>
          <td class="col-num">
            <div class="val-venda">{vendas_f1_fmt}</div>
            <div class="sub-premio f1-color">{premio_f1_fmt}</div>
          </td>
          <td class="col-num">
            <div class="val-venda">{vendas_f2_fmt}</div>
            <div class="sub-premio f2-color">{premio_f2_fmt}</div>
          </td>
          <td class="col-num">
            <div style="font-weight:600; color:#fff;">{vendas_tot_fmt}</div>
          </td>
          <td class="col-num col-premio">
            <div class="premio-destaque">{premio_tot_fmt}</div>
          </td>
        </tr>
        """)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Incentivo de Vendas - {periodo_label}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    :root {{
      --bg: #0b0f19;
      --surface: #111827;
      --surface-hover: #1e293b;
      --border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #10b981;
      --f1-color: #38bdf8;
      --f2-color: #c084fc;
    }}
    body {{
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 2rem;
    }}
    .container {{
      max-width: 1050px;
      margin: 0 auto;
    }}
    .header {{
      background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
      padding: 2rem;
      border-radius: 16px;
      margin-bottom: 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .header h1 {{ margin: 0; font-size: 1.8rem; font-weight: 700; color: #fff; }}
    .header p {{ margin: 0.3rem 0 0; color: #94a3b8; font-size: 0.95rem; }}
    .badge-periodo {{
      background: rgba(255, 255, 255, 0.15);
      padding: 0.5rem 1rem;
      border-radius: 99px;
      font-weight: 600;
      font-size: 0.9rem;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.2rem;
    }}
    .kpi-label {{ font-size: 0.8rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }}
    .kpi-valor {{ font-size: 1.6rem; font-weight: 700; margin: 0.4rem 0; color: #fff; }}
    .kpi-desc {{ font-size: 0.8rem; color: var(--text-muted); }}
    .table-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      margin-bottom: 2rem;
    }}
    .table-header {{
      padding: 1.2rem 1.5rem;
      border-bottom: 1px solid var(--border);
      font-weight: 700;
      font-size: 1.1rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }}
    th {{
      background: rgba(0, 0, 0, 0.2);
      padding: 0.8rem 1.2rem;
      text-align: left;
      color: var(--text-muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    td {{
      padding: 1rem 1.2rem;
      border-bottom: 1px solid var(--border);
    }}
    tr:hover {{ background: var(--surface-hover); }}
    .col-rank {{ width: 50px; text-align: center; }}
    .rank-badge {{ font-weight: 700; }}
    .rank-1 {{ color: #fbbf24; font-size: 1.1rem; }}
    .rank-2 {{ color: #cbd5e1; font-size: 1.1rem; }}
    .rank-3 {{ color: #d97706; font-size: 1.1rem; }}
    .nome-destaque {{ font-weight: 600; color: #fff; }}
    .sub-pedidos {{ font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }}
    .col-num {{ text-align: right; }}
    .val-venda {{ font-weight: 500; color: #cbd5e1; }}
    .sub-premio {{ font-size: 0.75rem; font-weight: 600; margin-top: 2px; }}
    .f1-color {{ color: var(--f1-color); }}
    .f2-color {{ color: var(--f2-color); }}
    .premio-destaque {{ font-size: 1.1rem; font-weight: 700; color: #34d399; }}
    .footer {{ text-align: center; color: var(--text-muted); font-size: 0.8rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>🏆 Incentivo de Vendas Nevine</h1>
        <p>Relatório Analítico de Premiações por Vendedor</p>
      </div>
      <div class="badge-periodo">📅 {periodo_label}</div>
    </div>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Premiação Total Apurada</div>
        <div class="kpi-valor" style="color: #34d399;">{formatar_moeda_br(total_premio_geral)}</div>
        <div class="kpi-desc">Soma dos bônus de F1 e F2</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Volume de Vendas Elegíveis</div>
        <div class="kpi-valor">{formatar_moeda_br(total_vendas_geral)}</div>
        <div class="kpi-desc">Total gerador de premiação</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Pedidos Elegíveis</div>
        <div class="kpi-valor">{total_pedidos_geral}</div>
        <div class="kpi-desc">{total_pedidos_f1} em F1 + {total_pedidos_f2} em F2</div>
      </div>
    </div>

    <div class="table-card">
      <div class="table-header">📊 Ranking Consolidado por Vendedor</div>
      <table>
        <thead>
          <tr>
            <th class="col-rank">Pos</th>
            <th>Vendedor</th>
            <th style="text-align:right">F1 (Cliente Novo)</th>
            <th style="text-align:right">F2 (Espaço Nevine)</th>
            <th style="text-align:right">Total Vendas</th>
            <th style="text-align:right">Total Prêmio</th>
          </tr>
        </thead>
        <tbody>
          {"".join(linhas_tabela)}
        </tbody>
      </table>
    </div>

    <div class="footer">
      Automação de Premiações Nevine • Gerado pela assistente SofIA em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
    </div>
  </div>
</body>
</html>"""

    with open(caminho_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [Prêmio] Relatório HTML gravado em: {caminho_html}", flush=True)

if __name__ == "__main__":
    import sys
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    res = asyncio.run(apurar_premio_vendas(cmd))
    print(f"\nResultado da Apuração ({res['periodo_label']}):")
    print(f"Total Vendas : {res['total_vendas_str']}")
    print(f"Total Prêmio : {res['total_premio_str']}")
    print(f"Pedidos      : {res['total_pedidos']}")
    print("\nRanking:")
    print(formatar_tabela_ranking_discord(res['ranking']))
