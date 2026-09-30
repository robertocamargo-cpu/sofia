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
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100", timeout=30000)
        await page.wait_for_timeout(3000)

        # Select Fornecedor
        await page.select_option("#ttp_favorecido_tp_id", value="1")
        await page.wait_for_timeout(500)

        # Click edit on first row
        edit_link = await page.query_selector("a[id^='btnEd_']")
        if edit_link:
            await edit_link.click()
            await page.wait_for_timeout(3000)
            print("Edit title opened")

        # Click Copiar Titulo
        copiar = await page.query_selector("#Copiar")
        if copiar:
            await copiar.click()
            await page.wait_for_timeout(4000)
            print("Copiar Titulo clicked")
            await page.screenshot(path="logs/05_apos_copiar.png")

            # Inspect page for form fields
            inputs = await page.eval_on_selector_all("input:not([type=hidden]), select, textarea",
                "els => els.map(e => ({tag: e.tagName, type: e.type, id: e.id, name: e.name, ph: e.placeholder, val: (e.value||'').slice(0,20), vis: e.offsetParent !== null, cl: (e.className||'').slice(0,30)}))")
            print(f"\nCampos ({len(inputs)}):")
            for inp in inputs:
                if inp["vis"]:
                    print(f'  {inp["tag"]} id={inp["id"]} name={inp["name"]} ph={inp["ph"]} val={inp["val"]}')

            # Check for iframes
            iframes = await page.query_selector_all("iframe")
            print(f"\nIframes: {len(iframes)}")
            for i, ifr in enumerate(iframes):
                src = await ifr.get_attribute("src")
                print(f"  Iframe {i}: src={src}")
                try:
                    frame = await ifr.content_frame()
                    if frame:
                        f_inputs = await frame.eval_on_selector_all("input:not([type=hidden]), select, textarea",
                            "els => els.map(e => ({id: e.id, name: e.name, vis: e.offsetParent !== null}))")
                        print(f"    Frame inputs: {len(f_inputs)}")
                        for fi in f_inputs[:10]:
                            if fi["vis"]:
                                print(f"      id={fi['id']}")
                except:
                    pass

            buttons = await page.eval_on_selector_all("button, a[role=button], a[id^='btn'], input[type=submit]",
                "els => els.map(e => ({txt: (e.innerText||e.value||'').trim().slice(0,25), id: e.id, vis: e.offsetParent !== null}))")
            print(f"\nBotoes ({len(buttons)}):")
            for b in buttons:
                if b["txt"]:
                    print(f'  [{b["txt"]}] id={b["id"]} vis={b["vis"]}')

        await page.screenshot(path="logs/06_form_campos.png")
        print("\nScreenshot: logs/06_form_campos.png")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(check())
