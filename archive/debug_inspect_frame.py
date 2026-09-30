import asyncio
import os
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

async def get_form_frame(page):
    for ifr in await page.query_selector_all("iframe"):
        src = await ifr.get_attribute("src") or ""
        if "FICHA" in src:
            return await ifr.content_frame()
    return None

async def inspect_frame(frame, label):
    print(f"\n=== INSPECIONANDO {label} ===")
    # All visible text elements
    all_els = await frame.eval_on_selector_all(
        "button, a, span, div[role=tab], li, input[type=submit], input[type=button], [onclick]",
        "els => els.map(e => ({txt: (e.innerText||e.value||e.title||'').trim().slice(0,60), id: e.id, cls: e.className?.slice(0,40), tag: e.tagName, vis: e.offsetParent !== null}))"
    )
    print(f"  Total elements: {len(all_els)}")
    for e in all_els:
        if e["vis"] and (e["txt"] or e["id"]):
            print(f'    [{e["txt"]}] id={e["id"]} cls={e["cls"]}')

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

        frame = await get_form_frame(page)
        if frame:
            await inspect_frame(frame, "FRAME APOS COPIAR (ANTES DE PREENCHER)")
        else:
            print("Frame FICHA nao encontrado apos copiar!")

        print("\n\nJanela aberta 60s p/ inspecao manual...")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
