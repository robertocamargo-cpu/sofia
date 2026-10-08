#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor Interativo de Ponto Eletrônico (REP Henry 601 + Nevine)
Orquestra o fluxo de coleta entre redes Wi-Fi diferentes com solicitação de troca e confirmação OK.
"""

import os
import sys
import time
import socket
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from download_afd import download_afd, DEVICES, next_output_filename
from gerar_consolidado import gerar_espelho_ponto_consolidado

def testar_conexao(ip, porta=80, timeout=2.5) -> bool:
    """Verifica se o IP e porta do relógio estão acessíveis na rede atual."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, porta))
        s.close()
        return True
    except Exception:
        return False

def obter_credenciais(device_key: str):
    dev = DEVICES[device_key]
    user = os.environ.get(dev["user_env"]) or "teste fabrica"
    pwd = os.environ.get(dev["pass_env"]) or "111111"
    return user, pwd

def coletar_relogio(device_key: str) -> bool:
    dev = DEVICES[device_key]
    user, pwd = obter_credenciais(device_key)
    output_file = next_output_filename(dev["serial"])
    print(f"\n📡 Conectando ao relógio {device_key.upper()} ({dev['ip']})...")
    sucesso = download_afd(dev["ip"], user, pwd, output_file)
    if sucesso:
        print(f"✅ Coleta do relógio {device_key.upper()} concluída: {os.path.basename(output_file)}")
    else:
        print(f"❌ Falha ao descarregar AFD do relógio {device_key.upper()}.")
    return sucesso

def fluxo_completo_ponto():
    print("=" * 65)
    print("⏱️  FLUXO INTERATIVO DE COLETA DE PONTO ELETRÔNICO (REP HENRY)")
    print("=" * 65)

    relogio_1 = "601"
    relogio_2 = "nevine"

    # 1. Identificar qual rede está ativa no momento
    ip_1 = DEVICES[relogio_1]["ip"]
    ip_2 = DEVICES[relogio_2]["ip"]

    rede_1_ok = testar_conexao(ip_1)
    rede_2_ok = testar_conexao(ip_2)

    primeiro = None
    segundo = None

    if rede_1_ok:
        primeiro, segundo = relogio_1, relogio_2
    elif rede_2_ok:
        primeiro, segundo = relogio_2, relogio_1
    else:
        print(f"\n⚠️  Nenhum dos relógios ({ip_1} ou {ip_2}) respondeu na rede atual.")
        print(f"👉 Conecte o computador na rede Wi-Fi da Matriz (601) ou da Filial (Nevine).")
        input("\nPressione [ENTER] após conectar para tentar novamente...")
        if testar_conexao(ip_1):
            primeiro, segundo = relogio_1, relogio_2
        elif testar_conexao(ip_2):
            primeiro, segundo = relogio_2, relogio_1
        else:
            print("❌ Não foi possível alcançar nenhum dos relógios. Abortando.")
            return False

    # 2. Coletar do primeiro relógio acessível
    print(f"\n[ETAPA 1/2] Relógio detectado na rede atual: {primeiro.upper()} ({DEVICES[primeiro]['ip']})")
    coletou_1 = coletar_relogio(primeiro)

    # 3. Solicitar troca de rede para o segundo relógio
    dev_segundo = DEVICES[segundo]
    print("\n" + "=" * 65)
    print(f"🔄 TROCA DE REDE NECESSÁRIA")
    print("=" * 65)
    print(f"O primeiro relógio ({primeiro.upper()}) foi processado.")
    print(f"👉 Por favor, MUDE DE REDE no Wi-Fi deste computador para a rede do relógio {segundo.upper()}.")
    print(f"   (IP de destino: {dev_segundo['ip']})")
    print("=" * 65)

    while True:
        resp = input(f"\nDigite 'OK' (ou pressione ENTER) após conectar na rede do relógio {segundo.upper()}: ").strip()
        print(f"🔍 Verificando conectividade com {dev_segundo['ip']}...")
        if testar_conexao(dev_segundo["ip"]):
            print(f"📶 Conexão estabelecida com sucesso com o relógio {segundo.upper()}!")
            break
        else:
            print(f"⚠️  Ainda não foi possível alcançar o IP {dev_segundo['ip']}.")
            print("   Verifique se o Wi-Fi já conectou na rede correta.")
            tentar_novamente = input("   Deseja tentar novamente? (S/n): ").strip().lower()
            if tentar_novamente == 'n':
                print(f"⚠️  Seguindo apenas com os dados coletados do relógio {primeiro.upper()}...")
                break

    # 4. Coletar do segundo relógio (se acessível)
    if testar_conexao(dev_segundo["ip"]):
        print(f"\n[ETAPA 2/2] Coletando relógio {segundo.upper()} ({dev_segundo['ip']})...")
        coletar_relogio(segundo)

    # 5. Consolidar e Gerar Espelho HTML
    print("\n" + "=" * 65)
    print("📊 GERANDO ESPELHO DE PONTO CONSOLIDADO...")
    print("=" * 65)
    
    hoje = date.today()
    # Padrão: Mês atual (ex: 01/10/2026 até hoje)
    d_ini = date(hoje.year, hoje.month, 1)
    d_fim = hoje

    caminho_html = gerar_espelho_ponto_consolidado(d_ini=d_ini, d_fim=d_fim)
    print(f"\n🎉 Processo concluído com sucesso!")
    print(f"📄 Espelho de ponto disponível em: {caminho_html}")
    
    # Abre no navegador no macOS
    try:
        os.system(f'open "{caminho_html}"')
    except Exception:
        pass
        
    return True

if __name__ == "__main__":
    fluxo_completo_ponto()
