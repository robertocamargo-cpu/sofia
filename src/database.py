import os
import sqlite3
import datetime
import json
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "historico_nfe.db")
JSON_METRICAS_PATH = os.path.join(BASE_DIR, "logs", "metricas_nfe.json")


def conectar_bd():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    """Cria a tabela de emissões caso não exista."""
    os.makedirs(os.path.dirname(JSON_METRICAS_PATH), exist_ok=True)
    with conectar_bd() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emissoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido TEXT NOT NULL,
                planilha TEXT,
                nfe_numero TEXT,
                qtd_boletos INTEGER DEFAULT 1,
                status TEXT NOT NULL,
                detalhes TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                data_emissao DATE NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_emissao ON emissoes(data_emissao);
        """)
        conn.commit()


def registrar_emissao(pedido: str, planilha: str, status: str, nfe_numero: str = "", qtd_boletos: int = 1, detalhes: str = ""):
    """Registra ou atualiza a emissão de NFe/Boleto para um determinado pedido."""
    inicializar_banco()
    agora = datetime.datetime.now()
    hoje_str = agora.strftime("%Y-%m-%d")
    iso_timestamp = agora.isoformat()

    with conectar_bd() as conn:
        cursor = conn.cursor()
        # Verificar se já existe registro deste pedido no dia de hoje
        cursor.execute(
            "SELECT id, status FROM emissoes WHERE pedido = ? AND data_emissao = ?",
            (str(pedido), hoje_str)
        )
        existente = cursor.fetchone()

        if existente:
            # Se o registro existente hoje já foi 'OK', não sobrescreve com 'PULADO'
            if existente["status"] == "OK" and status == "PULADO":
                logging.info(f"      [BD] Pedido {pedido} já consta como OK hoje. Mantendo status OK (ignorando PULADO).")
                return
            cursor.execute("""
                UPDATE emissoes
                SET planilha = ?, nfe_numero = ?, qtd_boletos = ?, status = ?, detalhes = ?, timestamp = ?
                WHERE id = ?
            """, (planilha, nfe_numero, qtd_boletos, status, detalhes, iso_timestamp, existente["id"]))
        else:
            cursor.execute("""
                INSERT INTO emissoes (pedido, planilha, nfe_numero, qtd_boletos, status, detalhes, timestamp, data_emissao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(pedido), planilha, nfe_numero, qtd_boletos, status, detalhes, iso_timestamp, hoje_str))
        
        conn.commit()
    
    # Atualizar o arquivo JSON para o site externo
    exportar_json_metricas()


def obter_metricas():
    """Retorna o número de NFes e Boletos para Hoje, Ontem, Este Mês e Mês Passado."""
    inicializar_banco()
    agora = datetime.datetime.now()
    hoje = agora.date()
    ontem = hoje - datetime.timedelta(days=1)

    # Cálculo do primeiro dia do mês atual e mês passado
    primeiro_dia_este_mes = hoje.replace(day=1)
    ultimo_dia_mes_passado = primeiro_dia_este_mes - datetime.timedelta(days=1)
    primeiro_dia_mes_passado = ultimo_dia_mes_passado.replace(day=1)

    hoje_str = hoje.strftime("%Y-%m-%d")
    ontem_str = ontem.strftime("%Y-%m-%d")

    # Data de Sexta Passada
    dias_para_sexta = (hoje.weekday() - 4) % 7
    if dias_para_sexta == 0 and hoje.weekday() != 4:
        dias_para_sexta = 7
    sexta_passada = hoje - datetime.timedelta(days=dias_para_sexta)
    sexta_str = sexta_passada.strftime("%Y-%m-%d")

    inicio_este_mes_str = primeiro_dia_este_mes.strftime("%Y-%m-%d")
    fim_este_mes_str = hoje_str
    inicio_mes_passado_str = primeiro_dia_mes_passado.strftime("%Y-%m-%d")
    fim_mes_passado_str = ultimo_dia_mes_passado.strftime("%Y-%m-%d")

    def _consultar_periodo(cursor, inicio, fim):
        query = """
            SELECT 
                COUNT(*) as total_nfe,
                COUNT(CASE WHEN detalhes LIKE '%Boleto Gerados%' THEN 1 END) as total_boletos
            FROM emissoes
            WHERE data_emissao BETWEEN ? AND ? AND status = 'OK'
        """
        cursor.execute(query, (inicio, fim))
        res = cursor.fetchone()
        nfe = res["total_nfe"] or 0
        boletos = res["total_boletos"] or 0
        return nfe, boletos

    with conectar_bd() as conn:
        cursor = conn.cursor()
        hoje_nfe, hoje_boletos = _consultar_periodo(cursor, hoje_str, hoje_str)
        ontem_nfe, ontem_boletos = _consultar_periodo(cursor, ontem_str, ontem_str)
        sexta_nfe, sexta_boletos = _consultar_periodo(cursor, sexta_str, sexta_str)
        este_mes_nfe, este_mes_boletos = _consultar_periodo(cursor, inicio_este_mes_str, fim_este_mes_str)
        mes_passado_nfe, mes_passado_boletos = _consultar_periodo(cursor, inicio_mes_passado_str, fim_mes_passado_str)

    return {
        "atualizado_em": agora.strftime("%d/%m/%Y às %H:%M"),
        "hoje": {
            "nfe": hoje_nfe,
            "boletos": hoje_boletos,
            "data": hoje.strftime("%d/%m/%Y")
        },
        "ontem": {
            "nfe": ontem_nfe,
            "boletos": ontem_boletos,
            "data": ontem.strftime("%d/%m/%Y")
        },
        "sexta_passada": {
            "nfe": sexta_nfe,
            "boletos": sexta_boletos,
            "data": sexta_passada.strftime("%d/%m/%Y")
        },
        "este_mes": {
            "nfe": este_mes_nfe,
            "boletos": este_mes_boletos,
            "mes": agora.strftime("%m/%Y")
        },
        "mes_passado": {
            "nfe": mes_passado_nfe,
            "boletos": mes_passado_boletos,
            "mes": ultimo_dia_mes_passado.strftime("%m/%Y")
        }
    }


def exportar_json_metricas():
    """Salva o resumo de métricas em logs/metricas_nfe.json para consumo de outros sistemas/sites."""
    metricas = obter_metricas()
    try:
        os.makedirs(os.path.dirname(JSON_METRICAS_PATH), exist_ok=True)
        with open(JSON_METRICAS_PATH, "w", encoding="utf-8") as f:
            json.dump(metricas, f, ensure_ascii=False, indent=2)
        logging.info(f"      [BD] Métricas exportadas em {JSON_METRICAS_PATH}")
    except Exception as e:
        logging.error(f"      [ERRO BD] Falha ao exportar JSON de métricas: {e}")


if __name__ == "__main__":
    inicializar_banco()
    exportar_json_metricas()
    print("Banco de dados inicializado com sucesso.")
    print("Métricas Atuais:", json.dumps(obter_metricas(), ensure_ascii=False, indent=2))
