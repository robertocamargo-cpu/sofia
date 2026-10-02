import http.server
import socketserver
import json
import os
import sys
import database

import importlib.util

gnre_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gnre_emissao", "database.py")
if not os.path.exists(gnre_db_path):
    gnre_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gnre", "database.py")
if os.path.exists(gnre_db_path):
    spec = importlib.util.spec_from_file_location("database_gnre", gnre_db_path)
    database_gnre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(database_gnre)
else:
    database_gnre = None

PORT = 8080


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Apenas NFe
        if self.path in ["/nfe/metricas", "/nfe"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            metricas_nfe = database.obter_metricas()
            body = json.dumps(metricas_nfe, ensure_ascii=False, indent=2).encode("utf-8")
            self.wfile.write(body)
            return

        # Apenas Boletos
        if self.path in ["/boletos/metricas", "/boletos", "/boleto"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            m_nfe = database.obter_metricas()
            metricas_boletos = {
                "atualizado_em": m_nfe.get("atualizado_em"),
                "hoje": { "boletos": m_nfe["hoje"]["boletos"], "data": m_nfe["hoje"]["data"] },
                "ontem": { "boletos": m_nfe["ontem"]["boletos"], "data": m_nfe["ontem"]["data"] },
                "sexta_passada": { "boletos": m_nfe.get("sexta_passada", {}).get("boletos", 0), "data": m_nfe.get("sexta_passada", {}).get("data", "") },
                "este_mes": { "boletos": m_nfe["este_mes"]["boletos"], "mes": m_nfe["este_mes"]["mes"] },
                "mes_passado": { "boletos": m_nfe["mes_passado"]["boletos"], "mes": m_nfe["mes_passado"]["mes"] }
            }
            body = json.dumps(metricas_boletos, ensure_ascii=False, indent=2).encode("utf-8")
            self.wfile.write(body)
            return

        # Apenas GNRE
        if self.path in ["/gnre/metricas", "/gnre"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            metricas_gnre = database_gnre.obter_metricas_gnre() if (database_gnre and hasattr(database_gnre, 'obter_metricas_gnre')) else {}
            body = json.dumps(metricas_gnre, ensure_ascii=False, indent=2).encode("utf-8")
            self.wfile.write(body)
            return

        # Consolidado (NFe + Boletos + GNRE juntos)
        if self.path in ["/metricas", "/api/metricas", "/"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                m_nfe = database.obter_metricas()
                m_gnre = database_gnre.obter_metricas_gnre() if (database_gnre and hasattr(database_gnre, 'obter_metricas_gnre')) else {}
                resultado = {
                    "atualizado_em": m_nfe.get("atualizado_em"),
                    "nfe": m_nfe,
                    "boletos": {
                        "hoje": { "boletos": m_nfe["hoje"]["boletos"], "data": m_nfe["hoje"]["data"] },
                        "ontem": { "boletos": m_nfe["ontem"]["boletos"], "data": m_nfe["ontem"]["data"] },
                        "sexta_passada": { "boletos": m_nfe.get("sexta_passada", {}).get("boletos", 0), "data": m_nfe.get("sexta_passada", {}).get("data", "") },
                        "este_mes": { "boletos": m_nfe["este_mes"]["boletos"], "mes": m_nfe["este_mes"]["mes"] },
                        "mes_passado": { "boletos": m_nfe["mes_passado"]["boletos"], "mes": m_nfe["mes_passado"]["mes"] }
                    },
                    "gnre": m_gnre
                }
                body = json.dumps(resultado, ensure_ascii=False, indent=2).encode("utf-8")
                self.wfile.write(body)
            except Exception as e:
                err_body = json.dumps({"erro": str(e)}).encode("utf-8")
                self.wfile.write(err_body)
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"erro": "Endpoint nao encontrado. Use /metricas, /nfe/metricas, /boletos/metricas ou /gnre/metricas"}')

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
        print(f"[API] Servidor de Métricas rodando em http://localhost:{porta}/metricas")
        httpd.serve_forever()


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    iniciar_servidor(porta)
