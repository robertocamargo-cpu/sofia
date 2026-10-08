#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envia o resumo do espelho de ponto de Outubro de 2026 para o canal Discord da SofIA (#📝╽assistente-administrativo).
"""

import os
import asyncio
import discord
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_BOT_TOKEN")
channel_id = int(os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1541880446600609902"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logado no Discord como {client.user}!")
    channel = client.get_channel(channel_id)
    if not channel:
        print(f"Canal {channel_id} não encontrado!")
        await client.close()
        return

    from ponto_eletronico.resumo_discord import obter_resumo_ponto, gerar_embed_resumo_discord
    
    dados_resumo = obter_resumo_ponto()
    embed = gerar_embed_resumo_discord(dados_resumo)

    # Anexos
    files_to_send = []
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "ponto_consolidado.html")
    if os.path.exists(html_path):
        files_to_send.append(discord.File(html_path, filename="espelho_ponto_consolidado.html"))
        
    img_601 = os.path.join(base_dir, "espelho_matriz_601.png")
    if os.path.exists(img_601):
        files_to_send.append(discord.File(img_601, filename="espelho_ponto_matriz_601.png"))

    img_nevine = os.path.join(base_dir, "espelho_filial_nevine.png")
    if os.path.exists(img_nevine):
        files_to_send.append(discord.File(img_nevine, filename="espelho_ponto_filial_nevine.png"))

    print(f"Enviando para o canal #{channel.name}...")
    await channel.send(embed=embed, files=files_to_send)
    print("✅ Mensagem e arquivos enviados com sucesso para o Discord!")
    await client.close()

if __name__ == "__main__":
    client.run(token)
