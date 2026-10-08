#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline de Sincronização Total do Ponto Eletrônico (Super SofIA):
1. Detecta em qual rede o computador está conectado (601 ou Nevine).
2. Baixa o AFD do relógio da rede atual sem nenhuma troca prévia.
3. Alterna temporariamente para a outra rede Wi-Fi.
4. Baixa o segundo relógio.
5. Retorna obrigatoriamente para a rede de origem (Failsafe).
6. Consolida as batidas e atualiza o Espelho Interativo HTML.
7. Posta o relatório formatado no Discord (#📝╽assistente-administrativo).
"""

import os
import sys
import time
from ponto_eletronico.wifi_manager import (
    detectar_rede_atual,
    alternar_rede_segura,
    REDES,
    obter_ip_atual
)
from ponto_eletronico.download_afd import download_afd, next_output_filename, DEVICES
from ponto_eletronico.gerar_consolidado import gerar_espelho_ponto_consolidado

def executar_sincronizacao_completa(enviar_discord: bool = True):
    print("=" * 65)
    print("🤖 SINCRONIZAÇÃO COMPLETA DE PONTO ELETRÔNICO - SUPER SOFIA")
    print("=" * 65)

    info_inicial = detectar_rede_atual()
    chave_atual = info_inicial["chave"]
    
    if chave_atual not in ("601", "NEVINE"):
        print(f"❌ [ERRO] O computador não está em nenhuma das redes cadastradas (IP atual: {info_inicial['ip_local']}).")
        print(f"Por favor, conecte-se ao Wi-Fi '{REDES['601']['ssid']}' ou '{REDES['NEVINE']['ssid']}'.")
        return False

    outra_chave = info_inicial["outra_chave"]
    print(f"📍 [REDE ATUAL] {info_inicial['nome']} (SSID: {info_inicial['ssid']}) | IP: {info_inicial['ip_local']}")
    print(f"🎯 [PLANO DE AÇÃO]:")
    print(f"   1. Baixar relógio local: {info_inicial['nome']} ({info_inicial['ip_relogio']})")
    print(f"   2. Alternar para rede: {REDES[outra_chave]['nome']} ({REDES[outra_chave]['ssid']})")
    print(f"   3. Baixar relógio remoto: ({REDES[outra_chave]['ip_relogio']})")
    print(f"   4. Retornar automaticamente para: {info_inicial['ssid']}")
    print("-" * 65)

    resultados = {}

    # ETAPA 1: Baixar o relógio da rede onde já estamos
    print(f"\n📥 [PASSO 1/3] Extraindo dados do relógio local ({info_inicial['nome']})...")
    dev1_key = chave_atual.lower()
    dev1 = DEVICES[dev1_key]
    out1 = next_output_filename(dev1["serial"])
    res1 = download_afd(dev1["ip"], None, None, out1)
    resultados[chave_atual] = res1
    print(f"Status {info_inicial['nome']}: {'✅ Sucesso' if res1 else '❌ Falha'}")

    # ETAPA 2: Alternar para a outra rede e baixar o segundo relógio
    print(f"\n🔄 [PASSO 2/3] Alternando para a rede {REDES[outra_chave]['nome']}...")
    with alternar_rede_segura(outra_chave) as conectou:
        if conectou:
            print(f"📥 Extraindo dados do segundo relógio ({REDES[outra_chave]['nome']})...")
            dev2_key = outra_chave.lower()
            dev2 = DEVICES[dev2_key]
            out2 = next_output_filename(dev2["serial"])
            res2 = download_afd(dev2["ip"], None, None, out2)
            resultados[outra_chave] = res2
            print(f"Status {REDES[outra_chave]['nome']}: {'✅ Sucesso' if res2 else '❌ Falha'}")
        else:
            print(f"❌ Não foi possível obter conexão na rede {REDES[outra_chave]['ssid']}.")
            resultados[outra_chave] = False

    # ETAPA 3: O context manager já garantiu o retorno para a rede inicial!
    ip_final = obter_ip_atual()
    print(f"\n🏁 [PASSO 3/3] Rede restabelecida na origem: IP {ip_final}")

    # ETAPA 4: Consolidar os dados
    print("\n📊 Consolidando marcações e calculando jornadas CLT...")
    caminho_html = gerar_espelho_ponto_consolidado()

    # ETAPA 5: Notificar no Discord se solicitado
    if enviar_discord:
        print("📢 Publicando resumo formatado no canal Discord...")
        try:
            from ponto_eletronico.enviar_resumo_discord import client, token
            # Executa o envio
            cmd_envio = [sys.executable, os.path.join(os.path.dirname(__file__), "enviar_resumo_discord.py")]
            import subprocess
            subprocess.run(cmd_envio, check=True)
            print("✅ Notificação enviada para o canal #📝╽assistente-administrativo!")
        except Exception as ex:
            print(f"⚠️ Erro ao enviar Discord: {ex}")

    print("=" * 65)
    print("🎉 FLUXO TOTAL CONCLUÍDO COM SUCESSO!")
    print("=" * 65)
    return True

if __name__ == "__main__":
    executar_sincronizacao_completa()
