"""
====================================================================
  SOFIA - Assistente de Automação de Contas a Pagar (Discord Bot)
====================================================================
Este bot recebe comandos no Discord (ex: "@sofia lance este pagamento"
com o PDF em anexo), realiza o fluxo completo no ERP ADMSIS e devolve
o PDF da Autorização de Pagamento diretamente no chat.

Como rodar:
  1. Configure no seu .env:
     DISCORD_BOT_TOKEN=seu_token_aqui
  2. Execute:
     python sofia_bot.py
"""
import os
import sys
import asyncio
import tempfile
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import discord
from discord.ext import commands
from sofia_core import processar_documento

from contextlib import asynccontextmanager

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

INBOX_DIR = os.path.join(os.path.dirname(__file__), "inbox")
os.makedirs(INBOX_DIR, exist_ok=True)

# Lock de concorrência global para serializar o acesso de múltiplos usuários ao ERP ADMSIS
erp_lock = asyncio.Lock()

@asynccontextmanager
async def gerenciar_sessao_erp(message: discord.Message, descricao: str):
    """
    Controla o acesso concorrente ao ERP ADMSIS. Se o ERP estiver ocupado,
    envia mensagem amigável avisando que a requisição está na fila e a processa
    assim que a sessão for liberada.
    """
    aviso_fila = None
    if erp_lock.locked():
        aviso_fila = await message.reply(
            f"⏳ **Fila de Execução ERP:** O sistema ADMSIS está sendo utilizado em outra operação no momento.\n"
            f"Sua solicitação (**{descricao}**) foi enfileirada e começará automaticamente assim que liberar!"
        )
    await erp_lock.acquire()
    if aviso_fila:
        try:
            await aviso_fila.delete()
        except Exception:
            pass
    try:
        yield
    finally:
        erp_lock.release()

def formatar_tabela_historico(lotes: list) -> str:
    if not lotes:
        return "Nenhum histórico de lotes registrado até o momento."
    
    linhas = [
        "```text",
        f"{'Tipo':<14} | {'Comp.':<10} | {'Fil.':<6} | {'Sucesso':<8} | {'Valor (R$)':>12}",
        "-" * 60
    ]
    for l in lotes:
        tipo = str(l.get("tipo", "N/D"))[:14]
        comp = str(l.get("competencia", "N/D"))[:10]
        fil = str(l.get("filial", "N/D"))[:6]
        sucessos = f"{l.get('total_sucesso', 0)}/{l.get('total_colaboradores', 0)}"
        val = l.get("valor_total_lancado", 0.0)
        val_str = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        linhas.append(f"{tipo:<14} | {comp:<10} | {fil:<6} | {sucessos:<8} | {val_str:>12}")
    linhas.append("```")
    return "\n".join(linhas)

def formatar_valor_br(val: float) -> str:
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_tabela_colaboradores(colaboradores: list) -> str:
    if not colaboradores:
        return "Nenhum colaborador registrado."
    
    linhas = [
        "```text",
        f"{'#':<3} | {'Colaborador':<30} | {'Valor (R$)':>12} | {'Filial':<6}",
        "-" * 58
    ]
    for i, c in enumerate(colaboradores, 1):
        nome = c.get("fornecedor") or c.get("nome", "N/D")
        nome_curto = (nome[:28] + "..") if len(nome) > 30 else nome
        val = c.get("valor", 0.0)
        fil = str(c.get("filial", "")).upper()
        val_str = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        linhas.append(f"{i:<3} | {nome_curto:<30} | {val_str:>12} | {fil:<6}")
    linhas.append("-" * 58)
    tot = sum(c.get("valor", 0.0) for c in colaboradores)
    tot_str = f"{tot:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    linhas.append(f"TOTAL: {len(colaboradores)} colaborador(es) | R$ {tot_str}")
    linhas.append("```")
    return "\n".join(linhas)

def formatar_tabela_individual(entry: dict) -> str:
    forn = entry.get("fornecedor", "N/D")
    val = entry.get("valor", 0.0)
    val_str = formatar_valor_br(val)
    venc = entry.get("vencimento")
    venc_str = venc.strftime("%d/%m/%Y") if hasattr(venc, "strftime") else str(venc)
    filial = entry.get("filial", "429")
    ref = entry.get("referencia", "N/D")
    tipo = entry.get("tipo", "TITULO")
    
    linhas = [
        "```text",
        f"{'Campo':<16} | {'Dado Lançado no ERP'}",
        "-" * 52,
        f"{'Favorecido':<16} | {forn}",
        f"{'Valor':<16} | {val_str}",
        f"{'Vencimento':<16} | {venc_str}",
        f"{'Filial':<16} | {filial}",
        f"{'Referência':<16} | {ref}",
        f"{'Tipo':<16} | {tipo}",
        f"{'Situação':<16} | Gravado no ERP com Sucesso ✅",
        "```"
    ]

# ── AGENDADOR AUTOMÁTICO DE TAREFAS (CRON INTELIGENTE) ──────────────────────
async def executar_tarefa_agendada(nome: str, coro_func):
    """Executa uma rotina automática serializada pelo erp_lock."""
    async with erp_lock:
        print(f"\n[CRON] 🚀 Iniciando execução automática: {nome}...")
        try:
            await coro_func()
            print(f"[CRON] ✅ Concluído com sucesso: {nome}!\n")
        except Exception as e:
            print(f"[CRON] ❌ Erro ao executar {nome}: {e}\n")

async def _rodar_nfe_cron():
    from gerar_nfe_automatica import main as nfe_main
    await nfe_main()

async def _rodar_gnre_cron():
    from gnre_emissao.gnre_pipeline import executar_pipeline
    await asyncio.to_thread(executar_pipeline)

async def _rodar_previsao_cron():
    from automacao_previsao import executar_previsao
    await executar_previsao()

# Armazena estado dos agendamentos para consulta no Discord
agendamentos_status = {
    "ativo": True,
    "ultima_execucao": {},
    "proxima_execucao": "Calculando..."
}

async def agendador_sofia():
    """
    Loop assíncrono em segundo plano que monitora o relógio e dispara
    as rotinas agendadas (NF-e, GNRE, Previsão) respeitando o erp_lock.
    """
    await bot.wait_until_ready()
    print("[AGENDADOR] ⏰ Agendador de tarefas em segundo plano ATIVO e operacional!")

    ultimas_execucoes = {}

    while not bot.is_closed():
        try:
            agora = datetime.now()
            dia_semana = agora.weekday() # 0 = Segunda, 4 = Sexta
            hh_mm = (agora.hour, agora.minute)
            chave_minuto = (agora.date(), agora.hour, agora.minute)

            # Executa apenas nos dias úteis (Segunda a Sexta)
            if dia_semana in range(5):
                # 1. NF-e Horária (07:50, 08:50, 09:50, 10:50, 11:50, 12:50, 13:50, 14:50, 15:50, 16:50, 17:50)
                horarios_nfe = [
                    (7, 50), (8, 50), (9, 50), (10, 50), (11, 50),
                    (12, 50), (13, 50), (14, 50), (15, 50), (16, 50), (17, 50)
                ]
                if hh_mm in horarios_nfe and ultimas_execucoes.get("nfe") != chave_minuto:
                    ultimas_execucoes["nfe"] = chave_minuto
                    agendamentos_status["ultima_execucao"]["nfe"] = agora.strftime("%d/%m/%Y %H:%M")
                    asyncio.create_task(executar_tarefa_agendada(f"NF-e / Faturamento ({agora.strftime('%H:%M')})", _rodar_nfe_cron))

                # 2. GNRE (09:00, 11:00, 14:00, 16:00)
                horarios_gnre = [(9, 0), (11, 0), (14, 0), (16, 0)]
                if hh_mm in horarios_gnre and ultimas_execucoes.get("gnre") != chave_minuto:
                    ultimas_execucoes["gnre"] = chave_minuto
                    agendamentos_status["ultima_execucao"]["gnre"] = agora.strftime("%d/%m/%Y %H:%M")
                    asyncio.create_task(executar_tarefa_agendada(f"GNRE Sefaz ({agora.strftime('%H:%M')})", _rodar_gnre_cron))

                # 3. Previsão Financeira (09:30)
                if hh_mm == (9, 30) and ultimas_execucoes.get("previsao") != chave_minuto:
                    ultimas_execucoes["previsao"] = chave_minuto
                    agendamentos_status["ultima_execucao"]["previsao"] = agora.strftime("%d/%m/%Y %H:%M")
                    asyncio.create_task(executar_tarefa_agendada(f"Previsão Financeira ({agora.strftime('%H:%M')})", _rodar_previsao_cron))

        except Exception as ex:
            print(f"[AGENDADOR] Erro no loop de agendamento: {ex}")

        await asyncio.sleep(20)

@bot.event
async def on_ready():
    print(f"\n{'='*60}")
    print(f"  SUPER SOFIA ONLINE! Logado como: {bot.user.name} (ID: {bot.user.id})")
    print(f"  Todas as automações unificadas e prontas no Discord!")
    print(f"{'='*60}\n")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ADMSIS ERP & Financeiro"))

    # Inicia o servidor HTTP de métricas (Porta 8080) em segundo plano se não estiver rodando
    import threading
    def rodar_api_metricas():
        try:
            from api_server import iniciar_servidor
            iniciar_servidor(8080)
        except OSError:
            print("[API] Servidor de métricas na porta 8080 já ativo no sistema.")
        except Exception as ex:
            print(f"[API] Aviso ao iniciar servidor de métricas: {ex}")

    threading.Thread(target=rodar_api_metricas, daemon=True).start()

    # Inicia o agendador de tarefas em segundo plano da SofIA
    asyncio.create_task(agendador_sofia())

@bot.event
async def on_message(message: discord.Message):
    # 1. Ignora IMEDIATAMENTE mensagens do próprio bot e de qualquer outro bot (evita loop infinito)
    if message.author == bot.user or message.author.bot:
        return

    # A Sofia SÓ deve aparecer no canal se for explicitamente chamada:
    # 1. Mencionada (@SofIA)
    # 2. Chamada pelo nome no texto ("sofia", "olá sofia", etc.)
    # 3. Mensagem Direta (DM privada com o bot)
    # 4. Respondendo diretamente a uma mensagem enviada pela Sofia (reply)
    conteudo = message.content.lower()
    mencionado = bot.user in message.mentions
    chamou_por_nome = "sofia" in conteudo
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_reply_to_sofia = bool(
        message.reference 
        and message.reference.resolved 
        and getattr(message.reference.resolved, "author", None) == bot.user
    )

    foi_chamada = mencionado or chamou_por_nome or is_dm or is_reply_to_sofia

    if not foi_chamada:
        return

    # Consulta de Histórico de Lotes Executados
    if "historico" in conteudo or "histórico" in conteudo:
        from batch_logger import consultar_historico_lotes
        lotes = consultar_historico_lotes(limite=8)
        tabela = formatar_tabela_historico(lotes)
        embed_hist = discord.Embed(
            title="📜 Histórico de Lotes Financeiros Processados",
            description=f"Registro dos últimos lançamentos em lote gravados no sistema:\n\n{tabela}",
            color=discord.Color.blue()
        )
        embed_hist.set_footer(text="Automação Contas a Pagar • ADMSIS ERP (data/batch_history.json)")
        await message.reply(embed=embed_hist)
        return

    # Verifica se é comando de Alteração de Título (Individual ou em Lote)
    if any(k in conteudo for k in ["altere", "alterar", "prorrogar", "mudar"]):
        from alteracao_launcher import (
            parse_alteracao_command,
            alterar_titulo_individual,
            alterar_titulos_lote
        )
        dados_alt = parse_alteracao_command(message.content)

        if dados_alt.get("erros"):
            embed_err = discord.Embed(
                title="⚠️ Comando de Alteração Incompleto",
                description="Não foi possível identificar todos os dados necessários:\n" + "\n".join([f"• {e}" for e in dados_alt["erros"]]) + "\n\n*💡 Exemplos de uso:*\n"
                + "> `@SofIA altere o plano de contas do favorecido Eduardo Laurindo para 41038`\n"
                + "> `@SofIA altere a data de vencimento do favorecido Eduardo Laurindo para 01/10/2026`\n"
                + "> `@SofIA altere a data de vencimento de TODOS os favorecidos de HOJE para 01/10/2026`",
                color=discord.Color.gold()
            )
            embed_err.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
            await message.reply(embed=embed_err)
            return

        if dados_alt["modo"] == "lote":
            orig = dados_alt["lote_origem_str"]
            dest = dados_alt["lote_destino_str"]
            async with gerenciar_sessao_erp(message, f"Alteração em Lote ({orig} ➔ {dest})"):
                status_msg = await message.reply(
                    f"🔄 **Alteração em Lote Detectada!**\n"
                    f"📅 Prorrogando vencimento de **TODOS** os títulos pendentes de `{orig}` para `{dest}`...\n"
                    f"Acessando o ERP ADMSIS e aplicando filtros..."
                )
                try:
                    res_lote = await alterar_titulos_lote(
                        data_origem=dados_alt["lote_origem"],
                        data_destino=dados_alt["lote_destino"],
                        filial=dados_alt.get("filial_filtro")
                    )
                    if res_lote["sucesso"]:
                        total_alt = res_lote.get("total_alterados", 0)
                        embed_ok = discord.Embed(
                            title="✅ Alteração em Lote Concluída com Sucesso!",
                            description=f"Foram alterados **{total_alt} título(s)** no ERP ADMSIS.\n\n"
                            f"• **Data de Origem:** `{orig}`\n"
                            f"• **Nova Data de Vencimento:** `{dest}`\n"
                            f"• **Situação:** Pendente",
                            color=discord.Color.green()
                        )
                        embed_ok.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                        await status_msg.edit(content=None, embed=embed_ok)
                    else:
                        embed_fail = discord.Embed(
                            title="❌ Falha na Alteração em Lote",
                            description=res_lote["mensagem"],
                            color=discord.Color.red()
                        )
                        embed_fail.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                        await status_msg.edit(content=None, embed=embed_fail)
                except Exception as ex:
                    await status_msg.edit(content=f"❌ Erro ao processar alteração em lote: `{ex}`")
            return

        else:
            # Modo Individual
            forn = dados_alt["fornecedor"]
            campos = dados_alt["campos"]
            async with gerenciar_sessao_erp(message, f"Alteração ({forn})"):
                status_msg = await message.reply(
                    f"✏️ **Alteração de Título Detectada!**\n"
                    f"👤 Favorecido: **{forn}**\n"
                    f"Acessando o último título pendente no ERP ADMSIS..."
                )
                try:
                    res_ind = await alterar_titulo_individual(
                        fornecedor=forn,
                        campos=campos
                    )
                    if res_ind["sucesso"]:
                        linhas_mods = [
                            f"• **{campo}:** `{detalhe}`"
                            for campo, detalhe in res_ind.get("modificados", {}).items()
                        ]
                        embed_ok = discord.Embed(
                            title="✅ Título Alterado com Sucesso no ERP!",
                            description=f"O título pendente de **{forn}** foi atualizado no ADMSIS.\n\n"
                            f"**📋 Campos Modificados:**\n" + "\n".join(linhas_mods),
                            color=discord.Color.green()
                        )
                        embed_ok.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                        await status_msg.edit(content=None, embed=embed_ok)
                    else:
                        embed_fail = discord.Embed(
                            title="❌ Falha na Alteração do Título",
                            description=res_ind["mensagem"],
                            color=discord.Color.red()
                        )
                        embed_fail.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                        await status_msg.edit(content=None, embed=embed_fail)
                except Exception as ex:
                    await status_msg.edit(content=f"❌ Erro ao processar alteração: `{ex}`")
            return

    # Verifica se e comando de Pagamento Avulso (sem boleto / PIX / transferencia)
    if "avulso" in conteudo:
        from avulso_launcher import parse_avulso_command, lancar_pagamento_avulso
        dados_av = parse_avulso_command(message.content)
        
        # Se faltar referencia ou vencimento ou fornecedor/valor, solicita interativamente no Discord
        if dados_av["campos_faltantes"]:
            faltando = []
            if "fornecedor" in dados_av["campos_faltantes"]:
                faltando.append("• 👤 **Favorecido/Fornecedor:** Informe para quem é o pagamento (ex: `para EDUARDO LAURINDO`)")
            if "valor" in dados_av["campos_faltantes"]:
                faltando.append("• 💰 **Valor:** Informe o valor (ex: `valor 760` ou `760,00`)")
            if "referencia" in dados_av["campos_faltantes"]:
                faltando.append("• 📋 **Referência:** Informe a referência ou nota fiscal (ex: `ref MANUTENÇÃO PREDIAL`)")
            if "vencimento" in dados_av["campos_faltantes"]:
                faltando.append("• ⏰ **Data de Vencimento:** Informe a data de vencimento (ex: `vencimento hoje`, `vencimento amanhã` ou `15/10/2026`)")

            desc = (
                f"Detectei um pedido de **Pagamento Avulso**"
                + (f" para **{dados_av['fornecedor']}**" if dados_av.get('fornecedor') else "")
                + (f" no valor de **{formatar_valor_br(dados_av['valor'])}**" if dados_av.get('valor') else "")
                + f" (Filial **{dados_av.get('filial', '429')}**).\n\n"
                + "**Campos obrigatórios faltantes:**\n"
                + "\n".join(faltando)
                + "\n\n*💡 Dica: Você pode enviar a mensagem completa, por exemplo:*\n"
                + f"> `@SofIA lance o pagamento avulso para {dados_av.get('fornecedor') or 'EDUARDO LAURINDO'}, valor {dados_av.get('valor') or 760}, filial {dados_av.get('filial') or 429}, ref SUA REFERENCIA, vencimento hoje`"
            )
            embed_av_incompleto = discord.Embed(
                title="⚠️ Pagamento Avulso - Dados Incompletos",
                description=desc,
                color=discord.Color.gold()
            )
            embed_av_incompleto.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
            await message.reply(embed=embed_av_incompleto)
            return

        # Todos os dados informados: executa o lançamento no ERP com lock de concorrência
        forn = dados_av["fornecedor"]
        val = dados_av["valor"]
        fil = dados_av["filial"]
        ref = dados_av["referencia"]
        venc = dados_av["vencimento"]
        obs = dados_av.get("observacao")

        async with gerenciar_sessao_erp(message, f"Pagamento Avulso ({forn})"):
            status_msg = await message.reply(
                f"💸 **Comando de Pagamento Avulso detectado!**\n"
                f"👤 Favorecido: **{forn}** | 💰 Valor: **{formatar_valor_br(val)}** | 🏢 Filial: **{fil}**\n"
                f"📋 Ref: `{ref or '(Herdada da cópia + avançar mês)'}` | ⏰ Vencimento: `{venc.strftime('%d/%m/%Y')}`\n"
                f"Localizando último título e duplicando no ERP ADMSIS..."
            )
            
            try:
                res_av = await lancar_pagamento_avulso(
                    fornecedor=forn,
                    valor=val,
                    filial=fil,
                    referencia=ref,
                    vencimento=venc,
                    observacao=obs
                )
                
                if res_av["sucesso"]:
                    tabela_av = [
                        "```text",
                        f"{'Campo':<16} | {'Dado Lançado no ERP'}",
                        "-" * 52,
                        f"{'Favorecido':<16} | {res_av['fornecedor']}",
                        f"{'Valor':<16} | {res_av['valor_str']}",
                        f"{'Vencimento':<16} | {res_av['vencimento']}",
                        f"{'Filial':<16} | {res_av['filial']}",
                        f"{'Referência':<16} | {res_av['referencia']}",
                        f"{'Observação':<16} | {res_av['observacao']}",
                        f"{'Tipo':<16} | Pagamento Avulso (Clonado)",
                        f"{'Situação':<16} | Gravado no ERP com Sucesso ✅",
                        "```"
                    ]
                    embed_av_sucesso = discord.Embed(
                        title="✅ Pagamento Avulso Gravado com Sucesso!",
                        description=f"O último título de **{forn}** foi duplicado e atualizado no ERP ADMSIS.\n\n**📋 Tabela de Dados do Título Lançado:**\n" + "\n".join(tabela_av),
                        color=discord.Color.green()
                    )
                    embed_av_sucesso.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_av_sucesso)
                else:
                    embed_av_err = discord.Embed(
                        title="❌ Falha no Lançamento de Pagamento Avulso",
                        description=res_av["mensagem"],
                        color=discord.Color.red()
                    )
                    embed_av_err.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_av_err)
            except Exception as err:
                await status_msg.edit(content=f"❌ Erro ao processar pagamento avulso: `{err}`")
            return

    # Verifica se e comando de VR (Vale Refeicao)
    if "vr" in conteudo or "vale refeicao" in conteudo or "vale refeição" in conteudo:
        meses_busca = ["janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        mes_encontrado = None
        for m in meses_busca:
            if m in conteudo:
                mes_encontrado = m
                break
                
        if not mes_encontrado:
            # Pega mes atual se nao especificado
            from datetime import datetime
            mes_encontrado = meses_busca[datetime.now().month - 1]

        async with gerenciar_sessao_erp(message, f"Vale Refeição ({mes_encontrado.capitalize()})"):
            status_msg = await message.reply(f"🍽️ **Comando de VR detectado ({mes_encontrado.capitalize()})!**\nConsultando `Planilha VR.xlsx` e iniciando os lançamentos no ERP ADMSIS...")
            try:
                from vr_launcher import processar_vr_lote
                res = await processar_vr_lote(mes_encontrado)
                
                if res["total_sucesso"] == res["total_colaboradores"]:
                    titulo_embed = "✅ Lançamento de VR Concluído com Sucesso!"
                    desc_embed = f"Todos os títulos de Vale Refeição da competência **{res['competencia']}** foram processados no ERP."
                    cor_embed = discord.Color.green()
                elif res["total_sucesso"] > 0:
                    titulo_embed = "⚠️ Lançamento de VR Parcialmente Concluído"
                    desc_embed = f"Foram processados **{res['total_sucesso']}** de **{res['total_colaboradores']}** colaboradores da competência **{res['competencia']}**."
                    cor_embed = discord.Color.orange()
                else:
                    titulo_embed = "❌ Falha no Lançamento de VR"
                    desc_embed = f"Nenhum título de Vale Refeição pôde ser lançado no ERP para a competência **{res['competencia']}**."
                    cor_embed = discord.Color.red()

                tabela_colabs = formatar_tabela_colaboradores(res.get("sucessos", []))
                desc_embed_completa = f"{desc_embed}\n\n**📋 Tabela de Colaboradores Lançados:**\n{tabela_colabs}"
                embed_vr = discord.Embed(
                    title=titulo_embed,
                    description=desc_embed_completa,
                    color=cor_embed
                )
                embed_vr.add_field(name="📅 Competência", value=f"`{res['competencia']}`", inline=True)
                embed_vr.add_field(name="⏰ Vencimento", value=f"`{res['vencimento']}`", inline=True)
                embed_vr.add_field(name="👥 Total Colaboradores", value=f"**{res['total_sucesso']} / {res['total_colaboradores']}**", inline=True)
                embed_vr.add_field(name="💰 Valor Total da Folha", value=f"**{formatar_valor_br(res['valor_total_lancado'])}**", inline=False)
                embed_vr.add_field(name="📋 Plano de Contas", value="`DESPESAS COM ALIMENTAÇÃO (VR)`", inline=True)
                embed_vr.add_field(name="🏢 Filiais", value="`429` • `601` • `Nevine`", inline=True)
                embed_vr.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                
                await status_msg.edit(content=None, embed=embed_vr)
            except Exception as err:
                await status_msg.edit(content=f"❌ Erro ao processar folha de VR: `{err}`")
            return

    # Verifica se e comando de Adiantamento Salarial
    if "adiantamento" in conteudo:
        filial_alvo = None
        if "601" in conteudo:
            filial_alvo = "601"
        elif "nevine" in conteudo:
            filial_alvo = "NEVINE"
        elif "429" in conteudo:
            filial_alvo = "429"

        # Localiza o PDF correspondente
        pdf_alvo = None
        candidatos = [
            f"adiantamento_{filial_alvo.lower()}.pdf" if filial_alvo else None,
            f"Recibo de Pagamento ADIANTAMENTO_{filial_alvo}- JULHO.pdf" if filial_alvo else None,
            "adiantamento_601.pdf",
            "adiantamento_nevine.pdf",
            "Recibo de Pagamento ADIANTAMENTO_601- JULHO.pdf",
            "Recibo de Pagamento ADIANTAMENTO_NEVINE- JULHO.pdf",
        ]
        for c in candidatos:
            if c:
                caminho_teste = os.path.join(os.path.dirname(__file__), c)
                if os.path.isfile(caminho_teste):
                    pdf_alvo = caminho_teste
                    break
                
        if not pdf_alvo:
            await message.reply("⚠️ Nenhum arquivo PDF de adiantamento foi localizado na pasta. Por favor, anexe o PDF do adiantamento.")
            return

        async with gerenciar_sessao_erp(message, f"Adiantamento ({os.path.basename(pdf_alvo)})"):
            status_msg = await message.reply(f"💼 **Comando de Adiantamento detectado!**\nArquivo: `{os.path.basename(pdf_alvo)}`\nIniciando lançamentos no ERP ADMSIS...")
            try:
                from adiantamento_launcher import processar_adiantamento_pdf
                res = await processar_adiantamento_pdf(pdf_alvo)
                
                if res["total_sucesso"] == res["total_colaboradores"]:
                    titulo_embed = "✅ Lançamento de Adiantamento Concluído com Sucesso!"
                    desc_embed = f"Todos os títulos de Adiantamento da filial **{res['filial']}** ({res['competencia']}) foram gravados no ERP."
                    cor_embed = discord.Color.green()
                elif res["total_sucesso"] > 0:
                    titulo_embed = "⚠️ Lançamento de Adiantamento Parcialmente Concluído"
                    desc_embed = f"Foram processados **{res['total_sucesso']}** de **{res['total_colaboradores']}** colaboradores da filial **{res['filial']}**."
                    cor_embed = discord.Color.orange()
                else:
                    titulo_embed = "❌ Falha no Lançamento de Adiantamento"
                    desc_embed = f"Nenhum título de Adiantamento pôde ser lançado para a filial **{res['filial']}**."
                    cor_embed = discord.Color.red()

                tabela_colabs = formatar_tabela_colaboradores(res.get("sucessos", []))
                desc_embed_completa = f"{desc_embed}\n\n**📋 Tabela de Colaboradores Lançados:**\n{tabela_colabs}"
                embed_ad = discord.Embed(title=titulo_embed, description=desc_embed_completa, color=cor_embed)
                embed_ad.add_field(name="🏢 Filial", value=f"`{res['filial']}`", inline=True)
                embed_ad.add_field(name="📅 Competência", value=f"`{res['competencia']}`", inline=True)
                embed_ad.add_field(name="⏰ Vencimento", value=f"`{res['vencimento']}`", inline=True)
                embed_ad.add_field(name="👥 Total Colaboradores", value=f"**{res['total_sucesso']} / {res['total_colaboradores']}**", inline=True)
                embed_ad.add_field(name="💰 Total da Folha", value=f"**{formatar_valor_br(res['valor_total_lancado'])}**", inline=False)
                embed_ad.add_field(name="📋 Plano de Contas", value="`ADIANTAMENTO SALARIAL`", inline=True)
                embed_ad.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                
                await status_msg.edit(content=None, embed=embed_ad)
            except Exception as err:
                await status_msg.edit(content=f"❌ Erro ao processar folha de adiantamento: `{err}`")
            return

    # Verifica se e comando de Pagamento de Salarios / Folha Mensal
    if ("pagamento" in conteudo or "salario" in conteudo or "salário" in conteudo or "folha" in conteudo) and not any(k in conteudo for k in ["vr", "vale refeicao", "vale refeição", "adiantamento"]):
        filial_alvo = None
        if "601" in conteudo:
            filial_alvo = "601"
        elif "nevine" in conteudo:
            filial_alvo = "NEVINE"
        elif "429" in conteudo:
            filial_alvo = "429"

        # Para folha de pagamento, é OBRIGATÓRIO o envio do PDF com o resumo de líquido
        pdf_alvo = None
        if message.attachments:
            for att in message.attachments:
                if att.filename.lower().endswith(".pdf"):
                    temp_filename = f"{message.id}_{att.filename}"
                    pdf_alvo = os.path.join(INBOX_DIR, temp_filename)
                    await att.save(pdf_alvo)
                    break

        if not pdf_alvo:
            embed_precisa_pdf = discord.Embed(
                title="⚠️ Envio de PDF Obrigatório",
                description=(
                    "Para o lançamento de **Folha de Pagamento / Salários**, é **obrigatório anexar o PDF** com o resumo dos valores líquidos.\n\n"
                    "💡 *Exemplo de comando:*\n"
                    f"> `@SofIA lance folha de pagamento filial {filial_alvo or '601'}` *(anexando o PDF do resumo de líquido)*"
                ),
                color=discord.Color.gold()
            )
            embed_precisa_pdf.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
            await message.reply(embed=embed_precisa_pdf)
            return

        async with gerenciar_sessao_erp(message, f"Folha de Pagamento ({os.path.basename(pdf_alvo)})"):
                status_msg = await message.reply(f"💼 **Comando de Folha de Pagamento detectado!**\nArquivo: `{os.path.basename(pdf_alvo)}`\nIniciando lançamentos no ERP ADMSIS...")
                try:
                    from pagamento_launcher import processar_pagamento_pdf
                    res = await processar_pagamento_pdf(pdf_alvo)
                    
                    if res["total_sucesso"] == res["total_colaboradores"]:
                        titulo_embed = "✅ Folha de Pagamento Concluída com Sucesso!"
                        desc_embed = f"Todos os títulos de Salário da filial **{res['filial']}** ({res['competencia']}) foram gravados no ERP."
                        cor_embed = discord.Color.green()
                    elif res["total_sucesso"] > 0:
                        titulo_embed = "⚠️ Folha de Pagamento Parcialmente Concluída"
                        desc_embed = f"Foram processados **{res['total_sucesso']}** de **{res['total_colaboradores']}** colaboradores da filial **{res['filial']}**."
                        cor_embed = discord.Color.orange()
                    else:
                        titulo_embed = "❌ Falha no Lançamento de Folha de Pagamento"
                        desc_embed = f"Nenhum título de Salário pôde ser lançado para a filial **{res['filial']}**."
                        cor_embed = discord.Color.red()

                    tabela_colabs = formatar_tabela_colaboradores(res.get("sucessos", []))
                    desc_embed_completa = f"{desc_embed}\n\n**📋 Tabela de Colaboradores Lançados:**\n{tabela_colabs}"
                    embed_pag = discord.Embed(title=titulo_embed, description=desc_embed_completa, color=cor_embed)
                    embed_pag.add_field(name="🏢 Filial", value=f"`{res['filial']}`", inline=True)
                    embed_pag.add_field(name="📅 Competência", value=f"`{res['competencia']}`", inline=True)
                    embed_pag.add_field(name="⏰ Vencimento", value=f"`{res['vencimento']}`", inline=True)
                    embed_pag.add_field(name="👥 Total Colaboradores", value=f"**{res['total_sucesso']} / {res['total_colaboradores']}**", inline=True)
                    embed_pag.add_field(name="💰 Total da Folha", value=f"**{formatar_valor_br(res['valor_total_lancado'])}**", inline=False)
                    embed_pag.add_field(name="📋 Plano de Contas", value="`SALÁRIOS / FOLHA DE PAGAMENTO`", inline=True)
                    embed_pag.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    
                    await status_msg.edit(content=None, embed=embed_pag)
                    return
                except Exception as err:
                    await status_msg.edit(content=f"❌ Erro ao processar folha de pagamento: `{err}`")
                    return

    # Verifica se e comando de Relatório de Contas a Pagar / Pagamentos do Dia
    if any(k in conteudo for k in ["contas a pagar", "titulos a pagar", "títulos a pagar", "pagamentos do dia", "pagamentos de hoje", "relatorio de pagamentos", "relatório de pagamentos", "o que tem para pagar", "relatorio 2015", "relatório 2015"]):
        import re
        from datetime import datetime, timedelta
        
        data_consulta = None
        m_data = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", conteudo)
        if m_data:
            dia, mes, ano = m_data.groups()
            if len(ano) == 2:
                ano = f"20{ano}"
            data_consulta = f"{int(dia):02d}/{int(mes):02d}/{ano}"
        elif "amanhã" in conteudo or "amanha" in conteudo:
            data_consulta = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        elif "ontem" in conteudo:
            data_consulta = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
        else:
            data_consulta = datetime.now().strftime("%d/%m/%Y")
            
        filial_alvo = None
        for fil_opt in ["302", "429", "551", "601", "nevine", "relevo"]:
            if fil_opt in conteudo:
                filial_alvo = fil_opt
                break
                
        async with gerenciar_sessao_erp(message, f"Contas a Pagar ({data_consulta})"):
            status_msg = await message.reply(
                f"📊 **Comando de Contas a Pagar detectado!**\n"
                f"📅 Data: **{data_consulta}**" + (f" | Filial: **{filial_alvo.upper()}**" if filial_alvo else "") + "\n"
                f"Gerando Relatório Oficial 2015 no ERP ADMSIS..."
            )
            
            try:
                from relatorio_launcher import gerar_relatorio_titulos_pagar
                pdf_path, resumo = await gerar_relatorio_titulos_pagar(
                    data_inicio=data_consulta,
                    data_fim=data_consulta,
                    filial=filial_alvo
                )
                
                qtd = resumo.get("qtd_titulos", 0)
                val_total = resumo.get("valor_total", "R$ 0,00")
                periodo = resumo.get("periodo", data_consulta)
                
                embed_rel = discord.Embed(
                    title=f"📊 Contas a Pagar - {data_consulta}",
                    description=f"Relatório de Títulos a Pagar (Cód. 2015) emitido com sucesso no ERP ADMSIS.\nSegue em anexo o PDF oficial completo.",
                    color=discord.Color.blue()
                )
                embed_rel.add_field(name="📅 Período", value=f"`{periodo}`", inline=True)
                embed_rel.add_field(name="📑 Quantidade de Títulos", value=f"**{qtd} título(s)**", inline=True)
                embed_rel.add_field(name="💰 Valor Total a Pagar", value=f"**{val_total}**", inline=False)
                
                totais_fil = resumo.get("totais_por_filial", {})
                if totais_fil:
                    fil_linhas = [f"• **Filial {f}**: R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for f, v in totais_fil.items()]
                    embed_rel.add_field(name="🏢 Desdobramento por Filial", value="\n".join(fil_linhas), inline=False)
                    
                embed_rel.set_footer(text="Automação Contas a Pagar • ADMSIS ERP (Tela 0117030100)")
                
                # Anexa o PDF oficial e envia de volta ao Discord
                file_anexo = discord.File(pdf_path, filename=f"Contas_a_Pagar_{data_consulta.replace('/', '-')}.pdf")
                await status_msg.delete()
                await message.reply(embed=embed_rel, file=file_anexo)
                return
            except Exception as err:
                await status_msg.edit(content=f"❌ Erro ao gerar relatório de contas a pagar: `{err}`")
                return

    # Verifica se e comando de Relatório de Contas a Receber / Recebimentos do Dia
    if any(k in conteudo for k in ["contas a receber", "titulos a receber", "títulos a receber", "recebimentos do dia", "recebimento do dia", "recebimentos de hoje", "recebimento de hoje", "o que tem para receber", "relatorio 2004", "relatório 2004", "a receber"]):
        import re
        from datetime import datetime, timedelta
        
        data_consulta = None
        m_data = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", conteudo)
        if m_data:
            dia, mes, ano = m_data.groups()
            if len(ano) == 2:
                ano = f"20{ano}"
            data_consulta = f"{int(dia):02d}/{int(mes):02d}/{ano}"
        elif "amanhã" in conteudo or "amanha" in conteudo:
            data_consulta = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        elif "ontem" in conteudo:
            data_consulta = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
        else:
            data_consulta = datetime.now().strftime("%d/%m/%Y")
            
        filial_alvo = None
        for fil_opt in ["302", "429", "551", "601", "nevine", "relevo"]:
            if fil_opt in conteudo:
                filial_alvo = fil_opt
                break
                
        async with gerenciar_sessao_erp(message, f"Contas a Receber ({data_consulta})"):
            status_msg = await message.reply(
                f"📥 **Comando de Contas a Receber detectado!**\n"
                f"📅 Data: **{data_consulta}**" + (f" | Filial: **{filial_alvo.upper()}**" if filial_alvo else "") + "\n"
                f"Gerando Relatório Oficial 2004 no ERP ADMSIS..."
            )
            
            try:
                from relatorio_launcher import gerar_relatorio_titulos_receber
                pdf_path, resumo = await gerar_relatorio_titulos_receber(
                    data_inicio=data_consulta,
                    data_fim=data_consulta,
                    filial=filial_alvo
                )
                
                qtd = resumo.get("qtd_titulos", 0)
                val_total = resumo.get("valor_total", "R$ 0,00")
                periodo = resumo.get("periodo", data_consulta)
                
                embed_rec = discord.Embed(
                    title=f"📥 Contas a Receber - {data_consulta}",
                    description=f"Relatório de Títulos a Receber em Aberto (Cód. 2004) emitido com sucesso no ERP ADMSIS.\nSegue em anexo o PDF oficial completo.",
                    color=discord.Color.green()
                )
                embed_rec.add_field(name="📅 Período", value=f"`{periodo}`", inline=True)
                embed_rec.add_field(name="📑 Quantidade de Títulos", value=f"**{qtd} título(s)**", inline=True)
                embed_rec.add_field(name="💰 Valor Total a Receber", value=f"**{val_total}**", inline=False)
                
                totais_fil = resumo.get("totais_por_filial", {})
                if totais_fil:
                    fil_linhas = [f"• **Filial {f}**: R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for f, v in totais_fil.items()]
                    embed_rec.add_field(name="🏢 Desdobramento por Filial", value="\n".join(fil_linhas), inline=False)
                    
                titulos = resumo.get("titulos", [])
                if titulos:
                    cli_linhas = [f"• {t.get('cliente', 'Cliente N/D')[:32]}: **{t['valor_str']}** (Filial {t['filial']})" for t in titulos[:5]]
                    embed_rec.add_field(name="👥 Principais Clientes / Devedores", value="\n".join(cli_linhas), inline=False)
                    
                embed_rec.set_footer(text="Automação Financeira • ADMSIS ERP (Tela 0117030100)")
                
                # Anexa o PDF oficial e envia de volta ao Discord
                file_anexo = discord.File(pdf_path, filename=f"Contas_a_Receber_{data_consulta.replace('/', '-')}.pdf")
                await status_msg.delete()
                await message.reply(embed=embed_rec, file=file_anexo)
                return
            except Exception as err:
                await status_msg.edit(content=f"❌ Erro ao gerar relatório de contas a receber: `{err}`")
                return

    # Verifica se e comando de Incentivo / Prêmio de Vendas (Nevine)
    if any(k in conteudo for k in ["premio", "prêmio", "incentivo", "comissao", "comissão"]):
        status_msg = await message.reply(
            "🏆 **Comando de Incentivo / Prêmio de Vendas detectado!**\n"
            "Conectando à base oficial de vendas e consolidando os bônus por vendedor..."
        )
        try:
            from premio_launcher import apurar_premio_vendas, formatar_tabela_ranking_discord
            res = await apurar_premio_vendas(message.content)

            embed_premio = discord.Embed(
                title=f"🏆 Incentivo de Vendas Nevine - {res['periodo_label']}",
                description=(
                    f"Apuração consolidada da premiação comercial para o período **{res['periodo_label']}**.\n\n"
                    f"**📊 Ranking Consolidado:**\n{formatar_tabela_ranking_discord(res['ranking'])}"
                ),
                color=discord.Color.gold()
            )
            embed_premio.add_field(name="📅 Período de Vendas", value=f"`{res['dt_inicio']} a {res['dt_fim']}`", inline=True)
            embed_premio.add_field(name="📦 Pedidos Elegíveis", value=f"**{res['total_pedidos']} pedidos**", inline=True)
            embed_premio.add_field(name="💰 Premiação Total", value=f"**{res['total_premio_str']}**", inline=True)
            embed_premio.add_field(name="🛒 Volume de Vendas", value=f"**{res['total_vendas_str']}**", inline=True)
            embed_premio.add_field(
                name="🏷️ Desdobramento por Regra de Bonificação",
                value=(
                    f"• **F1 (Cliente Novo):** {res['subtotal_f1']['pedidos']} pedidos | {res['subtotal_f1']['vendas_str']} vendas | {res['subtotal_f1']['premio_str']} bônus\n"
                    f"• **F2 (Espaço Nevine):** {res['subtotal_f2']['pedidos']} pedidos | {res['subtotal_f2']['vendas_str']} vendas | {res['subtotal_f2']['premio_str']} bônus"
                ),
                inline=False
            )
            embed_premio.set_footer(text="Automação Comercial & Financeira • Planilha Oficial Google Sheets (Nevine)")

            anexos = []
            if res.get("pdf_path") and os.path.exists(res["pdf_path"]):
                anexos.append(discord.File(res["pdf_path"], filename=f"Incentivo_Vendas_{res['periodo_label'].replace('/', '-').replace(' ', '_')}.pdf"))
            elif res.get("html_path") and os.path.exists(res["html_path"]):
                anexos.append(discord.File(res["html_path"], filename=f"Incentivo_Vendas_{res['periodo_label'].replace('/', '-').replace(' ', '_')}.html"))

            await status_msg.delete()
            if anexos:
                await message.reply(embed=embed_premio, files=anexos)
            else:
                await message.reply(embed=embed_premio)
            return
        except Exception as err:
            await status_msg.edit(content=f"❌ Erro ao apurar incentivo de vendas: `{err}`")
            return

    # ── 1. FATURAMENTO / EMISSÃO DE NF-e ────────────────────────────────────
    if any(k in conteudo for k in ["crie a nf", "gerar nf", "gerar nfe", "emitir nf", "emitir nfe", "faturar"]):
        import re
        m_ped = re.search(r"\b(?:nf[e]?|faturar|fature|pedido)?\s*(\d{3,8})\b", conteudo)
        if not m_ped:
            await message.reply("⚠️ Por favor, informe o número do pedido para faturamento. Exemplo:\n> `@SofIA faturar pedido 1585` ou `@SofIA crie a NF 1585`")
            return
        num_pedido = m_ped.group(1)
        async with gerenciar_sessao_erp(message, f"Faturamento NF-e Pedido {num_pedido}"):
            status_msg = await message.reply(f"🏭 **Faturamento de NF-e Iniciado!**\nPedido: `{num_pedido}`\nAcessando ERP ADMSIS, autorizando NF-e e verificando boleto...")
            try:
                from gerar_nfe_automatica import processar_pedido_avulso
                res_nfe = await processar_pedido_avulso(num_pedido)
                cor = discord.Color.green() if ("OK" in str(res_nfe) or "autorizada" in str(res_nfe).lower()) else discord.Color.gold()
                embed_nfe = discord.Embed(
                    title=f"📑 Resultado Faturamento NF-e - Pedido {num_pedido}",
                    description=f"Status: **{res_nfe}**",
                    color=cor
                )
                embed_nfe.set_footer(text="Automação NFe • ADMSIS ERP")
                await status_msg.edit(content=None, embed=embed_nfe)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao faturar pedido `{num_pedido}`: `{ex}`")
            return

    # ── 2. CONSULTA DE DANFE / XML DE NF-e ──────────────────────────────────
    if any(k in conteudo for k in ["danfe", "ver nf", "ver nfe", "xml", "consultar nf", "baixar nf"]) and not any(k in conteudo for k in ["fechamento", "fechar"]):
        import re
        m_ped = re.search(r"\b(\d{3,8})\b", conteudo)
        if not m_ped:
            await message.reply("⚠️ Por favor, informe o número do pedido para consulta do DANFE/XML. Exemplo:\n> `@SofIA danfe 1585`")
            return
        num_pedido = m_ped.group(1)
        async with gerenciar_sessao_erp(message, f"Consulta DANFE Pedido {num_pedido}"):
            status_msg = await message.reply(f"🔍 **Consultando DANFE/XML no ERP...**\nPedido: `{num_pedido}`\nLocalizando nota na tela 0103050100...")
            try:
                from gerar_nfe_automatica import obter_arquivos_nfe_pedido
                arquivos = await obter_arquivos_nfe_pedido(num_pedido)
                if arquivos:
                    anexos_discord = [discord.File(f) for f in arquivos if os.path.exists(f)]
                    embed_danfe = discord.Embed(
                        title=f"📄 DANFE / XML - Pedido {num_pedido}",
                        description=f"Foram localizados **{len(anexos_discord)} arquivo(s)** da nota fiscal no ERP ADMSIS.",
                        color=discord.Color.green()
                    )
                    embed_danfe.set_footer(text="Automação NFe • ADMSIS ERP")
                    await status_msg.delete()
                    await message.reply(embed=embed_danfe, files=anexos_discord)
                else:
                    embed_vazio = discord.Embed(
                        title="⚠️ DANFE Não Localizado",
                        description=f"Não foi possível obter o DANFE/XML para o pedido `{num_pedido}` no ERP. Verifique se o pedido já foi devidamente faturado.",
                        color=discord.Color.gold()
                    )
                    await status_msg.edit(content=None, embed=embed_vazio)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao consultar DANFE do pedido `{num_pedido}`: `{ex}`")
            return

    # ── 3. ORDEM DE PRODUÇÃO (OP) ──────────────────────────────────────────
    if any(k in conteudo for k in ["ordem de produção", "ordem de producao", "avançar op", "avancar op", "concluir op", "op "]):
        import re
        m_ped = re.search(r"\b(\d{3,8})\b", conteudo)
        if not m_ped:
            await message.reply("⚠️ Por favor, informe o número da OP/Pedido. Exemplo:\n> `@SofIA avançar op 1585`")
            return
        num_pedido = m_ped.group(1)
        async with gerenciar_sessao_erp(message, f"Ordem de Produção Pedido {num_pedido}"):
            status_msg = await message.reply(f"⚙️ **Ordem de Produção detectada!**\nPedido/OP: `{num_pedido}`\nAcessando tela 0102080100 e concluindo componente...")
            try:
                from gerar_nfe_automatica import avancar_ordem_producao
                res_op = await avancar_ordem_producao(num_pedido)
                cor = discord.Color.green() if "OK" in res_op else discord.Color.red()
                embed_op = discord.Embed(
                    title=f"⚙️ Ordem de Produção - Pedido {num_pedido}",
                    description=res_op,
                    color=cor
                )
                embed_op.set_footer(text="Automação OP • ADMSIS ERP")
                await status_msg.edit(content=None, embed=embed_op)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao processar ordem de produção: `{ex}`")
            return

    # ── 4. EMISSÃO DE GUIA GNRE (SEFAZ) ────────────────────────────────────
    if any(k in conteudo for k in ["crie a gnre", "emitir gnre", "gerar gnre", "gnre do pedido", "emitir guia gnre", "gerar guia gnre", "verificar gnre"]):
        import re
        m_ped = re.search(r"\b(\d{3,8})\b", conteudo)
        pedido_gnre = m_ped.group(1) if m_ped else None
        
        async with gerenciar_sessao_erp(message, f"Emissão de GNRE ({pedido_gnre or 'Planilha'})"):
            status_msg = await message.reply(
                f"🏛️ **Automação de GNRE Iniciada!**\n"
                + (f"Pedido específico: `{pedido_gnre}`\n" if pedido_gnre else "Varrendo pedidos interestaduais pendentes na planilha de transporte...\n")
                + "Acessando ERP para extrair dados fiscais (ICMS-ST/FCP) e gerando guia oficial no Portal GNRE..."
            )
            try:
                from gnre_emissao.gnre_pipeline import executar_pipeline
                sucesso = await asyncio.to_thread(executar_pipeline, pedido_especifico=pedido_gnre)
                if sucesso:
                    embed_gnre = discord.Embed(
                        title="✅ Processamento de GNRE Concluído!",
                        description=f"A emissão da Guia GNRE" + (f" do pedido `{pedido_gnre}`" if pedido_gnre else " dos pedidos pendentes") + " foi executada com sucesso e registrada no histórico.",
                        color=discord.Color.green()
                    )
                else:
                    embed_gnre = discord.Embed(
                        title="⚠️ Processamento de GNRE com Avisos",
                        description="O pipeline de GNRE foi executado. Verifique os logs e a pasta de PDFs gerados.",
                        color=discord.Color.gold()
                    )
                embed_gnre.set_footer(text="Automação Fiscal • Portal GNRE Nacional (gnre.pe.gov.br)")
                await status_msg.edit(content=None, embed=embed_gnre)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao emitir GNRE: `{ex}`")
            return

    # ── 5. PREVISÃO FINANCEIRA (FLUXO DE CAIXA) ─────────────────────────────
    if any(k in conteudo for k in ["gerar previsão", "gerar previsao", "previsão financeira", "previsao financeira", "fluxo de caixa", "atualizar previsão", "atualizar previsao"]):
        import re
        m_dt = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", conteudo)
        dt_base = m_dt.group(1) if m_dt else None

        async with gerenciar_sessao_erp(message, "Previsão Financeira"):
            status_msg = await message.reply(
                "📈 **Robô de Previsão Financeira Iniciado!**\n"
                "1. Extraindo relatórios oficiais 2004 (Receber) e 2015 (Pagar) do ERP ADMSIS...\n"
                "2. Consolidando compensação bancária e feriados por filial (302, 429, 551, 601, Nevine)...\n"
                "3. Duplicando aba do dia e preenchendo as 50 células no Google Sheets..."
            )
            try:
                from automacao_previsao import executar_previsao
                res_prev = await executar_previsao(data_base_str=dt_base)
                if res_prev.get("sucesso"):
                    embed_prev = discord.Embed(
                        title="✅ Previsão Financeira Atualizada com Sucesso!",
                        description=(
                            f"A planilha oficial de fluxo de caixa foi sincronizada com o ERP ADMSIS.\n\n"
                            f"• **Aba Gerada/Atualizada:** `{res_prev.get('aba')}`\n"
                            f"• **Período de Extração:** `{res_prev.get('periodo')}`\n"
                            f"• **Planilha:** [Acessar Google Sheets]({res_prev.get('planilha_url')})"
                        ),
                        color=discord.Color.green()
                    )
                    embed_prev.set_footer(text="Automação Financeira • ADMSIS ERP & Google Sheets")
                    await status_msg.edit(content=None, embed=embed_prev)
                else:
                    embed_prev_fail = discord.Embed(
                        title="❌ Falha na Previsão Financeira",
                        description=res_prev.get("mensagem", "Erro desconhecido ao gerar previsão."),
                        color=discord.Color.red()
                    )
                    await status_msg.edit(content=None, embed=embed_prev_fail)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao executar previsão financeira: `{ex}`")
            return

    # ── 6. FECHAMENTO FISCAL XML (RELATÓRIO 2001 + XMLs) ───────────────────
    if any(k in conteudo for k in ["fechamento fiscal", "fechamento xml", "fechamento mensal", "xmls do mês", "xmls do mes", "fechar mês", "fechar mes"]):
        import re
        m_mes = re.search(r"\b(?:mes|mês)?\s*(\d{1,2})[/.-](\d{4})\b", conteudo)
        mes_f, ano_f = (int(m_mes.group(1)), int(m_mes.group(2))) if m_mes else (None, None)
        
        async with gerenciar_sessao_erp(message, "Fechamento Fiscal XML"):
            status_msg = await message.reply(
                "📦 **Fechamento Fiscal Mensal Iniciado!**\n"
                "Baixando pacotes ZIP de NF-e (0104040100) e Relatórios 2001 (0117020100) para todas as filiais (302, 429, 551, 601, Nevine)..."
            )
            try:
                from automacao_fechamento import executar_fechamento_fiscal
                res_fech = await executar_fechamento_fiscal(mes=mes_f, ano=ano_f)
                if res_fech.get("sucesso"):
                    fils = ", ".join(res_fech.get("filiais", []))
                    embed_fech = discord.Embed(
                        title="✅ Fechamento Fiscal Concluído!",
                        description=(
                            f"Todos os arquivos fiscais do período **{res_fech.get('periodo')}** foram exportados com sucesso do ERP ADMSIS.\n\n"
                            f"• **Filiais Processadas:** `{fils}`\n"
                            f"• **Pasta de Destino:** `{res_fech.get('pasta_destino')}`\n"
                            f"• **Total de Arquivos Gerados:** `{len(res_fech.get('arquivos', []))} arquivos`"
                        ),
                        color=discord.Color.green()
                    )
                    embed_fech.set_footer(text="Automação Fiscal • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_fech)
                else:
                    embed_fail = discord.Embed(
                        title="❌ Falha no Fechamento Fiscal",
                        description=res_fech.get("mensagem", "Erro desconhecido ao executar fechamento."),
                        color=discord.Color.red()
                    )
                    await status_msg.edit(content=None, embed=embed_fail)
            except Exception as ex:
                await status_msg.edit(content=f"❌ Erro ao executar fechamento fiscal: `{ex}`")
            return

    # ── 7. PONTO ELETRÔNICO (REP HENRY) ────────────────────────────────────
    if any(k in conteudo for k in ["espelho de ponto", "consolidado de ponto", "ponto eletronico", "ponto eletrônico", "relatorio de ponto", "relatório de ponto", "ver ponto"]):
        status_msg = await message.reply("⏱️ **Processando Ponto Eletrônico Consolidado...**\nConsolidando marcações dos relógios 601 e Nevine e calculando jornada CLT...")
        try:
            from ponto_eletronico.gerar_consolidado import gerar_espelho_ponto_consolidado
            caminho_html = await asyncio.to_thread(gerar_espelho_ponto_consolidado)
            if os.path.exists(caminho_html):
                embed_ponto = discord.Embed(
                    title="⏱️ Espelho de Ponto Consolidado (601 + Nevine)",
                    description="O relatório consolidado de ponto foi gerado com sucesso.\nSegue o arquivo interativo HTML em anexo para visualização no navegador.",
                    color=discord.Color.blue()
                )
                embed_ponto.set_footer(text="Automação Ponto • Relógios REP Henry")
                file_ponto = discord.File(caminho_html, filename="Espelho_Ponto_Consolidado.html")
                await status_msg.delete()
                await message.reply(embed=embed_ponto, file=file_ponto)
            else:
                await status_msg.edit(content="❌ Não foi possível gerar o espelho de ponto consolidado.")
        except Exception as ex:
            await status_msg.edit(content=f"❌ Erro ao gerar ponto eletrônico: `{ex}`")
        return

    # ── 8. MÉTRICAS CONSOLIDADAS ───────────────────────────────────────────
    if any(k in conteudo for k in ["metricas", "métricas", "dashboard", "estatisticas", "estatísticas"]) and not any(k in conteudo for k in ["ajuda", "menu"]):
        try:
            import database as db_nfe
            m_nfe = db_nfe.obter_metricas()
            import importlib.util
            gnre_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "gnre_emissao", "database.py")
            if not os.path.exists(gnre_db_path):
                gnre_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gnre_emissao", "database.py")
            m_gnre = {}
            if os.path.exists(gnre_db_path):
                spec = importlib.util.spec_from_file_location("db_gnre", gnre_db_path)
                db_gnre = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(db_gnre)
                if hasattr(db_gnre, "obter_metricas_gnre"):
                    m_gnre = db_gnre.obter_metricas_gnre()

            embed_m = discord.Embed(
                title="📊 Dashboard Geral de Automações - Super SofIA",
                description="Métricas consolidadas de operação em produção:",
                color=discord.Color.teal()
            )
            embed_m.add_field(
                name="🏭 Emissão de NF-e",
                value=(
                    f"• **Hoje ({m_nfe['hoje']['data']}):** {m_nfe['hoje']['total']} total | {m_nfe['hoje']['sucesso']} autorizadas\n"
                    f"• **Ontem ({m_nfe['ontem']['data']}):** {m_nfe['ontem']['total']} total | {m_nfe['ontem']['sucesso']} autorizadas\n"
                    f"• **Mês Atual ({m_nfe['este_mes']['mes']}):** {m_nfe['este_mes']['total']} total | {m_nfe['este_mes']['sucesso']} autorizadas"
                ),
                inline=False
            )
            embed_m.add_field(
                name="📄 Boletos Faturamento",
                value=(
                    f"• **Hoje:** {m_nfe['hoje']['boletos']} boletos gerados\n"
                    f"• **Ontem:** {m_nfe['ontem']['boletos']} boletos gerados\n"
                    f"• **Mês Atual:** {m_nfe['este_mes']['boletos']} boletos gerados"
                ),
                inline=False
            )
            if m_gnre:
                embed_m.add_field(
                    name="🏛️ Emissão de Guias GNRE",
                    value=(
                        f"• **Hoje:** {m_gnre.get('hoje', {}).get('sucesso', 0)} guias geradas\n"
                        f"• **Mês Atual:** {m_gnre.get('este_mes', {}).get('sucesso', 0)} guias geradas\n"
                        f"• **Taxa de Sucesso:** {m_gnre.get('geral', {}).get('taxa_sucesso', '100%')}"
                    ),
                    inline=False
                )
            embed_m.add_field(
                name="🌐 Servidor HTTP de Métricas",
                value="`http://localhost:8080/metricas` • Ativo e atualizando em tempo real",
                inline=False
            )
            embed_m.set_footer(text="Super SofIA • Automações Integradas")
            await message.reply(embed=embed_m)
            return
        except Exception as ex:
            await message.reply(f"❌ Erro ao consultar métricas: `{ex}`")
            return

    # ── 9. CRONOGRAMA DE TAREFAS AUTOMÁTICAS ──────────────────────────────
    if any(k in conteudo for k in ["agendamento", "agendamentos", "cronograma", "tarefas agendadas", "cron"]) and not any(k in conteudo for k in ["ajuda", "menu"]):
        embed_cron = discord.Embed(
            title="⏰ Cronograma de Tarefas Automáticas - Super SofIA",
            description="Todas as rotinas em segundo plano são executadas com fila serializada (`erp_lock`), sem risco de travamento de sessão.",
            color=discord.Color.purple()
        )
        embed_cron.add_field(
            name="🏭 Faturamento & NF-e (De hora em hora)",
            value="• **Horários:** `07:50, 08:50, 09:50, 10:50, 11:50, 12:50, 13:50, 14:50, 15:50, 16:50, 17:50`\n• **Dias:** Segunda a Sexta\n• **Regra:** Às 07:50 fatura o dia atual; a partir das 08:50 adianta para o próximo dia útil.",
            inline=False
        )
        embed_cron.add_field(
            name="🏛️ Emissão de Guias GNRE (Portal Sefaz)",
            value="• **Horários:** `09:00, 11:00, 14:00, 16:00`\n• **Dias:** Segunda a Sexta\n• **Ação:** Varredura de pedidos interestaduais na planilha e emissão automática.",
            inline=False
        )
        embed_cron.add_field(
            name="📈 Previsão Financeira (Google Sheets)",
            value="• **Horário:** `09:30`\n• **Dias:** Segunda a Sexta\n• **Ação:** Baixa relatórios 2004/2015 e preenche a aba do dia.",
            inline=False
        )

        status_txt = []
        for rotina, dth in agendamentos_status.get("ultima_execucao", {}).items():
            status_txt.append(f"• **{rotina.upper()}:** Última execução em `{dth}`")
        if not status_txt:
            status_txt.append("• Agendador ativo e aguardando o próximo horário programado.")

        embed_cron.add_field(
            name="📊 Status em Tempo Real",
            value="\n".join(status_txt),
            inline=False
        )
        embed_cron.set_footer(text="Agendador Interno da SofIA • Concorrência Protegida por Lock")
        await message.reply(embed=embed_cron)
        return

    # Mostra o menu de ajuda/comandos SOMENTE se o usuário solicitar explicitamente (ou marcar apenas @SofIA)
    texto_limpo = conteudo.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").replace("sofia", "").strip()
    pediu_ajuda = any(k in conteudo for k in ["ajuda", "help", "menu", "comandos", "manual", "o que você faz", "o que voce faz"]) or texto_limpo in ["", "?", "oi", "olá", "ola"]

    if pediu_ajuda:
        embed_aviso = discord.Embed(
            title="🤖 Central Super SofIA - Central Unificada de Automações ERP & Financeiro",
            description="Olá! Sou a **SofIA**, central unificada de automações financeiras, fiscais e operacionais. Veja todas as minhas capacidades organizadas por setor:",
            color=discord.Color.blue()
        )
        embed_aviso.add_field(
            name="1️⃣ Contas a Pagar & Tesouraria",
            value=(
                "• **Boletos / GNRE / Holerite:** `@SofIA lance este pagamento` *(anexando o PDF)*\n"
                "• **Vale Refeição (VR):** `@SofIA faça o VR de outubro`\n"
                "• **Adiantamento Salarial:** `@SofIA lance adiantamento filial 601`\n"
                "• **Folha de Pagamento:** `@SofIA lance pagamento filial 601` *(anexando o PDF de resumo)*\n"
                "• **Pagamento Avulso (PIX):** `@SofIA lance pagamento avulso para NOME, valor 760, filial 429, ref SERVIÇO, vencimento hoje`\n"
                "• **Alteração de Título Individual:** `@SofIA altere a data de vencimento do favorecido NOME para 01/10/2026`\n"
                "• **Alteração em Lote:** `@SofIA altere a data de vencimento de TODOS os favorecidos de HOJE para 01/10/2026`\n"
                "• **Relatórios Oficiais Diários:** `@SofIA contas a pagar de hoje` ou `@SofIA contas a receber de hoje` *(PDF oficial do ERP)*"
            ),
            inline=False
        )
        embed_aviso.add_field(
            name="2️⃣ Faturamento & Emissão de NF-e",
            value=(
                "• **Faturar Pedido:** `@SofIA faturar pedido 1585` ou `@SofIA crie a NF 1585` *(autoriza NF-e e gera boleto)*\n"
                "• **Consultar DANFE / XML:** `@SofIA danfe 1585` ou `@SofIA ver nf 1585` *(retorna PDF e XML)*\n"
                "• **Ordem de Produção (OP):** `@SofIA avançar op 1585` *(conclui componente na tela 0102080100)*"
            ),
            inline=False
        )
        embed_aviso.add_field(
            name="3️⃣ Fiscal & Tributário",
            value=(
                "• **Emissão de Guia GNRE:** `@SofIA crie a GNRE do pedido 1760` ou `@SofIA verificar gnre` *(Sefaz Nacional)*\n"
                "• **Fechamento Fiscal Mensal:** `@SofIA fechamento fiscal 09/2026` *(baixa pacotes ZIP de NF-e e Relatório 2001 das 5 filiais)*"
            ),
            inline=False
        )
        embed_aviso.add_field(
            name="4️⃣ Controladoria, RH & Comercial",
            value=(
                "• **Previsão Financeira / Fluxo de Caixa:** `@SofIA gerar previsão` *(sincroniza relatórios 2004/2015 e preenche o Google Sheets)*\n"
                "• **Espelho de Ponto (REP Henry):** `@SofIA espelho de ponto` *(gera HTML consolidado de jornadas, horas extras e atrasos)*\n"
                "• **Prêmio / Incentivo de Vendas:** `@SofIA calcule o prêmio de setembro` *(ranking comercial e apuração Nevine)*"
            ),
            inline=False
        )
        embed_aviso.add_field(
            name="5️⃣ Gestão & Auditoria",
            value=(
                "• **Histórico de Lotes:** `@SofIA historico` *(auditoria dos últimos lotes processados)*\n"
                "• **Dashboard de Métricas:** `@SofIA metricas` *(resumo operacional + servidor HTTP porta 8080)*\n"
                "• **Tarefas Agendadas (Cron):** `@SofIA agendamentos` *(cronograma e status das automações em segundo plano)*"
            ),
            inline=False
        )
        embed_aviso.set_footer(text="Super SofIA • Unificação Integral dos Projetos em Produção")
        await message.reply(embed=embed_aviso)
        return

    # Se não pediu ajuda e não há arquivos anexados, permanece em silêncio para não poluir o canal
    if not message.attachments:
        return

    # Processa cada anexo recebido
    for attachment in message.attachments:
        ext = os.path.splitext(attachment.filename)[1].lower()
        if ext not in [".pdf", ".jpeg", ".jpg", ".png"]:
            await message.reply(f"⚠️ O arquivo `{attachment.filename}` não é um formato suportado (envie PDF ou imagem).")
            continue

        async with gerenciar_sessao_erp(message, f"Documento `{attachment.filename}`"):
            # Mensagem inicial de processamento
            status_msg = await message.reply(f"⏳ **Recebido:** `{attachment.filename}`\nValidando dados e iniciando lançamento no ERP ADMSIS...")

            # Baixa o anexo para a pasta inbox
            temp_filename = f"{message.id}_{attachment.filename}"
            local_path = os.path.join(INBOX_DIR, temp_filename)
            await attachment.save(local_path)

            try:
                # Executa o fluxo no Sofia Core
                resultado = await processar_documento(local_path)

                if not resultado.get("sucesso"):
                    motivo = resultado.get("motivo")
                    msg_erro = resultado.get("mensagem", "Erro desconhecido durante o processamento.")
                    
                    if motivo == "DUPLICADO":
                        embed_dup = discord.Embed(
                            title="⚠️ Documento Já Lançado Anterioremente",
                            description=msg_erro,
                            color=discord.Color.gold()
                        )
                        await status_msg.edit(content=None, embed=embed_dup)
                    else:
                        embed_err = discord.Embed(
                            title="❌ Falha no Lançamento",
                            description=msg_erro,
                            color=discord.Color.red()
                        )
                        await status_msg.edit(content=None, embed=embed_err)
                    continue

                # Caso especial: Folha de Adiantamento Salarial em lote
                if resultado.get("tipo") == "Adiantamento" or "resumo_adiantamento" in resultado:
                    res_ad = resultado.get("resumo_adiantamento", {})
                    tabela_colabs = formatar_tabela_colaboradores(res_ad.get("sucessos", []))
                    embed_ad = discord.Embed(
                        title="✅ Folha de Adiantamento Lançada com Sucesso!",
                        description=f"Todos os colaboradores do arquivo `{attachment.filename}` foram processados no ERP.\n\n**📋 Tabela de Colaboradores Lançados:**\n{tabela_colabs}",
                        color=discord.Color.green()
                    )
                    embed_ad.add_field(name="🏢 Filial", value=f"`{res_ad.get('filial')}`", inline=True)
                    embed_ad.add_field(name="📅 Competência", value=f"`{res_ad.get('competencia')}`", inline=True)
                    embed_ad.add_field(name="⏰ Vencimento", value=f"`{res_ad.get('vencimento')}`", inline=True)
                    embed_ad.add_field(name="👥 Colaboradores", value=f"**{res_ad.get('total_sucesso')} / {res_ad.get('total_colaboradores')}**", inline=True)
                    embed_ad.add_field(name="💰 Total da Folha", value=f"**{formatar_valor_br(res_ad.get('valor_total_lancado', 0))}**", inline=False)
                    embed_ad.add_field(name="📋 Plano de Contas", value="`ADIANTAMENTO SALARIAL`", inline=True)
                    embed_ad.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_ad)
                    continue

                # Caso especial: Folha de Pagamento de Salários em lote
                if resultado.get("tipo") == "Pagamento" or "resumo_pagamento" in resultado:
                    res_pag = resultado.get("resumo_pagamento", {})
                    tabela_colabs = formatar_tabela_colaboradores(res_pag.get("sucessos", []))
                    embed_pag = discord.Embed(
                        title="✅ Folha de Pagamento Lançada com Sucesso!",
                        description=f"Todos os colaboradores do arquivo `{attachment.filename}` foram processados no ERP.\n\n**📋 Tabela de Colaboradores Lançados:**\n{tabela_colabs}",
                        color=discord.Color.green()
                    )
                    embed_pag.add_field(name="🏢 Filial", value=f"`{res_pag.get('filial')}`", inline=True)
                    embed_pag.add_field(name="📅 Competência", value=f"`{res_pag.get('competencia')}`", inline=True)
                    embed_pag.add_field(name="⏰ Vencimento", value=f"`{res_pag.get('vencimento')}`", inline=True)
                    embed_pag.add_field(name="👥 Colaboradores", value=f"**{res_pag.get('total_sucesso')} / {res_pag.get('total_colaboradores')}**", inline=True)
                    embed_pag.add_field(name="💰 Total da Folha", value=f"**{formatar_valor_br(res_pag.get('valor_total_lancado', 0))}**", inline=False)
                    embed_pag.add_field(name="📋 Plano de Contas", value="`SALÁRIOS / FOLHA DE PAGAMENTO`", inline=True)
                    embed_pag.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_pag)
                    continue

                # Sucesso! Monta o Embed com a tabela dos dados lançados (SEM anexar arquivos)
                lancamentos = resultado.get("lancamentos", [])
                for entry in lancamentos:
                    tabela_dados = formatar_tabela_individual(entry)
                    embed_sucesso = discord.Embed(
                        title="✅ Pagamento Lançado com Sucesso no ERP!",
                        description=f"Os dados do documento `{attachment.filename}` foram gravados no ERP ADMSIS.\n\n**📋 Tabela de Dados do Título Lançado:**\n{tabela_dados}",
                        color=discord.Color.green()
                    )
                    embed_sucesso.set_footer(text="Automação Contas a Pagar • ADMSIS ERP")
                    await status_msg.edit(content=None, embed=embed_sucesso)

            except Exception as e:
                embed_exc = discord.Embed(
                    title="🚨 Erro Inesperado",
                    description=f"Ocorreu um erro interno ao processar o título:\n```{str(e)}```",
                    color=discord.Color.dark_red()
                )
                await status_msg.edit(content=None, embed=embed_exc)

def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "seu_token_aqui":
        print("\n" + "!"*60)
        print("  AVISO: DISCORD_BOT_TOKEN nao configurado no arquivo .env!")
        print("  Para ativar a Sofia no Discord:")
        print("  1. Crie o bot no Discord Developer Portal (https://discord.com/developers)")
        print("  2. Adicione 'DISCORD_BOT_TOKEN=seu_token_aqui' no arquivo .env")
        print("  3. Execute 'python sofia_bot.py'")
        print("!"*60 + "\n")
        return

    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
