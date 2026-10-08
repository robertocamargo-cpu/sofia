#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download de AFD para REP Henry Hexa via Playwright
Conecta na interface web Atenas, autentica e descarrega o arquivo fiscal AFD oficial (Portaria 671/1510).
"""

import sys
import time
import socket
import argparse
import os
import asyncio
from playwright.async_api import async_playwright

DEVICES = {
    "601": {
        "ip": "192.168.15.36",
        "serial": "00004004330216717",
        "user_env": "REP_601_USER",
        "pass_env": "REP_601_PASS",
    },
    "nevine": {
        "ip": "192.168.1.35",
        "serial": "00004004330212445",
        "user_env": "REP_NEVINE_USER",
        "pass_env": "REP_NEVINE_PASS",
    },
}

DEFAULT_CREDENTIALS = [
    ("teste fabrica", "222222"),
    ("teste fabrica", "111111"),
    ("rep", "123456"),
]

def testar_conexao(ip, port=80, timeout=2.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False

async def _download_afd_playwright(ip: str, users_and_passwords: list, output_filename: str) -> bool:
    print(f"[{ip}] Iniciando comunicação com o relógio REP Henry...")
    if not testar_conexao(ip, 80):
        print(f"[{ip}] Erro: IP inacessível nesta rede (timeout de conexão).")
        return False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        logado = False
        for usuario, senha in users_and_passwords:
            print(f"[{ip}] Tentando autenticação como '{usuario}'...")
            try:
                await page.goto(f"http://{ip}", timeout=10000)
                await page.wait_for_timeout(1500)
                await page.fill("#lblLogin", usuario)
                await page.fill("#lblPass", senha)
                await page.evaluate("login()")
                await page.wait_for_timeout(3500)

                body_text = await page.inner_text("body")
                if "Senha inválida" in body_text or "Requisição inválida" in body_text:
                    print(f"[{ip}] Credenciais recusadas para '{usuario}'.")
                    continue
                if "Bem-vindo" in body_text or "Principal" in body_text:
                    print(f"[{ip}] ✅ Login efetuado com sucesso como '{usuario}'!")
                    logado = True
                    break
            except Exception as e:
                print(f"[{ip}] Erro durante tentativa de login: {e}")

        if not logado:
            print(f"[{ip}] ❌ Nenhuma das credenciais foi aceita pelo relógio.")
            await browser.close()
            return False

        print(f"[{ip}] Acessando módulo de eventos do relógio...")
        try:
            await page.evaluate("submitMainForm(4, 32, 0)")
            await page.wait_for_timeout(3000)

            print(f"[{ip}] Solicitando compilação e download do AFD completo...")
            async with page.expect_download(timeout=90000) as download_info:
                await page.evaluate("downloadData(1, 32, 0)")

            download = await download_info.value
            await download.save_as(output_filename)
            
            # Validação do arquivo
            tamanho = os.path.getsize(output_filename)
            if tamanho > 10000:
                print(f"[{ip}] ✅ SUCESSO: AFD salvo em '{output_filename}' ({tamanho:,} bytes).")
                await browser.close()
                return True
            else:
                print(f"[{ip}] ⚠️ Arquivo baixado parece incompleto ({tamanho} bytes).")
                await browser.close()
                return False
        except Exception as e:
            print(f"[{ip}] ❌ Erro durante o download do AFD: {e}")
            await browser.close()
            return False

def download_afd(ip, username=None, password=None, output_filename=None):
    creds = []
    if username and password:
        creds.append((username, password))
    for c in DEFAULT_CREDENTIALS:
        if c not in creds:
            creds.append(c)

    return asyncio.run(_download_afd_playwright(ip, creds, output_filename))

def next_output_filename(serial):
    import glob
    import re

    base_dir = os.path.dirname(os.path.abspath(__file__))
    highest = 0
    for filename in glob.glob(os.path.join(base_dir, f"{serial}*.txt")):
        match = re.search(r"\((\d+)\)\.txt$", filename)
        if match:
            highest = max(highest, int(match.group(1)))
        elif filename.endswith(f"{serial}.txt"):
            highest = max(highest, 0)
    return os.path.join(base_dir, f"{serial} ({highest + 1}).txt")

def main():
    parser = argparse.ArgumentParser(description="Baixa AFD de um REP Henry via interface web oficial.")
    parser.add_argument("device", choices=DEVICES.keys(), help="Dispositivo a baixar (601 ou nevine).")
    parser.add_argument("--username", help="Usuario do REP.")
    parser.add_argument("--password", help="Senha do REP.")
    parser.add_argument("--output", help="Arquivo de saida.")
    args = parser.parse_args()

    dev = DEVICES[args.device]
    username = args.username or os.environ.get(dev["user_env"])
    password = args.password or os.environ.get(dev["pass_env"])
    output = args.output or next_output_filename(dev["serial"])

    return 0 if download_afd(dev["ip"], username, password, output) else 1

if __name__ == '__main__':
    raise SystemExit(main())
