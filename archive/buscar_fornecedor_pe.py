import asyncio
import os
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

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

        print("2. Abrindo lookup de fornecedor pela tela inicial...")
        # First let's search for the exact fornecedor name in the lookup from the grid
        lookup_btn = await page.query_selector("#btnLookupJanela_ttp_fornecedor_id")
        if lookup_btn and await lookup_btn.is_visible():
            await lookup_btn.click()
            await page.wait_for_timeout(3000)
            print("   Lookup aberto!")

            # Wait for modal iframe
            modal = await page.wait_for_selector("#eng-lookup-janela.in", timeout=5000)
            if not modal:
                modal = await page.query_selector("#eng-lookup-janela")
            if modal:
                lk_iframe = await modal.query_selector("iframe")
                if lk_iframe:
                    lk_frame = await lk_iframe.content_frame()
                    if lk_frame:
                        await lk_frame.wait_for_timeout(1000)

                        # Find search fields
                        inputs = await lk_frame.eval_on_selector_all("input:not([type=hidden]), select",
                            "els => els.map(e => ({id: e.id, name: e.name, type: e.type, ph: e.placeholder, vis: e.offsetParent !== null}))")
                        vis = [i for i in inputs if i["vis"]]
                        for i in vis:
                            print(f'     id={i["id"]} name={i["name"]} type={i["type"]} ph={i["ph"]}')

                        text_fields = [i for i in vis if i["type"] == "text"]
                        if text_fields:
                            # Try the first text field
                            tf = text_fields[0]
                            print(f"   Buscando: SECRETARIA DA FAZENDA")
                            await lk_frame.fill(f"#{tf['id']}", "SECRETARIA DA FAZENDA", timeout=5000)
                            await lk_frame.wait_for_timeout(500)

                            # Try to find and click a Filtrar button
                            botoes = await lk_frame.eval_on_selector_all("button",
                                "els => els.map(e => ({txt: e.innerText.trim().slice(0,20), id: e.id, vis: e.offsetParent !== null}))")
                            for b in botoes:
                                if b["vis"] and b["txt"]:
                                    print(f"     Botao: [{b['txt']}] id={b['id']}")
                                    if "Filtrar" in b["txt"] or "Pesquisar" in b["txt"]:
                                        btn = await lk_frame.query_selector(f"#{b['id']}")
                                        if btn:
                                            await btn.click()
                                            await lk_frame.wait_for_timeout(3000)
                                            break

                            rows = await lk_frame.eval_on_selector_all("tr",
                                "rows => rows.map((r,i) => ({idx: i, data: r.cells ? Array.from(r.cells).map(c => c.innerText.trim()).join(' | ') : ''})).filter(r => r.data)")
                            print(f"   Resultados: {len(rows)}")
                            for r in rows[:10]:
                                print(f"     [{r['idx']}] {r['data'][:250]}")

        await page.screenshot(path=os.path.join(LOG_DIR, "busca_fornecedor_lookup.png"))
        print("\nJanela aberta 30s para inspecao...")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
