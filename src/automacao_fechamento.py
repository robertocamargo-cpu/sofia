import asyncio
import os
import sys
import zipfile
import io
from datetime import datetime, timedelta
import pandas as pd
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = r"C:\Users\finan\OneDrive\Área de Trabalho\Automacao Fechamento xml"
ERP_URL = "https://erp.admsis.com/Home"
ERP_USER = os.getenv("ERP_USER")
ERP_PASS = os.getenv("ERP_PASS")

FILIAIS = ["302", "429", "551", "601", "Nevine"]

FILIAL_IDS = {
    "302": "253",
    "429": "155",
    "551": "161",
    "601": "216",
    "Nevine": "293"
}

def get_last_month():
    hoje = datetime.now()
    ultimo_dia = hoje.replace(day=1) - timedelta(days=1)
    primeiro_dia = ultimo_dia.replace(day=1)
    return primeiro_dia, ultimo_dia

def str_data(d):
    return d.strftime("%d/%m/%Y")

async def esperar_carregamento(page):
    try:
        overlay = page.locator('.blockUI, .loading, :text("Aguarde"), :text("carregando")').first
        for _ in range(20):
            if await overlay.is_visible():
                await asyncio.sleep(1)
            else:
                break
    except:
        pass
    await asyncio.sleep(1)

async def login_erp(page):
    print("Acessando ERP...")
    await page.goto(ERP_URL, timeout=90000, wait_until="load")
    await asyncio.sleep(3)

    usuario_logado = page.locator(f'text="{ERP_USER}"').first
    if await usuario_logado.count() > 0:
        print("Sessão do ERP já está ativa.")
        return True

    print("Realizando login no ERP...")
    try:
        await page.fill('input[name="usu_codigo"]', ERP_USER)
        await page.fill('input[name="usu_senha"]', ERP_PASS)
        await page.click('button#login')
        await asyncio.sleep(5)
        await esperar_carregamento(page)
        print("Login ERP concluído.")
        return True
    except Exception as e:
        print(f"Erro no login ERP: {e}")
        return False

async def preencher_campo_data(page, campo_id, data):
    str_num = data.strftime("%d%m%Y")
    str_full = data.strftime("%d/%m/%Y")
    try:
        await page.wait_for_selector(f'input#{campo_id}', state="attached", timeout=10000)
        await asyncio.sleep(0.3)
        await page.evaluate(f'document.getElementById("{campo_id}").value = "";')
        await asyncio.sleep(0.2)
        await page.type(f'input#{campo_id}', str_num, delay=30, no_wait_after=True)
        await asyncio.sleep(0.5)
        val = await page.input_value(f'input#{campo_id}')
        if not val or val.replace("/", "") != str_num:
            await page.evaluate(f'document.getElementById("{campo_id}").value = "{str_full}";')
            await page.evaluate(f'''
                var el = document.getElementById("{campo_id}");
                el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                el.dispatchEvent(new Event("change", {{ bubbles: true }}));
            ''')
            await asyncio.sleep(0.3)
            val = await page.input_value(f'input#{campo_id}')
        print(f"    {campo_id} = {val}")
        return True
    except Exception as e:
        print(f"  Erro ao preencher {campo_id}: {e}")
        return False

async def selecionar_filial_simples(page, filial):
    filial_id = FILIAL_IDS[filial]
    try:
        await page.select_option('select#filial', filial_id)
        await asyncio.sleep(0.5)
        await esperar_carregamento(page)
        return True
    except Exception as e:
        print(f"  Erro ao selecionar filial {filial}: {e}")
        return False

async def selecionar_filial_multipla(page, filial):
    filial_id = FILIAL_IDS[filial]
    try:
        await page.evaluate(f'''
            var sel = document.getElementById("filial");
            for (var i = 0; i < sel.options.length; i++) {{
                sel.options[i].selected = false;
            }}
            sel.options[sel.options.length] = undefined;
        ''')
        await page.evaluate(f'''
            var sel = document.getElementById("filial");
            for (var i = 0; i < sel.options.length; i++) {{
                if (sel.options[i].value == "{filial_id}") {{
                    sel.options[i].selected = true;
                    break;
                }}
            }}
        ''')
        await page.evaluate('document.getElementById("filial").dispatchEvent(new Event("change", { bubbles: true }))')
        await asyncio.sleep(0.5)
        await esperar_carregamento(page)
        return True
    except Exception as e:
        print(f"  Erro ao selecionar filial múltipla {filial}: {e}")
        return False

async def baixar_nfe_zip_filial(page, filial, d_ini, d_fim):
    print(f"\n--- NF-e ZIP - Filial {filial} ---")

    try:
        await page.goto(f"{ERP_URL}?eng_tela=0104040100", timeout=60000)
    except:
        pass
    await asyncio.sleep(5)
    await esperar_carregamento(page)

    await preencher_campo_data(page, "data_inicio", d_ini)
    await preencher_campo_data(page, "data_fim", d_fim)

    await selecionar_filial_simples(page, filial)

    nome_zip = f"nfe_{filial}_{d_ini.strftime('%Y%m')}.zip"
    caminho_zip = os.path.join(BASE_DIR, filial, nome_zip)

    await page.evaluate('''
        EngDialogs.confirm = function(msg, callback) { callback(); };
        f_btGerarArquivo = function() {
            EngDialogs.confirm('', function() {
                if (!EngNavegacao.checkDuploSubmit()) return;
                if (!EngValidacao.validarTudo()) return;
                var emp_id = '';
                try {emp_id = $('#emp_id').val(); } catch(e) {};
                Formulario.action = 'ErpDownload/NFE?emp_id='+emp_id;
                Formulario.target = "_self";
                Formulario.submit();
            });
        };
    ''')

    print("  Gerando arquivo ZIP...")
    try:
        async with page.expect_download(timeout=180000) as download_info:
            await page.click('button#btGerarArquivo')

        download = await download_info.value
        await download.save_as(caminho_zip)
        print(f"  ZIP salvo: {caminho_zip}")
        return True
    except Exception as e:
        print(f"  Erro ao baixar ZIP: {e}")
        try:
            async with page.expect_download(timeout=180000) as download_info:
                await page.click('button#btGerarArquivo')
            download = await download_info.value
            await download.save_as(caminho_zip)
            print(f"  ZIP salvo (2ª tentativa): {caminho_zip}")
            return True
        except Exception as e2:
            print(f"  Erro na 2ª tentativa: {e2}")

    print("  Salvando debug...")
    with open(os.path.join(BASE_DIR, filial, "debug_nfe_zip.html"), "w", encoding="utf-8") as f:
        f.write(await page.content())
    await page.screenshot(path=os.path.join(BASE_DIR, filial, "debug_nfe_zip.png"), full_page=True)
    return False

async def baixar_relatorio_2001_filial(page, filial, d_ini, d_fim):
    print(f"\n--- Relatório 2001 - Filial {filial} ---")

    try:
        await page.goto(f"{ERP_URL}?eng_tela=0117020100", timeout=60000)
    except:
        pass
    await asyncio.sleep(5)
    await esperar_carregamento(page)

    try:
        url_antes = page.url
        await page.select_option('select#relatorio', '2001')
        await asyncio.sleep(1)
        for _ in range(20):
            await asyncio.sleep(0.5)
            if page.url != url_antes:
                await page.wait_for_load_state("load", timeout=30000)
                break
        await asyncio.sleep(2)
        await esperar_carregamento(page)
        await page.wait_for_selector('input#data_emissao_i', state="attached", timeout=15000)
        print("  Relatório 2001 selecionado.")
    except Exception as e:
        print(f"  Erro ao selecionar relatório 2001: {e}")
        return False

    await preencher_campo_data(page, "data_i", d_ini)
    await preencher_campo_data(page, "data_f", d_fim)

    await selecionar_filial_multipla(page, filial)

    nome_csv = f"rel2001_{filial}_{d_ini.strftime('%Y%m')}.csv"
    nome_xlsx = f"rel2001_{filial}_{d_ini.strftime('%Y%m')}.xlsx"
    caminho_csv = os.path.join(BASE_DIR, filial, nome_csv)
    caminho_xlsx = os.path.join(BASE_DIR, filial, nome_xlsx)

    print("  Gerando CSV...")
    try:
        await page.evaluate('document.getElementById("Formulario").removeAttribute("target");')
        await asyncio.sleep(1)

        async with page.expect_download(timeout=180000) as download_info:
            await page.click('button#btRelatorioCSV')

        download = await download_info.value
        await download.save_as(caminho_csv)
        print(f"  CSV salvo: {caminho_csv}")

        print("  Convertendo para XLSX...")
        try:
            data = open(caminho_csv, 'rb').read()
            if data[:2] == b'PK':
                print("  Arquivo é um ZIP. Extraindo CSV interno...")
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    csv_interno = [n for n in z.namelist() if n.endswith('.csv')]
                    if csv_interno:
                        with z.open(csv_interno[0]) as f:
                            df = pd.read_csv(f, sep=';', encoding='latin-1', on_bad_lines='skip')
                    else:
                        print("  Nenhum CSV encontrado dentro do ZIP.")
                        return True
            else:
                df = pd.read_csv(caminho_csv, sep=';', encoding='latin-1', on_bad_lines='skip')
            df.to_excel(caminho_xlsx, index=False, engine='openpyxl')
            print(f"  XLSX salvo: {caminho_xlsx}")
        except Exception as e:
            print(f"  Erro na conversão: {e}")

        return True
    except Exception as e:
        print(f"  Erro ao baixar CSV: {e}")
        return False

async def inspecionar_tela(page, screen_id, nome):
    print(f"\n=== Inspecionando tela {screen_id} ({nome}) ===")
    try:
        await page.goto(f"{ERP_URL}?eng_tela={screen_id}", timeout=60000)
    except:
        pass
    await asyncio.sleep(5)
    await esperar_carregamento(page)

    html = await page.content()
    with open(os.path.join(BASE_DIR, f"tela_{screen_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    await page.screenshot(path=os.path.join(BASE_DIR, f"tela_{screen_id}.png"), full_page=True)
    print(f"  HTML e screenshot salvos.")

    campos = await page.query_selector_all("select, input:not([type='hidden']):not([type='submit'])")
    print(f"  Campos:")
    for campo in campos:
        el_id = await campo.get_attribute("id") or ""
        el_name = await campo.get_attribute("name") or ""
        el_type = await campo.get_attribute("type") or await campo.evaluate("el => el.tagName")
        if el_id or el_name:
            print(f"    {el_type:>8} | id={el_id:<25} | name={el_name}")

    botoes = await page.query_selector_all("button")
    print(f"  Botões:")
    for btn in botoes:
        btn_id = await btn.get_attribute("id") or ""
        btn_text = await btn.inner_text() or ""
        if btn_id or btn_text.strip():
            print(f"    id={btn_id:<30} | text={btn_text.strip()[:40]}")

async def main():
    if "--inspect" in sys.argv:
        async with async_playwright() as p:
            local_app_data = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            user_data_dir = os.path.join(local_app_data, "Automacao_Fechamento_XML", "sessao")
            os.makedirs(user_data_dir, exist_ok=True)
            context = await p.chromium.launch_persistent_context(
                user_data_dir, headless=False,
                viewport={"width": 1366, "height": 768},
                args=["--start-maximized"]
            )
            page = context.pages[0] if context.pages else await context.new_page()
            if await login_erp(page):
                await inspecionar_tela(page, "0104040100", "NF-e ZIP")
                await inspecionar_tela(page, "0117020100", "Relatório 2001")
            await context.close()
            print("\nInspeção concluída.")
        return

async def executar_fechamento_fiscal(mes=None, ano=None, filiais_alvo=None) -> dict:
    if mes and ano:
        import calendar
        d_ini = datetime(int(ano), int(mes), 1)
        _, ultimo_dia = calendar.monthrange(int(ano), int(mes))
        d_fim = datetime(int(ano), int(mes), ultimo_dia)
    else:
        d_ini, d_fim = get_last_month()

    lista_filiais = [filiais_alvo] if isinstance(filiais_alvo, str) else (filiais_alvo or FILIAIS)
    print(f"Período: {str_data(d_ini)} até {str_data(d_fim)}")
    print(f"Filiais: {', '.join(lista_filiais)}")

    local_app_data = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    user_data_dir = os.path.join(local_app_data, "Automacao_Fechamento_XML", "sessao")
    os.makedirs(user_data_dir, exist_ok=True)

    arquivos_gerados = []
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir, headless=True,
            viewport={"width": 1366, "height": 768}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            if not await login_erp(page):
                return {"sucesso": False, "mensagem": "Falha no login do ERP ADMSIS."}

            for filial in lista_filiais:
                filial_dir = os.path.join(BASE_DIR, filial)
                os.makedirs(filial_dir, exist_ok=True)

                print(f"\n{'='*50}\nProcessando filial: {filial}\n{'='*50}")
                await baixar_nfe_zip_filial(page, filial, d_ini, d_fim)
                await baixar_relatorio_2001_filial(page, filial, d_ini, d_fim)

                # Coletar arquivos gerados para retorno
                for root, _, files in os.walk(filial_dir):
                    for f in files:
                        caminho_completo = os.path.join(root, f)
                        if os.path.getmtime(caminho_completo) >= (datetime.now() - timedelta(minutes=15)).timestamp():
                            arquivos_gerados.append(caminho_completo)

            return {
                "sucesso": True,
                "periodo": f"{str_data(d_ini)} até {str_data(d_fim)}",
                "filiais": lista_filiais,
                "arquivos": arquivos_gerados,
                "pasta_destino": BASE_DIR
            }
        finally:
            await context.close()

async def main():
    if "--inspect" in sys.argv:
        async with async_playwright() as p:
            local_app_data = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            user_data_dir = os.path.join(local_app_data, "Automacao_Fechamento_XML", "sessao")
            os.makedirs(user_data_dir, exist_ok=True)
            context = await p.chromium.launch_persistent_context(
                user_data_dir, headless=False,
                viewport={"width": 1366, "height": 768},
                args=["--start-maximized"]
            )
            page = context.pages[0] if context.pages else await context.new_page()
            if await login_erp(page):
                await inspecionar_tela(page, "0104040100", "NF-e ZIP")
                await inspecionar_tela(page, "0117020100", "Relatório 2001")
            await context.close()
            print("\nInspeção concluída.")
        return

    res = await executar_fechamento_fiscal()
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
