import sys, os, re, asyncio
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

USE_CAMOUFOX = os.getenv("USE_CAMOUFOX", "false").lower() in ("true", "1", "yes")
if USE_CAMOUFOX:
    from camoufox.async_api import AsyncCamoufox as BrowserLauncher
else:
    from playwright.async_api import async_playwright as BrowserLauncher

ERP_URL = os.getenv("ERP_URL", "https://erp.admsis.com/Home?eng_tela=0103070100")
USERNAME = os.getenv("ERP_USERNAME", "")
PASSWORD = os.getenv("ERP_PASSWORD", "")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

from erp_launcher import (
    login, poll_frame, find_lookup_frame, get_pesq_selector,
    navigate_to_grid, get_form_frame, fill_field, select_option_safe,
    valor_br, close_modal, click_copiar, fill_fields, click_alterar,
    attach_document, emitir_autorizacao_pagamento, filter_grid, find_column_idx
)

UF_NOME = {
    "PE": "PERNAMBUCO", "AL": "ALAGOAS", "RJ": "RIO DE JANEIRO",
    "RS": "RIO GRANDE DO SUL", "SC": "SANTA CATARINA", "DF": "DISTRITO FEDERAL",
    "SP": "SAO PAULO", "MG": "MINAS GERAIS", "BA": "BAHIA",
    "PR": "PARANA", "CE": "CEARA", "PA": "PARA",
    "MA": "MARANHAO", "GO": "GOIAS", "AM": "AMAZONAS",
    "ES": "ESPIRITO SANTO", "RN": "RIO GRANDE DO NORTE",
    "PB": "PARAIBA", "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL",
    "PI": "PIAUI", "RO": "RONDONIA", "SE": "SERGIPE",
    "TO": "TOCANTINS", "AC": "ACRE", "AP": "AMAPA", "RR": "RORAIMA",
}

async def select_supplier_in_lookup(page, fornecedor, uf):
    print("  Abrindo janela de lookup de fornecedor...", flush=True)
    for lk_sel in ["#btnLookupJanela_ttp_fornecedor_id", "button[id*='Lookup'][id*='fornecedor']", "button[id*='LookupJanela']"]:
        try:
            btn = await page.query_selector(lk_sel)
            if btn and await btn.is_visible():
                await btn.click(timeout=5000)
                print(f"  Botao lookup clicado: {lk_sel}", flush=True)
                break
        except:
            continue

    lk_frame = None
    for _ in range(30):
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
        print("  ERRO: Frame de lookup nao encontrado!", flush=True)
        return False

    estado = UF_NOME.get(uf.upper(), fornecedor.split()[-1])
    search_terms = [estado, uf]

    for term in search_terms:
        try:
            print(f"  Pesquisando termo no lookup: '{term}'...", flush=True)
            await lk_frame.fill("#txtPesquisa", "")
            await asyncio.sleep(0.2)
            await lk_frame.fill("#txtPesquisa", term)
            await asyncio.sleep(0.3)
            await lk_frame.click("#btEnviar")
            await asyncio.sleep(2)

            # Look for matching row
            rows = await lk_frame.query_selector_all("table tr")
            for tr in rows:
                text = (await tr.inner_text()).upper()
                if ("SECRETARIA" in text or "FAZENDA" in text or "SEFAZ" in text) and (uf.upper() in text or estado.upper() in text):
                    chk = await tr.query_selector("input.eng-lookup-multi-chk")
                    if chk:
                        val = await chk.get_attribute("value")
                        print(f"  Encontrada linha: {text[:80]} (id: {val})", flush=True)
                        await chk.check()
                        await asyncio.sleep(0.5)
                        btn_conf = await lk_frame.query_selector("#btConfirmarSelecao")
                        if btn_conf:
                            await btn_conf.click()
                            print("  Botao Confirmar Selecao clicado!", flush=True)
                            await asyncio.sleep(1.5)
                            await close_modal(page)
                            return True
                    
                    # Alternative: Selecionar link
                    links = await tr.query_selector_all("a[href*='Selecionar']")
                    for a in links:
                        href = await a.get_attribute("href") or ""
                        m = re.search(r"Selecionar\((\d+)\)", href)
                        if m and m.group(1) != "-1":
                            await lk_frame.evaluate(f"Selecionar({m.group(1)})")
                            print(f"  Selecionado via JS: {m.group(1)}", flush=True)
                            await asyncio.sleep(1)
                            await close_modal(page)
                            return True
        except Exception as e:
            print(f"  Aviso na busca por '{term}': {e}", flush=True)
            continue

    await close_modal(page)
    return False

async def open_any_title(page, expected_filial):
    print("  Filtrando grid com #ConfirmaFiltroS...", flush=True)
    try:
        await page.click("#ConfirmaFiltroS", timeout=15000)
    except:
        pass
    await asyncio.sleep(2)
    try:
        await page.wait_for_selector("a[id^='btnEd_']", timeout=10000)
    except:
        pass

    filial_col = await find_column_idx(page, "Filial")
    sit_col = await find_column_idx(page, "Situa") or await find_column_idx(page, "Status")

    if filial_col is not None:
        js_fn = f"""
            () => {{
                const tables = document.querySelectorAll('table');
                for (const table of tables) {{
                    if (!table.querySelector('a[id^="btnEd_"]')) continue;
                    const rows = table.querySelectorAll('tr');
                    const items = [];
                    let bestItem = null;
                    for (const tr of rows) {{
                        const link = tr.querySelector('a[id^="btnEd_"]');
                        if (!link) continue;
                        const filial = tr.cells[{filial_col}]?.innerText?.trim() || '';
                        const situ = {(sit_col or '-1')} >= 0 ? (tr.cells[{sit_col or -1}]?.innerText?.trim() || '') : '';
                        items.push({{ filial, situ, linkId: link.id }});
                        if (filial.includes("{expected_filial}")) {{
                            bestItem = {{ filial, situ, linkId: link.id }};
                        }}
                    }}
                    if (bestItem) return {{ found: true, item: bestItem }};
                    if (items.length > 0) return {{ found: true, item: items[0] }};
                    return {{ found: false }};
                }}
                return {{ found: false }};
            }}
        """
        result = await page.evaluate(js_fn)
        if result.get("found") and result.get("item"):
            it = result["item"]
            print(f"  Titulo encontrado: filial={it['filial']} situ={it.get('situ','?')} link={it['linkId']}", flush=True)
            await page.click(f"#{it['linkId']}")
            await page.wait_for_selector("#Copiar", timeout=15000)
            return True

    edit_link = await page.query_selector("a[id^='btnEd_']")
    if edit_link:
        link_id = await edit_link.get_attribute("id")
        await edit_link.click()
        try:
            await page.wait_for_selector("#Copiar", timeout=10000)
        except:
            pass
        print(f"  Ultimo titulo aberto (fallback): {link_id}", flush=True)
        return True

    print("  Nenhum link de edicao encontrado no grid", flush=True)
    return False

async def run_gnre_process(pdf_path: str):
    from pdf_parser import extract_invoice_data
    
    if not os.path.exists(pdf_path):
        print(f"ERRO: Arquivo nao encontrado: {pdf_path}", flush=True)
        return False, None

    data = extract_invoice_data(pdf_path)
    entry = data if isinstance(data, list) else [data]
    entry = entry[0]
    entry["pdf_path"] = pdf_path
    if not entry.get("filial"):
        entry["filial"] = "429"
    doc_num = entry.get("documento", "")
    entry["referencia"] = f"REF-GNRE {doc_num}" if doc_num else "REF-GNRE"

    print("\n" + "="*60, flush=True)
    print("  DADOS EXTRAIDOS DA GNRE:", flush=True)
    print("="*60, flush=True)
    for k, v in entry.items():
        print(f"  {k}: {v}", flush=True)
    print("="*60 + "\n", flush=True)

    async with BrowserLauncher() as p:
        if USE_CAMOUFOX:
            browser = None
            page = await p.new_page()
        else:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

        try:
            page.on("pageerror", lambda err: print(f"  [Page error] {err}", flush=True))

            print("1. Efetuando login no ERP ADMSIS...", flush=True)
            await login(page)
            print("2. Navegando para o grid de titulos a pagar...", flush=True)
            await navigate_to_grid(page)
            print("3. Filtrando tipo favorecido = FORNECEDOR...", flush=True)
            await filter_grid(page, tipo="GNRE")

            print(f"4. Selecionando fornecedor no lookup: {entry['fornecedor']} (UF: {entry.get('uf')})...", flush=True)
            found = await select_supplier_in_lookup(page, entry["fornecedor"], entry.get("uf", ""))
            if not found:
                print("  Lookup nao encontrou, tentando busca direta...", flush=True)
                pesq_sel = get_pesq_selector("")
                await page.fill(pesq_sel, entry["fornecedor"], timeout=3000)
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)

            print(f"5. Localizando titulo filial {entry['filial']} no grid para copiar...", flush=True)
            if not await open_any_title(page, entry["filial"]):
                await page.screenshot(path=os.path.join(LOG_DIR, "erro_sem_titulo_gnre.png"))
                print("  ERRO: Nenhum titulo encontrado para copiar no grid!", flush=True)
                return False, None

            print("6. Copiando titulo existente...", flush=True)
            if not await click_copiar(page):
                print("  ERRO: Falha ao clicar em Copiar", flush=True)
                return False, None

            print("7. Preenchendo campos do novo titulo a pagar...", flush=True)
            frame = await get_form_frame(page)
            ctx = frame if frame else page
            await fill_fields(page, ctx, entry)
            await page.screenshot(path=os.path.join(LOG_DIR, f"02_preenchido_gnre_{doc_num}.png"))

            print("8. Salvando alteracoes (clicando em Alterar)...", flush=True)
            if not await click_alterar(ctx, page):
                print("  ERRO: Falha ao clicar em Alterar", flush=True)
                return False, None
            await page.screenshot(path=os.path.join(LOG_DIR, f"03_final_gnre_{doc_num}.png"))

            await asyncio.sleep(2)
            print("9. Anexando documento GNRE em PDF via GED...", flush=True)
            await attach_document(page, entry)

            print("10. Emitindo e capturando a Autorizacao de Pagamento (#ImprAutPagto)...", flush=True)
            try:
                aut_pdf = await emitir_autorizacao_pagamento(page, entry)
                if aut_pdf:
                    entry["autorizacao_pdf"] = aut_pdf
            except Exception as e:
                print(f"  Aviso ao emitir autorizacao: {e}", flush=True)

            await close_modal(page)

            print(f"\n{'='*60}", flush=True)
            print(">>> SUCESSO: Lancamento de GNRE concluido com sucesso! <<<", flush=True)
            print(f"    Fornecedor: {entry['fornecedor']}", flush=True)
            print(f"    Valor: R$ {entry['valor']:.2f}", flush=True)
            print(f"    Vencimento: {entry['vencimento']}", flush=True)
            print(f"    Filial: {entry['filial']}", flush=True)
            print(f"    Referencia: {entry['referencia']}", flush=True)
            print("="*60 + "\n", flush=True)
            return True, entry
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass

def main():
    base = os.path.dirname(os.path.dirname(__file__))
    if len(sys.argv) > 1:
        pdf_arg = sys.argv[1]
        pdf_path = pdf_arg if os.path.isabs(pdf_arg) else os.path.join(base, pdf_arg)
    else:
        pdf_path = os.path.join(base, "GNRE NF 54949.pdf")
    
    asyncio.run(run_gnre_process(pdf_path))

if __name__ == "__main__":
    main()
