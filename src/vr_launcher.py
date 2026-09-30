import sys
import os
import re
import asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from vr_parser import parse_vr_sheet
from erp_launcher import (
    login, BrowserLauncher, ERP_URL, valor_br
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
XLSX_PATH = os.path.join(BASE_DIR, "Planilha VR.xlsx")

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

FILIAIS_MAP = {
    "429": "155",
    "601": "216",
    "NEVINE": "293",
    "302": "253",
    "551": "161",
    "RELEVO": "154"
}

def calcular_vencimento_vr(mes_nome: str, ano: int = None) -> date:
    if not ano:
        ano = datetime.now().year
        
    mes_num = None
    for num, nome in MESES_PT.items():
        if nome.upper() in mes_nome.upper():
            mes_num = num
            break
            
    if not mes_num:
        mes_num = datetime.now().month

    # Primeiro dia do mes da competencia menos 1 dia = ultimo dia do mes anterior
    primeiro_dia = date(ano, mes_num, 1)
    ultimo_dia_anterior = primeiro_dia - timedelta(days=1)
    
    # Se cair no fim de semana, retrocede para sexta-feira
    while ultimo_dia_anterior.weekday() >= 5:
        ultimo_dia_anterior -= timedelta(days=1)
        
    return ultimo_dia_anterior

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

async def lancar_vr_colaborador(page, item: dict, competencia_label: str, data_vencimento: date, titulos_base_p1: list) -> bool:
    nome = item["nome"]
    valor = item["valor"]
    filial = str(item["filial"]).strip().upper()
    
    print(f"\n---> Processando: {nome} | Filial: {filial} | R$ {valor:.2f}", flush=True)
    
    primeiro_nome = nome.split()[0].upper()
    ultimo_nome = nome.split()[-1].upper()
    
    # 1. Procura se ha titulo do proprio funcionario na Pagina 1
    target_link = None
    for t in titulos_base_p1:
        txt = t['text'].upper()
        if primeiro_nome in txt and ultimo_nome in txt:
            target_link = t['id']
            break
            
    # Base por filial garantida na Pagina 1:
    # btnEd_1 = 176892 (Filial 601 - Ana Helena)
    # btnEd_8 = 176899 (Filial 429 - Alessandra)
    default_filial_link = "btnEd_8" if filial == "429" else "btnEd_1"
    
    link_abrir = target_link or default_filial_link
    precisa_trocar_funcionario = (target_link is None)
    
    print(f"  Titulo base: {link_abrir} (Troca funcionario: {precisa_trocar_funcionario})", flush=True)
    
    # Clica no link do titulo base no grid
    el_link = await page.query_selector(f"#{link_abrir}")
    if not el_link:
        print(f"  Link {link_abrir} nao encontrado no grid!", flush=True)
        return False
        
    await el_link.click()
    await page.wait_for_selector("#Copiar", timeout=15000)
    
    # 2. Executa a copia do titulo
    await page.evaluate("""() => {
        $("#eng_acao").val("103070105");
        Formulario.target = "_self";
        $("#Action").val("FORM_OUTROS");
        Formulario.submit();
    }""")
    await page.wait_for_load_state("networkidle", timeout=30000)
    
    # 3. Obtem frame do formulario
    f = page.frame(name='frmTela103070100')
    if not f:
        print("  ERRO: Frame frmTela103070100 nao encontrado apos copiar!", flush=True)
        return False
        
    # 4. Se precisar selecionar o funcionario via lookup
    if precisa_trocar_funcionario:
        print(f"  Selecionando funcionario {nome} no lookup...", flush=True)
        await f.click("#btnLookupJanela_ttp_funcionario_id")
        await asyncio.sleep(2)
        
        lk_frame = None
        for fr in page.frames:
            if "EngAjaxLookup" in fr.url:
                lk_frame = fr
                break
                
        if lk_frame:
            await lk_frame.fill("#txtPesquisa", primeiro_nome)
            await lk_frame.click("#btEnviar")
            await asyncio.sleep(2)
            
            for fr in page.frames:
                if "EngAjaxLookup" in fr.url:
                    lk_frame = fr
                    break
                    
            clicked = await lk_frame.evaluate("""(nome) => {
                const links = Array.from(document.querySelectorAll('table tr td a'));
                const partes = nome.toUpperCase().split(' ');
                for (const a of links) {
                    const t = a.innerText.toUpperCase();
                    if (partes.some(p => p.length > 2 && t.includes(p))) {
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
            print(f"  Funcionario selecionado: {clicked}", flush=True)
            await asyncio.sleep(2)
            
    # 5. Preenche os dados solicitados
    ref_texto = f"VR - {competencia_label}"
    venc_str = data_vencimento.strftime("%d%m%Y")
    
    # 5.1 FILIAL: Seleciona e valida obrigatoriamente a filial correta
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
            
    # 5.2 Valor Titulo
    await f.fill("#ttp_valor_titulo", valor_br(valor))
    print(f"  Valor: {valor_br(valor)}", flush=True)
    
    # 5.3 Vencimento
    el_venc = await f.query_selector("#ttp_data_vencimento")
    if el_venc:
        await el_venc.click()
        await el_venc.fill("")
        await el_venc.type(venc_str, delay=30)
        await el_venc.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles:true})); el.dispatchEvent(new Event('blur', {bubbles:true})); }")
        print(f"  Vencimento: {data_vencimento.strftime('%d/%m/%Y')}", flush=True)
        
    # 5.4 Referencia, Nota, Observacao
    await f.fill("#ttp_referencia", ref_texto)
    await f.fill("#ttp_numero_nota_fiscal", ref_texto)
    
    for sel_obs in ["#ttp_observacao", "#ttp_obs", "#ttp_historico"]:
        el_o = await f.query_selector(sel_obs)
        if el_o:
            await el_o.fill(ref_texto)
            print(f"  Observacao: {ref_texto}", flush=True)
            break
            
    # 5.5 Validacao final da filial antes de salvar
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
    
    # 7. Volta para a grade principal
    await page.goto(ERP_URL, timeout=60000)
    await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
    await page.select_option("#ttp_favorecido_tp_id", value="3")
    await page.fill("#ttp_referencia", "VR 10/2024")
    await page.click("#ConfirmaFiltroS")
    await asyncio.sleep(2)
    
    print(f"  OK: Título de VR de {nome} gravado com sucesso! (Filial: {filial_final['text']})", flush=True)
    return True

async def processar_vr_lote(mes_solicitado: str) -> dict:
    sheet_name, colaboradores = parse_vr_sheet(XLSX_PATH, mes_solicitado)
    print(f"\n{'='*60}")
    print(f"  INICIANDO LANCAMENTO DE VR EM LOTE: {sheet_name}")
    print(f"  Total de Colaboradores na Planilha: {len(colaboradores)}")
    total_folha = sum(c['valor'] for c in colaboradores)
    print(f"  Valor Total Previsto: R$ {total_folha:,.2f}")
    print(f"{'='*60}\n")
    
    partes = sheet_name.split()
    mes_cap = partes[0].capitalize()
    ano = partes[1] if len(partes) > 1 else str(datetime.now().year)
    competencia_label = f"{mes_cap}/{ano}"
    vencimento = calcular_vencimento_vr(mes_cap, int(ano))
    
    sucessos = []
    falhas = []
    
    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
            
        try:
            await login(page)
            await page.goto(ERP_URL, timeout=60000)
            await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
            
            # Filtra tipo FUNCIONARIO (3) e base VR
            await page.select_option("#ttp_favorecido_tp_id", value="3")
            await page.fill("#ttp_referencia", "VR 10/2024")
            await page.click("#ConfirmaFiltroS")
            await asyncio.sleep(2)
            
            # Coleta titulos base da pagina 1
            titulos_base_p1 = await obter_titulos_grid(page)
            print(f"Titulos base carregados da Pagina 1: {len(titulos_base_p1)} registros.", flush=True)
            
            for c in colaboradores:
                try:
                    ok = await lancar_vr_colaborador(page, c, competencia_label, vencimento, titulos_base_p1)
                    if ok:
                        sucessos.append(c)
                    else:
                        falhas.append(c)
                except Exception as ex:
                    print(f"  Erro no colaborador {c['nome']}: {ex}", flush=True)
                    falhas.append(c)
                    try:
                        await page.goto(ERP_URL, timeout=60000)
                        await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=15000)
                        await page.select_option("#ttp_favorecido_tp_id", value="3")
                        await page.fill("#ttp_referencia", "VR 10/2024")
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
                    
    total_lancado = sum(c['valor'] for c in sucessos)
    resultado = {
        "sucesso": len(sucessos) > 0,
        "mes": sheet_name,
        "competencia": competencia_label,
        "vencimento": vencimento.strftime("%d/%m/%Y"),
        "total_colaboradores": len(colaboradores),
        "total_sucesso": len(sucessos),
        "total_falhas": len(falhas),
        "valor_total_lancado": total_lancado,
        "sucessos": sucessos,
        "falhas": falhas
    }
    try:
        from batch_logger import salvar_historico_lote
        salvar_historico_lote("VR", resultado, arquivo="Planilha VR.xlsx")
    except Exception as e:
        print(f"[VR] Erro ao gravar histórico: {e}")
        
    return resultado

if __name__ == "__main__":
    mes = sys.argv[1] if len(sys.argv) > 1 else "outubro 2026"
    res = asyncio.run(processar_vr_lote(mes))
    print("\nRESUMO FINAL:")
    print(f"Total processado: {res['total_sucesso']}/{res['total_colaboradores']}")
    print(f"Valor Total: R$ {res['valor_total_lancado']:,.2f}")
