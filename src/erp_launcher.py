import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

USE_CAMOUFOX = os.getenv("USE_CAMOUFOX", "false").lower() in ("true", "1", "yes")

if USE_CAMOUFOX:
    from camoufox.async_api import AsyncCamoufox as BrowserLauncher
else:
    from playwright.async_api import async_playwright as BrowserLauncher

ERP_URL = os.getenv("ERP_URL", "https://erp.admsis.com/Home?eng_tela=0103070100")
USERNAME = os.getenv("ERP_USERNAME", "")
PASSWORD = os.getenv("ERP_PASSWORD", "")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

async def login(page):
    print("Login...", flush=True)
    await page.goto(ERP_URL, timeout=60000)
    await page.wait_for_selector("#usu_codigo", timeout=15000)
    await page.fill("#usu_codigo", USERNAME, timeout=10000)
    await page.fill("#usu_senha", PASSWORD, timeout=10000)
    await page.click('button:has-text("Acessar")', timeout=10000)
    await page.wait_for_load_state("networkidle", timeout=30000)
    print("Login OK", flush=True)

async def poll_frame(page, url_contains=None, name_contains=None, timeout_ms=10000):
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        for f in page.frames:
            if url_contains and url_contains in f.url:
                try:
                    ready = await f.evaluate("document.readyState")
                    if ready == "complete":
                        return f
                except:
                    pass
            if name_contains and name_contains in f.name:
                try:
                    ready = await f.evaluate("document.readyState")
                    if ready == "complete":
                        return f
                except:
                    pass
        await asyncio.sleep(0.2)
    return None

async def wait_modal_closed(page, timeout_ms=5000):
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        modal = await page.query_selector(".ui-dialog:visible, .modal:visible, [role='dialog']:visible")
        if not modal:
            return
        await asyncio.sleep(0.2)

async def find_lookup_frame(page):
    for url_sub in ["EngAjaxLookup", "lookup"]:
        for name_sub in ["eng-lookup", "lookup"]:
            lk = await poll_frame(page, url_contains=url_sub, name_contains=name_sub, timeout_ms=3000)
            if lk:
                return lk
    for f in page.frames:
        if "lookup" in f.url.lower() or "lookup" in f.name.lower() or "EngAjax" in f.url:
            try:
                ready = await f.evaluate("document.readyState")
                if ready == "complete":
                    return f
            except:
                pass
    return None

def get_pesq_selector(tipo):
    return "#pesq_ttp_funcionario_id" if tipo == "Holerit" else "#pesq_ttp_fornecedor_id"

async def search_supplier_grid(page, fornecedor, uf=None, tipo=""):
    if not fornecedor:
        return False

    pesq_sel = get_pesq_selector(tipo)
    print(f"  Buscando fornecedor direto no grid ({pesq_sel}): {fornecedor}", flush=True)

    # Try full name first, then first name only
    nomes_tentar = [fornecedor, fornecedor.split()[0]]
    for nome_tentar in nomes_tentar:
        try:
            await page.fill(pesq_sel, "", timeout=3000)
            await asyncio.sleep(0.3)
            await page.fill(pesq_sel, nome_tentar, timeout=3000)
            await asyncio.sleep(0.5)
            # Try pressing Enter to trigger filter
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
            print(f"  Digitado e Enter ({pesq_sel}): {nome_tentar}", flush=True)

            # Check if any edit links appeared in the grid
            try:
                await page.wait_for_selector("a[id^='btnEd_']", timeout=5000)
                print(f"  Grid respondeu com resultados para: {nome_tentar}", flush=True)
                return True
            except:
                continue
        except:
            continue
    return False

async def filter_grid(page, tipo=None):
    await page.wait_for_selector("#ttp_favorecido_tp_id", timeout=10000)
    if tipo == "Holerit":
        try:
            await page.select_option("#ttp_favorecido_tp_id", value="2", timeout=8000)
            print("  Tipo favorecido: FUNCIONARIO", flush=True)
        except:
            pass
    else:
        try:
            await page.select_option("#ttp_favorecido_tp_id", value="1", timeout=8000)
            print("  Tipo favorecido: FORNECEDOR", flush=True)
        except:
            pass

async def find_column_idx(page, name):
    try:
        result = await page.evaluate("""(name) => {
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                if (!table.querySelector('a[id^="btnEd_"]')) continue;
                const headerRow = table.querySelector('tr');
                if (!headerRow) continue;
                const ths = headerRow.querySelectorAll('th, td');
                for (let i = 0; i < ths.length; i++) {
                    if (ths[i].innerText.trim().includes(name)) return i;
                }
            }
            return -1;
        }""", name)
        if result >= 0:
            print(f"  Coluna {name} indice: {result}", flush=True)
            return result
    except:
        pass
    return None

async def open_matching_title(page, expected_filial):
    filial_col = await find_column_idx(page, "Filial")
    sit_col = await find_column_idx(page, "Situa") or await find_column_idx(page, "Status")
    if filial_col is not None:
        js_fn = f"""
            () => {{
                const tables = document.querySelectorAll('table');
                for (const table of tables) {{
                    if (!table.querySelector('a[id^=\"btnEd_\"]')) continue;
                    const rows = table.querySelectorAll('tr');
                    const items = [];
                    for (const tr of rows) {{
                        const link = tr.querySelector('a[id^=\"btnEd_\"]');
                        if (!link) continue;
                        const filial = tr.cells[{filial_col}]?.innerText?.trim() || '';
                        const situ = {(sit_col or '-1')} >= 0 ? (tr.cells[{sit_col or -1}]?.innerText?.trim() || '') : '';
                        items.push({{ filial, situ, linkId: link.id }});
                    }}
                    return {{ tableFound: true, itemCount: items.length, items: items }};
                }}
                return {{ tableFound: false }};
            }}
        """
        result = await page.evaluate(js_fn)
        if result.get('items'):
            it = result['items'][0]
            print(f"  Titulo mais recente: filial={it['filial']} situ={it.get('situ','?')} link={it['linkId']}", flush=True)
            await page.click(f"#{it['linkId']}")
            await page.wait_for_selector("#Copiar", timeout=10000)
            return True
        print(f"  Nenhum titulo com filial '{expected_filial}' encontrado.", flush=True)
        await page.screenshot(path=os.path.join(LOG_DIR, "erro_sem_filial.png"))
        return False

    edit_link = await page.query_selector("a[id^='btnEd_']")
    if edit_link:
        link_id = await edit_link.get_attribute("id")
        await edit_link.click()
        try:
            await page.wait_for_selector("#Copiar", timeout=5000)
        except:
            pass
        print(f"Ultimo titulo aberto: {link_id}", flush=True)
        return True
    await page.screenshot(path=os.path.join(LOG_DIR, "erro_sem_edit_link.png"))
    print("Nenhum link de edicao encontrado (fornecedor nao existe no ERP)", flush=True)
    return False

async def click_copiar(page):
    copiar = await page.wait_for_selector("#Copiar", timeout=8000)
    if copiar and await copiar.is_visible():
        await copiar.click(timeout=5000)
        for sel in ['button:has-text("Sim")', 'button:has-text("Confirmar")']:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000)
                if btn and await btn.is_visible():
                    await btn.click()
                    print(f"Copiar confirmado: {sel}", flush=True)
                    break
            except:
                continue
        await page.wait_for_load_state("networkidle", timeout=10000)
        print("Titulo copiado!", flush=True)
        return True
    print("Botao Copiar nao encontrado", flush=True)
    return False

async def get_form_frame(page, max_retries=10):
    for attempt in range(max_retries):
        frames = [f for f in page.frames if "FICHA" in f.url]
        if frames:
            return frames[-1]
        if attempt < max_retries - 1:
            try:
                await page.wait_for_selector("iframe[src*='FICHA']", timeout=2000)
            except:
                pass
    all_frames = [f.url[:80] for f in page.frames]
    print(f"  Frames disponiveis: {all_frames}", flush=True)
    return None

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

async def fill_field(ctx, selector, value, label=""):
    if not value:
        return
    try:
        await ctx.fill(selector, value, timeout=5000)
        print(f"  {label or selector}: {value}", flush=True)
    except Exception as e:
        print(f"  Erro {label or selector}: {e}", flush=True)

async def select_option_safe(ctx, selector, label_or_value, field_name=""):
    if not label_or_value:
        return
    try:
        await ctx.select_option(selector, label=label_or_value, timeout=5000)
        print(f"  {field_name}: {label_or_value}", flush=True)
    except:
        try:
            await ctx.select_option(selector, value=label_or_value, timeout=5000)
            print(f"  {field_name} (value): {label_or_value}", flush=True)
        except Exception as e:
            print(f"  Erro {field_name}: {e}", flush=True)

def valor_br(valor):
    return f"{valor:.2f}".replace(".", ",")

async def close_modal(page):
    for sel in ['button:has-text("Fechar")', "#btFechar"]:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click(timeout=3000)
                await asyncio.sleep(0.3)
                return
        except:
            pass
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
    except:
        pass
    await wait_modal_closed(page)

async def fill_fields(page, ctx, entry):
    print(f"  Preenchendo campos...", flush=True)
    fill_valor = entry.get("valor")
    if fill_valor:
        await fill_field(ctx, "#ttp_valor_titulo", valor_br(fill_valor), "Valor")

    venc = entry.get("vencimento")
    if venc:
        val_digits = venc.strftime("%d%m%Y")
        try:
            el = await ctx.query_selector("#ttp_data_vencimento")
            if el:
                await el.click()
                await asyncio.sleep(0.2)
                await el.fill("")
                await asyncio.sleep(0.2)
                await el.type(val_digits, delay=50)
                await asyncio.sleep(0.3)
                await el.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles:true})); el.dispatchEvent(new Event('blur', {bubbles:true})); }")
                await asyncio.sleep(0.2)
            print(f"  Vencimento: {val_digits}", flush=True)
        except Exception as e:
            print(f"  Erro vencimento: {e}", flush=True)

    ref = entry.get("referencia") or "REF-AUTO"
    tipo = entry.get("tipo", "")
    fornecedor_nome = (entry.get("fornecedor") or "").upper()
    is_relevo = "RELEVO" in fornecedor_nome
    is_holerit = tipo == "Holerit"

    if is_holerit:
        hoje = datetime.now()
        mes = MESES_PT[hoje.month]
        obs = f"Adiantamento Salarial - {mes}/{hoje.year % 100}"
        await fill_field(ctx, "#ttp_referencia", obs, "Referencia")
        for sel_nf in ["#ttp_numero_nota_fiscal", "#ttp_nota_fiscal", "#ttp_nf", "#ttp_numero_nf", "#ttp_documento", "#ttp_nr_nota"]:
            try:
                el = await ctx.query_selector(sel_nf)
                if el:
                    await el.fill(obs, timeout=3000)
                    print(f"  Nr. Nota Fiscal: {obs}", flush=True)
                    break
            except:
                continue
    elif is_relevo and entry.get("nf_numero"):
        obs_original = ""
        for sel_read in ["#ttp_observacao", "textarea[name*='observacao']", "#ttp_obs"]:
            try:
                el = await ctx.query_selector(sel_read)
                if el:
                    obs_original = await el.input_value()
                    break
            except:
                continue

        if "SEGUNDA REMESSA" in obs_original.upper():
            nova_remessa = "Primeira Remessa"
        elif "PRIMEIRA REMESSA" in obs_original.upper():
            nova_remessa = "Segunda Remessa"
        else:
            nova_remessa = "Primeira Remessa"

        hoje = datetime.now()
        mes = MESES_PT[hoje.month]
        obs = f"NF. {entry['nf_numero']} - {entry['parcela_atual']:02d}/{entry['total_parcelas']:02d} - {nova_remessa} - {mes}/{hoje.year % 100}"

        await fill_field(ctx, "#ttp_referencia", obs, "Referencia")
        await fill_field(ctx, "#ttp_numero_nota_fiscal", entry['nf_numero'], "Nr. Nota Fiscal")
    else:
        obs = ref
        await fill_field(ctx, "#ttp_referencia", ref, "Referencia")

        for sel_nf in ["#ttp_numero_nota_fiscal", "#ttp_nota_fiscal", "#ttp_nf", "#ttp_numero_nf", "#ttp_documento", "#ttp_nr_nota"]:
            try:
                el = await ctx.query_selector(sel_nf)
                if el:
                    await el.fill(ref, timeout=3000)
                    print(f"  Nr. Nota Fiscal: {ref}", flush=True)
                    break
            except:
                continue

    for sel_obs in ["#ttp_observacao", "#ttp_obs", "#ttp_historico", "#ttp_observacao_titulo", "textarea[name*='observacao']", "textarea[name*='obs']"]:
        try:
            el = await ctx.query_selector(sel_obs)
            if el:
                await el.fill(obs, timeout=3000)
                print(f"  Observacao: {obs}", flush=True)
                break
        except:
            continue

    await select_option_safe(ctx, "#ttp_filial_id", str(entry.get("filial", "")), "Filial")

async def click_alterar(ctx, page):
    for sel in ['button:has-text("Alterar")', '#AlterarI', '#Alterar', "input[value*='Alterar']", 'button[id*="Alterar"]']:
        try:
            btn = await ctx.query_selector(sel)
            if not btn:
                btn = await page.query_selector(sel)
            if not btn:
                continue
            await btn.click(timeout=5000, force=True, no_wait_after=True)
            print(f"  Clicou: {sel}", flush=True)
            await asyncio.sleep(1)
            for confirm in ['button:has-text("Confirmar")', 'button:has-text("OK")', 'button:has-text("Sim")', 'button:has-text("Salvar")']:
                try:
                    c = await page.wait_for_selector(confirm, timeout=5000)
                    if c and await c.is_visible():
                        await c.click()
                        print(f"  Alterar confirmado: {confirm}", flush=True)
                        break
                except:
                    continue
            return True
        except:
            continue
    print("  Botao Alterar nao encontrado", flush=True)
    return False

async def navigate_to_grid(page):
    await page.goto(ERP_URL, timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except:
        pass
    
    if await page.locator("#usu_codigo").count() > 0 or await page.locator("button:has-text('Acessar')").count() > 0:
        print("  Sessao expirada, efetuando login novamente...", flush=True)
        await login(page)
        await page.goto(ERP_URL, timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except:
            pass
    for attempt in range(3):
        try:
            await page.wait_for_selector("#pesq_ttp_fornecedor_id", timeout=15000)
            return
        except:
            await page.screenshot(path=os.path.join(LOG_DIR, f"erro_grid_nao_carregou_{attempt}.png"))
            print(f"  Aviso: grid nao carregou (tentativa {attempt+1}), recarregando...", flush=True)
            await page.goto(ERP_URL, timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except:
                pass
    await page.screenshot(path=os.path.join(LOG_DIR, "erro_grid_final.png"))
    print("  ERRO: grid nao carregou apos 3 tentativas", flush=True)
    raise SystemExit(1)

async def verify_grid_fornecedor(page, fornecedor):
    try:
        result = await page.evaluate("""(fornecedorUpper) => {
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                if (!table.querySelector('a[id^="btnEd_"]')) continue;
                const rows = table.querySelectorAll('tr');
                for (const tr of rows) {
                    const link = tr.querySelector('a[id^="btnEd_"]');
                    if (!link) continue;
                    const cells = tr.querySelectorAll('td');
                    for (let i = 0; i < cells.length; i++) {
                        const txt = cells[i].innerText.trim();
                        if (txt.toUpperCase().includes(fornecedorUpper)) {
                            return { found: true, texto: txt.substring(0, 100), coluna: i };
                        }
                    }
                }
            }
            return { found: false, texto: '' };
        }""", fornecedor.upper()[:30])
        if result.get("found"):
            print(f"  Fornecedor confirmado no grid: {result['texto']}", flush=True)
            return True
        return False
    except Exception as e:
        print(f"  Erro na verificacao: {e}", flush=True)
        return False

async def find_pendente_title(page, expected_filial):
    js_fn = """(filial) => {
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            if (!table.querySelector('a[id^="btnEd_"]')) continue;
            const rows = table.querySelectorAll('tr');
            for (const tr of rows) {
                const link = tr.querySelector('a[id^="btnEd_"]');
                if (!link) continue;
                const cells = tr.querySelectorAll('td');
                const f = cells[4]?.innerText?.trim() || '';
                const s = cells[7]?.innerText?.trim() || '';
                if (f.includes(filial) && s.includes('Pendente'))
                    return link.id;
            }
        }
        return null;
    }"""
    link_id = await page.evaluate(js_fn, expected_filial)
    if link_id:
        return link_id

    js_fn2 = """(filial) => {
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            if (!table.querySelector('a[id^="btnEd_"]')) continue;
            const rows = table.querySelectorAll('tr');
            for (const tr of rows) {
                const link = tr.querySelector('a[id^="btnEd_"]');
                if (!link) continue;
                const cells = tr.querySelectorAll('td');
                const f = cells[4]?.innerText?.trim() || '';
                if (f.includes(filial))
                    return link.id;
            }
        }
        return null;
    }"""
    return await page.evaluate(js_fn2, expected_filial)


async def click_documentos_tab(page):
    for sel in ["#tab_btn_0", 'label:has-text("Documentos")', 'a:has-text("Documentos")', 'span:has-text("Documentos")', 'li:has-text("Documentos")']:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el and await el.is_visible():
                await el.click()
                print(f"  Aba Documentos clicada: {sel}", flush=True)
                return True
        except:
            continue
    print("  Aba Documentos nao encontrada", flush=True)
    await page.screenshot(path=os.path.join(LOG_DIR, "erro_aba_documentos.png"))
    return False


async def upload_file_ged(frame, pdf_path):
    file_sel = await frame.query_selector("input[type='file']")
    if file_sel:
        try:
            await file_sel.set_input_files(pdf_path)
            print("  Arquivo selecionado via input[type=file]", flush=True)
            return True
        except Exception as e:
            print(f"  set_input_files: {e}", flush=True)

    try:
        async with frame.expect_file_chooser(timeout=10000) as fc_info:
            el = await frame.query_selector("input[type='file']")
            if el:
                await el.click()
            else:
                await frame.click("text=Selecionar", timeout=5000)
            file_chooser = await fc_info
            await file_chooser.set_files(pdf_path)
            print("  Arquivo selecionado via file chooser", flush=True)
            return True
    except Exception as e:
        print(f"  File chooser: {e}", flush=True)

    print("  ERRO: Nao foi possivel selecionar o arquivo", flush=True)
    return False


async def verify_document_attached(page, nome_doc):
    print("  Verificando anexo...", flush=True)

    # Re-poll EngGedList after upload (iframe may have reloaded)
    ged_list = await poll_frame(page, url_contains="EngGedList", timeout_ms=15000)
    if not ged_list:
        print("  Nao foi possivel verificar: sem iframe EngGedList", flush=True)
        return False

    try:
        for attempt in range(5):
            await asyncio.sleep(1)
            result = await ged_list.evaluate("""(nomeDoc) => {
                const rows = document.querySelectorAll('table tr');
                if (rows.length <= 1) return { found: false, reason: 'grid vazio' };
                const texts = Array.from(rows).map(r => r.innerText || '');
                for (const t of texts) {
                    if (t.includes(nomeDoc)) return { found: true, text: t.substring(0, 120) };
                }
                return { found: false, reason: 'nome nao encontrado', sample: texts.slice(0, 5).join(' | ') };
            }""", nome_doc)

            if result.get("found"):
                print(f"  OK: Documento confirmado no grid! ({result['text']})", flush=True)
                return True

            if "grid vazio" not in result.get("reason", ""):
                break

        print(f"  ATENCAO: {result.get('reason', '')}", flush=True)
        if result.get('sample'):
            print(f"    Linhas no grid: {result['sample']}", flush=True)
        await page.screenshot(path=os.path.join(LOG_DIR, "erro_verificacao_anexo.png"))
        return False
    except Exception as e:
        print(f"  Erro na verificacao: {e}", flush=True)
        return False


async def attach_document(page, entry):
    pdf_path = entry.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        print("  Sem PDF para anexar", flush=True)
        return

    nome_doc = os.path.basename(pdf_path)
    print(f"  Anexando documento: {nome_doc}", flush=True)

    if not await click_documentos_tab(page):
        return

    await asyncio.sleep(2)

    ged_list = await poll_frame(page, url_contains="EngGedList", timeout_ms=15000)
    if not ged_list:
        print("  Iframe EngGedList nao encontrado", flush=True)
        return

    try:
        await ged_list.click("#btNovo", timeout=10000)
        print("  btNovo clicado", flush=True)
    except:
        print("  btNovo nao encontrado", flush=True)
        return

    await asyncio.sleep(2)

    ged_novo = await poll_frame(page, url_contains="EngGedNovo", timeout_ms=15000)
    if not ged_novo:
        print("  Iframe EngGedNovo nao encontrado", flush=True)
        return

    try:
        await ged_novo.fill("#doc_descricao", "boleto", timeout=5000)
        await ged_novo.evaluate("document.getElementById('doc_descricao').dispatchEvent(new Event('keyup', {bubbles: true}))")
        print("  Descricao: boleto", flush=True)
    except:
        print("  Campo descricao nao encontrado", flush=True)

    # Trigger file chooser by clicking the visible button
    try:
        async with page.expect_file_chooser(timeout=15000) as fc_info:
            await ged_novo.locator("text=CLIQUE AQUI PARA SELECIONAR O ARQUIVO").click(timeout=10000)
        file_chooser = await fc_info.value
        await file_chooser.set_files(pdf_path)
        print("  Arquivo selecionado via botao CLIQUE AQUI...", flush=True)
    except Exception as e:
        print(f"  Erro no file chooser via botao: {e}", flush=True)
        print("  Tentando fallback via input hidden...", flush=True)
        try:
            file_input = await ged_novo.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(pdf_path)
                await ged_novo.evaluate("""() => {
                    const el = document.querySelector('input[type="file"]');
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""")
                print("  Arquivo selecionado via set_input_files", flush=True)
            else:
                print("  Input file nao encontrado no fallback", flush=True)
                return
        except Exception as fallback_e:
            print(f"  Erro no fallback: {fallback_e}", flush=True)
            return

    await page.screenshot(path=os.path.join(LOG_DIR, "04_antes_upload.png"))
    await asyncio.sleep(2)

    # Click Carregar Arquivo
    try:
        await ged_novo.click("#btNovo", force=True, timeout=10000)
        print("  Carregar Arquivo clicado", flush=True)
    except Exception as e:
        print(f"  Erro click btNovo: {e}", flush=True)
        return

    await asyncio.sleep(5)

    novo_frames = [f for f in page.frames if "EngGedNovo" in f.url]
    if novo_frames:
        print("  EngGedNovo aberto apos upload - fechando manualmente...", flush=True)
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        still = [f for f in page.frames if "EngGedNovo" in f.url]
        if still:
            await page.screenshot(path=os.path.join(LOG_DIR, "erro_engnovo_aberto.png"))
    else:
        print("  EngGedNovo fechou apos upload", flush=True)

    await page.screenshot(path=os.path.join(LOG_DIR, "04_apos_upload.png"))
    await asyncio.sleep(2)
    # The modal for EngGedNovo is closed now. Let's make sure it doesn't close the whole title.
    # We remove close_modal(page) from here to avoid closing the main title window if they share selectors.
    await verify_document_attached(page, nome_doc)

async def emitir_autorizacao_pagamento(page, entry):
    print("  Emitindo Autorizacao de Pagamento (#ImprAutPagto)...", flush=True)
    btn = await page.query_selector("#ImprAutPagto")
    if not btn or not await btn.is_visible():
        for f in page.frames:
            try:
                b = await f.query_selector("#ImprAutPagto")
                if b and await b.is_visible():
                    btn = b
                    break
            except:
                pass

    if not btn:
        print("  Botao #ImprAutPagto nao encontrado na tela", flush=True)
        return None

    captured_url = None
    def on_response(response):
        nonlocal captured_url
        if "EngRelatorio" in response.url or "Pdf/840" in response.url:
            captured_url = response.url

    page.context.on("response", on_response)
    try:
        await btn.click()
    except Exception as e:
        print(f"  Erro ao clicar em #ImprAutPagto: {e}", flush=True)
        try:
            page.context.remove_listener("response", on_response)
        except:
            pass
        return None

    for _ in range(25):
        if captured_url:
            break
        await asyncio.sleep(0.4)

    try:
        page.context.remove_listener("response", on_response)
    except:
        pass

    if not captured_url:
        print("  Aviso: URL da Autorizacao de Pagamento nao interceptada", flush=True)
        return None

    try:
        print(f"  Baixando PDF da Autorizacao: {captured_url[:60]}...", flush=True)
        resp = await page.context.request.get(captured_url)
        if resp.status == 200:
            pdf_bytes = await resp.body()
            doc_id = entry.get("documento") or entry.get("nf_numero") or "aut"
            filename = f"autorizacao_pagamento_{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            save_path = os.path.join(LOG_DIR, filename)
            with open(save_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"  OK: Autorizacao de Pagamento salva com sucesso! ({filename}, {len(pdf_bytes)} bytes)", flush=True)
            entry["autorizacao_pdf"] = save_path
            return save_path
        else:
            print(f"  Erro ao baixar PDF da Autorizacao: HTTP {resp.status}", flush=True)
            return None
    except Exception as e:
        print(f"  Erro no download da Autorizacao: {e}", flush=True)
        return None

async def process_entry(page, entry):
    fornecedor = str(entry.get("fornecedor", ""))
    uf = entry.get("uf")
    print(f"\n--- Processando {fornecedor} - R$ {entry.get('valor',0):.2f} ---", flush=True)

    tipo = entry.get("tipo", "")

    await navigate_to_grid(page)

    if tipo == "Holerit":
        # Holerit: buscar direto pelo campo de funcionario
        await page.wait_for_selector("#pesq_ttp_funcionario_id", timeout=15000)
        nomes_tentar = [fornecedor, fornecedor.split()[0]]
        for nome_tentar in nomes_tentar:
            try:
                await page.fill("#pesq_ttp_funcionario_id", "", timeout=3000)
                await asyncio.sleep(0.3)
                await page.fill("#pesq_ttp_funcionario_id", nome_tentar, timeout=3000)
                await asyncio.sleep(0.5)

                # Try lookup button next to funcionario field
                for lk_sel in ["#btnLookupJanela_ttp_funcionario_id", "button[id*='Lookup'][id*='funcionario']", "button[id*='LookupJanela']"]:
                    try:
                        btn = await page.query_selector(lk_sel)
                        if btn:
                            await btn.click(timeout=5000)
                            await asyncio.sleep(1.5)
                            print(f"  Lookup funcionario clicado: {lk_sel}", flush=True)
                            break
                    except:
                        continue

                # If lookup opened, try to use it
                lk_frame = await find_lookup_frame(page)
                if lk_frame:
                    try:
                        await lk_frame.fill("#txtPesquisa", nome_tentar, timeout=5000)
                        for sel in ["#btEnviar", "#btnPesquisar", 'button:has-text("Pesquisar")']:
                            try:
                                btn_s = await lk_frame.query_selector(sel)
                                if btn_s and await btn_s.is_visible():
                                    await btn_s.click(timeout=5000)
                                    break
                            except:
                                continue
                        await asyncio.sleep(1.5)
                        # Try to select first result
                        for att in range(3):
                            try:
                                links = await lk_frame.query_selector_all("a[href*='Selecionar']")
                                if not links:
                                    links = await lk_frame.query_selector_all("table tr td a")
                                for link in links:
                                    href = await link.get_attribute("href") or ""
                                    m = re.search(r"Selecionar\((\d+)\)", href)
                                    if m and m.group(1) != "-1":
                                        await lk_frame.evaluate(f"Selecionar({m.group(1)})")
                                        print(f"  Selecionado funcionario: {nome_tentar}", flush=True)
                                        await asyncio.sleep(1)
                                        break
                                    text = await link.inner_text()
                                    if nome_tentar.upper() in text.upper():
                                        await link.click()
                                        print(f"  Selecionado: {text[:60]}", flush=True)
                                        await asyncio.sleep(1)
                                        break
                                break
                            except:
                                pass
                            await asyncio.sleep(0.5)
                        await close_modal(page)
                    except:
                        pass
                else:
                    # No lookup, try Enter
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                    print(f"  Buscando funcionario: {nome_tentar}", flush=True)

                try:
                    await page.click("#ConfirmaFiltroS", timeout=5000)
                    await asyncio.sleep(1)
                    print("  Filtro confirmado (ConfirmaFiltroS)", flush=True)
                except:
                    print("  ConfirmaFiltroS nao encontrado, tentando Enter...", flush=True)
                    try:
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(1)
                    except:
                        pass

                try:
                    await page.wait_for_selector("a[id^='btnEd_']", timeout=10000)
                    print(f"  Resultados encontrados para: {nome_tentar}", flush=True)
                    break
                except:
                    # Debug: check page structure
                    # Debug: check all frames for the grid
                    print(f"  DEBUG frames: {[{'id':f.name, 'url':f.url[:100]} for f in page.frames]}", flush=True)
                    for f in page.frames:
                        try:
                            has_tables = await f.evaluate("document.querySelectorAll('table').length")
                            has_edit = await f.evaluate("document.querySelectorAll('a[id^=\"btnEd_\"]').length")
                            if has_edit > 0:
                                print(f"  ENCONTRADO grid no frame: {f.url[:100]} (editLinks={has_edit})", flush=True)
                        except:
                            pass
                    continue
            except:
                continue
        await page.screenshot(path=os.path.join(LOG_DIR, "grid_state.png"))
    else:
        await filter_grid(page, tipo=tipo)
        await search_supplier_grid(page, fornecedor, uf=uf, tipo=tipo)
        try:
            await page.click("#ConfirmaFiltroS", timeout=15000)
            await page.wait_for_selector("a[id^='btnEd_']", timeout=10000)
            print("  Grid filtrado", flush=True)
        except:
            print("  ConfirmaFiltroS nao encontrado", flush=True)

        if not await verify_grid_fornecedor(page, fornecedor):
            nomes_tentar = []
            partes = fornecedor.split()
            if len(partes) > 2:
                nomes_tentar.append(" ".join(partes[:2]))
            nomes_tentar.append(partes[0])
            pesq_sel = get_pesq_selector(tipo)
            for nome_tentativa in nomes_tentar:
                print(f"  Fornecedor nao confirmado no grid, tentando ({pesq_sel}): {nome_tentativa}", flush=True)
                try:
                    await page.fill(pesq_sel, nome_tentativa, timeout=3000)
                    await page.keyboard.press("Tab")
                    await asyncio.sleep(1)
                    try:
                        await page.wait_for_selector("a[id^='btnEd_']", timeout=8000)
                    except:
                        pass
                    if await verify_grid_fornecedor(page, fornecedor):
                        print(f"  Fornecedor confirmado: {nome_tentativa}", flush=True)
                        break
                except:
                    pass

    await asyncio.sleep(0.5)
    try:
        await page.click("#header_ttp_data_vencimento", timeout=5000)
        await asyncio.sleep(1)
        print("  Ordenado por Data Vencimento ASC", flush=True)
    except:
        print("  Header Data Vencimento nao encontrado", flush=True)

    expected_filial = str(entry.get("filial", ""))
    if not await open_matching_title(page, expected_filial):
        await page.screenshot(path=os.path.join(LOG_DIR, "erro_sem_titulo.png"))
        print(f"  ERRO: Nenhum titulo com filial {expected_filial}. Pulando para o proximo.", flush=True)
        await close_modal(page)
        return

    if not await click_copiar(page):
        return

    frame = await get_form_frame(page)
    ctx = frame if frame else page
    await fill_fields(page, ctx, entry)

    await page.screenshot(path=os.path.join(LOG_DIR, "02_preenchido.png"))
    await click_alterar(ctx, page)
    await page.screenshot(path=os.path.join(LOG_DIR, "03_final.png"))

    # Wait for form to stabilize before attaching document
    await asyncio.sleep(2)
    
    # We DO NOT close the modal/window. We stay on the title we just altered.
    if tipo not in ["Holerit"]:
        await attach_document(page, entry)
    else:
        print("  Tipo Holerit: anexo de documento ignorado", flush=True)

    # Emitir e capturar a Autorizacao de Pagamento oficial do ERP
    try:
        await emitir_autorizacao_pagamento(page, entry)
    except Exception as e:
        print(f"  Aviso ao emitir autorizacao: {e}", flush=True)

    # Now that document is attached and authorization generated, close the title window
    await close_modal(page)
    await asyncio.sleep(1)

    print(f"--- Concluido: {fornecedor} - R$ {entry.get('valor',0):.2f} ---", flush=True)

async def suppress_page_errors(page):
    page.on("pageerror", lambda err: print(f"  [Page error suppressed] {err}", flush=True))

async def launch_erp(entries):
    if USE_CAMOUFOX:
        async with BrowserLauncher() as browser:
            page = await browser.new_page()
            await suppress_page_errors(page)
            await login(page)
            try:
                for entry in entries:
                    await process_entry(page, entry)
            finally:
                try:
                    await browser.close()
                except:
                    pass
    else:
        async with BrowserLauncher() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await suppress_page_errors(page)
            await login(page)
            try:
                for entry in entries:
                    await process_entry(page, entry)
            finally:
                try:
                    await browser.close()
                except:
                    pass

def run_entries(entries):
    asyncio.run(launch_erp(entries))
