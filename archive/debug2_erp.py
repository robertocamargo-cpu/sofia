import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100")
        await page.wait_for_timeout(2000)
        await page.fill("#usu_codigo", "N_FERNANDO")
        await page.fill("#usu_senha", "FF(25)Nevine+")
        await page.click('button:has-text("Acessar")')
        await page.wait_for_timeout(5000)
        
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100")
        await page.wait_for_timeout(3000)
        
        # Filtro
        await page.select_option("#ttp_favorecido_tp_id", value="1")
        inp = await page.wait_for_selector("#pesq_ttp_fornecedor_id")
        await inp.fill("BELA DIS")
        await page.wait_for_timeout(1000)
        await page.click("#ConfirmaFiltroS")
        await page.wait_for_timeout(3000)
        
        # Click the first edit link
        await page.click('a[id^="btnEd_"]')
        await page.wait_for_timeout(3000)
        
        # Copiar
        await page.click('button:has-text("Copiar")')
        await page.wait_for_timeout(2000)
        await page.click('button:has-text("Sim")')
        await page.wait_for_timeout(5000)
        
        html = await page.content()
        with open("logs/debug_form2.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
