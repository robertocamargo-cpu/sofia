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
        await page.screenshot(path=os.path.join(LOG_DIR, "explorar_01_login.png"))

        print("2. Listando botoes da tela...")
        botoes = await page.eval_on_selector_all("button, a[role=button], input[type=submit], input[type=button], a[id^='btn']",
            "els => els.map(e => ({tag: e.tagName, txt: (e.innerText||e.value||'').trim().slice(0,40), id: e.id, onclick: (e.getAttribute('onclick')||'').slice(0,80), vis: e.offsetParent !== null}))")
        for b in botoes:
            if b["vis"]:
                print(f'  [{b["txt"]}] id={b["id"]} onclick={b["onclick"]}')

        print("\n3. Preenchendo REFERENCIA com GNRE...")
        await page.fill("#ttp_referencia", "GNRE", timeout=5000)
        # Also select Tipo Favorecido = FORNECEDOR (value=1)
        try:
            await page.select_option("#ttp_favorecido_tp_id", value="1", timeout=5000)
            print("  Tipo Favorecido = FORNECEDOR")
        except Exception as e:
            print(f"  Erro tipo favorecido: {e}")
        await page.wait_for_timeout(500)

        print("4. Clicando em filtrar...")
        for sel in ['#ConfirmaFiltroS', 'button:has-text("Filtrar")', 'button:has-text("Pesquisar")', 'input[value="Filtrar"]', '#btnFiltrar']:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=5000)
                    print(f"  Clicou: {sel}")
                    break
            except:
                continue

        await page.wait_for_timeout(4000)
        await page.screenshot(path=os.path.join(LOG_DIR, "explorar_03_apos_filtrar.png"))

        print("\n5. Analisando grid de resultados...")
        all_rows = await page.eval_on_selector_all("tr",
            "rows => rows.map((r,i) => ({idx: i, data: r.cells ? Array.from(r.cells).map(c => c.innerText.trim()).join(' | ') : ''})).filter(r => r.data)")
        print(f"  Linhas com dados: {len(all_rows)}")
        for r in all_rows[:20]:
            print(f"  [{r['idx']}] {r['data'][:200]}")

        print("\n6. Procurando links de acao no grid...")
        acoes = await page.eval_on_selector_all("a[id^='btnEd_'], a[id^='btnCp_'], a[id^='btnEx_'], a[id^='btn']",
            "els => els.map(e => ({id: e.id, txt: e.innerText.trim(), href: (e.href||'').slice(0,60), vis: e.offsetParent !== null}))")
        for a in acoes:
            print(f'  id={a["id"]} txt="{a["txt"]}" vis={a["vis"]}')

        await page.screenshot(path=os.path.join(LOG_DIR, "explorar_04_grid.png"))
        print("\nA janela vai ficar aberta por 60s para inspecao manual.")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
