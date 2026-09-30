"""
====================================================================
  MÓDULO DE PAGAMENTO AVULSO NO ERP ADMSIS (Playwright RPA)
====================================================================
Fluxo para pagamentos via PIX ou transferências sem boleto/título prévio:
  1. Acessa a tela 0103070100 (Títulos a Pagar).
  2. Localiza o favorecido/fornecedor via lookup (EngAjaxLookup).
  3. Filtra o grid de títulos do favorecido (#ConfirmaFiltroS).
  4. Identifica o último título realizado para ele.
  5. Clica em 'Copiar Título' (#Copiar) para herdar plano de contas e impostos.
  6. Altera os campos obrigatórios:
     - Valor (#ttp_valor_titulo)
     - Filial (#ttp_filial_id)
     - Referência (#ttp_referencia)
     - Data de Vencimento (#ttp_data_vencimento)
     - Observação (#ttp_historico - somente se solicitada; caso contrário, mantém como está)
  7. Grava o novo título (#AlterarI).
  8. Registra no histórico estruturado (data/batch_history.json).
"""

import os
import sys
import re
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from erp_launcher import (
    login, BrowserLauncher, ERP_URL, close_modal, valor_br, click_alterar
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

FILIAIS_MAP = {
    "429": "155",
    "601": "216",
    "NEVINE": "293",
    "302": "253",
    "551": "161",
    "RELEVO": "154"
}

def parse_avulso_command(texto: str) -> Dict[str, Any]:
    """
    Interpreta os parâmetros de um comando de pagamento avulso enviado pelo usuário.
    Retorna os dados identificados e a lista de campos faltantes obrigatórios.
    """
    dados = {
        "fornecedor": None,
        "valor": None,
        "filial": None,
        "referencia": None,
        "vencimento": None,
        "vencimento_str": None,
        "observacao": None,
        "campos_faltantes": []
    }
    
    t = texto.strip()

    # 1. Favorecido / Fornecedor
    m_forn = re.search(r"(?:para|favorecido|fornecedor|a favor de)\s+([^,;\n]+?)(?:\s*,|\s+valor|\s+filial|\s+ref|\s+vencimento|$)", t, re.IGNORECASE)
    if m_forn:
        dados["fornecedor"] = m_forn.group(1).strip()
    else:
        # Fallback: tenta capturar após "avulso"
        m_av = re.search(r"avulso\s+([A-ZÀ-Úa-zà-ú\s]+?)(?:\s*,|\s+valor|\s+\d+|\s+filial|$)", t, re.IGNORECASE)
        if m_av:
            candidato = m_av.group(1).strip()
            if candidato.lower() not in ["para", "de", "do"]:
                dados["fornecedor"] = candidato

    # 2. Valor
    m_val = re.search(r"(?:valor|quantia|total)\s*[:=]?\s*r?\$?\s*(\d+(?:[.,]\d{1,2})?)\b", t, re.IGNORECASE)
    if not m_val:
        m_val = re.search(r"r\$\s*(\d+(?:[.,]\d{1,2})?)\b", t, re.IGNORECASE)
    if m_val:
        v_str = m_val.group(1).replace(".", "").replace(",", ".")
        try:
            dados["valor"] = float(v_str)
        except ValueError:
            pass

    # 3. Filial
    m_fil = re.search(r"\bfilial\s*[:=]?\s*(\d{3}|nevine|relevo)\b", t, re.IGNORECASE)
    if m_fil:
        dados["filial"] = m_fil.group(1).upper()
    else:
        for f_cand in ["429", "601", "302", "551", "nevine", "relevo"]:
            if f_cand in t.lower():
                dados["filial"] = f_cand.upper()
                break
    if not dados["filial"]:
        dados["filial"] = os.getenv("FILIAL_PADRAO", "429")

    # 4. Referência (Obrigatório)
    m_ref = re.search(r"(?:ref|referencia|referência|nf|documento)\s*[:=]?\s*([^,;\n]+?)(?:\s*,|\s+vencimento|\s+obs|\s+observacao|$)", t, re.IGNORECASE)
    if m_ref:
        dados["referencia"] = m_ref.group(1).strip()

    # 5. Data de Vencimento (Obrigatório)
    if "hoje" in t.lower():
        dados["vencimento"] = date.today()
        dados["vencimento_str"] = dados["vencimento"].strftime("%d/%m/%Y")
    elif "amanhã" in t.lower() or "amanha" in t.lower():
        dados["vencimento"] = date.today() + timedelta(days=1)
        dados["vencimento_str"] = dados["vencimento"].strftime("%d/%m/%Y")
    elif "ontem" in t.lower():
        dados["vencimento"] = date.today() - timedelta(days=1)
        dados["vencimento_str"] = dados["vencimento"].strftime("%d/%m/%Y")
    else:
        m_data = re.search(r"(?:vencimento|vence|data|para o dia)?\s*[:=]?\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", t, re.IGNORECASE)
        if m_data:
            d, m, y = m_data.groups()
            if len(y) == 2:
                y = f"20{y}"
            try:
                dados["vencimento"] = date(int(y), int(m), int(d))
                dados["vencimento_str"] = dados["vencimento"].strftime("%d/%m/%Y")
            except ValueError:
                pass

    # 6. Observação (Opcional - se ausente, mantém o título copiado como está)
    m_obs = re.search(r"(?:obs|observacao|observação|historico|histórico)\s*[:=]?\s*(.+)$", t, re.IGNORECASE)
    if m_obs:
        dados["observacao"] = m_obs.group(1).strip()

    # Validação de campos faltantes obrigatórios
    if not dados["fornecedor"]:
        dados["campos_faltantes"].append("fornecedor")
    if not dados["valor"] or dados["valor"] <= 0:
        dados["campos_faltantes"].append("valor")
    # Referência agora é opcional no comando: se não informada, herda da cópia avançando o mês
    if not dados["vencimento"]:
        dados["campos_faltantes"].append("vencimento")

    return dados

async def selecionar_fornecedor_lookup(page, termo_busca: str) -> bool:
    """Abre o lookup de fornecedor na tela 0103070100 e seleciona o registro no EngAjaxLookup."""
    print(f"  [Avulso] Abrindo lookup para pesquisar: '{termo_busca}'...", flush=True)
    
    # 1. Clica no botão de lookup
    lookup_btn = None
    for sel in ["#btnLookupJanela_ttp_fornecedor_id", "button[id*='LookupJanela'][id*='fornecedor']"]:
        b = await page.query_selector(sel)
        if b and await b.is_visible():
            lookup_btn = b
            break
            
    if lookup_btn:
        await lookup_btn.click()
    else:
        # Fallback: clica pelo evaluate
        await page.evaluate("""() => {
            const btn = document.querySelector('#btnLookupJanela_ttp_fornecedor_id') || document.querySelector("button[id*='Lookup']");
            if (btn) btn.click();
        }""")
        
    await asyncio.sleep(2)
    
    # 2. Localiza o frame EngAjaxLookup
    lk_frame = None
    for _ in range(20):
        for f in page.frames:
            if "EngAjaxLookup" in f.url or "eng-lookup" in f.name:
                try:
                    inp = await f.query_selector("#txtPesquisa")
                    if inp:
                        lk_frame = f
                        break
                except:
                    pass
        if lk_frame:
            break
        await asyncio.sleep(0.5)
        
    if not lk_frame:
        print("  [Avulso] ERRO: Frame de lookup EngAjaxLookup não carregou!", flush=True)
        return False
        
    # 3. Pesquisa o fornecedor
    primeiro_termo = termo_busca.split()[0] if termo_busca else termo_busca
    termos = [termo_busca, primeiro_termo]
    
    for t_pesq in termos:
        print(f"  [Avulso] Pesquisando '{t_pesq}' no lookup...", flush=True)
        try:
            await lk_frame.fill("#txtPesquisa", "")
            await asyncio.sleep(0.2)
            await lk_frame.fill("#txtPesquisa", t_pesq)
            await asyncio.sleep(0.3)
            # Submete a pesquisa evitando o input hidden id="btEnviar"
            submetido = False
            for sel_btn in ["button#btEnviar", "input[type='submit']", "button[type='submit']", "button:has-text('Pesquisar')"]:
                try:
                    btn_pesq = await lk_frame.query_selector(sel_btn)
                    if btn_pesq and await btn_pesq.is_visible():
                        await btn_pesq.click(timeout=3000, force=True, no_wait_after=True)
                        submetido = True
                        break
                except:
                    pass
            if not submetido:
                await lk_frame.evaluate("() => { if(window.Pesquisa && Pesquisa.submit) { Pesquisa.submit(); } else { const b = document.querySelector('input[type=\"submit\"], button#btEnviar, button[type=\"submit\"]'); if(b) b.click(); } }")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"  [Avulso] Erro ao submeter pesquisa: {e}", flush=True)
            continue
        
        # 4. Procura linha correspondente
        rows = await lk_frame.query_selector_all("table tr")
        print(f"  [Avulso] Linhas encontradas no lookup: {len(rows)}", flush=True)
        
        for tr in rows:
            text = (await tr.inner_text()).upper()
            if termo_busca.upper() in text or primeiro_termo.upper() in text:
                chk = await tr.query_selector("input.eng-lookup-multi-chk")
                if chk:
                    print(f"  [Avulso] Fornecedor selecionado: {text[:60]}", flush=True)
                    await chk.check()
                    await asyncio.sleep(0.5)
                    btn_conf = await lk_frame.query_selector("#btConfirmarSelecao")
                    if btn_conf:
                        try:
                            await btn_conf.click(timeout=5000, force=True, no_wait_after=True)
                        except Exception:
                            await lk_frame.evaluate("() => { const b = document.querySelector('#btConfirmarSelecao'); if(b) b.click(); }")
                        await asyncio.sleep(1.5)
                        await close_modal(page)
                        return True
                        
                # Fallback: link Selecionar(id)
                links = await tr.query_selector_all("a[href*='Selecionar']")
                for a in links:
                    href = await a.get_attribute("href") or ""
                    m = re.search(r"Selecionar\((\d+)\)", href)
                    if m and m.group(1) != "-1":
                        await lk_frame.evaluate(f"Selecionar({m.group(1)})")
                        print(f"  [Avulso] Selecionado via JS: {m.group(1)}", flush=True)
                        await asyncio.sleep(1.5)
                        await close_modal(page)
                        return True

    await close_modal(page)
    return False

async def lancar_pagamento_avulso(
    fornecedor: str,
    valor: float,
    filial: str,
    referencia: str,
    vencimento: date,
    observacao: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa o fluxo completo de pagamento avulso no ERP ADMSIS:
    1. Pesquisa e seleciona o fornecedor.
    2. Filtra o grid.
    3. Abre o último título feito e clica em Copiar Título.
    4. Preenche valor, filial, referência, vencimento e observação.
    5. Grava com 'Alterar'.
    """
    print(f"\n{'='*65}")
    print(f"  INICIANDO LANÇAMENTO DE PAGAMENTO AVULSO")
    print(f"  Favorecido : {fornecedor}")
    print(f"  Valor      : R$ {valor:,.2f}")
    print(f"  Filial     : {filial}")
    print(f"  Referência : {referencia}")
    print(f"  Vencimento : {vencimento.strftime('%d/%m/%Y')}")
    print(f"  Observação : {observacao if observacao else '(Manter original da cópia)'}")
    print(f"{'='*65}\n")
    
    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        # Aceita automaticamente diálogos nativos do navegador (alert/confirm)
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
        
        try:
            # 1. Login no ERP
            await login(page)
            await page.goto(ERP_URL, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=20000)
            
            # 2. Seleciona o fornecedor no Lookup
            ok_lk = await selecionar_fornecedor_lookup(page, fornecedor)
            if not ok_lk:
                return {
                    "sucesso": False,
                    "mensagem": f"Não foi possível localizar o fornecedor '{fornecedor}' no cadastro do ERP ADMSIS."
                }
                
            # 3. Clica em Filtrar (#ConfirmaFiltroS / fa-filter)
            print("  [Avulso] Clicando em Filtrar (#ConfirmaFiltroS)...", flush=True)
            try:
                await page.click("#ConfirmaFiltroS", timeout=10000, force=True, no_wait_after=True)
            except:
                await page.evaluate("() => { const b = document.querySelector('#ConfirmaFiltroS'); if(b) b.click(); }")
                
            await asyncio.sleep(3)

            # Ordena por Código Decrescente (ttp_id DESC) para garantir que o primeiro registro seja o mais recente
            print("  [Avulso] Ordenando grid por Código Decrescente (ttp_id DESC) para obter o último título...", flush=True)
            try:
                await page.evaluate("""() => {
                    if (window.$ && $('#order_by').length && window.EngNavegacao) {
                        $('#order_by').val('ttp_id DESC');
                        EngNavegacao.refresh();
                    }
                }""")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"  [Avulso] Aviso ao ordenar grid: {e}", flush=True)
            
            # 4. Verifica se existem títulos no grid para duplicar
            edit_links = await page.query_selector_all("a[id^='btnEd_']")
            if not edit_links:
                await page.screenshot(path=os.path.join(LOG_DIR, "erro_avulso_grid_vazio.png"))
                return {
                    "sucesso": False,
                    "mensagem": f"O fornecedor '{fornecedor}' foi selecionado, mas não possui nenhum título anterior no sistema para ser copiado. É necessário cadastrar ao menos um título base para permitir a clonagem automática."
                }
                
            # 5. O primeiro registro da lista ordenada DESC é o mais recente / último título feito
            ultimo_titulo_link = edit_links[0]
            link_id = await ultimo_titulo_link.get_attribute("id")
            print(f"  [Avulso] Último título localizado no grid: {link_id}. Abrindo...", flush=True)
            try:
                await ultimo_titulo_link.click(timeout=8000, force=True, no_wait_after=True)
            except Exception:
                await page.evaluate(f"() => {{ const el = document.getElementById('{link_id}'); if(el) el.click(); }}")
            await asyncio.sleep(2)
            
            # 6. Aguarda o botão Copiar Título
            btn_copiar = await page.wait_for_selector("#Copiar", timeout=15000)
            if not btn_copiar:
                return {
                    "sucesso": False,
                    "mensagem": "Botão 'Copiar Título' (#Copiar) não foi encontrado no formulário do ERP."
                }
                
            print("  [Avulso] Acionando 'Copiar Título'...", flush=True)
            try:
                await btn_copiar.click(timeout=5000, force=True, no_wait_after=True)
            except Exception:
                await page.evaluate("() => { const b = document.querySelector('#Copiar'); if(b) b.click(); }")
            
            # Confirma diálogo de cópia ("Sim")
            for sel in ['button:has-text("Sim")', 'button:has-text("OK")', 'button:has-text("Confirmar")', 'input[value="Sim"]']:
                try:
                    b_conf = await page.wait_for_selector(sel, timeout=3000)
                    if b_conf and await b_conf.is_visible():
                        await b_conf.click(timeout=3000, force=True, no_wait_after=True)
                        print(f"  [Avulso] Diálogo de cópia confirmado ({sel})", flush=True)
                        break
                except:
                    pass
                    
            await asyncio.sleep(2)
            
            # 7. Identifica frame de edição (frmTela103070100 ou página principal)
            f = page.frame(name='frmTela103070100') or page
            
            # 8. Preenchimento dos campos variáveis
            # 8.1 Valor do Título
            val_formatado = valor_br(valor)
            await f.fill("#ttp_valor_titulo", val_formatado)
            await f.evaluate("() => { const el = document.querySelector('#ttp_valor_titulo'); if(el) el.dispatchEvent(new Event('change', {bubbles: true})); }")
            print(f"  [Avulso] Valor preenchido: R$ {val_formatado}", flush=True)
            
            # 8.2 Filial
            val_filial = FILIAIS_MAP.get(filial.upper())
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
                    print(f"  [Avulso] Filial preenchida: {filial} (código {val_filial})", flush=True)
                except Exception as e:
                    print(f"  [Avulso] Aviso ao preencher filial: {e}", flush=True)
                    
            # 8.3 Referência (Se informada, usa; se ausente, herda da cópia e avança o mês)
            ref_final = referencia
            if not ref_final or ref_final.upper() == "REF-AUTO":
                try:
                    ref_herdada = (await f.input_value("#ttp_referencia") or "").strip()
                    if ref_herdada and ref_herdada.upper() != "REF-AUTO":
                        from erp_launcher import avancar_mes_referencia
                        ref_final = avancar_mes_referencia(ref_herdada)
                        print(f"  [Avulso] Referência herdada '{ref_herdada}' -> Atualizada para próximo mês: '{ref_final}'", flush=True)
                except Exception as e:
                    print(f"  [Avulso] Aviso ao ler referência herdada: {e}", flush=True)

            if not ref_final:
                ref_final = f"PAGAMENTO AVULSO - {datetime.now().strftime('%m/%Y')}"

            await f.fill("#ttp_referencia", ref_final)
            await f.evaluate("() => { const el = document.querySelector('#ttp_referencia'); if(el) el.dispatchEvent(new Event('change', {bubbles: true})); }")
            print(f"  [Avulso] Referência preenchida: {ref_final}", flush=True)
            
            # 8.4 Data de Vencimento (Obrigatório)
            venc_formatado = vencimento.strftime("%d/%m/%Y")
            try:
                el_venc = await f.query_selector("#ttp_data_vencimento")
                if el_venc:
                    await el_venc.fill(venc_formatado)
                    await el_venc.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles:true})); el.dispatchEvent(new Event('blur', {bubbles:true})); }")
            except Exception:
                await f.evaluate("""(v) => {
                    const el = document.querySelector('#ttp_data_vencimento');
                    if (el) {
                        el.value = v;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new Event('blur', {bubbles: true}));
                    }
                }""", venc_formatado)
            print(f"  [Avulso] Vencimento preenchido: {venc_formatado}", flush=True)
                
            # 8.5 Observação (Opcional - se informada, altera; se ausente, mantém como está)
            if observacao:
                for sel_obs in ["#ttp_historico", "#ttp_observacao", "#ttp_obs"]:
                    try:
                        el_o = await f.query_selector(sel_obs)
                        if el_o:
                            await el_o.fill(observacao)
                            print(f"  [Avulso] Observação atualizada: {observacao}", flush=True)
                            break
                    except:
                        pass
            else:
                print("  [Avulso] Observação não informada no chat; mantendo valor original herdado da cópia.", flush=True)
                
            # 9. Gravar com 'Alterar' (#AlterarI)
            print("  [Avulso] Clicando em Gravar / Alterar...", flush=True)
            saved = await click_alterar(f, page)
            if not saved:
                try:
                    await f.evaluate("() => { const b = document.querySelector('#AlterarI') || document.querySelector('button[id*=\"Alterar\"]'); if(b) b.click(); }")
                    saved = True
                    await asyncio.sleep(2)
                except Exception:
                    pass
                    
            if not saved:
                return {
                    "sucesso": False,
                    "mensagem": "Botão de gravação ('Alterar') não encontrado no formulário clonado."
                }
                    
            await asyncio.sleep(3)
            
            # 10. Registra no histórico estruturado
            resumo_execucao = {
                "fornecedor": fornecedor,
                "valor": valor,
                "filial": filial,
                "referencia": ref_final,
                "vencimento": vencimento.strftime("%d/%m/%Y"),
                "observacao": observacao or "Original mantida",
                "total_colaboradores": 1,
                "total_sucesso": 1,
                "total_falhas": 0,
                "valor_total_lancado": valor,
                "sucessos": [{"fornecedor": fornecedor, "valor": valor, "filial": filial}],
                "falhas": []
            }
            
            try:
                from batch_logger import salvar_historico_lote
                salvar_historico_lote("PAGAMENTO_AVULSO", resumo_execucao, arquivo="Discord / Avulso")
            except Exception as e:
                print(f"  [Avulso] Erro ao gravar histórico: {e}", flush=True)

            print(f"\n[OK] Pagamento avulso de {fornecedor} (R$ {valor_br(valor)}) gravado com sucesso no ERP ADMSIS!\n")
            
            return {
                "sucesso": True,
                "fornecedor": fornecedor,
                "valor": valor,
                "valor_str": f"R$ {val_formatado}",
                "filial": filial,
                "referencia": ref_final,
                "vencimento": vencimento.strftime("%d/%m/%Y"),
                "observacao": observacao or "(Mantida do título base clonado)",
                "mensagem": "Pagamento avulso gravado com sucesso no ERP ADMSIS."
            }
            
        except Exception as exc:
            await page.screenshot(path=os.path.join(LOG_DIR, "erro_pagamento_avulso.png"))
            print(f"  [Avulso] ERRO INESPERADO: {exc}", flush=True)
            return {
                "sucesso": False,
                "mensagem": f"Falha na execução do pagamento avulso: {str(exc)}"
            }
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
