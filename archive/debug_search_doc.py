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

        # Search ALL elements on the PAGE for "Doc" or "doc" or "Anexo" or "anexo"
        print("\n=== PAGE: elementos com 'doc' ou 'anexo' ===")
        doc_els = await page.eval_on_selector_all(
            "text=doc, text=Doc, text=DOC, text=anexo, text=Anexo, text=ANEXO, text=arquivo, text=Arquivo, text=ARQUIVO",
            "els => els.map(e => ({txt: e.innerText?.trim().slice(0,80), id: e.id, tag: e.tagName, vis: e.offsetParent !== null}))"
        )
        for e in doc_els:
            print(f'  [{e["txt"]}] id={e["id"]} vis={e["vis"]}')

        # Also search FRAME
        for ifr in await page.query_selector_all("iframe"):
            src = await ifr.get_attribute("src") or ""
            if "FICHA" in src:
                f = await ifr.content_frame()
                if f:
                    doc_els = await f.eval_on_selector_all(
                        "text=doc, text=Doc, text=DOC, text=anexo, text=Anexo, text=ANEXO, text=arquivo, text=Arquivo, text=ARQUIVO",
                        "els => els.map(e => ({txt: e.innerText?.trim().slice(0,80), id: e.id, tag: e.tagName, vis: e.offsetParent !== null}))"
                    )
                    print(f"\n=== FRAME FICHA: elementos com 'doc' ou 'anexo' ===")
                    for e in doc_els:
                        print(f'  [{e["txt"]}] id={e["id"]} vis={e["vis"]}')

        # Also get ALL text from page (outer HTML) and search for Documentos
        all_text = await page.evaluate("document.body.innerText")
        print(f"\n=== TEXTO COMPLETO DA PAGE (primeiros 2000 chars) ===")
        print(all_text[:2000])

        print("\n\nJanela aberta 60s p/ inspecao manual...")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
