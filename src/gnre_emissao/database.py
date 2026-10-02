import os
import sqlite3
import datetime
import json
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "historico_gnre.db")
JSON_METRICAS_PATH = os.path.join(BASE_DIR, "logs", "metricas_gnre.json")


def conectar_bd():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    """Cria a tabela de emissões de GNRE caso não exista."""
    os.makedirs(os.path.dirname(JSON_METRICAS_PATH), exist_ok=True)
    with conectar_bd() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emissoes_gnre (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido TEXT NOT NULL,
                uf TEXT,
                status TEXT NOT NULL,
                detalhes TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                data_emissao DATE NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_gnre ON emissoes_gnre(data_emissao);
        """)
        conn.commit()


def registrar_emissao_gnre(pedido: str, uf: str = "", status: str = "OK", detalhes: str = ""):
    """Registra ou atualiza a emissão de GNRE para um determinado pedido."""
    inicializar_banco()
    agora = datetime.datetime.now()
    hoje_str = agora.strftime("%Y-%m-%d")
    iso_timestamp = agora.isoformat()

    with conectar_bd() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM emissoes_gnre WHERE pedido = ? AND data_emissao = ?",
            (str(pedido), hoje_str)
        )
        existente = cursor.fetchone()

        if existente:
            cursor.execute("""
                UPDATE emissoes_gnre
                SET uf = ?, status = ?, detalhes = ?, timestamp = ?
                WHERE id = ?
            """, (uf, status, detalhes, iso_timestamp, existente["id"]))
        else:
            cursor.execute("""
                INSERT INTO emissoes_gnre (pedido, uf, status, detalhes, timestamp, data_emissao)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(pedido), uf, status, detalhes, iso_timestamp, hoje_str))
        
        conn.commit()
    
    exportar_json_metricas()


def obter_metricas_gnre():
    """Retorna o número de GNREs geradas para Hoje, Ontem, Este Mês e Mês Passado."""
    inicializar_banco()
    agora = datetime.datetime.now()
    hoje = agora.date()
    ontem = hoje - datetime.timedelta(days=1)

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
            SELECT COUNT(*) as total_gnre
            FROM emissoes_gnre
            WHERE data_emissao BETWEEN ? AND ? AND status LIKE 'OK%'
        """
        cursor.execute(query, (inicio, fim))
        res = cursor.fetchone()
        return res["total_gnre"] or 0

    with conectar_bd() as conn:
        cursor = conn.cursor()
        hoje_gnre = _consultar_periodo(cursor, hoje_str, hoje_str)
        ontem_gnre = _consultar_periodo(cursor, ontem_str, ontem_str)
        sexta_gnre = _consultar_periodo(cursor, sexta_str, sexta_str)
        este_mes_gnre = _consultar_periodo(cursor, inicio_este_mes_str, fim_este_mes_str)
        mes_passado_gnre = _consultar_periodo(cursor, inicio_mes_passado_str, fim_mes_passado_str)

    return {
        "atualizado_em": agora.strftime("%d/%m/%Y às %H:%M"),
        "hoje": {
            "gnre": hoje_gnre,
            "data": hoje.strftime("%d/%m/%Y")
        },
        "ontem": {
            "gnre": ontem_gnre,
            "data": ontem.strftime("%d/%m/%Y")
        },
        "sexta_passada": {
            "gnre": sexta_gnre,
            "data": sexta_passada.strftime("%d/%m/%Y")
        },
        "este_mes": {
            "gnre": este_mes_gnre,
            "mes": agora.strftime("%m/%Y")
        },
        "mes_passado": {
            "gnre": mes_passado_gnre,
            "mes": ultimo_dia_mes_passado.strftime("%m/%Y")
        }
    }


def exportar_json_metricas():
    """Salva o resumo de métricas GNRE em logs/metricas_gnre.json para consumo externo."""
    metricas = obter_metricas_gnre()
    try:
        os.makedirs(os.path.dirname(JSON_METRICAS_PATH), exist_ok=True)
        with open(JSON_METRICAS_PATH, "w", encoding="utf-8") as f:
            json.dump(metricas, f, ensure_ascii=False, indent=2)
        logging.info(f"      [BD GNRE] Métricas exportadas em {JSON_METRICAS_PATH}")
    except Exception as e:
        logging.error(f"      [ERRO BD GNRE] Falha ao exportar JSON de métricas GNRE: {e}")


if __name__ == "__main__":
    inicializar_banco()
    exportar_json_metricas()
    print("Banco de dados GNRE inicializado com sucesso.")
    print("Métricas GNRE Atuais:", json.dumps(obter_metricas_gnre(), ensure_ascii=False, indent=2))
