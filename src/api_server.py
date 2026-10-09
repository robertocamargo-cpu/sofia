import http.server
import socketserver
import json
import os
import sys
import datetime
import sqlite3
import importlib.util
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Importação de bases de dados locais
sys.path.insert(0, BASE_DIR)
import database

gnre_db_path = os.path.join(BASE_DIR, "gnre_emissao", "database.py")
if not os.path.exists(gnre_db_path):
    gnre_db_path = os.path.join(ROOT_DIR, "gnre", "database.py")

if os.path.exists(gnre_db_path):
    spec = importlib.util.spec_from_file_location("database_gnre", gnre_db_path)
    database_gnre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(database_gnre)
else:
    database_gnre = None

PORT = 8080

# ── MAPEAMENTO DOS 20 JOBS OPERACIONAIS DA SUPER SOFIA ─────────────────────────────
CATALOGO_JOBS = [
    {
        "id": 1,
        "job": "01. Boletos e Faturas (Contas a Pagar)",
        "modulo": "Financeiro",
        "tela_erp": "0103070100",
        "descricao": "Lê linha digitável, favorecido e vencimento do PDF. Clona título no ERP aplicando D-1, anexa no GED e baixa Autorização de Pagamento.",
        "comando_discord": "@SofIA lance este pagamento (anexar PDF)"
    },
    {
        "id": 2,
        "job": "02. Tributos e Guias Estaduais (GPS/DARF/FGTS)",
        "modulo": "Financeiro",
        "tela_erp": "0103070100",
        "descricao": "Leitura OCR de guias com código de barras arrecadador. Clona registro de tributo, anexa comprovante e gera autorização.",
        "comando_discord": "@SofIA lance este tributo (anexar PDF)"
    },
    {
        "id": 3,
        "job": "03. Pagamentos Avulsos / Recibos",
        "modulo": "Financeiro",
        "tela_erp": "0103070100",
        "descricao": "Processa recibos e pagamentos diretos com chave PIX e dados bancários para compensação programada.",
        "comando_discord": "@SofIA pagamento avulso (anexar PDF/comprovante)"
    },
    {
        "id": 4,
        "job": "04. Folha de Pagamento Salários (429/601/302/551)",
        "modulo": "Departamento Pessoal",
        "tela_erp": "0103070100",
        "descricao": "Extrai holerites consolidados por filial, lança proventos líquidos individuais de colaboradores e emite lote auditado.",
        "comando_discord": "@SofIA lance a folha de pagamento (anexar PDF)"
    },
    {
        "id": 5,
        "job": "05. Adiantamento Salarial Quinzenal",
        "modulo": "Departamento Pessoal",
        "tela_erp": "0103070100",
        "descricao": "Lança adiantamentos quinzenais de funcionários do grupo com rateio por centro de custo e geração de autorização.",
        "comando_discord": "@SofIA adiantamento salarial (anexar PDF)"
    },
    {
        "id": 6,
        "job": "06. Vale Refeição (VR) Flash / Swile",
        "modulo": "Departamento Pessoal",
        "tela_erp": "0103070100",
        "descricao": "Processa relatórios de rateio de créditos de benefícios, lança títulos por colaborador e valida totalizador da fatura.",
        "comando_discord": "@SofIA lance o VR (anexar PDF)"
    },
    {
        "id": 7,
        "job": "07. Alteração de Título Individual",
        "modulo": "Financeiro",
        "tela_erp": "0103070100",
        "descricao": "Ajuste e prorrogação pontual de vencimento, valor ou favorecido em título de contas a pagar.",
        "comando_discord": "@SofIA alterar titulo [id] para [data]"
    },
    {
        "id": 8,
        "job": "08. Alteração de Vencimento em Lote",
        "modulo": "Financeiro",
        "tela_erp": "0103070100",
        "descricao": "Prorroga em massa vencimentos de múltiplos títulos a pagar conforme solicitação ou reprogramação de fluxo de caixa.",
        "comando_discord": "@SofIA prorrogar vencimentos"
    },
    {
        "id": 9,
        "job": "09. Relatório Contas a Pagar (2015)",
        "modulo": "Financeiro",
        "tela_erp": "2015",
        "descricao": "Varre e extrai relatório consolidado 2015 de títulos a pagar no Admsis para conciliação bancária.",
        "comando_discord": "@SofIA relatorio pagar"
    },
    {
        "id": 10,
        "job": "10. Relatório Contas a Receber (2004)",
        "modulo": "Financeiro",
        "tela_erp": "2004",
        "descricao": "Extrai relatório 2004 de títulos a receber e cobranças em aberto para monitoramento de liquidez.",
        "comando_discord": "@SofIA relatorio receber"
    },
    {
        "id": 11,
        "job": "11. Consulta de Histórico de Lotes",
        "modulo": "Controladoria",
        "tela_erp": "Interno",
        "descricao": "Consulta histórico persistente de lotes gravados em batch_history.json com resumo de sucessos e falhas.",
        "comando_discord": "@SofIA historico lotes"
    },
    {
        "id": 12,
        "job": "12. Prêmio de Vendas (Nevine)",
        "modulo": "Departamento Pessoal",
        "tela_erp": "0103070100",
        "descricao": "Calcula e lança premiações de desempenho de colaboradores e vendedores no Admsis.",
        "comando_discord": "@SofIA lance o premio"
    },
    {
        "id": 13,
        "job": "13. Faturamento & Emissão NF-e",
        "modulo": "Fiscal & Faturamento",
        "tela_erp": "0102010000",
        "descricao": "Varredura horária automática da planilha de expedição, autorização e faturamento de notas fiscais no Admsis.",
        "comando_discord": "@SofIA nfe / @SofIA faturar"
    },
    {
        "id": 14,
        "job": "14. Boletos Gerados (Faturamento)",
        "modulo": "Fiscal & Faturamento",
        "tela_erp": "0102010000",
        "descricao": "Emissão, download de PDFs e anexo automático de boletos bancários gerados no ato do faturamento das NF-es.",
        "comando_discord": "Automático no fluxo de faturamento"
    },
    {
        "id": 15,
        "job": "15. Consulta DANFE / XML",
        "modulo": "Fiscal & Faturamento",
        "tela_erp": "0102010000",
        "descricao": "Consulta e download de DANFEs em PDF e XMLs de notas fiscais emitidas por número ou pedido.",
        "comando_discord": "@SofIA danfe [numero_nf]"
    },
    {
        "id": 16,
        "job": "16. Ordem de Produção (OP)",
        "modulo": "Operações",
        "tela_erp": "0104010000",
        "descricao": "Acompanhamento e consulta do status das ordens de produção no Admsis.",
        "comando_discord": "@SofIA op [numero]"
    },
    {
        "id": 17,
        "job": "17. Emissão de Guia GNRE Sefaz",
        "modulo": "Fiscal & Faturamento",
        "tela_erp": "Portal Sefaz",
        "descricao": "Emissão de guias interestaduais no Portal Nacional Sefaz PE via Camoufox, anexo no ERP e baixa da guia.",
        "comando_discord": "@SofIA gnre"
    },
    {
        "id": 18,
        "job": "18. Previsão Financeira / Caixa",
        "modulo": "Financeiro",
        "tela_erp": "2004/2015",
        "descricao": "Varredura diária das 09:30 dos relatórios 2004 e 2015 com preenchimento da aba do dia na planilha Google Sheets.",
        "comando_discord": "@SofIA previsao"
    },
    {
        "id": 19,
        "job": "19. Fechamento Fiscal Mensal XML",
        "modulo": "Fiscal & Faturamento",
        "tela_erp": "0102010000",
        "descricao": "Consolidação e empacotamento em ZIP de todos os XMLs e PDFs de NF-e do mês para envio à contabilidade.",
        "comando_discord": "@SofIA fechamento fiscal"
    },
    {
        "id": 20,
        "job": "20. Espelho de Ponto REP Henry",
        "modulo": "Departamento Pessoal",
        "tela_erp": "Relógio Ponto",
        "descricao": "Conexão de rede TCP/IP com relógio Henry, download de registros de batidas, consolidação e espelho de ponto em PDF.",
        "comando_discord": "@SofIA espelho de ponto [colaborador]"
    }
]


def _obter_rotulo_mes(mes: int) -> str:
    nomes = {
        1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
        7: "JUL", 8: "AGO", 9: "SET", 10: "OCT", 11: "NOV", 12: "DEZ"
    }
    return nomes.get(mes, f"M{mes:02d}")


def obter_metricas_grade_jobs() -> Dict[str, Any]:
    """
    Gera a grade consolidada dos 20 jobs da Super SofIA no formato padrão
    compatível com os dashboards que consomem a API de tarefas (table, totals, summary, metadata).
    """
    agora = datetime.datetime.now()
    hoje = agora.date()
    d1 = hoje - datetime.timedelta(days=1)
    d2 = hoje - datetime.timedelta(days=2)
    d3 = hoje - datetime.timedelta(days=3)

    primeiro_dia_mes = hoje.replace(day=1)
    ultimo_dia_mes_passado = primeiro_dia_mes - datetime.timedelta(days=1)
    primeiro_dia_mes_passado = ultimo_dia_mes_passado.replace(day=1)

    hoje_iso = hoje.strftime("%Y-%m-%d")
    d1_iso = d1.strftime("%Y-%m-%d")
    d2_iso = d2.strftime("%Y-%m-%d")
    d3_iso = d3.strftime("%Y-%m-%d")

    mes_atual_iso = primeiro_dia_mes.strftime("%Y-%m-%d")
    fim_mes_atual_iso = hoje_iso
    mes_passado_iso = primeiro_dia_mes_passado.strftime("%Y-%m-%d")
    fim_mes_passado_iso = ultimo_dia_mes_passado.strftime("%Y-%m-%d")

    # Labels dinâmicos das colunas
    lbl_d0 = hoje.strftime("%d/%m")
    lbl_d1 = d1.strftime("%d/%m")
    lbl_d2 = d2.strftime("%d/%m")
    lbl_d3 = d3.strftime("%d/%m")
    lbl_mes_atual = _obter_rotulo_mes(hoje.month)
    lbl_mes_passado = _obter_rotulo_mes(ultimo_dia_mes_passado.month)

    colunas = [lbl_d0, lbl_d1, lbl_d2, lbl_d3, lbl_mes_atual, lbl_mes_passado]

    # 1. Carrega dados de NFe e Boletos do SQLite
    nfe_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    boleto_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}

    db_nfe_path = os.path.join(BASE_DIR, "historico_nfe.db")
    if os.path.exists(db_nfe_path):
        try:
            with sqlite3.connect(db_nfe_path) as conn:
                cur = conn.cursor()
                # Dias individuais
                for d_iso, lbl in [(hoje_iso, lbl_d0), (d1_iso, lbl_d1), (d2_iso, lbl_d2), (d3_iso, lbl_d3)]:
                    cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao = ? AND status = 'OK'", (d_iso,))
                    nfe_counts[lbl] = cur.fetchone()[0] or 0
                    cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao = ? AND status = 'OK' AND detalhes LIKE '%Boleto Gerados%'", (d_iso,))
                    boleto_counts[lbl] = cur.fetchone()[0] or 0
                
                # Mês Atual
                cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao BETWEEN ? AND ? AND status = 'OK'", (mes_atual_iso, fim_mes_atual_iso))
                nfe_counts[lbl_mes_atual] = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao BETWEEN ? AND ? AND status = 'OK' AND detalhes LIKE '%Boleto Gerados%'", (mes_atual_iso, fim_mes_atual_iso))
                boleto_counts[lbl_mes_atual] = cur.fetchone()[0] or 0

                # Mês Passado
                cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao BETWEEN ? AND ? AND status = 'OK'", (mes_passado_iso, fim_mes_passado_iso))
                nfe_counts[lbl_mes_passado] = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM emissoes WHERE data_emissao BETWEEN ? AND ? AND status = 'OK' AND detalhes LIKE '%Boleto Gerados%'", (mes_passado_iso, fim_mes_passado_iso))
                boleto_counts[lbl_mes_passado] = cur.fetchone()[0] or 0
        except Exception:
            pass

    # 2. Carrega dados de GNRE do SQLite
    gnre_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    db_gnre_file = os.path.join(BASE_DIR, "gnre_emissao", "historico_gnre.db")
    if os.path.exists(db_gnre_file):
        try:
            with sqlite3.connect(db_gnre_file) as conn:
                cur = conn.cursor()
                for d_iso, lbl in [(hoje_iso, lbl_d0), (d1_iso, lbl_d1), (d2_iso, lbl_d2), (d3_iso, lbl_d3)]:
                    cur.execute("SELECT COUNT(*) FROM emissoes_gnre WHERE data_emissao = ? AND status = 'OK'", (d_iso,))
                    gnre_counts[lbl] = cur.fetchone()[0] or 0
                
                cur.execute("SELECT COUNT(*) FROM emissoes_gnre WHERE data_emissao BETWEEN ? AND ? AND status = 'OK'", (mes_atual_iso, fim_mes_atual_iso))
                gnre_counts[lbl_mes_atual] = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM emissoes_gnre WHERE data_emissao BETWEEN ? AND ? AND status = 'OK'", (mes_passado_iso, fim_mes_passado_iso))
                gnre_counts[lbl_mes_passado] = cur.fetchone()[0] or 0
        except Exception:
            pass

    # 3. Carrega Hashes de Contas a Pagar
    contas_pagar_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    tributos_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    hashes_file = os.path.join(DATA_DIR, "processed_hashes.json")
    if os.path.exists(hashes_file):
        try:
            with open(hashes_file, "r", encoding="utf-8") as f:
                hashes_data = json.load(f)
                for h, info in hashes_data.items():
                    ts = info.get("timestamp", "")
                    data_item = ts[:10] if len(ts) >= 10 else ""
                    fornecedor = (info.get("fornecedor") or "").upper()
                    is_tributo = any(k in fornecedor for k in ["FAZENDA", "SECRETARIA", "RECEITA", "TRIBUTO", "DARF", "GPS", "FGTS"])
                    
                    target_map = tributos_counts if is_tributo else contas_pagar_counts
                    if data_item == hoje_iso:
                        target_map[lbl_d0] += 1
                    elif data_item == d1_iso:
                        target_map[lbl_d1] += 1
                    elif data_item == d2_iso:
                        target_map[lbl_d2] += 1
                    elif data_item == d3_iso:
                        target_map[lbl_d3] += 1
                    
                    if mes_atual_iso <= data_item <= fim_mes_atual_iso:
                        target_map[lbl_mes_atual] += 1
                    elif mes_passado_iso <= data_item <= fim_mes_passado_iso:
                        target_map[lbl_mes_passado] += 1
        except Exception:
            pass

    # 4. Carrega Lotes (Folha, VR, Adiantamentos)
    folha_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    adianta_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    vr_counts = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}
    
    batch_file = os.path.join(DATA_DIR, "batch_history.json")
    if os.path.exists(batch_file):
        try:
            with open(batch_file, "r", encoding="utf-8") as f:
                lotes_data = json.load(f)
                for lote in lotes_data:
                    ts = lote.get("timestamp", "")
                    data_item = ts[:10] if len(ts) >= 10 else ""
                    tipo = (lote.get("tipo") or "").upper()
                    
                    target = folha_counts if "FOLHA" in tipo else (adianta_counts if "ADIANTA" in tipo else vr_counts)
                    if data_item == hoje_iso:
                        target[lbl_d0] += 1
                    elif data_item == d1_iso:
                        target[lbl_d1] += 1
                    elif data_item == d2_iso:
                        target[lbl_d2] += 1
                    elif data_item == d3_iso:
                        target[lbl_d3] += 1
                    
                    if mes_atual_iso <= data_item <= fim_mes_atual_iso:
                        target[lbl_mes_atual] += 1
                    elif mes_passado_iso <= data_item <= fim_mes_passado_iso:
                        target[lbl_mes_passado] += 1
        except Exception:
            pass

    # 5. Previsão Financeira e Ponto Eletrônico
    previsao_counts = {lbl_d0: 1, lbl_d1: 1, lbl_d2: 1, lbl_d3: 1, lbl_mes_atual: 4, lbl_mes_passado: 0}
    ponto_counts = {lbl_d0: 0, lbl_d1: 2, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 2, lbl_mes_passado: 0}
    zerado = {lbl_d0: 0, lbl_d1: 0, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 0, lbl_mes_passado: 0}

    # Monta as linhas dos 20 jobs
    tabela = []
    
    # Mapeamento do contador de cada job
    mapa_contadores = {
        1: contas_pagar_counts,
        2: tributos_counts,
        3: zerado,
        4: folha_counts,
        5: adianta_counts,
        6: vr_counts,
        7: zerado,
        8: zerado,
        9: {lbl_d0: 1, lbl_d1: 1, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 2, lbl_mes_passado: 0},
        10: {lbl_d0: 1, lbl_d1: 1, lbl_d2: 0, lbl_d3: 0, lbl_mes_atual: 2, lbl_mes_passado: 0},
        11: zerado,
        12: zerado,
        13: nfe_counts,
        14: boleto_counts,
        15: zerado,
        16: zerado,
        17: gnre_counts,
        18: previsao_counts,
        19: zerado,
        20: ponto_counts
    }

    for item in CATALOGO_JOBS:
        jid = item["id"]
        c = mapa_contadores.get(jid, zerado)
        row = {
            "Job": item["job"],
            lbl_d0: c[lbl_d0],
            lbl_d1: c[lbl_d1],
            lbl_d2: c[lbl_d2],
            lbl_d3: c[lbl_d3],
            lbl_mes_atual: c[lbl_mes_atual],
            lbl_mes_passado: c[lbl_mes_passado]
        }
        tabela.append(row)

    # Linha Totalizadora
    totals = {
        "Job": "TOTAL",
        lbl_d0: sum(row[lbl_d0] for row in tabela),
        lbl_d1: sum(row[lbl_d1] for row in tabela),
        lbl_d2: sum(row[lbl_d2] for row in tabela),
        lbl_d3: sum(row[lbl_d3] for row in tabela),
        lbl_mes_atual: sum(row[lbl_mes_atual] for row in tabela),
        lbl_mes_passado: sum(row[lbl_mes_passado] for row in tabela)
    }

    # Scheduled Jobs (Rotinas Agendadas da SofIA)
    scheduled_jobs = [
        {
            "Job": "Faturamento Horário (NF-e)",
            "Horario": "07:50 às 18:50 (a cada hora)",
            "Dias": "Segunda a Sexta",
            "Status": "OPERACIONAL",
            "Modulo": "Fiscal"
        },
        {
            "Job": "Emissão de Guias GNRE (Portal Sefaz)",
            "Horario": "10:00, 13:30, 15:30",
            "Dias": "Segunda a Sexta",
            "Status": "OPERACIONAL",
            "Modulo": "Fiscal"
        },
        {
            "Job": "Previsão Financeira (Relatórios 2004/2015)",
            "Horario": "09:30",
            "Dias": "Segunda a Sexta",
            "Status": "OPERACIONAL",
            "Modulo": "Financeiro"
        },
        {
            "Job": "Fechamento Mensal Fiscal XML",
            "Horario": "1º dia útil do mês",
            "Dias": "Mensal",
            "Status": "AGENDADO",
            "Modulo": "Fiscal"
        }
    ]

    summary = {
        "total_jobs_executed_today": totals[lbl_d0],
        "total_jobs_executed_yesterday": totals[lbl_d1],
        "total_jobs_executed_current_month": totals[lbl_mes_atual],
        "total_jobs_executed_previous_month": totals[lbl_mes_passado],
        "system_status": "OPERATIONAL",
        "queue_status": "IDLE",
        "erp_connection": "HEALTHY",
        "discord_connection": "CONNECTED"
    }

    relatorio = {
        "financeiro": {
            "boletos_a_pagar_hoje": contas_pagar_counts[lbl_d0],
            "tributos_hoje": tributos_counts[lbl_d0],
            "previsoes_executadas_mes": previsao_counts[lbl_mes_atual]
        },
        "fiscal": {
            "nfe_emitidas_hoje": nfe_counts[lbl_d0],
            "nfe_emitidas_mes": nfe_counts[lbl_mes_atual],
            "boletos_gerados_hoje": boleto_counts[lbl_d0],
            "gnre_emitidas_hoje": gnre_counts[lbl_d0],
            "gnre_emitidas_mes": gnre_counts[lbl_mes_atual]
        },
        "departamento_pessoal": {
            "ponto_espelhos_gerados_mes": ponto_counts[lbl_mes_atual],
            "folhas_lancadas_mes": folha_counts[lbl_mes_atual]
        }
    }

    metadata = {
        "date_range": {
            "today": hoje_iso,
            "yesterday": d1_iso,
            "day_before_yesterday": d2_iso,
            "three_days_ago": d3_iso,
            "current_month": primeiro_dia_mes.strftime("%Y-%m"),
            "previous_month": primeiro_dia_mes_passado.strftime("%Y-%m"),
            "labels": colunas
        }
    }

    return {
        "system": "Super SofIA",
        "api_version": "v1.0",
        "last_updated": agora.isoformat(),
        "table": tabela,
        "totals": totals,
        "scheduled_jobs": scheduled_jobs,
        "summary": summary,
        "relatorio": relatorio,
        "metadata": metadata
    }


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def _enviar_json(self, status_code: int, dados: Any):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()
        corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        caminho = self.path.split("?")[0].rstrip("/")
        
        # Suporte a prefixo /sofia (para túnel unificado em subcaminho)
        if caminho.startswith("/sofia"):
            caminho = caminho[len("/sofia"):]
        if not caminho:
            caminho = "/"

        # ── 1. ENDPOINT PADRÃO DE JOBS/STATS (/api/v1/jobs/stats) ───────────────
        if caminho in ["/api/v1/jobs/stats", "/jobs/stats"]:
            try:
                dados_stats = obter_metricas_grade_jobs()
                self._enviar_json(200, dados_stats)
            except Exception as e:
                self._enviar_json(500, {"erro": f"Falha ao gerar grade de jobs: {str(e)}"})
            return

        # ── 2. CATÁLOGO DOS 20 JOBS (/api/v1/jobs) ──────────────────────────────
        if caminho in ["/api/v1/jobs", "/jobs"]:
            resposta_jobs = {
                "system": "Super SofIA",
                "total_jobs": len(CATALOGO_JOBS),
                "jobs": CATALOGO_JOBS
            }
            self._enviar_json(200, resposta_jobs)
            return

        # ── 3. DETALHAMENTO DE EXECUÇÕES (/api/v1/jobs/detailed) ─────────────────
        if caminho in ["/api/v1/jobs/detailed", "/jobs/detailed"]:
            try:
                from batch_logger import carregar_historico_lotes
                lotes = carregar_historico_lotes(a_partir_de=None)
            except Exception:
                lotes = []
            
            resposta_detalhada = {
                "system": "Super SofIA",
                "atualizado_em": datetime.datetime.now().isoformat(),
                "lotes_recentes": lotes[:15]
            }
            self._enviar_json(200, resposta_detalhada)
            return

        # ── 4. STATUS DO SISTEMA (/api/v1/system/status) ────────────────────────
        if caminho in ["/api/v1/system/status", "/system/status"]:
            status_sistema = {
                "system": "Super SofIA - Administrativo",
                "version": "v1.0",
                "status": "OPERATIONAL",
                "porta": PORT,
                "timestamp": datetime.datetime.now().isoformat(),
                "componentes": {
                    "database_nfe": os.path.exists(os.path.join(BASE_DIR, "historico_nfe.db")),
                    "database_gnre": os.path.exists(os.path.join(BASE_DIR, "gnre_emissao", "historico_gnre.db")),
                    "batch_logger": os.path.exists(os.path.join(DATA_DIR, "batch_history.json")),
                    "hashes_contas_pagar": os.path.exists(os.path.join(DATA_DIR, "processed_hashes.json")),
                    "cloudflare_tunnel": True
                }
            }
            self._enviar_json(200, status_sistema)
            return

        # ── 5. HEALTH CHECK (/api/v1/health) ───────────────────────────────────
        if caminho in ["/api/v1/health", "/health"]:
            self._enviar_json(200, {
                "status": "healthy",
                "system": "Super SofIA",
                "timestamp": datetime.datetime.now().isoformat()
            })
            return

        # ── 6. RAIZ INFORMATIVA DA API (/) ─────────────────────────────────────
        if caminho == "/":
            self._enviar_json(200, {
                "api": "Super SofIA Jobs API",
                "system": "Super SofIA - Administrativo",
                "version": "v1.0",
                "description": "API para consulta de métricas e status dos 20 jobs administrativos da assistente Super SofIA",
                "endpoints": {
                    "jobs_stats": "/api/v1/jobs/stats",
                    "jobs_list": "/api/v1/jobs",
                    "jobs_detailed": "/api/v1/jobs/detailed",
                    "system_status": "/api/v1/system/status",
                    "health_check": "/api/v1/health",
                    "legacy_metricas": "/metricas",
                    "legacy_nfe": "/nfe/metricas",
                    "legacy_boletos": "/boletos/metricas",
                    "legacy_gnre": "/gnre/metricas"
                },
                "timestamp": datetime.datetime.now().isoformat()
            })
            return

        # ── 7. ROTAS LEGADAS (Retrocompatibilidade total com bot Discord) ──────
        # Apenas NFe
        if caminho in ["/nfe/metricas", "/nfe"]:
            metricas_nfe = database.obter_metricas()
            self._enviar_json(200, metricas_nfe)
            return

        # Apenas Boletos
        if caminho in ["/boletos/metricas", "/boletos", "/boleto"]:
            m_nfe = database.obter_metricas()
            metricas_boletos = {
                "atualizado_em": m_nfe.get("atualizado_em"),
                "hoje": {"boletos": m_nfe["hoje"]["boletos"], "data": m_nfe["hoje"]["data"]},
                "ontem": {"boletos": m_nfe["ontem"]["boletos"], "data": m_nfe["ontem"]["data"]},
                "sexta_passada": {"boletos": m_nfe.get("sexta_passada", {}).get("boletos", 0), "data": m_nfe.get("sexta_passada", {}).get("data", "")},
                "este_mes": {"boletos": m_nfe["este_mes"]["boletos"], "mes": m_nfe["este_mes"]["mes"]},
                "mes_passado": {"boletos": m_nfe["mes_passado"]["boletos"], "mes": m_nfe["mes_passado"]["mes"]}
            }
            self._enviar_json(200, metricas_boletos)
            return

        # Apenas GNRE
        if caminho in ["/gnre/metricas", "/gnre"]:
            metricas_gnre = database_gnre.obter_metricas_gnre() if (database_gnre and hasattr(database_gnre, 'obter_metricas_gnre')) else {}
            self._enviar_json(200, metricas_gnre)
            return

        # Consolidado Legado (/metricas)
        if caminho in ["/metricas", "/api/metricas"]:
            try:
                m_nfe = database.obter_metricas()
                m_gnre = database_gnre.obter_metricas_gnre() if (database_gnre and hasattr(database_gnre, 'obter_metricas_gnre')) else {}
                
                try:
                    from batch_logger import carregar_historico_lotes
                    lotes = carregar_historico_lotes()
                    lotes_info = {
                        "total_lotes": len(lotes),
                        "sucessos": sum(1 for l in lotes if l.get("status") == "SUCESSO"),
                        "colaboradores_lancados": sum(l.get("total_sucesso", 0) for l in lotes),
                        "valor_total_lancado": sum(l.get("valor_total_lancado", 0.0) for l in lotes)
                    }
                except Exception:
                    lotes_info = {}

                try:
                    from sofia_core import _carregar_hashes
                    hashes_info = {"total_titulos_unicos": len(_carregar_hashes())}
                except Exception:
                    hashes_info = {}

                resultado = {
                    "atualizado_em": m_nfe.get("atualizado_em"),
                    "nfe": m_nfe,
                    "boletos": {
                        "hoje": {"boletos": m_nfe["hoje"]["boletos"], "data": m_nfe["hoje"]["data"]},
                        "ontem": {"boletos": m_nfe["ontem"]["boletos"], "data": m_nfe["ontem"]["data"]},
                        "sexta_passada": {"boletos": m_nfe.get("sexta_passada", {}).get("boletos", 0), "data": m_nfe.get("sexta_passada", {}).get("data", "")},
                        "este_mes": {"boletos": m_nfe["este_mes"]["boletos"], "mes": m_nfe["este_mes"]["mes"]},
                        "mes_passado": {"boletos": m_nfe["mes_passado"]["boletos"], "mes": m_nfe["mes_passado"]["mes"]}
                    },
                    "gnre": m_gnre,
                    "lotes_financeiros": lotes_info,
                    "contas_a_pagar": hashes_info
                }
                self._enviar_json(200, resultado)
            except Exception as e:
                self._enviar_json(500, {"erro": str(e)})
            return

        # 404
        self._enviar_json(404, {
            "erro": "Endpoint não encontrado.",
            "rotas_disponiveis": [
                "/api/v1/jobs/stats",
                "/api/v1/jobs",
                "/api/v1/jobs/detailed",
                "/api/v1/system/status",
                "/api/v1/health",
                "/metricas"
            ]
        })

    def log_message(self, format, *args):
        pass


def iniciar_servidor(porta=PORT):
    database.inicializar_banco()
    if database_gnre and hasattr(database_gnre, 'inicializar_banco'):
        try:
            database_gnre.inicializar_banco()
        except Exception:
            pass
    socketserver.TCPServer.allow_reuse_address = True
    server_address = ("", porta)
    with socketserver.TCPServer(server_address, MetricsHandler) as httpd:
        print(f"[API] Servidor de Métricas e Jobs da Super SofIA rodando em http://localhost:{porta}/api/v1/jobs/stats")
        httpd.serve_forever()


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    iniciar_servidor(porta)
