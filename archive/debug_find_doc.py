import asyncio
import os
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"

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

        # Find exact element for "Documentos" 
        print("\n=== Buscando 'Documentos' por diferentes seletores ===")
        for sel in [
            'text="Documentos"',
            'a:has-text("Documentos")',
            'li:has-text("Documentos")',
            'span:has-text("Documentos")',
            'div:has-text("Documentos")',
            'a[id*="Documentos"]',
            'a[id*="documento"]',
            '#Documentos',
            '[class*="documento"]',
            'a[href*="documento"]',
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    tag = await el.evaluate("e => e.tagName")
                    txt = await el.evaluate("e => (e.innerText||'').trim()")
                    vis = await el.is_visible()
                    print(f"  ENCONTRADO: {sel} -> tag={tag} text='{txt}' visible={vis}")
                    # Get parent info
                    parent_info = await el.evaluate("""e => {
                        const p = e.parentElement;
                        return {tag: p?.tagName, id: p?.id, cls: p?.className?.slice(0,50)};
                    }""")
                    print(f"    Parent: tag={parent_info['tag']} id={parent_info['id']} cls={parent_info['cls']}")
            except:
                continue

        # Also search for links in a nav/tab context
        print("\n=== Todos os elementos <a> com texto visivel ===")
        links = await page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({txt: (e.innerText||'').trim().slice(0,40), id: e.id, href: (e.href||'').slice(0,60), vis: e.offsetParent !== null}))"
        )
        for l in links:
            if l["vis"] and l["txt"]:
                print(f'  [{l["txt"]}] id={l["id"]} href={l["href"]}')

        print("\nJanela aberta 30s p/ inspecao...")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
