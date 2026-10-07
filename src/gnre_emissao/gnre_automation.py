from playwright.sync_api import sync_playwright
import os
import re
import argparse
from pathlib import Path
try:
    from PyPDF2 import PdfReader
except ImportError:
    raise ImportError('PyPDF2 is required. Install via pip install PyPDF2')
import os
import time
import mimetypes
import urllib.request
import urllib.error
import uuid
import random
from urllib.parse import urljoin
from datetime import datetime, timedelta

hoje = datetime.now()
amanha = hoje + timedelta(days=1)

# Dados da NF (extrair do DANFE)
def extract_data_from_pdf(pdf_path: str) -> dict:
    """Extract required GNRE fields from a Danfe/Nota Fiscal PDF.
    Returns a dictionary with keys matching the original `dados` structure.
    If a field cannot be found, an empty string is returned for that key.
    """
    text = ""
    reader = PdfReader(pdf_path)
    for page in reader.pages:
        text += page.extract_text() + "\n"
    # Helper regexes
    cnpj_pat = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
    chave_pat = re.compile(r"\d{44}")  # Will be used on text without spaces
    valor_pat = re.compile(r"[\d\.]+,\d{2}")
    data_pat = re.compile(r"\d{2}/\d{2}/\d{4}")
    nf_pat = re.compile(r"NF\s*(\d+)", re.IGNORECASE)

    def first_match(pattern):
        m = pattern.search(text)
        return m.group(0) if m else ""

    def first_match_chave(pattern):
        # Remove all whitespace and then search for 44 consecutive digits
        text_no_spaces = re.sub(r'\s', '', text)
        m = pattern.search(text_no_spaces)
        return m.group(0) if m else ""

    dados_extracted = {
        "uf_favorecida": "RJ",  # default could be overridden if needed
        "cnpj": first_match(cnpj_pat),
        "razao_social": "",  # not reliably in PDF, leave blank
        "endereco": "",
        "uf_emitente": "SP",
        "municipio": "3518800",
        "cep": "",
        "telefone": "",
        "receita": "100099",
        "chave_dfe": first_match_chave(chave_pat),
        "valor_icms_st": "",
        "valor_fcp": "",
        "data_emissao": "",
        "data_vencimento": "",
        "data_pagamento": "",
        "info_complementares": "",
        "numero_nf": "",
    }
    # Attempt to fill numeric values using heuristics
    # Find all monetary values (assuming first is ICMS/ST, second is FCP)
    valores = valor_pat.findall(text)
    if len(valores) >= 2:
        dados_extracted["valor_icms_st"] = valores[0]
        dados_extracted["valor_fcp"] = valores[1]
    elif len(valores) == 1:
        dados_extracted["valor_icms_st"] = valores[0]

    # Dates: try to get emission, due, payment
    datas = data_pat.findall(text)
    if datas:
        dados_extracted["data_emissao"] = datas[0]
        if len(datas) > 1:
            dados_extracted["data_vencimento"] = datas[1]
        if len(datas) > 2:
            dados_extracted["data_pagamento"] = datas[2]

    # NF number
    nf_match = nf_pat.search(text)
    if nf_match:
        dados_extracted["numero_nf"] = nf_match.group(1)
        dados_extracted["info_complementares"] = f"NF {nf_match.group(1)}"
    return dados_extracted

def run(dados=None):
    # If no data provided, fall back to hard‑coded example (useful for testing)
    if dados is None:
        # default example data (same as original script)
        dados = {
            "uf_favorecida": "RJ",
            "cnpj": "71.883.656/0001-48",
            "razao_social": "Nevine",
            "endereco": "Rua Silvio Manfredi, 404",
            "uf_emitente": "SP",
            "municipio": "3518800",
            "cep": "07222040",
            "telefone": "1155723945",
            "receita": "100099",
            "chave_dfe": "35260571883656000148550020000008041718836560",
            "valor_icms_st": "2337,54",
            "valor_fcp": "320,49",
            "data_emissao": hoje.strftime("%d/%m/%Y"),
            "data_vencimento": amanha.strftime("%d/%m/%Y"),
            "data_pagamento": amanha.strftime("%d/%m/%Y"),
            "info_complementares": "NF 804",
            "numero_nf": "804",
        }

    # Existing logic follows unchanged (browser automation)...

from dotenv import load_dotenv
load_dotenv()
EMAIL = os.getenv("GNRE_EMAIL")
SENHA = os.getenv("GNRE_SENHA")
SAVE_PATH = os.getenv("GNRE_SAVE_PATH") or str(Path(__file__).resolve().parent)
os.makedirs(SAVE_PATH, exist_ok=True)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GNRE_REPORT_CHANNEL_ID = (
    os.getenv("DISCORD_GNRE_REPORT_CHANNEL_ID")
    or os.getenv("DISCORD_GNRE_CHANNEL_ID")
    or os.getenv("DISCORD_CHANNEL_ID", "")
).strip()


def get_uf_path(uf: str) -> str:
    """Retorna e cria o diretório gnre/{UF}/ para salvar o PDF do estado."""
    base = os.path.join(SAVE_PATH, "gnre", uf.upper() if uf else "OUTROS")
    os.makedirs(base, exist_ok=True)
    return base


def enviar_discord(pdf_path, dados):
    """Envia PDF ao Discord. Tenta webhook primeiro (mais confiável),
    bot token como fallback."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    bot_token = (os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN).strip()
    canal_id = (
        os.getenv("DISCORD_GNRE_REPORT_CHANNEL_ID")
        or os.getenv("DISCORD_GNRE_CHANNEL_ID")
        or os.getenv("DISCORD_CHANNEL_ID")
        or DISCORD_GNRE_REPORT_CHANNEL_ID
    ).strip()
    bot_url = None
    if bot_token and canal_id:
        bot_url = f"https://discord.com/api/v10/channels/{canal_id}/messages"
    if not webhook_url and not bot_url:
        print("  [INFO] Discord nao configurado; envio do PDF ignorado.")
        return False
    if not pdf_path or not os.path.exists(pdf_path):
        print("  [AVISO] PDF nao encontrado para envio ao Discord.")
        return False

    boundary = f"----GNRE{uuid.uuid4().hex}"
    filename = os.path.basename(pdf_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    payload = {
        "content": (
            f"GNRE gerada - NF {dados.get('numero_nf', '')} "
            f"({dados.get('uf_favorecida', '')})"
        )
    }

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="payload_json"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json_dumps_ascii(payload).encode())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    with open(pdf_path, "rb") as f:
        body.extend(f.read())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())


    # Tenta webhook primeiro (mais estável), bot token como fallback
    urls_to_try = []
    if webhook_url:
        urls_to_try.append(("webhook", webhook_url, {}))
    if bot_url:
        urls_to_try.append(("bot", bot_url, {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}))

    for metodo, url, extra_headers in urls_to_try:
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0 GNREAutomation/1.0",
            "Accept": "application/json",
        }
        headers.update(extra_headers)
        req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    print(f"  [OK] PDF enviado ao Discord via {metodo}.")
                    return True
                print(f"  [AVISO] Discord ({metodo}) retornou HTTP {resp.status}.")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            print(f"  [AVISO] Falha ao enviar PDF ao Discord ({metodo}): HTTP {e.code} {detail}")
        except Exception as e:
            print(f"  [AVISO] Falha ao enviar PDF ao Discord ({metodo}): {e}")

    print("  [ERRO] Todos os métodos Discord falharam para envio do PDF.")
    return False


def enviar_alerta_discord(mensagem):
    """Envia alerta de texto ao Discord. Tenta webhook primeiro (mais confiável),
    bot token como fallback."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    bot_token = (os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN).strip()
    canal_id = (
        os.getenv("DISCORD_GNRE_REPORT_CHANNEL_ID")
        or os.getenv("DISCORD_GNRE_CHANNEL_ID")
        or os.getenv("DISCORD_CHANNEL_ID")
        or DISCORD_GNRE_REPORT_CHANNEL_ID
    ).strip()
    bot_url = None
    if bot_token and canal_id:
        bot_url = f"https://discord.com/api/v10/channels/{canal_id}/messages"

    if not webhook_url and not bot_url:
        print("  [INFO] Discord nao configurado; alerta ignorado.")
        return False

    payload = {"content": mensagem[:1900]}
    body = json_dumps_ascii(payload).encode("utf-8")

    # Tenta webhook primeiro (sem autenticação extra, mais estável)
    urls_to_try = []
    if webhook_url:
        urls_to_try.append(("webhook", webhook_url, {}))
    if bot_url:
        urls_to_try.append(("bot", bot_url, {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}))

    for metodo, url, extra_headers in urls_to_try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 GNREAutomation/1.0",
            "Accept": "application/json",
        }
        headers.update(extra_headers)
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    print(f"  [OK] Alerta enviado ao Discord via {metodo}.")
                    return True
                print(f"  [AVISO] Discord ({metodo}) retornou HTTP {resp.status}.")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            print(f"  [AVISO] Discord ({metodo}) falhou: HTTP {e.code} {detail}")
        except Exception as e:
            print(f"  [AVISO] Discord ({metodo}) falhou: {e}")

    print("  [ERRO] Todos os métodos Discord falharam.")
    return False


def json_dumps_ascii(payload):
    import json
    return json.dumps(payload, ensure_ascii=True)


def validar_dados_gnre(dados):
    obrigatorios = ("uf_favorecida", "cnpj", "razao_social", "endereco", "cep", "telefone", "numero_nf")
    faltando = [campo for campo in obrigatorios if not dados.get(campo)]
    if not dados.get("chave_dfe") and not dados.get("numero_nf"):
        faltando.append("chave_dfe/numero_nf")
    if dados.get("uf_favorecida") == "RJ" and len(dados.get("chave_dfe", "")) != 44:
        faltando.append("chave_dfe_44_digitos")
    if not dados.get("valor_icms_st") and not dados.get("valor_fcp"):
        faltando.append("valor_icms_st/valor_fcp")
    return faltando

def processar_gnre(dados, use_cdp=False, use_camoufox=False, persistent_camoufox=False):
    dados = (dados or {}).copy()
    if dados.get("uf_favorecida") in ("PR", "BA", "DF"):
        dados["tipo_doc_origem"] = "10"
        
    faltando = validar_dados_gnre(dados)
    if faltando:
        print(f"[AVISO] Dados incompletos para GNRE: {', '.join(faltando)}")
        if "chave_dfe_44_digitos" in faltando:
            raise ValueError("RJ exige chave DFe com 44 digitos; geracao interrompida.")

    with sync_playwright() as p:
        if use_camoufox:
            from camoufox import NewBrowser
            print("Usando Camoufox (navegador anti-deteccao)...")
            camoufox_kwargs = {
                "headless": True,
                "humanize": True,
                "window": (1280, 800),
            }
            if persistent_camoufox:
                profile_dir = os.path.join(get_uf_path(dados.get("uf_favorecida", "")), ".camoufox_profile")
                os.makedirs(profile_dir, exist_ok=True)
                camoufox_kwargs.update({
                    "persistent_context": True,
                    "user_data_dir": profile_dir,
                })
                print(f"  Perfil persistente Camoufox: {profile_dir}")
            browser = NewBrowser(p, **camoufox_kwargs)
            if hasattr(browser, 'new_context'):
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()
            else:
                context = browser
                page = context.pages[0] if context.pages else context.new_page()
            webdriver_check = page.evaluate("() => navigator.webdriver")
            print(f"  navigator.webdriver: {webdriver_check}")
            use_cdp_browser = False
        elif use_cdp:
            import subprocess
            CDP_PORT = 9222
            cdp_url = f"http://localhost:{CDP_PORT}"

            print(f"Aguardando Chrome em {cdp_url} (ate 120s)...")
            print("Certifique-se de que o Chrome foi aberto com:")
            print(f"  chrome.exe --remote-debugging-port={CDP_PORT}")
            print()

            for i in range(120):
                time.sleep(1)
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    print(f"  Conectou em {i+1}s!")
                    break
                except:
                    if i % 10 == 0:
                        print(f"  Aguardando... ({i+1}s)")
                    pass
            else:
                print(f"[ERRO] Chrome nao encontrado na porta {CDP_PORT}.")
                print("Abra o Chrome manualmente com o comando acima e tente novamente.")
                return

            print("Chrome conectado via CDP!")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            webdriver_check = page.evaluate("() => navigator.webdriver")
            print(f"  navigator.webdriver: {webdriver_check}")

            use_cdp_browser = True
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            use_cdp_browser = False

        print("1. Acessando site GNRE...")
        for tentativa in range(3):
            try:
                page.goto("https://www.gnre.pe.gov.br:444/gnre/v/guia/index", wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"  Tentativa {tentativa+1}: {e}")
            page.wait_for_timeout(8000)
            url_atual = page.evaluate("() => window.location.href")
            print(f"  URL atual: {url_atual}")
            if page.locator('#ufFavorecida').count() > 0:
                break
            print(f"  Tentativa {tentativa+1}: #ufFavorecida nao encontrado")
            if tentativa < 2:
                page.wait_for_timeout(5000)

        # Verifica se tem login
        if page.locator('input[name="email"]').count() > 0 or page.locator('input[type="email"]').count() > 0:
            print("2. Fazendo login...")
            try:
                if page.locator('input[name="email"]').count() > 0:
                    page.fill('input[name="email"]', EMAIL)
                elif page.locator('input[type="email"]').count() > 0:
                    page.fill('input[type="email"]', EMAIL)
            except: pass

            try:
                if page.locator('input[name="password"]').count() > 0:
                    page.fill('input[name="password"]', SENHA)
                elif page.locator('input[type="password"]').count() > 0:
                    page.fill('input[type="password"]', SENHA)
            except: pass

            try:
                page.click('button[type="submit"]')
            except: pass

            page.wait_for_timeout(3000)

        print("3. Preenchendo formulário GNRE...")

        def rm_overlay():
            page.evaluate("() => document.querySelectorAll('.ui-widget-overlay, .ui-dialog, .blockUI, .blockOverlay').forEach(el => el.remove())")
        rm_overlay()
        
        # Definir valores padrão conforme requisitos do usuário
        dados["receita"] = "100099"
        # Data de emissão, vencimento e pagamento
        hoje = datetime.now()
        # Regra de vencimento:
        # - Antes das 12h: vence hoje
        # - Depois das 12h: vence amanhã
        # - Se cair sábado/domingo: próxima segunda
        if hoje.hour < 12:
            venc = hoje
        else:
            venc = hoje + timedelta(days=1)
        # Ajusta fim de semana
        while venc.weekday() >= 5:  # 5=Sat, 6=Sun
            venc += timedelta(days=1)
        dados["data_emissao"] = hoje.strftime("%d/%m/%Y")
        dados["data_vencimento"] = venc.strftime("%d/%m/%Y")
        dados["data_pagamento"] = venc.strftime("%d/%m/%Y")
        # Normalizar valores monetários (trocar vírgula por ponto, remover separadores de milhar)
        def normalize(val):
            if not val:
                return val
            return val.replace(".", "").replace(",", ".")
        dados["valor_icms_st"] = normalize(dados.get("valor_icms_st", ""))
        dados["valor_fcp"] = normalize(dados.get("valor_fcp", ""))
        # UF Favorecida - selecionar pode disparar navegação
        rm_overlay()
        print(f"  Selecionando UF: {dados['uf_favorecida']}...")
        if page.locator('#ufFavorecida').count() > 0:
            # Tenta com expect_navigation (se navegar)
            try:
                with page.expect_navigation(timeout=15000):
                    page.select_option('#ufFavorecida', dados["uf_favorecida"])
                page.wait_for_load_state("networkidle")
            except:
                # Se não navegou, apenas seleciona e prossegue
                page.select_option('#ufFavorecida', dados["uf_favorecida"])
            page.wait_for_timeout(3000)
            # Aguarda o form recarregar
            for i in range(15):
                if page.locator('#receita').count() > 0 or page.locator('#documentoEmitente').count() > 0:
                    break
                page.wait_for_timeout(2000)

        # Seleciona GNRE Simples e aguarda os campos aparecerem
        rm_overlay()
        if page.locator('#optGnreSimples').count() > 0:
            try:
                page.click('#optGnreSimples', timeout=5000)
            except:
                page.evaluate("document.getElementById('optGnreSimples')?.click()")
        page.wait_for_timeout(2000)

        # NÃO inscrito - expande o formulário
        rm_overlay()
        if page.locator('#optNaoInscrito').count() > 0:
            try:
                page.click('#optNaoInscrito', timeout=5000)
            except:
                page.evaluate("document.getElementById('optNaoInscrito')?.click()")
        page.wait_for_timeout(2000)

        # Tipo documento: CNPJ
        rm_overlay()
        if page.locator('#tipoCNPJ').count() > 0:
            try:
                page.click('#tipoCNPJ', timeout=5000)
            except:
                page.evaluate("document.getElementById('tipoCNPJ')?.click()")
        page.wait_for_timeout(500)

        # CNPJ do emitente
        if page.locator('#documentoEmitente').count() > 0:
            page.fill('#documentoEmitente', dados["cnpj"])
        
        # Razão Social
        if page.locator('#razaoSocialEmitente').count() > 0:
            page.fill('#razaoSocialEmitente', dados["razao_social"])

        # Endereço
        if page.locator('#enderecoEmitente').count() > 0:
            page.fill('#enderecoEmitente', dados["endereco"])

        # UF Emitente
        try:
            if page.locator('#ufEmitente').count() > 0:
                page.select_option('#ufEmitente', dados["uf_emitente"], timeout=5000)
                page.evaluate("document.getElementById('ufEmitente').dispatchEvent(new Event('change'))")
        except Exception as e:
            print(f"  [AVISO] Nao foi possivel selecionar UF Emitente via Playwright: {e}")
            try:
                page.evaluate(f"() => {{ var el = document.getElementById('ufEmitente'); if (el) {{ el.value = '{dados['uf_emitente']}'; el.dispatchEvent(new Event('change')); }} }}")
                print("  UF Emitente selecionada via JS.")
            except Exception as e2:
                print(f"  [AVISO] Falha ao preencher UF Emitente via JS: {e2}")
        
        page.wait_for_timeout(5000)
        
        # Municipality selection
        if page.locator('#municipioEmitente').count() > 0:
            options = page.locator('#municipioEmitente option').count()
            print(f"  Município: {options} opções encontradas")
            
            if options > 1:
                page.evaluate("""
                    () => {
                        const sel = document.getElementById('municipioEmitente');
                        for (let i = 0; i < sel.options.length; i++) {
                            const opt = sel.options[i];
                            if (opt.text.includes('São Paulo') || opt.text.includes('3550308') || opt.text.toUpperCase().includes('SAO PAULO')) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                break;
                            }
                        }
                    }
                """)
                print("  Município: selecionado via JS")
            
            page.wait_for_timeout(500)

        # CEP
        if page.locator('#cepEmitente').count() > 0:
            page.fill('#cepEmitente', dados["cep"])

        # Telefone
        if page.locator('#telefoneEmitente').count() > 0:
            page.fill('#telefoneEmitente', dados["telefone"])

        # Receita
        try:
            page.wait_for_selector('#receita', timeout=5000)
            page.select_option('#receita', dados["receita"], timeout=5000)
            print("  Receita selecionada.")
        except Exception as e:
            print("  [ERRO] Não foi possível selecionar a Receita via #receita:", e)
            try:
                page.select_option('select[name="codigoReceita"]', dados["receita"], timeout=5000)
                print("  Receita selecionada via name.")
            except Exception as e2:
                print("  [ERRO] Receita não encontrada via name:", e2)
                try:
                    page.select_option('#codigoReceita', dados["receita"], timeout=5000)
                    print("  Receita selecionada via #codigoReceita.")
                except Exception as e3:
                    print("  [ERRO] Receita não encontrada em nenhum selector.", e3)
                    try:
                        page.evaluate(f"() => {{ var el = document.getElementById('receita') || document.querySelector('select[name=\"codigoReceita\"]') || document.getElementById('codigoReceita'); if (el) {{ el.value = '{dados['receita']}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }} }}")
                        print("  Receita selecionada via JS fallback.")
                    except Exception as e4:
                        print("  [ERRO] Falha no fallback JS de Receita:", e4)
        page.wait_for_timeout(2000)

        # Tipo Documento Origem
        tipo_doc = dados.get("tipo_doc_origem", "24")  # default 24, override via dados
        try:
            page.wait_for_selector('#tipoDocOrigem', timeout=5000)
            page.select_option('#tipoDocOrigem', tipo_doc, timeout=5000)
            page.evaluate("document.getElementById('tipoDocOrigem').dispatchEvent(new Event('change', {bubbles: true}))")
            print(f"  Tipo Documento Origem: {tipo_doc}")
        except Exception as e:
            print(f"  [AVISO] Não foi possível selecionar Tipo Documento Origem {tipo_doc} via Playwright (pode não existir): {e}")
            try:
                page.evaluate(f"""() => {{
                    var el = document.getElementById('tipoDocOrigem');
                    if (el) {{
                        var found = false;
                        for (var i = 0; i < el.options.length; i++) {{
                            var txt = (el.options[i].text || '').toUpperCase();
                            var wantsNota = '{tipo_doc}' === '10';
                            var textMatches = wantsNota
                                ? (txt.includes('NOTA') || txt.includes('FISCAL') || txt.includes('DANFE'))
                                : (txt.includes('CHAVE') || txt.includes('NFE') || txt.includes('DFE'));
                            if (el.options[i].value === '{tipo_doc}' || textMatches) {{
                                el.selectedIndex = i;
                                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                                found = true;
                                break;
                            }}
                        }}
                        if (!found && !('{tipo_doc}' === '10') && el.options.length > 1) {{
                            el.selectedIndex = 1;
                            el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        }}
                    }}
                }}""")
                print("  Tipo Documento Origem selecionado via JS fallback.")
            except Exception as e2:
                print(f"  [AVISO] Falha no fallback JS de Tipo Documento Origem: {e2}")
        page.wait_for_timeout(1000)

        # Chave do DFe ou numero da nota fiscal - tentativa múltipla
        documento_origem = dados["numero_nf"] if tipo_doc == "10" else dados["chave_dfe"]
        try:
            page.fill('#numeroDocumentoOrigem', documento_origem, timeout=5000)
            print(f"  Documento Origem preenchido: {documento_origem}")
        except Exception as e:
            print(f"  [AVISO] Não preencheu Chave DFe via #numeroDocumentoOrigem: {e}")
            # Se falhou, tenta campoAdicional00 (RN usa como Chave de Acesso da NFe)
            try:
                if page.locator('#campoAdicional00').count() > 0:
                    is_chave = page.evaluate("""() => {
                        var el = document.getElementById('campoAdicional00');
                        return el && (el.maxLength == 44 || (el.title || '').toLowerCase().includes('chave'));
                    }""")
                    if is_chave:
                        page.fill('#campoAdicional00', dados["chave_dfe"])
                        print("  Chave DFe preenchida via #campoAdicional00 (Chave de Acesso da NFe)")
            except Exception as e2:
                print(f"  [AVISO] Chave via campoAdicional00: {e2}")
            # Fallback: outros seletores
            try:
                page.fill('input[name*="chave"]', documento_origem, timeout=3000)
                print("  Documento Origem preenchido via name.")
            except:
                try:
                    page.fill('#chaveDFe', documento_origem, timeout=3000)
                    print("  Documento Origem preenchido via #chaveDFe.")
                except:
                    try:
                        page.fill('#documentoOrigem', documento_origem, timeout=3000)
                        print("  Documento Origem preenchido via #documentoOrigem.")
                    except:
                        page.evaluate("""(chave) => {
                            var el = document.querySelector('input[name*="documento"], input[title*="documento"], input[id*="documento"]');
                            if (el) { el.value = chave; el.dispatchEvent(new Event('input', {bubbles: true})); }
                        }""", documento_origem)
        # Data Emissao (NAO usar #campoAdicional00)
        try:
            page.fill('input[name*="Emissao"], input[name*="emissao"]', dados["data_emissao"], timeout=3000)
        except:
            try:
                if page.locator('#campoAdicional00').count() > 0:
                    campo = page.locator('#campoAdicional00')
                    is_chave = page.evaluate("""() => {
                        var el = document.getElementById('campoAdicional00');
                        return el && (el.maxLength == 44 || (el.title || '').toLowerCase().includes('chave'));
                    }""")
                    if not is_chave:
                        campo.fill(dados["data_emissao"], timeout=3000)
                        print("  Data Emissao preenchida via #campoAdicional00.")
                    else:
                        print("  [AVISO] Campo Data Emissao nao encontrado ou nao necessario.")
                else:
                    print("  [AVISO] Campo Data Emissao nao encontrado ou nao necessario.")
            except Exception as e:
                print(f"  [AVISO] Campo Data Emissao nao preenchido: {e}")
        # Informações Complementares
        try:
            if page.locator('#campoAdicional01').count() > 0:
                page.fill('#campoAdicional01', dados["info_complementares"], timeout=3000)
            else:
                page.fill('input[name*="complementares"], textarea[name*="informacoes"]', dados["info_complementares"], timeout=3000)
        except Exception as e:
            print("  [AVISO] Campo Informações Complementares não preenchido:", e)

        # Data Vencimento - tentativa múltipla
        try:
            page.fill('#dataVencimento', dados["data_vencimento"], timeout=5000)
        except Exception as e:
            print("  [AVISO] Não preencheu Data Vencimento via #dataVencimento:", e)
            # Tenta seletor alternativo
            try:
                page.fill('input[name*="vencimento"]', dados["data_vencimento"], timeout=5000)
                print("  Data Vencimento preenchida via nome.")
            except Exception as e2:
                print("  [AVISO] Falha ao preencher Data Vencimento em todos os seletores.", e2)

        # Valor ICMS/ST - tentativa múltipla
        rm_overlay()
        try:
            loc = page.locator('#valor')
            loc.wait_for(state="attached", timeout=5000)
            loc.click()
            page.keyboard.press('Control+A')
            page.keyboard.press('Backspace')
            loc.type(dados["valor_icms_st"].replace('.', ','), delay=50)
        except Exception as e:
            print("  [AVISO] Não preencheu Valor ICMS/ST via #valor:", e)
            # Fallback: define via JS
            try:
                page.evaluate("""(val) => {
                    var el = document.getElementById('valor');
                    if (el) { el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); }
                }""", dados["valor_icms_st"].replace('.', ','))
                print("  Valor ICMS/ST preenchido via JS.")
            except Exception as e2:
                print("  [AVISO] Falha ao preencher Valor ICMS/ST.", e2)

        # Valor FCP - tentativa múltipla
        rm_overlay()
        try:
            loc_fcp = page.locator('#valorFecp')
            loc_fcp.wait_for(state="attached", timeout=5000)
            loc_fcp.click()
            page.keyboard.press('Control+A')
            page.keyboard.press('Backspace')
            loc_fcp.type(dados["valor_fcp"].replace('.', ','), delay=50)
        except Exception as e:
            print("  [AVISO] Não preencheu Valor FCP via #valorFecp:", e)
            # Fallback: define via JS
            try:
                page.evaluate("""(val) => {
                    var el = document.getElementById('valorFecp');
                    if (el) { el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); }
                }""", dados["valor_fcp"].replace('.', ','))
                print("  Valor FCP preenchido via JS.")
            except Exception as e2:
                print("  [AVISO] Falha ao preencher Valor FCP via JS.", e2)

        # Data Pagamento - tentativa múltipla
        try:
            page.fill('#dataPagamento', dados["data_pagamento"], timeout=5000)
        except Exception as e:
            print("  [AVISO] Não preencheu Data Pagamento via #dataPagamento:", e)
            # Tenta seletor alternativo
            try:
                page.fill('input[name*="pagamento"]', dados["data_pagamento"], timeout=5000)
                print("  Data Pagamento preenchida via nome.")
            except Exception as e2:
                print("  [AVISO] Falha ao preencher Data Pagamento em todos os seletores.", e2)

        page.wait_for_timeout(1000)

        # === Referência da Receita (mês/ano) ===
        hoje_local = datetime.now()
        try:
            mes = page.locator('#mesReferencia')
            if mes.count() > 0:
                mes.select_option(str(hoje_local.month).zfill(2))
                print(f"  Mês Referência: {str(hoje_local.month).zfill(2)}")
        except Exception as e:
            print(f"  [AVISO] Mês Referência: {e}")
        try:
            ano = page.locator('#anoReferencia')
            if ano.count() > 0:
                ano.select_option(str(hoje_local.year))
                print(f"  Ano Referência: {str(hoje_local.year)}")
        except Exception as e:
            print(f"  [AVISO] Ano Referência: {e}")

        if dados.get("uf_favorecida") == "BA":
            try:
                preenchidos = page.evaluate("""() => {
                    var changed = [];
                    document.querySelectorAll('select.campoObrigatorio').forEach(function(sel) {
                        if (sel.value) return;
                        for (var i = 0; i < sel.options.length; i++) {
                            var opt = sel.options[i];
                            if (opt.value && !/selecione/i.test(opt.text || '')) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                changed.push((sel.id || sel.name || 'select') + '=' + opt.text);
                                break;
                            }
                        }
                    });
                    return changed;
                }""")
                if preenchidos:
                    print(f"  Selects obrigatórios preenchidos via fallback BA: {preenchidos}")
            except Exception as e:
                print(f"  [AVISO] Fallback selects obrigatórios BA: {e}")

        # === Produto (AL, AM, BA, CE, PE e outros) ===
        produto_ok = True
        if dados.get("uf_favorecida") in ("AL", "AM", "BA", "CE", "PE"):
            produto_ok = False
            try:
                prod = page.locator('#produto')
                if prod.count() > 0:
                    produto_ok = page.evaluate("""() => {
                        var sel = document.getElementById('produto');
                        if (!sel) return false;
                        for (var i = 0; i < sel.options.length; i++) {
                            var txt = sel.options[i].text.toLowerCase();
                            if (txt.includes('cosmetic') || txt.includes('perfum') || txt.includes('higiene') || txt.includes('toucador')) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                console.log('Produto selecionado:', sel.options[i].text);
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if produto_ok:
                        print("  Produto: cosméticos/perfumaria/higiene selecionado")
                    else:
                        print("  [ERRO] Produto obrigatório não encontrado/selecionado.")
            except Exception as e:
                print(f"  [AVISO] Produto: {e}")

        if dados.get("uf_favorecida") == "AL" and not produto_ok:
            print("  [ERRO] AL exige Produto em Complementos da Receita. Validação cancelada.")
            try:
                page.screenshot(path=os.path.join(get_uf_path("AL"), "erro_produto_obrigatorio.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            return None

        # === Convênio (RN e outros) ===
        try:
            conv = page.locator('#convenio')
            if conv.count() > 0:
                rm_overlay()
                if conv.get_attribute('type') == 'text' or conv.evaluate("el => el.tagName") == 'INPUT':
                    conv.fill('NAO_CONVENIADO')
                else:
                    conv.select_option('NAO_CONVENIADO')
                print("  Convênio: NAO_CONVENIADO")
        except Exception as e:
            print(f"  [AVISO] Convênio: {e}")

        def preencher_destinatario_visivel():
            cliente_cnpj_local = dados.get("cliente_cnpj", "")
            cliente_razao_local = dados.get("cliente_razao", "")
            cliente_municipio_local = dados.get("cliente_municipio", "")
            cliente_uf_local = dados.get("cliente_uf", dados.get("uf_favorecida", ""))
            cliente_cep_local = dados.get("cliente_cep", "")
            cliente_endereco_local = dados.get("cliente_endereco", "")

            def selecionar_por_texto(selector, texto, valor_fallback=None):
                if not texto and not valor_fallback:
                    return False
                try:
                    loc = page.locator(selector)
                    if loc.count() == 0:
                        return False
                    return page.evaluate("""({selector, texto, valorFallback}) => {
                        function norm(s) {
                            return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase().trim();
                        }
                        var sel = document.querySelector(selector);
                        if (!sel) return false;
                        var alvo = norm(texto);
                        for (var i = 0; i < sel.options.length; i++) {
                            var opt = sel.options[i];
                            if ((valorFallback && opt.value === valorFallback) || (alvo && norm(opt.text).includes(alvo))) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                        return false;
                    }""", {"selector": selector, "texto": texto, "valorFallback": valor_fallback})
                except Exception:
                    return False

            def preencher_primeiro(seletores, valor, label):
                if not valor:
                    return False
                for selector in seletores:
                    try:
                        loc = page.locator(selector)
                        if loc.count() > 0:
                            loc.first.fill(valor)
                            print(f"  {label} preenchido.")
                            return True
                    except Exception:
                        pass
                return False

            def preencher_destinatario_por_secao():
                if not (cliente_cnpj_local or cliente_razao_local or cliente_municipio_local):
                    return {}
                try:
                    return page.evaluate("""(dadosDest) => {
                        function norm(s) {
                            return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase().trim();
                        }
                        function visivel(el) {
                            if (!el) return false;
                            var st = getComputedStyle(el);
                            var r = el.getBoundingClientRect();
                            return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                        }
                        function setValor(el, valor) {
                            if (!el || !valor) return false;
                            el.value = valor;
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }
                        function contexto(el) {
                            var partes = [];
                            if (el.id) {
                                var lab = document.querySelector('label[for="' + el.id + '"]');
                                if (lab) partes.push(lab.innerText || lab.textContent || '');
                            }
                            if (el.parentElement) partes.push(el.parentElement.innerText || el.parentElement.textContent || '');
                            return norm(partes.join(' '));
                        }
                        var marcadores = Array.from(document.querySelectorAll('legend,h1,h2,h3,h4,b,strong,span,div,td'))
                            .filter(function(el) {
                                return visivel(el) && norm(el.innerText || el.textContent).includes('CONTRIBUINTE DESTINATARIO');
                            })
                            .sort(function(a, b) { return a.getBoundingClientRect().top - b.getBoundingClientRect().top; });
                        var marcador = marcadores[marcadores.length - 1];
                        if (!marcador) return {sectionFound: false};
                        var section = marcador.closest('fieldset') || marcador.parentElement;
                        for (var i = 0; section && i < 5; i++) {
                            if (section.querySelectorAll('input,select,textarea').length >= 3) break;
                            section = section.parentElement;
                        }
                        if (!section) return {sectionFound: false};
                        var result = {sectionFound: true};

                        function controls() {
                            var marcadorTop = marcador.getBoundingClientRect().top;
                            return Array.from(section.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), select, textarea'))
                                .filter(function(el) { return visivel(el) && !el.disabled && el.getBoundingClientRect().top >= marcadorTop; })
                                .sort(function(a, b) {
                                    var ar = a.getBoundingClientRect();
                                    var br = b.getBoundingClientRect();
                                    return (ar.top - br.top) || (ar.left - br.left);
                                });
                        }
                        function controleDepoisDoLabel(labelTexto, pred) {
                            var alvo = norm(labelTexto);
                            var labels = Array.from(section.querySelectorAll('label,span,div,td'))
                                .filter(function(el) {
                                    var txt = norm(el.innerText || el.textContent);
                                    return visivel(el) && txt.includes(alvo);
                                })
                                .sort(function(a, b) { return a.getBoundingClientRect().top - b.getBoundingClientRect().top; });
                            var label = labels[labels.length - 1];
                            if (!label) return null;
                            var lr = label.getBoundingClientRect();
                            return controls().find(function(el) {
                                var r = el.getBoundingClientRect();
                                return r.top >= lr.top - 3 && (!pred || pred(el));
                            }) || null;
                        }
                        function selecionarOption(sel, texto, valor) {
                            if (!sel) return false;
                            var alvo = norm(texto);
                            for (var i = 0; i < sel.options.length; i++) {
                                var opt = sel.options[i];
                                if ((valor && opt.value === valor) || (alvo && norm(opt.text).includes(alvo))) {
                                    sel.selectedIndex = i;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                            }
                            return false;
                        }

                        var doc = controleDepoisDoLabel('DOCUMENTO DE IDENTIFICACAO', function(el) {
                            return el.tagName !== 'SELECT';
                        });
                        if (!doc || (doc.value || '').trim()) {
                            doc = controls().find(function(el) {
                                if (el.tagName === 'SELECT') return false;
                                var tipo = (el.type || '').toLowerCase();
                                if (tipo === 'button' || tipo === 'submit') return false;
                                return !(el.value || '').trim();
                            }) || doc;
                        }
                        if (doc) {
                            var docRect = doc.getBoundingClientRect();
                            Array.from(section.querySelectorAll('input[type="radio"]')).forEach(function(radio) {
                                var rr = radio.getBoundingClientRect();
                                if (Math.abs(rr.top - docRect.top) > 16) return;
                                var txt = '';
                                if (radio.id) {
                                    var lab = document.querySelector('label[for="' + radio.id + '"]');
                                    if (lab) txt += ' ' + (lab.innerText || lab.textContent || '');
                                }
                                var node = radio.nextSibling;
                                for (var i = 0; node && i < 3; i++, node = node.nextSibling) {
                                    txt += ' ' + (node.innerText || node.textContent || '');
                                }
                                if (norm(radio.value).includes('CNPJ') || norm(txt).includes('CNPJ')) {
                                    radio.click();
                                    result.tipoDocumento = 'CNPJ';
                                }
                            });
                        }
                        if (setValor(doc, dadosDest.cnpj)) result.documento = dadosDest.cnpj;

                        var razao = controleDepoisDoLabel('RAZAO SOCIAL', function(el) {
                            return el.tagName !== 'SELECT';
                        });
                        if (setValor(razao, dadosDest.razao)) result.razao = dadosDest.razao;

                        var uf = controleDepoisDoLabel('UF', function(el) { return el.tagName === 'SELECT'; });
                        if (selecionarOption(uf, dadosDest.uf, dadosDest.uf)) result.uf = dadosDest.uf;

                        var municipio = controleDepoisDoLabel('MUNICIPIO', function(el) { return el.tagName === 'SELECT'; });
                        if (selecionarOption(municipio, dadosDest.municipio, null)) result.municipio = dadosDest.municipio;

                        return result;
                    }""", {
                        "cnpj": cliente_cnpj_local,
                        "razao": cliente_razao_local[:60],
                        "municipio": cliente_municipio_local,
                        "uf": cliente_uf_local,
                    })
                except Exception as e:
                    return {"erro": str(e)}

            if cliente_cnpj_local:
                try:
                    cnpj_radio = page.locator('#tipoCNPJDest')
                    if cnpj_radio.count() > 0:
                        cnpj_radio.click()
                        print("  Tipo Doc Destinatário: CNPJ (#tipoCNPJDest)")
                except Exception as e:
                    print(f"  [AVISO] Tipo CNPJ Destinatário: {e}")
                try:
                    tdd = page.locator('#tipoDocumentoDestinatario')
                    if tdd.count() > 0:
                        try:
                            tdd.select_option('CNPJ')
                        except Exception:
                            selecionar_por_texto('#tipoDocumentoDestinatario', 'CNPJ')
                        print("  Tipo Doc Destinatário: CNPJ")
                except Exception as e:
                    print(f"  [AVISO] Tipo Doc Destinatário: {e}")
                try:
                    doc_dest = page.locator('#documentoDestinatario')
                    if doc_dest.count() > 0:
                        doc_dest.fill(cliente_cnpj_local)
                        if not doc_dest.input_value().strip():
                            doc_dest.fill(re.sub(r"\D", "", cliente_cnpj_local))
                        print("  CNPJ Destinatário preenchido via #documentoDestinatario.")
                except Exception as e:
                    print(f"  [AVISO] #documentoDestinatario: {e}")
                if not preencher_primeiro((
                    '#documentoDestinatario',
                    '#cnpjDestinatario',
                    'input[name="documentoDestinatario"]',
                    'input[name*="cnpj" i][name*="dest" i]',
                    'input[id*="cnpj" i][id*="dest" i]',
                ), cliente_cnpj_local, "CNPJ Destinatário"):
                    print("  [AVISO] CNPJ Destinatário não encontrado.")
            if cliente_razao_local:
                if not preencher_primeiro((
                    '#razaoSocialDestinatario',
                    'input[name="razaoSocialDestinatario"]',
                    'input[name*="razao" i][name*="dest" i]',
                    'input[id*="razao" i][id*="dest" i]',
                ), cliente_razao_local[:60], "Razão Social Destinatário"):
                    print("  [AVISO] Razão Social Destinatário não encontrada.")
            if cliente_uf_local:
                if selecionar_por_texto('#ufDestinatario', cliente_uf_local, cliente_uf_local):
                    print(f"  UF Destinatário: {cliente_uf_local}")
            if cliente_municipio_local:
                if selecionar_por_texto('#municipioDestinatario', cliente_municipio_local):
                    print(f"  Município Destinatário: {cliente_municipio_local}")
                else:
                    print(f"  [AVISO] Município Destinatário não encontrado: {cliente_municipio_local}")
            preencher_primeiro((
                '#cepDestinatario',
                'input[name="cepDestinatario"]',
                'input[name*="cep" i][name*="dest" i]',
                'input[id*="cep" i][id*="dest" i]',
            ), cliente_cep_local, "CEP Destinatário")
            preencher_primeiro((
                '#enderecoDestinatario',
                'input[name="enderecoDestinatario"]',
                'input[name*="endereco" i][name*="dest" i]',
                'input[id*="endereco" i][id*="dest" i]',
            ), cliente_endereco_local, "Endereço Destinatário")
            preenchido_secao = preencher_destinatario_por_secao()
            if preenchido_secao.get("documento"):
                print("  CNPJ Destinatário preenchido via seção.")
            if preenchido_secao.get("razao"):
                print("  Razão Social Destinatário preenchida via seção.")
            if preenchido_secao.get("municipio"):
                print(f"  Município Destinatário preenchido via seção: {cliente_municipio_local}")
            if preenchido_secao.get("erro"):
                print(f"  [AVISO] Destinatário por seção: {preenchido_secao['erro']}")

        # === Destinatário (RN e outros) ===
        cliente_cnpj = dados.get("cliente_cnpj", "")
        cliente_razao = dados.get("cliente_razao", "")
        preencher_destinatario_visivel()
        if cliente_cnpj:
            try:
                mc = page.locator('#municipioDestinatario')
                if mc.count() > 0:
                    mc.select_option('08102')
                    print("  Município Destinatário: NATAL/RN (08102)")
            except Exception as e:
                print(f"  [AVISO] Município Destinatário: {e}")

        # === Contribuinte Destinatário (Inscrito na UF Favorecida - SIM + IE) ===
        # Necessário para RN, RS, AL, AM e outros (exceto RJ, DF, BA)
        uf_contrib = dados.get("uf_favorecida", "")
        ufs_contrib_sim = ("RN", "RS", "AL", "AM")
        ie_dest = dados.get("ie_destinatario", "")
        if uf_contrib == "AL" and not ie_dest:
            print("  [ERRO] AL exige Inscrição Estadual do destinatário. Validação cancelada antes do reCAPTCHA.")
            try:
                page.screenshot(path=os.path.join(get_uf_path("AL"), "erro_ie_destinatario_obrigatoria.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            return None
        if uf_contrib == "CE" and not ie_dest:
            try:
                rm_overlay()
                if page.locator('#optNaoInscritoDest').count() > 0:
                    page.click('#optNaoInscritoDest')
                    print(f"  Contribuinte Destinatário: NÃO (#optNaoInscritoDest)")
                elif page.locator('input[name="tipoContribuinteDestinatario"][value="false"]').count() > 0:
                    page.locator('input[name="tipoContribuinteDestinatario"][value="false"]').click()
                    print(f"  Contribuinte Destinatário: NÃO (radio value=false)")
                elif page.locator('input[name*="tipoContribuinte"]').count() > 0:
                    page.evaluate("""() => {
                        var radios = document.querySelectorAll('input[name*="tipoContribuinte"]');
                        for (var r of radios) {
                            var id = (r.id || '').toLowerCase();
                            if (r.value === 'false' || r.value === 'N' || id.includes('nao') || id.includes('não')) {
                                r.click(); break;
                            }
                        }
                    }""")
                    print(f"  Contribuinte Destinatário: NÃO (fallback JS)")
                page.wait_for_timeout(1000)
                preencher_destinatario_visivel()
            except Exception as e:
                print(f"  [AVISO] Contribuinte Destinatário NÃO: {e}")

        if uf_contrib in ufs_contrib_sim or (uf_contrib == "CE" and ie_dest) or (uf_contrib not in ("RJ", "DF", "CE", "BA") and ie_dest):
            try:
                rm_overlay()
                # Tenta clicar no radio SIM do Contribuinte Destinatário
                if page.locator('#optInscritoDest').count() > 0:
                    page.click('#optInscritoDest')
                    print(f"  Contribuinte Destinatário: SIM (#optInscritoDest)")
                elif page.locator('input[name="tipoContribuinteDestinatario"][value="true"]').count() > 0:
                    page.locator('input[name="tipoContribuinteDestinatario"][value="true"]').click()
                    print(f"  Contribuinte Destinatário: SIM (radio value=true)")
                elif page.locator('input[name*="tipoContribuinte"]').count() > 0:
                    page.evaluate("""() => {
                        var radios = document.querySelectorAll('input[name*="tipoContribuinte"]');
                        for (var r of radios) {
                            if (r.value === 'true' || r.value === 'S' || r.id.includes('Sim')) {
                                r.click(); break;
                            }
                        }
                    }""")
                    print(f"  Contribuinte Destinatário: SIM (fallback JS)")
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"  [AVISO] Contribuinte Destinatário SIM: {e}")

            # Preenche IE do destinatário
            if ie_dest:
                try:
                    if page.locator('#ieDestinatario').count() > 0:
                        page.fill('#ieDestinatario', ie_dest)
                        print(f"  IE Destinatário preenchida: {ie_dest}")
                    elif page.locator('#inscricaoEstadualDestinatario').count() > 0:
                        page.fill('#inscricaoEstadualDestinatario', ie_dest)
                        print(f"  IE Destinatário preenchida via #inscricaoEstadualDestinatario: {ie_dest}")
                    else:
                        ie_field = page.locator('input[name*="ie" i], input[name*="inscricao" i], input[id*="ie" i], input[id*="inscricao" i]').first
                        if ie_field.count() > 0:
                            ie_field.fill(ie_dest)
                            print(f"  IE Destinatário preenchida (fallback): {ie_dest}")
                except Exception as e:
                    print(f"  [AVISO] IE Destinatário: {e}")

        _uf_path = get_uf_path(dados.get("uf_favorecida", ""))
        try:
            obrigatorios_vazios = page.evaluate("""() => {
                function visivel(el) {
                    if (!el) return false;
                    var st = getComputedStyle(el);
                    var r = el.getBoundingClientRect();
                    return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                }
                function valorCampo(el) {
                    if (!el) return '';
                    if (el.tagName === 'SELECT') return el.value || '';
                    if (el.type === 'radio' || el.type === 'checkbox') {
                        var checked = document.querySelector('input[name="' + el.name + '"]:checked');
                        return checked ? checked.value : '';
                    }
                    return el.value || '';
                }
                var vazios = [];
                document.querySelectorAll('label, td, div, span').forEach(function(label) {
                    var txt = (label.innerText || label.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (!txt || (!txt.includes('*') && !txt.includes('+'))) return;
                    var campo = null;
                    var forId = label.getAttribute && label.getAttribute('for');
                    if (forId) campo = document.getElementById(forId);
                    var parent = label.parentElement;
                    for (var i = 0; !campo && parent && i < 3; i++, parent = parent.parentElement) {
                        campo = parent.querySelector('input, select, textarea');
                    }
                    if (!campo || !visivel(campo) || campo.disabled) return;
                    if (!valorCampo(campo)) vazios.push(txt.slice(0, 80));
                });
                return Array.from(new Set(vazios)).slice(0, 20);
            }""")
            if obrigatorios_vazios:
                print(f"  [AVISO] Campos obrigatórios ainda vazios: {obrigatorios_vazios}")
                try:
                    debug_dest = page.evaluate("""() => {
                        function norm(s) {
                            return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase().trim();
                        }
                        function visivel(el) {
                            var st = getComputedStyle(el);
                            var r = el.getBoundingClientRect();
                            return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                        }
                        var marcadores = Array.from(document.querySelectorAll('legend,h1,h2,h3,h4,b,strong,span,div,td'))
                            .filter(function(el) {
                                return visivel(el) && norm(el.innerText || el.textContent).includes('CONTRIBUINTE DESTINATARIO');
                            })
                            .sort(function(a, b) { return a.getBoundingClientRect().top - b.getBoundingClientRect().top; });
                        var marcador = marcadores[marcadores.length - 1];
                        if (!marcador) return [];
                        var markerTop = marcador.getBoundingClientRect().top;
                        return Array.from(document.querySelectorAll('input,select,textarea'))
                            .filter(function(el) { return visivel(el) && el.getBoundingClientRect().top >= markerTop; })
                            .slice(0, 20)
                            .map(function(el) {
                                var r = el.getBoundingClientRect();
                                return {
                                    tag: el.tagName,
                                    type: el.type || '',
                                    id: el.id || '',
                                    name: el.name || '',
                                    value: el.value || '',
                                    checked: !!el.checked,
                                    x: Math.round(r.left),
                                    y: Math.round(r.top)
                                };
                            });
                    }""")
                    print(f"  Debug campos destinatário: {debug_dest}")
                except Exception as e:
                    print(f"  [AVISO] Debug destinatário: {e}")
            else:
                print("  Campos obrigatórios visíveis: sem vazios detectados.")
        except Exception as e:
            obrigatorios_vazios = []
            print(f"  [AVISO] Verificação de obrigatórios: {e}")
        page.screenshot(path=os.path.join(_uf_path, "form_preenchido.png"), full_page=True)

        if dados.get("uf_favorecida") == "CE" and any("Documento de Identificação" in campo for campo in obrigatorios_vazios):
            print("  [ERRO] CE ainda está sem Documento de Identificação do destinatário. Validação cancelada antes do reCAPTCHA.")
            browser.close()
            return None

        print("\n=== FORMULÁRIO PREENCHIDO ===")
        print(f"CNPJ: {dados['cnpj']}")
        print(f"Chave DFe: {dados['chave_dfe']}")
        print(f"Valor ICMS/ST: R$ {dados['valor_icms_st']}")
        print(f"Valor FCP: R$ {dados['valor_fcp']}")

        uf = dados.get("uf_favorecida", "")
        ufs_action_digitar = ("DF", "PE")
        ufs_pre_action_gerar = ("RJ", "BA")
        ufs_submit_action_gerar = ("RJ", "BA")
        if uf in ufs_pre_action_gerar:
            page.evaluate("""() => {
                var f = document.querySelector('form');
                if (f) f.action = '/gnre/v/guia/gerar';
            }""")
            print("  Form action pre-ajustado para /gnre/v/guia/gerar antes do Validar")

        sucesso_validacao = False
        btn_emitir = None

        print("\nClicando Validar e aguardando reCAPTCHA automático...")
        rm_overlay()
        page.wait_for_timeout(500)

        def clicar_validar_humano():
            btn = page.locator("#validar")
            if btn.count() == 0:
                return False
            try:
                btn.scroll_into_view_if_needed(timeout=5000)
                page.wait_for_timeout(random.randint(600, 1400))
                btn.click(timeout=5000)
                return True
            except Exception:
                try:
                    btn.click(timeout=5000)
                    return True
                except Exception:
                    page.evaluate("() => { var el = document.getElementById('validar'); if (el) el.click(); }")
                    return True

        # Habilita dataPagamento antes de submeter
        page.evaluate("""() => {
            var dp = document.getElementById('dataPagamento');
            if (dp) dp.removeAttribute('disabled');
        }""")

        # Tenta clicar no botao Validar (pode disparar reCAPTCHA via JS inline)
        tem_validar = page.locator("#validar").count() > 0
        if tem_validar:
            rm_overlay()
            clicar_validar_humano()
            print("  Botao Validar clicado, aguardando reCAPTCHA...")

        # Aguarda reCAPTCHA gerar token (ate 30s)
        token = ""
        for i in range(30):
            time.sleep(1)
            token = page.evaluate("() => { var el = document.getElementById('g-recaptcha-response'); return el ? el.value : ''; }")
            if token and len(token) > 50:
                print(f"  reCAPTCHA token obtido ({len(token)} chars) em {i+1}s")
                break

        page.evaluate("""() => {
            var dp = document.getElementById('dataPagamento');
            if (dp) dp.removeAttribute('disabled');
        }""")

        # Se o clique em Validar ja gerou token, nao reexecuta o captcha.
        if not (token and len(token) > 50):
            page.evaluate("""() => {
                try {
                    if (typeof grecaptcha !== 'undefined') {
                        var widgets = document.querySelectorAll('.g-recaptcha');
                        widgets.forEach(function(w) {
                            var id = w.getAttribute('data-widget-id');
                            if (id !== null) grecaptcha.execute(parseInt(id));
                        });
                    }
                } catch(e) {}
            }""")
            page.wait_for_timeout(3000)
            for i in range(10):
                time.sleep(1)
                token = page.evaluate("() => { var el = document.getElementById('g-recaptcha-response'); return el ? el.value : ''; }")
                if token and len(token) > 50:
                    print(f"  Token obtido apos grecaptcha.execute() ({i+1}s)")
                    break

        if not (token and len(token) > 50):
            if dados.get("uf_favorecida") == "CE":
                print("  [AVISO] Token CE não veio no primeiro Validar; reiniciando navegador em nova tentativa.")
            else:
                for tentativa_token in range(2):
                    print(f"  [AVISO] Token reCAPTCHA vazio; tentando Validar novamente ({tentativa_token + 1}/2)...")
                    clicar_validar_humano()
                    page.wait_for_timeout(3000)
                    page.evaluate("""() => {
                        try {
                            if (typeof grecaptcha !== 'undefined') {
                                var widgets = document.querySelectorAll('.g-recaptcha');
                                widgets.forEach(function(w) {
                                    var id = w.getAttribute('data-widget-id');
                                    if (id !== null) grecaptcha.execute(parseInt(id));
                                });
                            }
                        } catch(e) {}
                    }""")
                    for i in range(15):
                        time.sleep(1)
                        token = page.evaluate("() => { var el = document.getElementById('g-recaptcha-response'); return el ? el.value : ''; }")
                        if token and len(token) > 50:
                            print(f"  Token obtido apos nova tentativa ({len(token)} chars) em {i+1}s")
                            break
                    if token and len(token) > 50:
                        break

        if not (token and len(token) > 50):
            print("  [ERRO] reCAPTCHA nao gerou token; submissao cancelada para evitar sessao expirada.")
            try:
                page.screenshot(path=os.path.join(get_uf_path(dados.get("uf_favorecida", "")), "erro_captcha_sem_token.png"))
            except Exception:
                pass
            browser.close()
            return None

        if uf in ufs_submit_action_gerar:
            page.evaluate("""() => {
                var f = document.querySelector('form');
                if (f) f.action = '/gnre/v/guia/gerar';
            }""")
            print("  Form action confirmado como /gnre/v/guia/gerar")
        elif uf in ufs_action_digitar:
            print("  Form action mantido como digitar para UF especial")
        else:
            print("  Form action original mantido para esta UF")
        current_action = page.evaluate("() => { var f = document.querySelector('form'); return f ? f.action : 'no-form'; }")
        print(f"  Form action atual: {current_action}")

        # Submete formulario via requestSubmit() para navegacao natural
        print("  Submetendo formulario via requestSubmit()...")
        page.evaluate("""() => {
            var f = document.querySelector('form');
            if (!f) return;
            var validar = document.getElementById('validar');
            if (validar && validar.name && !f.querySelector('input[type="hidden"][name="' + validar.name + '"]')) {
                var hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = validar.name;
                hidden.value = validar.value || 'Validar';
                f.appendChild(hidden);
            }
            try { f.requestSubmit(); } catch(e) { f.submit(); }
        }""")
        print("  Form submitted, aguardando navegacao...")
        # Aguarda ate 20s para navegacao completar
        for _ in range(10):
            page.wait_for_timeout(2000)
            url_seg = page.url.split('/')[-1]
            if url_seg != "digitar" and url_seg != "index":
                break
        url_atual = page.url.split('/')[-1]
        print(f"  URL apos submit: {url_atual}")

        # Se foi redirecionado para index, tenta acessar resultado diretamente
        if url_atual == "index":
            print("  Redirect para index detectado, tentando /guia/resultado...")
            for _ in range(3):
                try:
                    page.goto("https://www.gnre.pe.gov.br:444/gnre/v/guia/resultado", timeout=15000)
                    page.wait_for_timeout(3000)
                    url_seg = page.url.split('/')[-1]
                    if url_seg != "index":
                        break
                except:
                    pass

        print("Aguardando ate 120s para confirmacao...")
        sucesso_validacao = False
        btn_emitir = None
        for tent in range(60):
            time.sleep(2)
            url_seg = page.url.split('/')[-1]
            try:
                body = page.evaluate("() => document.body.innerText")
            except:
                body = ""

            body_lower = body.lower()
            if "sessão expirada" in body_lower or "sessao expirada" in body_lower:
                print("  [ERRO] Sessao expirada detectada na tela de resultado.")
                break

            # Detect success: Emitir/Baixar buttons or resultado page
            if "Emitir" in body or "Baixar" in body:
                botoes_habilitados = page.locator(
                    'input[value="Emitir"]:not([disabled]), input[value="Baixar PDF"]:not([disabled]), '
                    'button:has-text("Emitir"):not([disabled]), button:has-text("Baixar PDF"):not([disabled])'
                ).count()
                if botoes_habilitados > 0:
                    print(f"  Confirmacao! url={url_seg}")
                    sucesso_validacao = True
                    btn_emitir = page.locator('input[value="Emitir"], input[value="Baixar PDF"]').first
                    break
                print("  [AVISO] Tela com Emitir/Baixar PDF, mas botões desabilitados; aguardando dados da guia...")

            if url_seg == "resultado" or url_seg == "confirmacao":
                print(f"  Pagina de {url_seg} detectada! Verificando...")
                # Check for success indicators
                has_erro = (
                    "erro" in body_lower[:500]
                    or "não foi possível" in body_lower
                    or "sessão expirada" in body_lower
                    or "sessao expirada" in body_lower
                )
                if not has_erro:
                    botoes_habilitados = page.locator(
                        'input[value="Emitir"]:not([disabled]), input[value="Baixar PDF"]:not([disabled]), '
                        'a:has-text("Baixar"), a:has-text("PDF"), button:has-text("Emitir"):not([disabled]), button:has-text("Baixar PDF"):not([disabled])'
                    ).count()
                    if botoes_habilitados > 0:
                        sucesso_validacao = True
                        print(f"  Pagina de {url_seg} - botoes habilitados, considerando sucesso!")
                        btn_emitir = page.locator('input[value="Emitir"], input[value="Baixar PDF"], a:has-text("Baixar"), a:has-text("PDF")').first
                        break
                    print(f"  Pagina de {url_seg} detectada, mas sem botoes habilitados.")
                else:
                    print(f"  Pagina de {url_seg} COM erros")

            if tent == 0:
                has_challenge = page.evaluate("""() => {
                    var frames = document.querySelectorAll('iframe[title*="desafio"], iframe[title*="challenge"]');
                    return frames.length > 0;
                }""")
                has_badge = page.evaluate("""() => {
                    var el = document.querySelector('.grecaptcha-badge');
                    return el ? el.style.visibility !== 'hidden' : false;
                }""")
                token_vazio = page.evaluate("""() => {
                    var el = document.getElementById('g-recaptcha-response');
                    return el ? el.value.length : -1;
                }""")
                print(f"  Desafio reCAPTCHA: {has_challenge}, badge visivel: {has_badge}, token_len: {token_vazio}")
            if tent % 5 == 0:
                print(f"  [{tent*2+2}s] url={url_seg}")

        if not sucesso_validacao:
            print("\n[ERRO FATAL] Nao foi possivel gerar a GNRE.")
            try:
                page.screenshot(path=os.path.join(get_uf_path(dados.get("uf_favorecida", "")), "erro_final.png"))
            except: pass
            browser.close()
            return None

        print("\nProcessando tela de confirmação...")
        pdf_path = None
        try:
            
            # Tenta validar o valor, mas prossegue mesmo se falhar
            total_calc = round(float(dados['valor_icms_st']) + float(dados['valor_fcp']), 2)
            total_esperado = f"{total_calc:.2f}".replace('.', ',')
            texto_pagina = page.locator('body').inner_text()
            if total_esperado in texto_pagina.replace('.', ''):
                print(f"  [OK] Valor R$ {total_esperado} confirmado na tela!")
            else:
                print(f"  [AVISO] Valor R$ {total_esperado} nao encontrado exatamente na tela, prosseguindo...")
            
            print("  Baixando PDF...")
            try:
                pdf_path_alvo = os.path.join(get_uf_path(dados.get("uf_favorecida", "")), f"GNRE NF {dados['numero_nf']}.pdf")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                try:
                    botoes_debug = page.evaluate("""() => Array.from(document.querySelectorAll('input, button, a'))
                        .map(function(el, idx) {
                            var r = el.getBoundingClientRect();
                            return {
                                idx: idx,
                                tag: el.tagName,
                                type: el.type || '',
                                id: el.id || '',
                                name: el.name || '',
                                value: (el.value || '').trim(),
                                text: (el.innerText || el.textContent || '').trim(),
                                href: el.href || '',
                                onclick: el.getAttribute('onclick') || '',
                                disabled: !!el.disabled,
                                visible: r.width > 0 && r.height > 0
                            };
                        })
                        .filter(function(x) { return x.value || x.text || x.href || x.onclick; })
                        .slice(0, 40)
                    """)
                    print(f"  Botoes/links visiveis: {botoes_debug}")
                except Exception:
                    pass

                def salvar_bytes_pdf(content, origem):
                    if not content or not content.startswith(b"%PDF"):
                        return None
                    with open(pdf_path_alvo, "wb") as f:
                        f.write(content)
                    print(f"  PDF capturado via {origem}.")
                    return pdf_path_alvo

                def salvar_response_pdf(response, origem):
                    try:
                        content_type = (response.headers.get("content-type") or "").lower()
                        body = response.body()
                        if "pdf" in content_type or (body and body.startswith(b"%PDF")):
                            return salvar_bytes_pdf(body, origem)
                    except Exception as e:
                        print(f"  [AVISO] Resposta PDF ({origem}): {e}")
                    return None

                def marcar_botao_por_termos(termos):
                    return page.evaluate("""(termos) => {
                        function visivel(el) {
                            var st = getComputedStyle(el);
                            var r = el.getBoundingClientRect();
                            return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                        }
                        var alvo = termos.map(function(t) { return t.toUpperCase(); });
                        var els = Array.from(document.querySelectorAll('input, button, a'));
                        for (var i = 0; i < els.length; i++) {
                            var el = els[i];
                            var texto = ((el.value || '') + ' ' + (el.innerText || el.textContent || '') + ' ' + (el.href || '') + ' ' + (el.getAttribute('onclick') || '')).toUpperCase();
                            if (!visivel(el) || el.disabled) continue;
                            if (alvo.some(function(t) { return texto.includes(t); })) {
                                el.setAttribute('data-gnre-download-target', '1');
                                return {
                                    idx: i,
                                    tag: el.tagName,
                                    type: el.type || '',
                                    id: el.id || '',
                                    name: el.name || '',
                                    value: el.value || '',
                                    text: el.innerText || el.textContent || '',
                                    href: el.href || '',
                                    onclick: el.getAttribute('onclick') || ''
                                };
                            }
                        }
                        return null;
                    }""", termos)

                def baixar_via_form_request(termos, origem):
                    try:
                        alvo = marcar_botao_por_termos(termos)
                        if not alvo:
                            return None
                        form_info = page.evaluate("""() => {
                            var btn = document.querySelector('[data-gnre-download-target="1"]');
                            if (!btn) return null;
                            var form = btn.form || btn.closest('form') || document.querySelector('form');
                            if (!form) return null;
                            var data = [];
                            Array.from(form.elements).forEach(function(el) {
                                if (!el.name || el.disabled) return;
                                var type = (el.type || '').toLowerCase();
                                if ((type === 'checkbox' || type === 'radio') && !el.checked) return;
                                if (type === 'submit' || type === 'button' || type === 'image') return;
                                data.push([el.name, el.value || '']);
                            });
                            if (btn.name) data.push([btn.name, btn.value || btn.innerText || '']);
                            return {
                                action: btn.formAction || form.action || location.href,
                                method: (btn.formMethod || form.method || 'GET').toUpperCase(),
                                target: btn.formTarget || form.target || '',
                                href: btn.href || '',
                                data: data
                            };
                        }""")
                        if not form_info:
                            return None
                        url = form_info.get("href") or form_info.get("action") or page.url
                        url = urljoin(page.url, url)
                        headers = {"referer": page.url}
                        if form_info.get("method") == "GET":
                            response = page.context.request.get(url, params=form_info.get("data") or [], headers=headers, timeout=30000)
                        else:
                            response = page.context.request.post(url, form=dict(form_info.get("data") or []), headers=headers, timeout=30000)
                        print(f"  Tentativa via formulario {origem}: status={response.status} url={url}")
                        return salvar_response_pdf(response, origem)
                    except Exception as e:
                        print(f"  [AVISO] Form request {origem}: {e}")
                        return None

                def locator_baixar():
                    loc = page.locator(
                        'input[value*="Baixar"], input[value*="PDF"], input[value*="Imprimir"], '
                        'button:has-text("Baixar"), button:has-text("PDF"), button:has-text("Imprimir"), '
                        'a:has-text("Baixar"), a:has-text("PDF"), a:has-text("Imprimir")'
                    ).first
                    if loc.count() == 0:
                        loc = page.get_by_text("Baixar PDF", exact=True).first
                    return loc

                def tentar_download(force=False):
                    btn = locator_baixar()
                    if btn.count() == 0:
                        return None
                    if not force and not btn.is_enabled():
                        return None
                    try:
                        with page.expect_download(timeout=20000) as download_info:
                            btn.click(force=force)
                        download = download_info.value
                        download.save_as(pdf_path_alvo)
                        return pdf_path_alvo
                    except Exception:
                        try:
                            with page.expect_response(lambda r: "pdf" in (r.headers.get("content-type") or "").lower() or r.url.lower().endswith(".pdf"), timeout=15000) as response_info:
                                btn.click(force=True)
                            return salvar_response_pdf(response_info.value, "click baixar")
                        except Exception as e:
                            raise e

                def salvar_pdf_de_pagina(pagina):
                    try:
                        resp = pagina.goto(pagina.url, wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        resp = None
                    try:
                        content_type = ""
                        if resp:
                            content_type = (resp.headers.get("content-type") or "").lower()
                        if "pdf" not in content_type and not pagina.url.lower().endswith(".pdf"):
                            return None
                        body = resp.body() if resp else None
                        if not body:
                            return None
                        with open(pdf_path_alvo, "wb") as f:
                            f.write(body)
                        return pdf_path_alvo
                    except Exception:
                        return None

                def tentar_click_com_popup(locator):
                    if locator.count() == 0:
                        return None
                    try:
                        with page.context.expect_page(timeout=10000) as popup_info:
                            locator.click(force=True)
                        popup = popup_info.value
                        popup.wait_for_load_state("domcontentloaded", timeout=15000)
                        return salvar_pdf_de_pagina(popup)
                    except Exception:
                        return None

                def tentar_emitir_com_download():
                    emitir = page.locator(
                        'input[value*="Emitir"], input[value*="Gerar"], input[value*="Confirmar"], '
                        'button:has-text("Emitir"), button:has-text("Gerar"), button:has-text("Confirmar"), '
                        'a:has-text("Emitir"), a:has-text("Gerar"), a:has-text("Confirmar")'
                    ).first
                    if emitir.count() == 0:
                        return None
                    try:
                        with page.expect_download(timeout=10000) as download_info:
                            emitir.click(force=True)
                        download = download_info.value
                        download.save_as(pdf_path_alvo)
                        return pdf_path_alvo
                    except Exception:
                        page.wait_for_timeout(5000)
                        return None

                def tentar_emitir_com_popup():
                    emitir = page.locator(
                        'input[value*="Emitir"], input[value*="Gerar"], input[value*="Confirmar"], '
                        'button:has-text("Emitir"), button:has-text("Gerar"), button:has-text("Confirmar"), '
                        'a:has-text("Emitir"), a:has-text("Gerar"), a:has-text("Confirmar")'
                    ).first
                    return tentar_click_com_popup(emitir)

                for tentativa in range(2):
                    try:
                        pdf_path = tentar_download(force=False)
                        if pdf_path:
                            break
                    except Exception as e:
                        print(f"  [AVISO] Download direto falhou ({tentativa + 1}/2): {e}")
                        page.wait_for_timeout(2000)

                if not pdf_path:
                    pdf_path = baixar_via_form_request(["BAIXAR", "PDF"], "baixar pdf")

                if not pdf_path:
                    print("  Botao Baixar PDF indisponivel. Tentando clicar em EMITIR/CONFIRMAR...")
                    pdf_path = tentar_emitir_com_download()
                    if not pdf_path:
                        pdf_path = tentar_emitir_com_popup()
                    if not pdf_path:
                        pdf_path = baixar_via_form_request(["EMITIR", "GERAR", "CONFIRMAR"], "emitir")
                    for tentativa in range(4):
                        if pdf_path:
                            break
                        try:
                            pdf_path = tentar_download(force=(tentativa >= 2))
                            if pdf_path:
                                break
                            btn_download = locator_baixar()
                            pdf_path = tentar_click_com_popup(btn_download)
                            if pdf_path:
                                break
                        except Exception as e:
                            print(f"  [AVISO] Download apos emitir falhou ({tentativa + 1}/4): {e}")
                            page.wait_for_timeout(3000)

                if pdf_path:
                    print(f"\n=== GUIA SALVA COM SUCESSO ===")
                    print(f"Caminho: {pdf_path}")
                    enviar_discord(pdf_path, dados)
                else:
                    try:
                        page.screenshot(path=os.path.join(get_uf_path(dados.get("uf_favorecida", "")), f"erro_download_nf_{dados['numero_nf']}.png"), full_page=True)
                    except Exception:
                        pass
                    print("  [INFO] Nao foi possivel baixar automaticamente. GNRE validada com sucesso!")
                    print(f"  Acesse o site e baixe manualmente pelo pedido {dados.get('numero_nf', '')}")
            except Exception as e:
                print(f"  [AVISO] Falha ao Baixar PDF: {e}")
        except Exception as e:
            print("  [ERRO] Não foi possível encontrar a tela de confirmação ou o botão Emitir:", e)

        page.wait_for_timeout(60000)
        if not use_cdp_browser:
            browser.close()
        else:
            print("\n[MODO CDP] Nao fechei o navegador (voce gerencia). Feche a aba quando quiser.")
        print("Concluído!")
        return pdf_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automação GNRE a partir de PDF de nota fiscal")
    parser.add_argument("pdf", nargs="?", help="Caminho completo para o arquivo PDF contendo os dados da NF")
    parser.add_argument("--cdp", action="store_true", help="Conectar via CDP ao Chrome ja aberto")
    args = parser.parse_args()
    dados = None
    if args.pdf:
        pdf_path = args.pdf
        print(f"[INFO] Usando PDF especificado: {pdf_path}")
        dados = extract_data_from_pdf(pdf_path)
    else:
        # Busca automaticamente o primeiro PDF na pasta pedidos_baixados
        default_dir = Path(__file__).parent / "pedidos_baixados"
        pdf_files = list(default_dir.glob("*.pdf"))
        if pdf_files:
            pdf_path = str(pdf_files[0])
            print(f"[INFO] Nenhum PDF especificado. Usando o primeiro encontrado: {pdf_path}")
            dados = extract_data_from_pdf(pdf_path)
        else:
            print("[AVISO] Nenhum PDF encontrado na pasta pedidos_baixados. Usando dados de exemplo.")
    processar_gnre(dados, use_cdp=args.cdp)
