#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de validação e teste prático da Opção A:
Troca autônoma de rede Wi-Fi (Matriz 601 <-> Filial Nevine).
"""

import sys
import time
import urllib.request
from ponto_eletronico.wifi_manager import (
    obter_ip_atual,
    testar_ping,
    alternar_para_filial_temporariamente,
    WIFI_MATRIZ_SSID,
    WIFI_FILIAL_SSID
)

def testar_http_rep(ip: str, timeout_seg: int = 4) -> bool:
    try:
        url = f"http://{ip}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout_seg) as resp:
            return resp.status in (200, 302, 401)
    except Exception:
        return False

def executar_teste():
    print("=" * 60)
    print("🚀 INICIANDO TESTE DA OPÇÃO A: TROCA AUTÔNOMA DE WI-FI")
    print("=" * 60)

    relatorio = []

    # 1. Ponto de Partida (Matriz)
    ip_inicio = obter_ip_atual()
    print(f"\n[1/3] Estado Inicial:")
    print(f"      • IP Atual: {ip_inicio}")
    
    ping_601 = testar_ping("192.168.15.36")
    http_601 = testar_http_rep("192.168.15.36")
    print(f"      • Ping REP 601 (192.168.15.36): {'✅ OK' if ping_601 else '❌ Falha'}")
    print(f"      • HTTP REP 601 (192.168.15.36): {'✅ OK' if http_601 else '❌ Falha'}")
    relatorio.append(("Matriz Inicial", ip_inicio, ping_601, http_601))

    # 2. Transição para a Filial
    print(f"\n[2/3] Alternando para a Filial '{WIFI_FILIAL_SSID}'...")
    t0 = time.time()
    
    with alternar_para_filial_temporariamente() as conectou:
        t_mudanca = time.time() - t0
        ip_filial = obter_ip_atual()
        print(f"      • IP Obtido na Filial: {ip_filial} (em {t_mudanca:.1f}s)")
        
        # Testar REP Nevine
        ping_nevine = testar_ping("192.168.1.35")
        http_nevine = testar_http_rep("192.168.1.35")
        print(f"      • Ping REP Nevine (192.168.1.35): {'✅ OK' if ping_nevine else '❌ Falha'}")
        print(f"      • HTTP REP Nevine (192.168.1.35): {'✅ OK' if http_nevine else '❌ Falha'}")
        relatorio.append(("Filial Nevine", ip_filial, ping_nevine, http_nevine))
        
        print("      • Teste na filial concluído! Liberando para retorno...")

    # 3. Retorno para a Matriz
    ip_final = obter_ip_atual()
    ping_601_pos = testar_ping("192.168.15.36")
    http_601_pos = testar_http_rep("192.168.15.36")
    ping_internet = testar_ping("8.8.8.8")
    
    print(f"\n[3/3] Estado Final (Pós-Retorno):")
    print(f"      • IP Atual: {ip_final}")
    print(f"      • Ping REP 601 (192.168.15.36): {'✅ OK' if ping_601_pos else '❌ Falha'}")
    print(f"      • HTTP REP 601 (192.168.15.36): {'✅ OK' if http_601_pos else '❌ Falha'}")
    print(f"      • Conexão Internet (8.8.8.8): {'✅ OK' if ping_internet else '❌ Falha'}")
    relatorio.append(("Matriz Retorno", ip_final, ping_601_pos, http_601_pos))

    print("\n" + "=" * 60)
    print("📋 RESUMO FINAL DO TESTE DE TROCA AUTOMÁTICA")
    print("=" * 60)
    print(f"{'Etapa':<16} | {'IP Obtido':<15} | {'Ping REP':<10} | {'HTTP REP':<10}")
    print("-" * 60)
    for etapa, ip, p, h in relatorio:
        p_str = "✅ OK" if p else "❌ FALHA"
        h_str = "✅ OK" if h else "❌ FALHA"
        print(f"{etapa:<16} | {ip:<15} | {p_str:<10} | {h_str:<10}")
    print("=" * 60)

    sucesso_total = all(r[2] for r in relatorio) and (ip_final.startswith("192.168.15"))
    if sucesso_total:
        print("🎉 TESTE 100% BEM-SUCEDIDO! A OPÇÃO A ESTÁ PRONTA E OPERACIONAL!")
    else:
        print("⚠️ O teste completou, mas alguns pontos necessitam de atenção.")
    print("=" * 60)

if __name__ == "__main__":
    executar_teste()
