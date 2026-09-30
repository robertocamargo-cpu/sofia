import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    os.makedirs("logs", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("1. Navegando para o ERP...")
        await page.goto("https://erp.admsis.com/Home?eng_tela=0103070100")
        await page.wait_for_timeout(2000)
        await page.screenshot(path="logs/test_login_1.png")
        print("   URL inicial:", page.url)
        
        print("2. Preenchendo dados de acesso...")
        await page.fill("#usu_codigo", "N_FERNANDO")
        await page.fill("#usu_senha", "FF(25)Nevine+")
        await page.screenshot(path="logs/test_login_2.png")
        
        print("3. Clicando em Acessar...")
        await page.click('button:has-text("Acessar")')
        await page.wait_for_timeout(5000)
        await page.screenshot(path="logs/test_login_3.png")
        print("   URL após clique:", page.url)
        
        print("4. Clicando no card Títulos a Pagar...")
        try:
            await page.click('a:has-text("Títulos a Pagar") >> visible=true', timeout=10000)
            await page.wait_for_timeout(5000)
            print("   Card clicado.")
        except Exception as e:
            print("   Erro ao clicar no card:", e)
        await page.screenshot(path="logs/test_login_4.png")
        print("   URL final:", page.url)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
