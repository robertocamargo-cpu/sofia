import asyncio
from playwright.async_api import async_playwright

ERP_URL = "https://erp.admsis.com/Home?eng_tela=0103070100"
USERNAME = "N_FERNANDO"
PASSWORD = "FF(25)Nevine+"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        await page.goto(ERP_URL, timeout=60000)
        await page.wait_for_timeout(3000)
        await page.fill("#usu_codigo", USERNAME, timeout=10000)
        await page.fill("#usu_senha", PASSWORD, timeout=10000)
        await page.click('button:has-text("Acessar")', timeout=10000)
        await page.wait_for_timeout(5000)
        await page.goto(ERP_URL, timeout=30000)
        await page.wait_for_timeout(3000)

        await page.fill("#pesq_ttp_fornecedor_id", "MOVVI LOGISTICA LTDA", timeout=5000)
        await page.click("#ConfirmaFiltroS", timeout=10000)
        await page.wait_for_timeout(3000)

        rows = await page.eval_on_selector_all(
            "table tr",
            """(trs) => {
                return trs.map((tr, ri) => {
                    if (!tr.cells || tr.cells.length < 2) return null;
                    const cells = Array.from(tr.cells).map(c => c.innerText.trim());
                    const link = tr.querySelector('a[id^=\"btnEd_\"]');
                    return {
                        idx: ri,
                        data: cells.slice(0, 10).join(' | '),
                        hasLink: !!link
                    };
                }).filter(r => r && r.data);
            }"""
        )
        print(f"\nTotal linhas: {len(rows)}")
        for r in rows:
            print(f"  [{r['idx']}] hasLink={r['hasLink']} {r['data'][:200]}")

        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
