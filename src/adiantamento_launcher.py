import sys
import os
import re
import asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from pdf_parser import extract_invoice_data
from erp_launcher import (
    login, BrowserLauncher, ERP_URL, valor_br
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

FILIAIS_MAP = {
    "429": "155",
    "601": "216",
    "NEVINE": "293",
    "302": "253",
    "551": "161",
    "RELEVO": "154"
}

# Títulos padrão de Adiantamento por filial no grid inicial
DEFAULT_FILIAL_LINKS = {
    "601": "btnEd_4",     # Ana Helena (601)
    "NEVINE": "btnEd_1",  # Poliane (Nevine)
    "429": "btnEd_11",    # Alessandra (429)
}

async def obter_titulos_grid(page):
    return await page.evaluate("""() => {
        const trs = Array.from(document.querySelectorAll('table tbody tr'));
        return trs.map(tr => {
            const link = tr.querySelector('a[id^="btnEd_"]');
            return {
                id: link ? link.id : null,
                text: tr.innerText.replace(/\\s+/g, ' ').trim()
            };
        }).filter(r => r.id);
    }""")

async def lancar_adiantamento_colaborador(page, item: dict, competencia_label: str, data_vencimento: date, titulos_base_p1: list) -> bool:
    nome = item.get("fornecedor") or item.get("nome")
    valor = item["valor"]
    filial = str(item.get("filial", "429")).strip().upper()
    
    print(f"\n---> [Adiantamento] Processando: {nome} | Filial: {filial} | R$ {valor:.2f}", flush=True)
    
    partes_nome = nome.split()
    primeiro_nome = partes_nome[0].upper()
    ultimo_nome = partes_nome[-1].upper() if len(partes_nome) > 1 else primeiro_nome
    
    # 1. Procura se há título do próprio funcionário na Página 1
    target_link = None
    for t in titulos_base_p1:
        txt = t['text'].upper()
        if primeiro_nome in txt and ultimo_nome in txt:
            target_link = t['id']
            break
            
    default_link = DEFAULT_FILIAL_LINKS.get(filial, "btnEd_4")
    link_abrir = target_link or default_link
    precisa_trocar_funcionario = (target_link is None)
    
    print(f"  Título base utilizado: {link_abrir} (Troca funcionário: {precisa_trocar_funcionario})", flush=True)
    
    # Clica no link do título base no grid
    el_link = await page.query_selector(f"#{link_abrir}")
    if not el_link:
        print(f"  Link {link_abrir} não encontrado no grid!", flush=True)
        return False
        
    await el_link.click()
    await page.wait_for_selector("#Copiar", timeout=15000)
    
    # 2. Executa a cópia do título (ação 103070105)
    await page.evaluate("""() => {
        $("#eng_acao").val("103070105");
        Formulario.target = "_self";
        $("#Action").val("FORM_OUTROS");
        Formulario.submit();
    }""")
    await page.wait_for_load_state("networkidle", timeout=30000)
    
    # 3. Obtém frame do formulário
    f = page.frame(name='frmTela103070100')
    if not f:
        print("  ERRO: Frame frmTela103070100 não encontrado após copiar!", flush=True)
        return False
        
    # 4. Se precisar selecionar o funcionário via lookup
    if precisa_trocar_funcionario:
        print(f"  Selecionando funcionário {nome} no lookup...", flush=True)
        await f.click("#btnLookupJanela_ttp_funcionario_id")
        await asyncio.sleep(2)
        
        lk_frame = None
        for fr in page.frames:
            if "EngAjaxLookup" in fr.url:
                lk_frame = fr
                break
                
        if lk_frame:
            termo = f"{primeiro_nome} {ultimo_nome}" if primeiro_nome != ultimo_nome else primeiro_nome
            await lk_frame.fill("#txtPesquisa", termo)
            await lk_frame.click("#btEnviar")
            await asyncio.sleep(2)
            
            tem_resultados = await lk_frame.evaluate("() => document.querySelectorAll('table tr td a').length > 0")
            if not tem_resultados:
                await lk_frame.fill("#txtPesquisa", primeiro_nome)
                await lk_frame.click("#btEnviar")
                await asyncio.sleep(2)
            
            for fr in page.frames:
                if "EngAjaxLookup" in fr.url:
                    lk_frame = fr
                    break
                    
            clicked = await lk_frame.evaluate("""(nome) => {
                const links = Array.from(document.querySelectorAll('table tr td a'));
                const partes = nome.toUpperCase().split(' ').filter(p => p.length > 2);
                const primeiro = partes[0];
                const ultimo = partes[partes.length - 1];
                
                // Prioridade 1: Contém primeiro e último nome
                for (const a of links) {
                    const t = a.innerText.toUpperCase();
                    if (t.includes(primeiro) && t.includes(ultimo)) {
                        a.click();
                        return a.innerText;
                    }
                }
                // Prioridade 2: Contém o primeiro nome como palavra inteira
                const regexPrim = new RegExp('\\\\b' + primeiro + '\\\\b');
                for (const a of links) {
                    const t = a.innerText.toUpperCase();
                    if (regexPrim.test(t)) {
                        a.click();
                        return a.innerText;
                    }
                }
                if (links.length > 0) {
                    links[0].click();
                    return links[0].innerText;
                }
                return null;
            }""", nome)
            print(f"  Funcionário selecionado no lookup: {clicked}", flush=True)
            await asyncio.sleep(2)
            
            # Garante que o backdrop e modal fecharam completamente
            try:
                await page.evaluate("""() => {
                    const m = document.querySelector('#eng-lookup-janela');
                    if (m) {
                        m.style.display = 'none';
                        m.classList.remove('in');
                    }
                    const b = document.querySelector('.modal-backdrop');
                    if (b) b.remove();
                }""")
            except:
                pass
            await asyncio.sleep(1)
            
    # 5. Preenchimento e Blindagem dos Campos
    ref_texto = f"Adiantamento de Salário - {competencia_label}"
    venc_str = data_vencimento.strftime("%d%m%Y")
    
    # 5.1 FILIAL: Seleciona e valida com blindagem absoluta
    val_filial = FILIAIS_MAP.get(filial)
    if val_filial:
        try:
            await f.select_option("#ttp_filial_id", value=val_filial)
            await f.evaluate("""(val) => {
                const sel = document.querySelector('#ttp_filial_id');
                if (sel) {
                    sel.value = val;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", val_filial)
            print(f"  Filial configurada: {filial} (value={val_filial})", flush=True)
        except Exception as e:
            print(f"  Erro ao selecionar filial {filial}: {e}", flush=True)
            
    # 5.2 Valor do Título
    await f.fill("#ttp_valor_titulo", valor_br(valor))
    print(f"  Valor: {valor_br(valor)}", flush=True)
    
    # 5.3 Vencimento (dia 20)
    el_venc = await f.query_selector("#ttp_data_vencimento")
    if el_venc:
        try:
            await el_venc.click(force=True)
            await el_venc.fill("")
            await el_venc.type(venc_str, delay=30)
            await el_venc.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles:true})); el.dispatchEvent(new Event('blur', {bubbles:true})); }")
        except:
            await f.evaluate("""(venc) => {
                const el = document.querySelector('#ttp_data_vencimento');
                if (el) {
                    el.value = venc;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            }""", venc_str)
        print(f"  Vencimento: {data_vencimento.strftime('%d/%m/%Y')}", flush=True)
        
    # 5.4 Referência, Nota, Observação
    await f.fill("#ttp_referencia", ref_texto)
    await f.fill("#ttp_numero_nota_fiscal", ref_texto)
    
    for sel_obs in ["#ttp_observacao", "#ttp_obs", "#ttp_historico"]:
        el_o = await f.query_selector(sel_obs)
        if el_o:
            await el_o.fill(ref_texto)
            print(f"  Observação: {ref_texto}", flush=True)
            break
            
    # 5.5 Validação final da filial no DOM antes de salvar
    filial_final = await f.evaluate("""() => {
        const sel = document.querySelector('#ttp_filial_id');
        return {
            value: sel ? sel.value : null,
            text: sel ? sel.options[sel.selectedIndex]?.text : null
        };
    }""")
    print(f"  Filial conferida antes de gravar: {filial_final['text']} (value={filial_final['value']})", flush=True)
    
    # 6. Salvar (Alterar)
    btn_salvar = await f.query_selector("#AlterarI")
    if btn_salvar:
        await btn_salvar.click()
    else:
        await f.evaluate("() => EngNavegacao.alterar()")
    await asyncio.sleep(3)
    
    print(f"  OK: Título de Adiantamento de {nome} gravado com sucesso! (Filial: {filial_final['text']})", flush=True)

    # 7. Volta para a grade principal com filtro de Adiantamento ativo
    for tentativa in range(2):
        try:
            await page.goto(ERP_URL, timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
            await page.select_option("#ttp_favorecido_tp_id", value="3")
            await page.fill("#ttp_referencia", "Adiantamento")
            await page.click("#ConfirmaFiltroS")
            await asyncio.sleep(2)
            break
        except Exception as e_nav:
            print(f"  Aviso: tentativa {tentativa+1} de retorno a grade: {e_nav}", flush=True)
            await asyncio.sleep(2)
    
    return True

async def processar_adiantamento_pdf(pdf_path: str) -> dict:
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")
        
    colaboradores = extract_invoice_data(pdf_path)
    if not isinstance(colaboradores, list):
        colaboradores = [colaboradores]
        
    colaboradores = [c for c in colaboradores if c.get("fornecedor") and c.get("valor")]
    if not colaboradores:
        raise ValueError(f"Nenhum colaborador com valor válido encontrado no arquivo {os.path.basename(pdf_path)}")
        
    filial = colaboradores[0].get("filial", "429")
    competencia = colaboradores[0].get("competencia", "08/2026")
    vencimento = colaboradores[0].get("vencimento", date(2026, 8, 20))
    total_previsto = sum(c["valor"] for c in colaboradores)
    
    print(f"\n{'='*60}")
    print(f"  INICIANDO LANÇAMENTO DE ADIANTAMENTO EM LOTE")
    print(f"  Arquivo: {os.path.basename(pdf_path)}")
    print(f"  Filial: {filial} | Competência: {competencia} | Vencimento: {vencimento}")
    print(f"  Total de Colaboradores: {len(colaboradores)} | Total: R$ {total_previsto:,.2f}")
    print(f"{'='*60}\n")
    
    sucessos = []
    falhas = []
    
    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await login(page)
            await page.goto(ERP_URL, timeout=60000)
            await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
            
            # Filtra tipo FUNCIONARIO (3) e base Adiantamento
            await page.select_option("#ttp_favorecido_tp_id", value="3")
            await page.fill("#ttp_referencia", "Adiantamento")
            await page.click("#ConfirmaFiltroS")
            await asyncio.sleep(3)
            
            # Coleta títulos base da página 1
            titulos_base_p1 = await obter_titulos_grid(page)
            print(f"Títulos base carregados da Página 1: {len(titulos_base_p1)} registros.", flush=True)
            
            for c in colaboradores:
                try:
                    ok = await lancar_adiantamento_colaborador(page, c, competencia, vencimento, titulos_base_p1)
                    if ok:
                        sucessos.append(c)
                    else:
                        falhas.append(c)
                except Exception as ex:
                    print(f"  Erro no colaborador {c.get('fornecedor')}: {ex}", flush=True)
                    falhas.append(c)
                    try:
                        await page.goto(ERP_URL, timeout=60000)
                        await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
                        await page.select_option("#ttp_favorecido_tp_id", value="3")
                        await page.fill("#ttp_referencia", "Adiantamento")
                        await page.click("#ConfirmaFiltroS")
                        await asyncio.sleep(2)
                    except:
                        pass
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
                    
    valor_total_lancado = sum(s["valor"] for s in sucessos)
    print(f"\n{'='*60}")
    print(f"  RESUMO FINAL - ADIANTAMENTO ({competencia} - Filial {filial})")
    print(f"  Lançados com Sucesso: {len(sucessos)} / {len(colaboradores)}")
    print(f"  Total Financeiro Lançado: R$ {valor_total_lancado:,.2f}")
    if falhas:
        print(f"  Colaboradores com Falha ({len(falhas)}): {[f.get('fornecedor') for f in falhas]}")
    print(f"{'='*60}\n")
    
    resultado = {
        "arquivo": os.path.basename(pdf_path),
        "filial": filial,
        "competencia": competencia,
        "vencimento": vencimento.strftime("%d/%m/%Y") if hasattr(vencimento, "strftime") else str(vencimento),
        "total_colaboradores": len(colaboradores),
        "total_sucesso": len(sucessos),
        "total_falhas": len(falhas),
        "valor_total_lancado": valor_total_lancado,
        "sucessos": sucessos,
        "falhas": falhas
    }
    try:
        from batch_logger import salvar_historico_lote
        salvar_historico_lote("ADIANTAMENTO", resultado, arquivo=os.path.basename(pdf_path))
    except Exception as e:
        print(f"[Adiantamento] Erro ao gravar histórico: {e}")
        
    return resultado
