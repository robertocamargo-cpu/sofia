import asyncio
import os
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"
LOG_DIR = "C:/Users/finan/OneDrive/Área de Trabalho/automacao contas a pagar/logs"

async def get_form_frame(page):
    for ifr in await page.query_selector_all("iframe"):
        src = await ifr.get_attribute("src") or ""
        if "FICHA" in src:
            return await ifr.content_frame()
    return None

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
        await page.wait_for_timeout(500)
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
        ctx = frame if frame else page
        print(f"   Usando {'FRAME' if frame else 'PAGE'} para preencher campos")

        print("5. Preenchendo valor no frame...")
        await ctx.fill("#ttp_valor_titulo", "999.99", timeout=5000)
        print("   OK")

        print("6. Clicando Alterar no frame...")
        for sel in ['button:has-text("Alterar")', "#AlterarI", "#Alterar"]:
            try:
                btn = await ctx.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=5000)
                    print(f"   Clicou: {sel}")
                    break
            except:
                continue
        await ctx.wait_for_timeout(2000)

        try:
            c = await ctx.wait_for_selector('button:has-text("Confirmar")', timeout=3000)
            if c and await c.is_visible():
                await c.click()
                print("   Confirmou Alterar")
        except:
            pass
        await ctx.wait_for_timeout(3000)

        print("\n7. AGORA: procurando Documentos...")
        await page.screenshot(path=os.path.join(LOG_DIR, "debug_pos_alterar2.png"))

        # Check page buttons
        print("\n   BOTOES VISIVEIS NA PAGE:")
        botoes = await page.eval_on_selector_all(
            "button, a[role=button], input[type=submit], input[type=button]",
            "els => els.map(e => ({txt: (e.innerText||e.value||'').trim().slice(0,50), id: e.id, vis: e.offsetParent !== null}))"
        )
        for b in botoes:
            if b["vis"]:
                print(f'     [{b["txt"]}] id={b["id"]}')

        print("\n   IFRAMES DISPONIVEIS:")
        for i, ifr in enumerate(await page.query_selector_all("iframe")):
            src = await ifr.get_attribute("src") or "(sem src)"
            print(f"     Iframe {i}: {src[:120]}")
            try:
                f = await ifr.content_frame()
                if f:
                    btns = await f.eval_on_selector_all(
                        "button, a[role=button]",
                        "els => els.map(e => ({txt: (e.innerText||'').trim().slice(0,50), id: e.id, vis: e.offsetParent !== null}))"
                    )
                    for b in btns:
                        if b["vis"]:
                            print(f'       FRAME[{i}] [{b["txt"]}] id={b["id"]}')
            except Exception as ex:
                print(f"       Erro: {ex}")

        print("\nJanela aberta p/ inspecao (60s)...")
        await page.wait_for_timeout(60000)
        await browser.close()

asyncio.run(main())
