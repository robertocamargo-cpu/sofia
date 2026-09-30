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

        await page.select_option("#ttp_favorecido_tp_id", value="1")
        await page.wait_for_timeout(500)
        await page.fill("#pesq_ttp_fornecedor_id", "BELA DISTRIBUIDORA")
        await page.wait_for_timeout(500)
        await page.click("#ConfirmaFiltroS")
        await page.wait_for_timeout(3000)

        # Click edit on first row
        edit_link = await page.query_selector("a[id^='btnEd_']")
        if edit_link:
            await edit_link.click()
            await page.wait_for_timeout(3000)
            print(f"URL apos editar: {page.url}")

        # Click Copiar
        copiar = await page.query_selector("#Copiar")
        if copiar:
            await copiar.click()
            # Wait for navigation or AJAX
            await page.wait_for_timeout(5000)
            print(f"URL apos copiar: {page.url}")

            # Check all HTML content for form fields
            body_html = await page.inner_html("body")
            form_indicators = ["ttp_valor_titulo", "ttp_data_vencimento", "ttp_filial_id", "Novo"]
            for ind in form_indicators:
                if ind in body_html:
                    print(f"'{ind}' encontrado no HTML!")
                else:
                    print(f"'{ind}' NAO encontrado no HTML")

            # Check all input/select/textarea in full DOM (including hidden)
            all_inputs = await page.eval_on_selector_all("input, select, textarea",
                "els => els.map(e => ({id: e.id, name: e.name, type: e.type, vis: e.offsetParent !== null, val: (e.value||'').slice(0,40)}))")
            print(f"\nTodos inputs ({len(all_inputs)}):")
            for inp in all_inputs:
                if inp["id"] or inp["name"]:
                    print(f'  {inp["id"] or "(sem id)"} name={inp["name"]} type={inp["type"]} vis={inp["vis"]} val="{inp["val"]}"')

        await page.screenshot(path="logs/debug_apos_copiar_full.png")
        print("\nScreenshot: logs/debug_apos_copiar_full.png")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(check())
