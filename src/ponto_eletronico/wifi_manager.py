#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciador Inteligente de Redes Wi-Fi dos Relógios REP Henry.
Detecta dinamicamente em qual rede o computador está conectado,
permite alternância segura e garante o retorno à rede de origem.
"""

import os
import time
import subprocess
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# Configurações das Redes
REDES = {
    "601": {
        "nome": "Matriz (REP 601)",
        "ssid": os.getenv("WIFI_601_SSID", "N3V2N3"),
        "senha": os.getenv("WIFI_601_PASS", "429N551@601"),
        "faixa": "192.168.15.",
        "ip_relogio": "192.168.15.36",
    },
    "NEVINE": {
        "nome": "Filial (REP Nevine)",
        "ssid": os.getenv("WIFI_NEVINE_SSID", "TIM ULTRAFIBRA_22E6"),
        "senha": os.getenv("WIFI_NEVINE_PASS", "h5n86u4r873ug6kj"),
        "faixa": "192.168.1.",
        "ip_relogio": "192.168.1.35",
    }
}

WIFI_INTERFACE = "en0"

def obter_ip_atual(interface: str = WIFI_INTERFACE) -> str:
    """Retorna o IPv4 da interface Wi-Fi."""
    try:
        res = subprocess.run(["ipconfig", "getifaddr", interface], capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception:
        return ""

def testar_ping(ip: str, timeout_ms: int = 1500) -> bool:
    """Testa se um IP responde ao ping."""
    try:
        res = subprocess.run(["ping", "-c", "1", "-W", str(timeout_ms), ip], capture_output=True, text=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False

def detectar_rede_atual() -> dict:
    """
    Identifica dinamicamente em qual das duas redes o computador está conectado:
    - Se o IP for 192.168.15.x: Retorna dados da rede '601' (N3V2N3).
    - Se o IP for 192.168.1.x: Retorna dados da rede 'NEVINE' (TIM ULTRAFIBRA_22E6).
    """
    ip = obter_ip_atual()
    for chave, r in REDES.items():
        if ip.startswith(r["faixa"]):
            ping_ok = testar_ping(r["ip_relogio"])
            return {
                "chave": chave,
                "nome": r["nome"],
                "ssid": r["ssid"],
                "ip_local": ip,
                "ip_relogio": r["ip_relogio"],
                "relogio_online": ping_ok,
                "outra_chave": "NEVINE" if chave == "601" else "601"
            }
    
    return {
        "chave": "DESCONHECIDA",
        "nome": "Rede Externa / Desconhecida",
        "ssid": "Desconhecido",
        "ip_local": ip,
        "ip_relogio": None,
        "relogio_online": False,
        "outra_chave": "601"
    }

def conectar_rede(chave_alvo: str, timeout_segundos: int = 25) -> bool:
    """
    Alterna o Wi-Fi para a rede especificada ('601' ou 'NEVINE')
    e aguarda a concessão de IP na faixa correta via DHCP.
    """
    if chave_alvo not in REDES:
        print(f"❌ [WIFI] Rede alvo '{chave_alvo}' inválida.")
        return False

    alvo = REDES[chave_alvo]
    ip_antigo = obter_ip_atual()
    print(f"📡 [WIFI] Solicitando conexão com '{alvo['ssid']}' (alvo: {alvo['nome']})...")

    try:
        cmd = ["networksetup", "-setairportnetwork", WIFI_INTERFACE, alvo["ssid"], alvo["senha"]]
        subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f"❌ [WIFI] Erro ao executar networksetup: {e}")
        return False

    # Aguardar o DHCP renovar para a faixa esperada
    inicio = time.time()
    time.sleep(3)  # Pausa para o rádio desconectar e reconectar
    
    while time.time() - inicio < timeout_segundos:
        ip = obter_ip_atual()
        if ip and ip.startswith(alvo["faixa"]):
            ping_ok = testar_ping(alvo["ip_relogio"])
            print(f"✅ [WIFI] Conectado com sucesso em '{alvo['ssid']}'! IP: {ip} | Relógio ({alvo['ip_relogio']}): {'Online ✅' if ping_ok else 'Sem resposta ⚠️'}")
            return True
        time.sleep(1.5)

    ip_final = obter_ip_atual()
    print(f"⚠️ [WIFI] Timeout ao aguardar faixa '{alvo['faixa']}'. IP atual: {ip_final}")
    return bool(ip_final.startswith(alvo["faixa"]))

@contextmanager
def alternar_rede_segura(chave_destino: str):
    """
    Context manager seguro:
    1. Grava a rede de origem onde o usuário estava.
    2. Alterna para a rede de destino.
    3. Executa o bloco de código.
    4. NO FINAL (FINALLY), SEMPRE retorna para a rede de origem!
    """
    info_origem = detectar_rede_atual()
    chave_origem = info_origem["chave"]
    print(f"\n🔄 [WIFI SEGURO] Origem detectada: {info_origem['nome']} ({info_origem['ssid']}) | IP: {info_origem['ip_local']}")
    
    if chave_origem == chave_destino:
        print(f"ℹ️ [WIFI SEGURO] Já estamos na rede '{chave_destino}'. Nenhuma troca necessária.")
        yield True
        return

    sucesso = conectar_rede(chave_destino)
    try:
        yield sucesso
    finally:
        if chave_origem in REDES:
            print(f"\n🔙 [WIFI SEGURO] Retornando obrigatoriamente para a rede de origem '{REDES[chave_origem]['ssid']}'...")
            conectar_rede(chave_origem)
            print(f"✅ [WIFI SEGURO] Rede de origem restaurada! IP atual: {obter_ip_atual()}")

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 DIAGNÓSTICO DE REDE WI-FI - SUPER SOFIA")
    print("=" * 60)
    info = detectar_rede_atual()
    print(f"• Rede Detectada: {info['nome']}")
    print(f"• SSID Conectado: {info['ssid']}")
    print(f"• IP Local: {info['ip_local']}")
    print(f"• IP Relógio Local: {info['ip_relogio']}")
    print(f"• Relógio Online: {'SIM ✅' if info['relogio_online'] else 'NÃO ❌'}")
    print(f"• Próxima Rede a Puxar: {info['outra_chave']} ({REDES.get(info['outra_chave'], {}).get('ssid')})")
    print("=" * 60)
