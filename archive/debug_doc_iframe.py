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

        await page.goto(ERP_URL, timeout=60000)
        await page.wait_for_timeout(3000)
        await page.fill("#usu_codigo", USERNAME, timeout=10000)
        await page.fill("#usu_senha", PASSWORD, timeout=10000)
        await page.click('button:has-text("Acessar")', timeout=10000)
        await page.wait_for_timeout(5000)
        await page.goto(ERP_URL, timeout=30000)
        await page.wait_for_timeout(3000)

        await page.fill("#pesq_ttp_fornecedor_id", "MOVVI LOGISTICA LTDA", timeout=5000)
        await page.click("#ConfirmaFiltroS", timeout=10000)
        await page.wait_for_timeout(3000)

        edit_link = await page.query_selector("a[id^='btnEd_']")
        if edit_link:
            await edit_link.click()
        await page.wait_for_timeout(3000)

        copiar = await page.query_selector("#Copiar")
        if copiar:
            await copiar.click()
        await page.wait_for_timeout(2000)
        try:
            await page.click('button:has-text("Sim")')
        except:
            pass
        await page.wait_for_timeout(3000)

        print("1. Clicando aba Documentos...")
        await page.click('label:has-text("Documentos")')
        await page.wait_for_timeout(3000)

        print("2. Procurando iframe EngGedList...")
        dframe = None
        for ifr in await page.query_selector_all("iframe"):
            src = await ifr.get_attribute("src") or ""
            if "EngGedList" in src:
                dframe = await ifr.content_frame()
                print(f"   Iframe encontrado: {src[:120]}")
                break

        if not dframe:
            print("   Iframe EngGedList nao encontrado!")
            await browser.close()
            return

        print("3. Conteudo do iframe:")
        texto = await dframe.evaluate("document.body.innerText")
        print(f"   Texto: {texto[:1500]}")

        print("4. Clicando btNovo...")
        await dframe.click("#btNovo")
        await dframe.wait_for_timeout(3000)

        await page.screenshot(path=os.path.join(LOG_DIR, "debug_doc_novo.png"))

        print("5. Conteudo do iframe apos btNovo:")
        texto2 = await dframe.evaluate("document.body.innerText")
        print(f"   Texto: {texto2[:2000]}")

        print("6. TODOS elementos visiveis no iframe:")
        els = await dframe.eval_on_selector_all(
            "*",
            "els => els.map(e => ({txt: (e.innerText||e.value||e.placeholder||'').trim().slice(0,60), id: e.id, tag: e.tagName, type: e.type, name: e.name, vis: e.offsetParent !== null}))"
        )
        for e in els:
            if e["vis"] and (e["txt"] or e["id"]):
                print(f'    [{e["txt"]}] id={e["id"]} tag={e["tag"]} type={e["type"]} name={e["name"]}')

        print("\nJanela aberta 60s p/ inspecao...")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
