import asyncio
import os
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        print("1. Login...")
        await page.goto(ERP_URL, timeout=60000)
        await page.wait_for_timeout(3000)
        await page.fill("#usu_codigo", USERNAME, timeout=10000)
        await page.fill("#usu_senha", PASSWORD, timeout=10000)
        await page.click('button:has-text("Acessar")', timeout=10000)
        await page.wait_for_timeout(5000)
        await page.goto(ERP_URL, timeout=30000)
        await page.wait_for_timeout(3000)

        print("2. Buscando...")
        await page.fill("#pesq_ttp_fornecedor_id", "RECEITA FEDERAL", timeout=5000)
        await page.click("#ConfirmaFiltroS", timeout=10000)
        await page.wait_for_timeout(3000)

        print("3. Abrindo...")
        edit_link = await page.query_selector("a[id^='btnEd_']")
        if edit_link:
            await edit_link.click()
        await page.wait_for_timeout(3000)

        print("4. Copiando...")
        copiar = await page.query_selector("#Copiar")
        if copiar:
            await copiar.click()
        await page.wait_for_timeout(2000)
        try:
            await page.click('button:has-text("Sim")')
        except:
            pass
        await page.wait_for_timeout(3000)

        print("5. Clicando na aba Documentos...")
        await page.click('label:has-text("Documentos")')
        await page.wait_for_timeout(3000)

        await page.screenshot(path=os.path.join(LOG_DIR, "debug_documentos_aba.png"))

        print("\n=== BOTOES VISIVEIS NA PAGE apos clicar Documentos ===")
        botoes = await page.eval_on_selector_all(
            "button, a[role=button], input[type=submit], input[type=button]",
            "els => els.map(e => ({txt: (e.innerText||e.value||'').trim().slice(0,50), id: e.id, vis: e.offsetParent !== null}))"
        )
        for b in botoes:
            if b["vis"]:
                print(f'  [{b["txt"]}] id={b["id"]}')

        print("\n=== TODOS ELEMENTOS VISIVEIS COM '+' ===")
        plus_els = await page.eval_on_selector_all(
            "button, a, span, div, input",
            "els => els.map(e => ({txt: (e.innerText||e.value||e.title||'').trim().slice(0,50), id: e.id, tag: e.tagName, vis: e.offsetParent !== null}))"
        )
        for e in plus_els:
            if e["vis"] and ("+" in e["txt"] or "Inserir" in e["txt"] or "Novo" in e["txt"] or "Adicionar" in e["txt"]):
                print(f'  [{e["txt"]}] id={e["id"]} tag={e["tag"]}')

        print("\n=== IFRAMES ===")
        for i, ifr in enumerate(await page.query_selector_all("iframe")):
            src = await ifr.get_attribute("src") or "(sem src)"
            print(f"  Iframe {i}: {src[:120]}")
            try:
                f = await ifr.content_frame()
                if f:
                    btns = await f.eval_on_selector_all(
                        "button, a[role=button]",
                        "els => els.map(e => ({txt: (e.innerText||'').trim().slice(0,50), id: e.id, vis: e.offsetParent !== null}))"
                    )
                    for b in btns:
                        if b["vis"]:
                            print(f'    FRAME[{i}] [{b["txt"]}] id={b["id"]}')
            except:
                pass

        print("\n=== PROCURANDO POR TABELA/GRID DE DOCUMENTOS ===")
        # Look for any table or grid in the page that might be the Documentos grid
        tables = await page.eval_on_selector_all(
            "table, .grid, [class*='table']",
            "els => els.map(e => ({id: e.id, cls: (e.className||'').slice(0,40), rows: e.rows ? e.rows.length : 0, vis: e.offsetParent !== null}))"
        )
        for t in tables:
            if t["vis"]:
                print(f'  table: id={t["id"]} cls={t["cls"]} rows={t["rows"]}')

        # Also try FRAME content
        for ifr in await page.query_selector_all("iframe"):
            src = await ifr.get_attribute("src") or ""
            if "FICHA" in src:
                f = await ifr.content_frame()
                if f:
                    tabs_text = await f.evaluate("document.body.innerText")
                    print(f"\n=== TEXTO DO FRAME FICHA (primeiros 3000 chars) ===")
                    print(tabs_text[:3000])

        print("\nJanela aberta 60s...")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
