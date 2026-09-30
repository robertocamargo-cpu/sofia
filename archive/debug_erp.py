import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100", timeout=60000)
        await page.wait_for_timeout(3000)
        await page.fill("#usu_codigo", "N_FERNANDO", timeout=10000)
        await page.fill("#usu_senha", "FF(25)Nevine+", timeout=10000)
        await page.click('button:has-text("Acessar")', timeout=10000)
        await page.wait_for_timeout(5000)

        print(f"URL atual: {page.url}")
        print(f"Titulo: {await page.title()}")

        # Navigate to the specific module (same as erp_launcher.py does)
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"URL apos navegacao: {page.url}")

        all_buttons = await page.eval_on_selector_all("button, a[role=button], input[type=submit]",
            "els => els.map(e => ({tag: e.tagName, text: e.innerText?.trim() || e.value, id: e.id, cls: (e.className||'').slice(0,60)}))")
        print("\n--- BOTOES ENCONTRADOS ---")
        for b in all_buttons[:50]:
            if b["text"]:
                print(f'  [{b["text"]}]  id={b["id"]}')

        inputs = await page.eval_on_selector_all("input:not([type=hidden]), select, textarea",
            "els => els.map(e => ({tag: e.tagName, type: e.type, id: e.id, name: e.name, placeholder: e.placeholder, cls: (e.className||'').slice(0,40)}))")
        print("\n--- CAMPOS ENCONTRADOS ---")
        for inp in inputs[:30]:
            print(f'  <{inp["tag"]}> id={inp["id"]} name={inp["name"]} placeholder={inp["placeholder"]} type={inp["type"]}')

        await page.screenshot(path="logs/debug_inicial.png")
        print("\nScreenshot: logs/debug_inicial.png")

        await page.wait_for_timeout(60000)  # 1 minuto pra usuario inspecionar
        await browser.close()

asyncio.run(check())
