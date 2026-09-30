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
    return "\n".join(linhas)

@bot.event
async def on_ready():
    print(f"\n{'='*60}")
    print(f"  SOFIA ONLINE! Logado como: {bot.user.name} (ID: {bot.user.id})")
    print(f"  Pronta para receber documentos no Discord!")
    print(f"{'='*60}\n")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Contas a Pagar"))

@bot.event
async def on_message(message: discord.Message):
    # Ignora mensagens do próprio bot
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

        pdf_alvo = None
        candidatos = [
            f"PAGAMENTO_{filial_alvo}.pdf" if filial_alvo else None,
            "PAGAMENTO_601.pdf",
            "PAGAMENTO_429.pdf",
            "PAGAMENTO_NEVINE.pdf",
        ]
        for c in candidatos:
            if c:
                caminho_teste = os.path.join(os.path.dirname(__file__), c)
                if os.path.isfile(caminho_teste):
                    pdf_alvo = caminho_teste
                    break
                    
        if pdf_alvo:
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

    # Verifica se há arquivos anexados
    if not message.attachments:
        embed_aviso = discord.Embed(
            title="🤖 Olá! Sou a SofIA, sua assistente do Contas a Pagar e Receber.",
            description=(
                "Como posso ajudar?\n\n"
                "• **Para Boletos / GNRE / Holerite:** envie `@SofIA lance este pagamento` e **anexe o PDF**.\n"
                "• **Para Vale Refeição (VR):** basta pedir `@SofIA faça o VR de outubro` (lido da planilha de VR).\n"
                "• **Para Adiantamento Salarial:** basta pedir `@SofIA lance adiantamento filial 601` ou anexe o PDF.\n"
                "• **Para Folha de Pagamento:** basta pedir `@SofIA lance pagamento filial 601` ou anexe o PDF.\n"
                "• **Para Contas a Pagar do Dia:** basta pedir `@SofIA contas a pagar de hoje` ou `@SofIA contas a pagar 03/07/2026` para receber o PDF oficial.\n"
                "• **Para Contas a Receber do Dia:** basta pedir `@SofIA contas a receber de hoje` ou `@SofIA recebimentos do dia` para receber o PDF oficial.\n"
                "• **Para Pagamento Avulso (PIX):** envie `@SofIA lance pagamento avulso para NOME, valor 760, filial 429, ref MANUTENÇÃO, vencimento hoje`.\n"
                "• **Para Alteração de Título:** envie `@SofIA altere o plano de contas do favorecido EDUARDO LAURINDO para 41038` ou `altere a data de vencimento do favorecido NOME para 01/10/2026`.\n"
                "• **Para Alteração em Lote:** envie `@SofIA altere a data de vencimento de TODOS os favorecidos de HOJE para 01/10/2026`.\n"
                "• **Para Histórico de Lotes:** basta pedir `@SofIA historico` para ver os últimos lançamentos em lote."
            ),
            color=discord.Color.blue()
        )
        await message.reply(embed=embed_aviso)
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
