import asyncio
import re
import sys
import logging

import csv
import io
import os
import datetime
import json
import time
import urllib.request
import urllib.error
from playwright.async_api import async_playwright

import database

# Pegar o diretorio onde o script esta localizado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "nfe_cron.log")
LOCKS_DIR = os.path.join(BASE_DIR, "locks")

log_handlers = [logging.FileHandler(LOG_PATH)]
if sys.stdout.isatty():
    log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers,
)

# Tentar carregar variaveis do arquivo .env se ele existir
# Usa setdefault para nao sobrescrever variaveis ja definidas na linha de comando
try:
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
except:
    pass

# ─── Configuracoes ─────────────────────────────────────────────────────────
SPREADSHEET_ID_1  = os.getenv("SPREADSHEET_ID_PRINCIPAL", os.getenv("SPREADSHEET_ID", "1dvIgAH5B3ePkB_4npXRMVcOB6GUBt8JhCFy5D5u-igs"))
SPREADSHEET_URL_1 = "https://docs.google.com/spreadsheets/d/" + SPREADSHEET_ID_1 + "/edit"

SPREADSHEET_ID_2  = os.getenv("SPREADSHEET_ID_TRANSPORTE", "1pVnhOWvuGKn66CmXNhEZNTPpsiQMcBUpyrYtHMcmp-g")
SPREADSHEET_URL_2 = "https://docs.google.com/spreadsheets/d/" + SPREADSHEET_ID_2 + "/edit"

SPREADSHEET_ID_3  = os.getenv("SPREADSHEET_ID_VALDEX", "1hIVyui_6Ciol94CVtdhNDv7WKSkqz8lM79I0z9TvA_c")
SPREADSHEET_URL_3 = "https://docs.google.com/spreadsheets/d/" + SPREADSHEET_ID_3 + "/edit"

def get_target_day():
    now = datetime.datetime.now()
    # Antes das 08:50 olha para hoje. A partir das 08:50 olha para o dia seguinte (+1).
    if now.hour < 8 or (now.hour == 8 and now.minute < 50):
        target_date = now
    else:
        target_date = now + datetime.timedelta(days=1)
    return target_date.strftime("%d")

ABA_ALVO = get_target_day()

ERP_URL = "https://erp.admsis.com/Home"
USUARIO = os.getenv("ERP_USER")
SENHA   = os.getenv("ERP_PASS")

GOOGLE_USER = os.getenv("GOOGLE_USER", "")
GOOGLE_PASS = os.getenv("GOOGLE_PASS", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_NFE_REPORT_CHANNEL_ID  = (
    os.getenv("DISCORD_NFE_REPORT_CHANNEL_ID")
    or os.getenv("DISCORD_NFE_CHANNEL_ID")
    or os.getenv("DISCORD_CHANNEL_ID", "")
)

MAX_TENTATIVAS_GERACAO = 5
LOCK_PEDIDO_TTL_SEGUNDOS = 2 * 60 * 60


def env_bool(nome_variavel, padrao=False):
    valor = os.getenv(nome_variavel)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


def env_int(nome_variavel, padrao=0):
    valor = os.getenv(nome_variavel)
    if valor is None or not valor.strip():
        return padrao
    try:
        return int(valor)
    except ValueError:
        logging.info(f"[AVISO] {nome_variavel} invalido: use apenas numeros. Usando {padrao}.")
        return padrao


def validar_credenciais_erp():
    if USUARIO and SENHA:
        return True
    logging.info("ERRO FATAL: Credenciais do ERP nao encontradas no .env!")
    return False


def get_user_data_dir():
    if os.name == 'nt':  # Windows
        local_app_data = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:  # Mac / Linux
        local_app_data = os.path.expanduser("~/Library/Application Support")
    user_data_dir = os.path.join(local_app_data, "Automacao_NFe_Transporte", "sessao_robo")
    os.makedirs(user_data_dir, exist_ok=True)
    return user_data_dir


def get_browser_options():
    options = {
        "headless": env_bool("NFE_HEADLESS", True),
        "slow_mo": env_int("NFE_SLOW_MO_MS", 0),
        "viewport": {"width": 1366, "height": 768},
    }
    if env_bool("NFE_RECORD_VIDEO", True):
        os.makedirs(os.path.join(BASE_DIR, "videos"), exist_ok=True)
        options["record_video_dir"] = os.path.join(BASE_DIR, "videos/")
    return options


def texto_curto(texto, limite=900):
    if not texto:
        return ""
    linhas = [re.sub(r"[^\S\r\n]+", " ", line).strip() for line in str(texto).splitlines()]
    texto_formatado = "\n".join(linhas).strip()
    if len(texto_formatado) > limite:
        return texto_formatado[:limite - 3] + "..."
    return texto_formatado


def motivo_erro_externo(resultado):
    """Retorna um motivo quando o ERP indica bloqueio externo a automacao."""
    txt = str(resultado or "").lower()
    motivos = [
        ("rejei", "Rejeicao retornada pelo ERP/SEFAZ"),
        ("sefaz", "Falha ou rejeicao da SEFAZ"),
        ("deneg", "NFe denegada"),
        ("duplic", "Possivel duplicidade de NFe"),
        ("certificado", "Problema de certificado no emissor"),
        ("cnpj", "Problema cadastral/CNPJ"),
        ("inscri", "Problema cadastral/inscricao estadual"),
        ("cadastro", "Cadastro do cliente/produto precisa de ajuste"),
        ("tribut", "Configuracao fiscal/tributaria precisa de ajuste"),
        ("cfop", "Configuracao fiscal/CFOP precisa de ajuste"),
        ("ncm", "Configuracao fiscal/NCM precisa de ajuste"),
        ("sem estoque", "Pedido/produto sem estoque"),
        ("estoque insuficiente", "Pedido/produto sem estoque suficiente"),
        ("saldo insuficiente", "Saldo insuficiente para faturamento"),
        ("ja faturado", "Pedido ja faturado ou indisponivel para gerar NFe"),
        ("indisponivel", "ERP nao disponibilizou a geracao para este pedido"),
        ("sem confirmacao clara", "ERP nao confirmou autorizacao da NFe"),
        ("invalid child element", "Erro de validacao de dados no cadastro/SEFAZ"),
        ("element", "Erro de validacao de dados no cadastro/SEFAZ"),
        ("expected", "Erro de validacao de dados no cadastro/SEFAZ"),
        ("schema", "Erro de schema XML no cadastro/SEFAZ"),
    ]
    for chave, motivo in motivos:
        if chave in txt:
            return motivo
    return None


def erro_de_sessao_ou_rede(resultado):
    txt = str(resultado or "").lower()
    return any(k in txt for k in [
        "closed",
        "network_io_suspended",
        "navigation failed",
        "connection refused",
        "target page",
        "browser has been closed",
        "timeout",
        "net::",
    ])


def caminho_lock_pedido(pedido):
    pedido_limpo = re.sub(r"\D+", "", str(pedido or "")) or "sem_numero"
    return os.path.join(LOCKS_DIR, f"pedido_{pedido_limpo}.lock")


def adquirir_lock_pedido(pedido):
    os.makedirs(LOCKS_DIR, exist_ok=True)
    lock_path = caminho_lock_pedido(pedido)

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()}\ncriado_em={datetime.datetime.now().isoformat()}\n")
        return lock_path
    except FileExistsError:
        try:
            idade = time.time() - os.path.getmtime(lock_path)
            if idade > LOCK_PEDIDO_TTL_SEGUNDOS:
                logging.info(f"      [AVISO] Lock antigo removido para o pedido {pedido}.")
                os.remove(lock_path)
                return adquirir_lock_pedido(pedido)
        except Exception as e:
            logging.info(f"      [AVISO] Nao foi possivel verificar lock do pedido {pedido}: {e}")
        return None


def liberar_lock_pedido(lock_path):
    if not lock_path:
        return
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logging.info(f"      [AVISO] Nao foi possivel liberar lock {lock_path}: {e}")


async def boleto_ja_emitido(erp_page):
    """Detecta sinais fortes de boleto ja existente antes de gerar algo novo."""
    try:
        texto = await erp_page.locator("body").inner_text(timeout=5000)
    except Exception:
        return False, ""

    texto_normalizado = re.sub(r"\s+", " ", texto or "").strip().lower()
    if not texto_normalizado:
        return False, ""

    padroes_boleto_emitido = [
        r"boleto\s+(?:ja\s+)?(?:emitido|gerado|existente|registrado)",
        r"boleto\(s\)\s+(?:emitido|gerado|registrado)",
        r"2[ªa]\s+via\s+(?:do\s+)?boleto",
        r"segunda\s+via\s+(?:do\s+)?boleto",
        r"linha\s+digit[aá]vel\s*[:\-]?\s*\d",
        r"nosso\s+n[uú]mero\s*[:\-]?\s*\d",
        r"imprimir\s+boleto",
        r"visualizar\s+boleto",
        r"baixar\s+boleto",
        r"reimprimir\s+boleto",
    ]

    for padrao in padroes_boleto_emitido:
        if re.search(padrao, texto_normalizado, re.IGNORECASE):
            return True, padrao

    return False, ""


async def verificar_forma_pagamento_boleto(erp_page):
    """Verifica com máxima precisão se a forma de pagamento do pedido no ERP é Boleto."""
    try:
        # 1. Espera explícita pelo campo oficial #lblvda_forma_pagamento_id
        campo_oficial = erp_page.locator("#lblvda_forma_pagamento_id").first
        try:
            await campo_oficial.wait_for(state="attached", timeout=7000)
        except Exception:
            pass

        if await campo_oficial.count() > 0:
            val = await campo_oficial.get_attribute("value") or ""
            txt = await campo_oficial.inner_text() or ""
            forma_str = (val + " " + txt).strip().lower()
            if "boleto" in forma_str:
                logging.info(f"  [BOLETO CONFIRMADO] Campo oficial #lblvda_forma_pagamento_id = '{val}'")
                return True
            else:
                logging.info(f"  [SEM BOLETO CONFIRMADO] Campo oficial #lblvda_forma_pagamento_id = '{val}'")
                return False

        # 2. Fallback de segurança em seletores alternativos
        seletores_alternativos = [
            "input[name*='forma_pagamento']",
            "input[id*='forma_pagamento']",
            "select[name*='forma_pagamento']",
        ]
        
        for seletor in seletores_alternativos:
            elementos = erp_page.locator(seletor)
            cnt = await elementos.count()
            for i in range(cnt):
                el = elementos.nth(i)
                val = await el.get_attribute("value") or ""
                txt = await el.inner_text() or ""
                forma_str = (val + " " + txt).strip().lower()
                if "boleto" in forma_str:
                    logging.info(f"  [BOLETO CONFIRMADO] Seletor alternativo {seletor} = '{val}'")
                    return True

    except Exception as e:
        logging.warning(f"  Aviso ao checar forma de pagamento: {e}")
    
    # Se não foi identificado como boleto
    return False


async def gerar_boleto_se_necessario(erp_page, pedido, eh_boleto=None):
    # Usar a checagem prévia realizada no momento exato em que a tela de detalhes abriu
    is_boleto = eh_boleto if eh_boleto is not None else await verificar_forma_pagamento_boleto(erp_page)
    if is_boleto is False:
        logging.info(f"  Forma de pagamento do pedido {pedido} não é boleto. Finalizando como NFe (sem boleto).")
        return "OK - NFe autorizada (sem boleto)"

    boleto_emitido, padrao_boleto = await boleto_ja_emitido(erp_page)
    if boleto_emitido:
        logging.info(f"  Boleto ja consta no ERP para o pedido {pedido} ({padrao_boleto}).")
        return "OK - NFe autorizada; boleto ja consta no ERP"

    seletores_boleto = [
        r"Gerar\s+Boleto",
        r"Emitir\s+Boleto",
        r"Gerar\s+Boleto\(s\)",
    ]

    for padrao in seletores_boleto:
        btn_boleto = erp_page.get_by_text(re.compile(padrao, re.IGNORECASE)).last
        try:
            if await btn_boleto.count() > 0 and await btn_boleto.is_visible():
                await btn_boleto.click()
                logging.info(f"  Boleto gerado para o pedido {pedido}.")
                await asyncio.sleep(3)
                await esperar_carregamento_erp(erp_page)
                return "OK - NFe e Boleto Gerados"
        except Exception as e:
            return "ERRO ao gerar boleto: " + str(e)

    logging.info(f"  NFe autorizada para o pedido {pedido} (Boleto confirmado via forma de pagamento).")
    return "OK - NFe e Boleto Gerados"


async def contar_boletos_erp(erp_page):
    """Conta a quantidade de parcelas/boletos gerados na tela do ERP com verificação estrita de Pix/Cartão/À Vista."""
    try:
        # Verificar se a tela indica pagamento sem boleto (Pix, Cartão, Dinheiro, À vista)
        texto_tela = (await erp_page.locator("body").inner_text(timeout=5000)).lower()
        if any(metodo in texto_tela for metodo in ["pix", "cartão", "cartao", "à vista", "a vista", "dinheiro", "sem boleto"]):
            cnt_boletos = await erp_page.locator("a:has-text('Imprimir'), a:has-text('Boleto'), a:has-text('Visualizar')").count()
            if cnt_boletos == 0:
                logging.info("  Forma de pagamento sem boleto detectada (Pix/Cartão/À vista). Contabilizando 0 boletos.")
                return 0

        locators = [
            erp_page.locator("a:has-text('Imprimir'), a:has-text('Boleto'), a:has-text('Visualizar')"),
            erp_page.locator("tr:has-text('Parcela'), tr:has-text('Duplicata')"),
            erp_page.locator("text=/parcela\\s+\\d+/i"),
        ]
        qtd_maxima = 1
        for loc in locators:
            cnt = await loc.count()
            if cnt > qtd_maxima:
                qtd_maxima = cnt
        return qtd_maxima
    except Exception as e:
        logging.warning(f"  Aviso ao contar boletos no ERP: {e}")
        return 1


def _enviar_mensagem_discord_sync(mensagem: str):
    """Envia mensagem como a SofIA (bot) via API. Fallback para webhook se não houver bot configurado."""
    texto = texto_curto(mensagem, 1900)
    payload = json.dumps({"content": texto}).encode("utf-8")
    erro_bot = None

    # Preferir API do Bot (mensagem aparece como SofIA)
    if DISCORD_BOT_TOKEN and DISCORD_NFE_REPORT_CHANNEL_ID:
        url = f"https://discord.com/api/v10/channels/{DISCORD_NFE_REPORT_CHANNEL_ID}/messages"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                "User-Agent": "SofIA-NFe-Bot/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp.read()
            return
        except urllib.error.HTTPError as e:
            erro_bot = f"Discord Bot API retornou HTTP {e.code}"
        except Exception as e:
            erro_bot = f"Discord Bot API falhou: {e}"

    # Fallback: webhook generico
    if DISCORD_WEBHOOK_URL:
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SofIA-NFe-Bot/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return

    if erro_bot:
        raise RuntimeError(f"{erro_bot}. Configure permissoes do bot no canal ou defina DISCORD_WEBHOOK_URL.")

    raise RuntimeError("Nenhum meio de envio Discord configurado (DISCORD_BOT_TOKEN+DISCORD_NFE_CHANNEL_ID ou DISCORD_WEBHOOK_URL).")


async def avisar_discord(mensagem):
    """Envia aviso pontual de erro/alerta como a SofIA."""
    if not DISCORD_BOT_TOKEN and not DISCORD_WEBHOOK_URL:
        logging.info("      [AVISO] Discord nao configurado. Defina DISCORD_BOT_TOKEN+DISCORD_NFE_CHANNEL_ID no .env.")
        return
    try:
        await asyncio.to_thread(_enviar_mensagem_discord_sync, mensagem)
        logging.info("      [DISCORD] Aviso enviado.")
    except Exception as e:
        logging.info(f"      [AVISO] Falha ao enviar aviso ao Discord: {e}")


async def sofia_relatorio(resultados: list):
    """
    Envia um relatório consolidado da rodada do cron como a SofIA.
    resultados: lista de dicts com chaves 'pedido', 'planilha', 'resultado'
    Exibe apenas o que a automação faturou e erros que requerem atenção.
    """
    if not DISCORD_BOT_TOKEN and not DISCORD_WEBHOOK_URL:
        return

    agora = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")

    ok_lines      = []
    erro_lines    = []
    total_boletos = 0
    for r in resultados:
        pedido   = r["pedido"]
        planilha = r["planilha"]
        res      = str(r["resultado"])

        if res.startswith("OK"):
            nome_planilha_limpo = planilha.replace("Planilha ", "")
            ok_lines.append(f"✅ Pedido {pedido} — {nome_planilha_limpo} ➔ {res}")
            if "boleto(s)" in res.lower() or "boleto gerado" in res.lower():
                # Extrair a quantidade de boletos se especificada [X boleto(s)]
                match_bol = re.search(r"\[(\d+)\s+boleto\(s\)\]", res, re.IGNORECASE)
                if match_bol:
                    total_boletos += int(match_bol.group(1))
                else:
                    total_boletos += 1
        elif "PULADO" in res or "Ja Faturado" in res:
            # Ignora pedidos já faturados / pulados (não exibe na mensagem)
            continue
        else:
            motivo = motivo_erro_externo(res) or texto_curto(res, 150)
            erro_lines.append(f"❌ Pedido {pedido} — {planilha}\n↳ {motivo}")

    linhas = []

    # ── Cabeçalho ──────────────────────────────────────────────────────────────
    linhas.append(f"📋 Relatório NFe — {agora}")

    # ── Sucessos ───────────────────────────────────────────────────────────────
    if ok_lines:
        linhas.append(f"✅ NFes emitidas ({len(ok_lines)}) | Boletos gerados ({total_boletos})")
        linhas.extend(ok_lines)

    # ── Erros ──────────────────────────────────────────────────────────────────
    if erro_lines:
        linhas.append(f"❌ Erros — requerem atenção ({len(erro_lines)})")
        linhas.extend(erro_lines)

    # ── Sem emissões nem erros ────────────────────────────────────────────────
    if not ok_lines and not erro_lines:
        linhas.append("✅ Nenhum novo faturamento realizado nesta rodada.")

    mensagem_final = "\n".join(linhas)
    try:
        await asyncio.to_thread(_enviar_mensagem_discord_sync, mensagem_final)
        logging.info("[DISCORD] Relatório final enviado pela SofIA.")
    except Exception as e:
        logging.info(f"[AVISO] Falha ao enviar relatório Discord: {e}")


def get_possiveis_nomes_mes_atual():
    mes = datetime.datetime.now().month
    ano = str(datetime.datetime.now().year)
    ano_curto = ano[-2:]
    nomes_por_mes = {
        1: ["JANEIRO", "JAN", "01", "1"],
        2: ["FEVEREIRO", "FEV", "02", "2"],
        3: ["MARÇO", "MARCO", "MAR", "03", "3"],
        4: ["ABRIL", "ABR", "04", "4"],
        5: ["MAIO", "MAI", "05", "5"],
        6: ["JUNHO", "JUN", "06", "6"],
        7: ["JULHO", "JUL", "07", "7"],
        8: ["AGOSTO", "AGO", "08", "8"],
        9: ["SETEMBRO", "SET", "09", "9"],
        10: ["OUTUBRO", "OUT", "10"],
        11: ["NOVEMBRO", "NOV", "11"],
        12: ["DEZEMBRO", "DEZ", "12"]
    }
    base = nomes_por_mes[mes]
    variacoes = set()
    for b in base:
        variacoes.add(b)
        variacoes.add(b.capitalize())
        variacoes.add(b.lower())
        variacoes.add(f"{b}/{ano}")
        variacoes.add(f"{b}/{ano_curto}")
        variacoes.add(f"{b.capitalize()}/{ano}")
        variacoes.add(f"{b.lower()}/{ano}")
    return list(variacoes)


def numero_antes_da_barra(texto):
    """True se houver digito(s) antes da primeira '/'."""
    if not texto or not texto.strip():
        return False
    antes = texto.strip().split("/")[0].strip()
    return bool(re.search(r"\d", antes))


def extrair_pedido(texto):
    """Retorna apenas os digitos do numero do pedido."""
    if not texto:
        return None
    # Tenta pegar a primeira sequencia de digitos (ex: 1585/2026 -> 1585)
    match = re.search(r"(\d+)", texto.strip())
    if match:
        return match.group(1)
    return None

async def fazer_login_google(page, user, password):
    """Realiza o login no Google se necessário, lidando com seleção de conta."""
    if not user or not password:
        return

    # Verificar se estamos em uma página de login ou seleção de conta
    is_login_page = "accounts.google.com" in page.url or await page.locator('input[type="email"], [data-identifier], #identifierNext').count() > 0
    
    if is_login_page:
        logging.info("      [LOGIN] Detectado necessidade de interação no Google...")
        try:
            # 1. Verificar se ja existe a conta na lista (Seleção de conta)
            conta_na_lista = page.locator(f'[data-email="{user}"], [data-identifier="{user}"]').first
            if await conta_na_lista.count() == 0:
                conta_na_lista = page.get_by_text(user).first

            if await conta_na_lista.count() > 0 and await conta_na_lista.is_visible():
                logging.info(f"      [LOGIN] Selecionando conta já listada: {user}")
                await conta_na_lista.click()
                await asyncio.sleep(2)
            
            # 2. Preencher E-mail (se campo estiver visivel)
            elif await page.locator('input[type="email"]').is_visible():
                await page.fill('input[type="email"]', user)
                await page.click('#identifierNext')
                await asyncio.sleep(2)
            
            # 3. Preencher Senha
            # Esperar o campo de senha aparecer
            try:
                await page.wait_for_selector('input[type="password"]', timeout=5000)
            except: pass

            if await page.locator('input[type="password"]').count() > 0:
                await page.fill('input[type="password"]', password)
                await page.click('#passwordNext')
                logging.info("      [LOGIN] Senha enviada. Aguardando...")
                await asyncio.sleep(5)
            
            # 4. Lidar com botões de "Continuar" ou "Confirmar"
            btn_continuar = page.locator('button:has-text("Continuar"), button:has-text("Continue"), button:has-text("Próxima")').first
            if await btn_continuar.count() > 0 and await btn_continuar.is_visible():
                await btn_continuar.click()
                await asyncio.sleep(3)

            # Se ainda estiver na página de contas, pode ser MFA
            if "accounts.google.com" in page.url:
                logging.info("      [!] Google pode estar solicitando MFA/CAPTCHA. Verifique o navegador.")
                for _ in range(30):
                    if "accounts.google.com" not in page.url: break
                    await asyncio.sleep(1)
        except Exception as e:
            logging.info(f"      [AVISO] Erro no login automático: {e}")

async def esperar_carregamento_erp(erp_page):
    """Espera que mensagens de 'Aguarde' ou overlays sumam."""
    try:
        overlay = erp_page.locator('.blockUI, .loading, :text("Aguarde"), :text("carregando")').first
        for _ in range(20):
            if await overlay.is_visible():
                await asyncio.sleep(1)
            else:
                break
    except Exception:
        pass
    await asyncio.sleep(1)

async def obter_gid_da_aba(page, url_planilha, aba, is_mes_atual=False):
    """Navega para a planilha, clica na aba e retorna o GID da URL com retentativas."""
    logging.info(f"[1/4] Abrindo planilha: {url_planilha[:50]}...")
    
    # Adicionar lógica de retentativa para abertura da planilha
    max_tentativas = 3
    for tentativa in range(max_tentativas):
        try:
            # Aumentar timeout para 60s em execuções agendadas
            await page.goto(url_planilha, timeout=60000, wait_until="load")
            break
        except Exception as e:
            if tentativa < max_tentativas - 1:
                logging.info(f"      [!] Falha na tentativa {tentativa+1}. Tentando novamente em 5s... ({e})")
                await asyncio.sleep(5)
            else:
                logging.info(f"      [ERRO] Nao foi possivel abrir a planilha apos {max_tentativas} tentativas.")
                return page, None
    
    # Tentar login se necessário
    await fazer_login_google(page, GOOGLE_USER, GOOGLE_PASS)
    
    try:
        await page.wait_for_selector(".docs-sheet-tab-name", timeout=120000)
        logging.info("      Planilha carregada!")
    except Exception:
        logging.info("      [ERRO] Timeout na planilha.")
        return page, None

    await asyncio.sleep(2)

    logging.info("[2/4] Selecionando aba alvo...")
    tabs = await page.query_selector_all(".docs-sheet-tab-name")
    nomes = []
    
    aba_selecionada = False
    
    if is_mes_atual:
        possiveis = [p.upper() for p in get_possiveis_nomes_mes_atual()]
        for tab in tabs:
            nome = (await tab.inner_text()).strip()
            nomes.append(nome)
            if nome.upper() in possiveis:
                await tab.click()
                logging.info("      Aba do mês atual '" + nome + "' selecionada.")
                aba_selecionada = True
                await asyncio.sleep(3)
                break
    else:
        for tab in tabs:
            nome = (await tab.inner_text()).strip()
            nomes.append(nome)
            aba_limpa = aba.lstrip("0")
            nome_limpo = nome.lstrip("0")
            if nome == aba or (aba_limpa != "" and aba_limpa == nome_limpo):
                await tab.click()
                logging.info(f"      Aba '{nome}' selecionada (correspondente a '{aba}').")
                aba_selecionada = True
                await asyncio.sleep(3)
                break

    if aba_selecionada:
        url_atual = page.url
        match = re.search(r"gid=(\d+)", url_atual)
        if match:
            gid = match.group(1)
            logging.info("      GID encontrado: " + gid)
            return page, gid
        else:
            logging.info("      [AVISO] GID nao encontrado na URL.")
            return page, None

    if is_mes_atual:
        logging.info("      [ERRO] Aba do mês atual não encontrada. Abas disponíveis: " + str(nomes))
    else:
        logging.info("      [ERRO] Aba '" + aba + "' nao encontrada. Abas disponíveis: " + str(nomes))
    return page, None


async def ler_dados_csv(page, url_planilha, gid):
    """Baixa o CSV da aba usando a mesma pagina para manter sessao."""
    import tempfile, os
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url_planilha)
    sheet_id = match.group(1) if match else SPREADSHEET_ID_1
    
    export_url = ("https://docs.google.com/spreadsheets/d/" + sheet_id +
                  "/export?format=csv&gid=" + gid)
    logging.info("[3/4] Baixando dados via CSV...")

    tmp_path = os.path.join(tempfile.gettempdir(), "planilha_nfe_" + gid + ".csv")
    
    # Garantir que aceitamos dialogos nesta pagina tambem (caso mude o comportamento)
    page.on("dialog", lambda dialog: dialog.accept())

    try:
        async with page.expect_download(timeout=45000) as download_info:
            try:
                await page.goto(export_url)
            except Exception as e:
                # O Playwright gera um erro proposital quando um goto vira download
                if "Download is starting" not in str(e):
                    logging.info(f"      [AVISO] Erro no goto: {e}")
        download = await download_info.value
        await download.save_as(tmp_path)
    except Exception as e:
        logging.info("      [ERRO] Download falhou: " + str(e))
        return None

    try:
        with open(tmp_path, encoding="utf-8", errors="replace") as f:
            conteudo = f.read()
    except Exception as e:
        logging.info("      [ERRO] Leitura do arquivo: " + str(e))
        return None

    linhas = []
    reader = csv.reader(io.StringIO(conteudo))
    for i, row in enumerate(reader):
        if any(cell.strip() for cell in row):
            linhas.append({"linha": i + 1, "cells": row})

    logging.info("      " + str(len(linhas)) + " linhas encontradas no CSV.")
    return linhas


async def gerar_nfe_erp(erp_page, pedido):
    """Fluxo ERP completo."""
    logging.info("\n  --- Pedido " + pedido + " ---")

    # Tentar navegar com retentativas para lidar com instabilidades de rede
    max_retries = 3
    for i in range(max_retries):
        try:
            await erp_page.goto("https://erp.admsis.com/Home?eng_tela=0103030100", timeout=60000)
            break
        except Exception as e:
            if i == max_retries - 1:
                return f"ERRO fatal ao acessar tela de NFe: {str(e)}"
            logging.info(f"      [!] Falha ao carregar tela (tentativa {i+1}). Tentando novamente em 5s... ({str(e)})")
            await asyncio.sleep(5)
            
    await asyncio.sleep(3)
    await esperar_carregamento_erp(erp_page)

    # Pesquisar
    try:
        lupa = erp_page.locator('.fa-search, .glyphicon-search, button[title*="Pesquisa"]').first
        if await lupa.count() > 0:
            await lupa.click()
            await asyncio.sleep(1)
    except Exception: pass

    # Preencher Pedido
    preencheu = False
    for seletor in ['input[id*="ped_numero"]', 'input[placeholder*="edido"]', 'input[name="ped_numero"]']:
        campo = erp_page.locator(seletor).first
        if await campo.count() > 0:
            await campo.fill(pedido)
            preencheu = True
            break
    
    if not preencheu:
        await erp_page.keyboard.press("Enter")

    # Filtrar (com timeout maior para o ADMSIS lento)
    try:
        btn_filtrar = erp_page.locator('button:has-text("FILTRAR"), button:has-text("Filtrar")').first
        await btn_filtrar.click(timeout=60000)
        logging.info("  Clicado em Filtrar.")
    except Exception as e:
        return "ERRO ao clicar Filtrar: " + str(e)
    
    await asyncio.sleep(3)
    await esperar_carregamento_erp(erp_page)

    # Abrir detalhes
    try:
        resultado = erp_page.locator("td:has-text('" + pedido + "'), tr:has-text('" + pedido + "')").first
        if await resultado.count() == 0:
            logging.info(f"  [!] Pedido {pedido} nao encontrado na grade de NFe do ERP. Provavelmente ja faturado.")
            return "PULADO - Pedido nao localizado na grade (Ja Faturado)"

        # Abrir detalhes clicando no ícone ou dblclick
        icone = resultado.locator("a, i, button, .fa-edit, .fa-search").first
        if await icone.count() > 0 and await icone.is_visible():
            await icone.click()
        else:
            await resultado.dblclick()
        await asyncio.sleep(3)
        await esperar_carregamento_erp(erp_page)

        # Checar IMEDIATAMENTE na tela de detalhes se a forma de pagamento é Boleto
        eh_boleto_pedido = await verificar_forma_pagamento_boleto(erp_page)
        logging.info(f"  [CHECK FORMA PAGTO] Pedido {pedido} -> É boleto? {eh_boleto_pedido}")

        boleto_existente, padrao_boleto = await boleto_ja_emitido(erp_page)
        if boleto_existente:
            logging.info(
                f"  [!] Boleto ja emitido detectado para o pedido {pedido}. "
                f"Nenhuma geracao nova sera feita. Sinal: {padrao_boleto}"
            )
            return "PULADO - Boleto ja emitido; nenhuma nova geracao feita"
        
        # --- FLUXO VITORIOSO (PADRAO 1585) ---
        # Tentar encontrar o botao GERAR NFE. Se ele existir, fazemos o processo.
        try:
            btn_gerar = erp_page.get_by_text(re.compile(r"Gerar NFE", re.IGNORECASE)).last
            
            if await btn_gerar.count() > 0 and await btn_gerar.is_visible():
                logging.info(f"  Botao Gerar NFE encontrado para o pedido {pedido}. Iniciando emissao...")
                await btn_gerar.click()
                
                # Espera dinâmica pelo botão SIM
                btn_sim = erp_page.locator('button:has-text("SIM"), button:has-text("Sim")')
                await btn_sim.wait_for(state="visible", timeout=30000)
                await btn_sim.click()
                
                await esperar_carregamento_erp(erp_page)

                # Verificar autorização e mensagens de erro na tela do ERP
                await asyncio.sleep(2)
                conteudo = (await erp_page.content()).lower()
                texto_tela = (await erp_page.locator("body").inner_text(timeout=5000)).lower()

                # Se houver indícios de erro/rejeição/falha na tela, registrar como erro
                palavras_erro = ["rejeicao", "rejeição", "erro", "falha", "denegad", "invalido", "inválido", "duplicida"]
                if any(p in texto_tela for p in palavras_erro) and not any(k in texto_tela for k in ["autorizada com sucesso", "nfe autorizada", "sucesso"]):
                    logging.warning(f"  [!] Erro/Rejeição detectado ao gerar NFe do pedido {pedido}: {texto_curto(texto_tela, 200)}")
                    return "ERRO na emissão da NFe: " + texto_curto(texto_tela, 300)

                if any(k in conteudo for k in ["autoriza", "sucesso", "emitida"]):
                    return await gerar_boleto_se_necessario(erp_page, pedido, eh_boleto=eh_boleto_pedido)

                return "VERIFICAR - Sem confirmacao clara. Tela ERP: " + texto_curto(texto_tela, 700)
            else:
                logging.info(f"  [!] Botao Gerar NFE nao disponivel para o pedido {pedido}. Provavelmente ja faturado.")
                return "PULADO - Ja Faturado ou Indisponivel"
        except Exception as e:
            return "ERRO no processo de geracao: " + str(e)
        # -------------------------------------
    except Exception as e:
        return "ERRO ao abrir detalhes: " + str(e)
    
    return "VERIFICAR - Sem confirmacao clara"

async def realizar_login_erp(erp_page):
    """Realiza o login no ERP se necessário."""
    logging.info("\n  [ERP] Acessando sistema...")
    try:
        await erp_page.goto(ERP_URL, timeout=90000, wait_until="load")
        
        # Verificar se ja esta logado (se ja vemos o nome do usuario ou menu)
        logging.info("      Verificando sessao ativa...")
        usuario_logado = erp_page.locator(f'text="{USUARIO}"').first
        dashboard = erp_page.locator('text="Faturamento", text="Pedidos"').first
        
        esta_logado = False
        try:
            # Esperar 5s para ver se ja carrega logado
            if await usuario_logado.count() > 0 or await dashboard.count() > 0:
                esta_logado = True
        except: pass

        if esta_logado:
            logging.info(f"      Sessao ativa detectada ({USUARIO}). Pulando login.")
            return True
        else:
            # Nao esta logado, fazer o processo normal
            logging.info("      Sessao nao encontrada. Iniciando login...")
            try:
                await erp_page.wait_for_selector('input[name="usu_codigo"]', timeout=20000)
            except Exception:
                # Tentar reload se nao aparecer nada
                await erp_page.reload()
                await erp_page.wait_for_selector('input[name="usu_codigo"]', timeout=20000)

            await erp_page.fill('input[name="usu_codigo"]', USUARIO)
            await erp_page.fill('input[name="usu_senha"]', SENHA)
            await erp_page.click('button#login')
            await asyncio.sleep(5)
            await esperar_carregamento_erp(erp_page)
            logging.info("      Login realizado com sucesso.")
            return True
        
    except Exception as e:
        logging.info(f"      [ERRO] Falha ao realizar login ERP: {e}")
        return False


async def gerar_nfe_com_tentativas(context, erp_page, item):
    pedido = item["pedido"]
    planilha = item["planilha"]
    ultimo_resultado = None
    lock_path = adquirir_lock_pedido(pedido)

    if not lock_path:
        logging.info(f"  [!] Pedido {pedido} ja esta em processamento por outra execucao. Pulando para evitar duplicidade.")
        return erp_page, "PULADO - Pedido ja em processamento por outra execucao"

    try:
        for tentativa in range(1, MAX_TENTATIVAS_GERACAO + 1):
            logging.info(f"\n  Tentativa {tentativa}/{MAX_TENTATIVAS_GERACAO} para o pedido {pedido} ({planilha})")
            try:
                ultimo_resultado = await gerar_nfe_erp(erp_page, pedido)
            except Exception as e:
                ultimo_resultado = "ERRO inesperado na automacao: " + str(e)

            logging.info(f"  Resultado Pedido {pedido} ({planilha}): {ultimo_resultado}")

            if str(ultimo_resultado).startswith("OK"):
                qtd_bol = 0
                res_str = str(ultimo_resultado)
                if any(k in res_str.lower() for k in ["boleto gerado", "boleto gerados", "boleto ja consta"]):
                    qtd_bol = await contar_boletos_erp(erp_page)
                    if qtd_bol == 0:
                        qtd_bol = 1
                database.registrar_emissao(pedido, planilha, status="OK", qtd_boletos=qtd_bol, detalhes=res_str)
                if qtd_bol > 0:
                    return erp_page, f"{ultimo_resultado} [{qtd_bol} boleto(s)]"
                return erp_page, f"{ultimo_resultado}"

            if str(ultimo_resultado).startswith("PULADO"):
                qtd_bol = await contar_boletos_erp(erp_page)
                database.registrar_emissao(pedido, planilha, status="PULADO", qtd_boletos=max(1, qtd_bol), detalhes=str(ultimo_resultado))
                return erp_page, ultimo_resultado

            motivo_externo = motivo_erro_externo(ultimo_resultado)
            if motivo_externo:
                database.registrar_emissao(pedido, planilha, status="ERRO", qtd_boletos=0, detalhes=str(motivo_externo))
                await avisar_discord(
                    f"⚠️ **NFe não gerada**\n"
                    f"📦 Pedido {pedido} — {planilha}\n"
                    f"🔎 Motivo: {motivo_externo}\n"
                    f"📄 Detalhe: {texto_curto(ultimo_resultado, 300)}"
                )
                return erp_page, ultimo_resultado

            if tentativa < MAX_TENTATIVAS_GERACAO:
                if erro_de_sessao_ou_rede(ultimo_resultado):
                    logging.info("      [!] Detectada falha de rede/sessao. Recuperando ERP antes de tentar novamente...")
                    await asyncio.sleep(10)
                    try:
                        erp_page = await context.new_page()
                        await realizar_login_erp(erp_page)
                    except Exception as e:
                        logging.info(f"      [!] Nao foi possivel recuperar a sessao ERP agora: {e}")
                else:
                    logging.info("      [!] Falha possivelmente temporaria. Tentando novamente em 5s...")
                    await asyncio.sleep(5)

        await avisar_discord(
            f"❌ **NFe não gerada após {MAX_TENTATIVAS_GERACAO} tentativas**\n"
            f"📦 Pedido {pedido} — {planilha}\n"
            f"📄 Último retorno: {texto_curto(ultimo_resultado, 300)}"
        )
        return erp_page, ultimo_resultado
    finally:
        liberar_lock_pedido(lock_path)

def limpar_locks_sessao_chrome(user_data_dir):
    """Remove symlinks de lock do Chromium se deixados por um crash anterior."""
    lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
    for lock in lock_files:
        path = os.path.join(user_data_dir, lock)
        if os.path.exists(path) or os.path.islink(path):
            try:
                os.remove(path)
                logging.info(f"      [SESSAO] Symlink de lock antigo {lock} removido.")
            except Exception as e:
                logging.info(f"      [AVISO] Nao foi possivel remover {lock}: {e}")


async def main():
    if not validar_credenciais_erp():
        return

    # sys.argv[1] = aba (ex: '01')
    # sys.argv[2] = URL da planilha principal (opcional)
    aba_param = sys.argv[1] if len(sys.argv) > 1 else ABA_ALVO

    # Suporte a URL customizada como segundo argumento
    url_principal_custom = None
    if len(sys.argv) > 2:
        arg_url = sys.argv[2].strip()
        if arg_url.startswith("http"):
            url_principal_custom = arg_url
            # Garante que a URL termina em /edit (normaliza)
            match_id = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_principal_custom)
            if match_id:
                sheet_id_custom = match_id.group(1)
                url_principal_custom = "https://docs.google.com/spreadsheets/d/" + sheet_id_custom + "/edit"
                logging.info(f"[ARG] Planilha Principal sobrescrita por argumento: {url_principal_custom}")
            else:
                logging.warning(f"[ARG] URL fornecida nao parece valida, usando padrao: {arg_url}")
                url_principal_custom = None

    url_principal = url_principal_custom or SPREADSHEET_URL_1
    nome_principal = "Planilha Principal" if not url_principal_custom else "Planilha Principal (custom)"

    logging.info("=== Automacao NFe Independente ===")

    planilhas_config = [
        {
            "nome": nome_principal,
            "url": url_principal,
            "aba": aba_param,
            "is_mes_atual": False,
            "force_idx_h": None
        },
        {
            "nome": "Planilha Transportadora",
            "url": SPREADSHEET_URL_2,
            "aba": None,
            "is_mes_atual": True,
            "force_idx_h": 9 # Coluna J (0-indexed)
        },
        {
            "nome": "Planilha Parceiras",
            "url": SPREADSHEET_URL_3,
            "aba": aba_param,
            "is_mes_atual": False,
            "force_idx_h": 7 # Coluna H (Nota Fiscal Filial)
        }
    ]

    user_data_dir = get_user_data_dir()
    logging.info(f"      Sessao do robo em: {user_data_dir}")

    MAX_RETENTATIVAS_CICLO = 3
    INTERVALO_MINUTOS = 3

    for ciclo in range(1, MAX_RETENTATIVAS_CICLO + 1):
        etapa_atual = "Inicialização do Navegador (Playwright / Chromium)"
        limpar_locks_sessao_chrome(user_data_dir)
        
        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    timeout=45000,
                    **get_browser_options()
                )
                
                page = context.pages[0] if context.pages else await context.new_page()
                page.on("dialog", lambda dialog: dialog.accept())

                todos_pendentes = []

                for p_conf in planilhas_config:
                    etapa_atual = f"Abertura e leitura da {p_conf['nome']}"
                    logging.info(f"\n--- Processando {p_conf['nome']} ---")
                    page, gid = await obter_gid_da_aba(page, p_conf['url'], p_conf['aba'], p_conf['is_mes_atual'])
                    if gid is None: 
                        continue

                    linhas = await ler_dados_csv(page, p_conf['url'], gid)
                    if linhas is None: 
                        continue

                    debug_csv = env_bool("NFE_DEBUG_CSV", False)
                    if debug_csv:
                        logging.info("\n  Depuracao de cabecalho (primeiras 3 linhas do CSV):")
                        for l in linhas[:3]:
                            logging.info(f"    L{l['linha']}: {l['cells']}")

                    idx_c, idx_h = 2, 7
                    for row in linhas:
                        if row["linha"] == 2:
                            cells = row["cells"]
                            for j, cell in enumerate(cells):
                                txt = re.sub(r"[^a-z0-9]", "", cell.lower().strip())
                                if "numeropedido" in txt or "nrpedido" in txt: 
                                    idx_c = j
                                if "notafiscalfilial" in txt or "nffilial" in txt: 
                                    idx_h = j
                            break
                    
                    if p_conf['force_idx_h'] is not None:
                        idx_h = p_conf['force_idx_h']

                    logging.info(f"\n  Iniciando analise de {len(linhas)} linhas...")
                    pendentes_planilha = 0
                    for row in linhas:
                        if row["linha"] <= 2: continue
                        
                        cells = row["cells"]
                        if len(cells) <= max(idx_c, idx_h): continue

                        val_c = cells[idx_c].strip()
                        val_h = cells[idx_h].strip()
                        
                        pedido = extrair_pedido(val_c)
                        
                        if pedido:
                            tem_nfe = numero_antes_da_barra(val_h)
                            if debug_csv:
                                status_txt = "[NFe OK]" if tem_nfe else "[PENDENTE]"
                                logging.info(f"    L{row['linha']} | Pedido: {pedido} | NFe: '{val_h}' -> {status_txt}")

                            if not tem_nfe:
                                pendentes_planilha += 1
                                logging.info(f"      [!] Adicionado a fila: {pedido}")
                                todos_pendentes.append({"pedido": pedido, "planilha": p_conf['nome']})

                    logging.info(f"  Pendentes encontrados em {p_conf['nome']}: {pendentes_planilha}")
                
                if not todos_pendentes:
                    logging.info("\n  [OK] Nada pendente em nenhuma planilha!")
                    await sofia_relatorio([])
                    await context.close()
                    return

                logging.info("\n  Pendentes totais: " + str([p["pedido"] for p in todos_pendentes]))

                etapa_atual = f"Acesso e Login no ERP ({USUARIO})"
                erp_page = await context.new_page()
                if not await realizar_login_erp(erp_page):
                    await context.close()
                    raise RuntimeError("Não foi possível realizar login no ERP.")

                resultados_finais = []
                for item in todos_pendentes:
                    etapa_atual = f"Emissão NFe do Pedido {item['pedido']} ({item['planilha']})"
                    erp_page, resultado = await gerar_nfe_com_tentativas(context, erp_page, item)
                    resultados_finais.append({
                        "pedido":   item["pedido"],
                        "planilha": item["planilha"],
                        "resultado": resultado,
                    })
                
                await sofia_relatorio(resultados_finais)

                logging.info("\n" + "="*50)
                logging.info("PROCESSAMENTO CONCLUIDO")
                logging.info("="*50)
                if sys.stdin.isatty():
                    input("\nPressione ENTER para fechar o navegador...")
                await context.close()
                return # Sucesso!
        except Exception as e:
            logging.error(f"[ERRO CRITICO] Falha na etapa '{etapa_atual}': {e}")
            if ciclo < MAX_RETENTATIVAS_CICLO:
                await avisar_discord(
                    f"⚠️ **Timeout / Falha Temporária (Tentativa {ciclo}/{MAX_RETENTATIVAS_CICLO})**\n"
                    f"📍 Etapa: {etapa_atual}\n"
                    f"📄 Detalhe: {texto_curto(str(e), 200)}\n"
                    f"⏳ Tentando novamente em {INTERVALO_MINUTOS} minutos..."
                )
                logging.info(f"      [RETENTATIVA] Aguardando {INTERVALO_MINUTOS} minutos antes da tentativa {ciclo+1}...")
                await asyncio.sleep(INTERVALO_MINUTOS * 60)
            else:
                await avisar_discord(
                    f"❌ **Falha na Execução NFe após {MAX_RETENTATIVAS_CICLO} tentativas**\n"
                    f"📍 Etapa com falha: {etapa_atual}\n"
                    f"📄 Detalhe: {texto_curto(str(e), 250)}"
                )

async def processar_pedido_avulso(pedido: str) -> str:
    if not validar_credenciais_erp():
        return "FALHA: Credenciais do ERP nao encontradas no .env."

    logging.info(f"=== Automacao NFe Avulsa: Pedido {pedido} ===")
    user_data_dir = get_user_data_dir()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            **get_browser_options()
        )
        
        try:
            erp_page = context.pages[0] if context.pages else await context.new_page()
            erp_page.on("dialog", lambda dialog: dialog.accept())

            if not await realizar_login_erp(erp_page):
                return "FALHA: Nao foi possivel fazer login no ERP."

            item = {"pedido": pedido, "planilha": "Discord (Avulso)"}
            _, resultado = await gerar_nfe_com_tentativas(context, erp_page, item)
            
            return str(resultado)
        finally:
            await context.close()

async def obter_arquivos_nfe_pedido(pedido: str) -> list:
    """
    Navega para a tela de consulta de NFes (0103050100), busca o pedido pelo
    campo #nfe_venda_referencia, filtra com #ConfirmaFiltroII, seleciona a linha
    e clica em #btDANFE. O DANFE abre no visualizador PDF do Chrome (nova aba) —
    capturamos a URL e baixamos o PDF via request autenticado.
    Retorna lista de caminhos de arquivos PDF locais gerados.
    """
    if not validar_credenciais_erp():
        logging.error("Credenciais do ERP nao encontradas.")
        return []

    pedido_limpo = re.sub(r"\D+", "", str(pedido or ""))
    if not pedido_limpo:
        return []

    logging.info(f"=== Obter DANFE: Pedido {pedido_limpo} ===")
    user_data_dir = get_user_data_dir()
    arquivos_gerados = []

    # Diretório temporário exclusivo por pedido (evita conflito entre consultas simultâneas)
    tmp_dir = os.path.join(BASE_DIR, "tmp_danfe", pedido_limpo)
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

    browser_opts = get_browser_options()
    browser_opts["accept_downloads"] = True

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            **browser_opts
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())

            if not await realizar_login_erp(page):
                logging.error("Falha ao logar no ERP para obter DANFE.")
                return []

            # ── Passo 1: Navegar para a tela de consulta de NF ──────────────────
            logging.info(f"  [1/5] Navegando para tela 0103050100...")
            await page.goto("https://erp.admsis.com/Home?eng_tela=0103050100", timeout=60000)
            await asyncio.sleep(2)
            await esperar_carregamento_erp(page)

            # ── Passo 2: Clicar no botão de busca (lupa) ────────────────────────
            logging.info(f"  [2/5] Abrindo filtro de busca...")
            lupa = page.locator(".fa-search").first
            if await lupa.count() > 0 and await lupa.is_visible():
                await lupa.click()
                await asyncio.sleep(1)

            # ── Passo 3: Preencher número do pedido ─────────────────────────────
            logging.info(f"  [3/5] Preenchendo pedido {pedido_limpo} em #nfe_venda_referencia...")
            try:
                campo_ped = page.locator("#nfe_venda_referencia").first
                await campo_ped.wait_for(state="visible", timeout=10000)
                await campo_ped.fill(pedido_limpo)
            except Exception as e_campo:
                logging.error(f"  Campo #nfe_venda_referencia nao encontrado: {e_campo}")
                diag_path = os.path.join(BASE_DIR, "logs", f"debug_danfe_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Screenshot de diagnostico salvo em: {diag_path}")
                return []

            # ── Passo 4: Clicar em Filtrar ──────────────────────────────────────
            logging.info(f"  [4/5] Clicando em Filtrar (#ConfirmaFiltroII)...")
            btn_filtrar = page.locator("#ConfirmaFiltroII").first
            if await btn_filtrar.count() == 0:
                btn_filtrar = page.locator('button:has-text("Filtrar"), button:has-text("FILTRAR")').first
            await btn_filtrar.click(timeout=30000)
            await asyncio.sleep(3)
            await esperar_carregamento_erp(page)

            # ── Passo 5: Clicar na linha do pedido na grade ─────────────────────
            logging.info(f"  [5/5] Selecionando pedido na grade de resultados...")
            tr = page.locator(f"tr:has-text('{pedido_limpo}')").first
            if await tr.count() == 0:
                logging.warning(f"  Pedido {pedido_limpo} nao encontrado na grade de NFes.")
                diag_path = os.path.join(BASE_DIR, "logs", f"debug_danfe_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Screenshot de diagnostico salvo em: {diag_path}")
                return []

            # Clicar no primeiro link da linha (seletor de registro)
            link_linha = tr.locator("a").first
            if await link_linha.count() > 0:
                await link_linha.click()
            else:
                await tr.click()
            await asyncio.sleep(2)
            await esperar_carregamento_erp(page)

            # ── Passo 6: Clicar no botão DANFE e capturar PDF ───────────────────
            btn_danfe = page.locator("#btDANFE").first
            if await btn_danfe.count() == 0:
                logging.warning(f"  Botao #btDANFE nao encontrado para o pedido {pedido_limpo}.")
                diag_path = os.path.join(BASE_DIR, "logs", f"debug_danfe_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Screenshot de diagnostico: {diag_path}")
                return []

            logging.info(f"  Clicando em #btDANFE para o pedido {pedido_limpo}...")
            danfe_path = os.path.join(tmp_dir, f"DANFE_Pedido_{pedido_limpo}.pdf")

            # O ERP dispara o DANFE como download direto (confirmado em teste 22/09/2026).
            # Tentativa primária: expect_download.
            # Fallback: capturar nova aba (caso o comportamento mude).
            baixou = False
            try:
                async with page.expect_download(timeout=20000) as dl_info:
                    await btn_danfe.click()
                dl = await dl_info.value
                await dl.save_as(danfe_path)
                arquivos_gerados.append(danfe_path)
                logging.info(f"  DANFE baixado com sucesso: {danfe_path}")
                baixou = True
            except Exception as e_dl:
                # Fallback: o DANFE pode abrir em nova aba no viewer do Chrome
                logging.warning(f"  Download direto nao detectado ({e_dl}). Tentando capturar nova aba...")
                try:
                    async with context.expect_page() as nova_pagina_info:
                        await btn_danfe.click()
                    pdf_page = await nova_pagina_info.value
                    await pdf_page.wait_for_load_state("load", timeout=20000)
                    pdf_url = pdf_page.url
                    logging.info(f"  PDF aberto em nova aba: {pdf_url}")
                    response = await context.request.get(pdf_url, timeout=20000)
                    if response.ok:
                        with open(danfe_path, "wb") as f:
                            f.write(await response.body())
                        arquivos_gerados.append(danfe_path)
                        logging.info(f"  DANFE baixado via nova aba: {danfe_path}")
                        baixou = True
                    else:
                        logging.error(f"  Falha ao baixar PDF via nova aba: HTTP {response.status}")
                    await pdf_page.close()
                except Exception as e_aba:
                    logging.error(f"  Nao foi possivel baixar DANFE para o pedido {pedido_limpo}: {e_aba}")
                    diag_path = os.path.join(BASE_DIR, "logs", f"debug_danfe_{pedido_limpo}.png")
                    await page.screenshot(path=diag_path)
                    logging.info(f"  Screenshot de diagnostico: {diag_path}")

            if not baixou:
                logging.error(f"  DANFE nao foi obtido para o pedido {pedido_limpo}.")

            # ── XML da NF ────────────────────────────────────────────────────────
            # Botão: <a href="ErpDownload/NFE/XXXXXX" target="_blank">Baixar XML</a>
            # URL relativa — monta URL completa e baixa via sessão autenticada.
            try:
                link_xml = page.locator("a:has-text('Baixar XML')").first
                if await link_xml.count() > 0:
                    href_xml = await link_xml.get_attribute("href") or ""
                    if href_xml:
                        # Garantir URL absoluta
                        if href_xml.startswith("http"):
                            url_xml = href_xml
                        else:
                            url_xml = "https://erp.admsis.com/" + href_xml.lstrip("/")
                        logging.info(f"  Baixando XML: {url_xml}")
                        resp_xml = await context.request.get(url_xml, timeout=20000, ignore_https_errors=True)
                        if resp_xml.ok:
                            xml_path = os.path.join(tmp_dir, f"XML_Pedido_{pedido_limpo}.xml")
                            with open(xml_path, "wb") as f:
                                f.write(await resp_xml.body())
                            arquivos_gerados.append(xml_path)
                            logging.info(f"  XML baixado com sucesso: {xml_path}")
                        else:
                            logging.warning(f"  Falha ao baixar XML: HTTP {resp_xml.status} — {url_xml}")
                    else:
                        logging.warning(f"  Link 'Baixar XML' encontrado mas href vazio para o pedido {pedido_limpo}.")
                else:
                    logging.info(f"  Botao 'Baixar XML' nao encontrado para o pedido {pedido_limpo} (pode nao ter XML disponivel).")
            except Exception as e_xml:
                logging.warning(f"  Erro ao baixar XML do pedido {pedido_limpo}: {e_xml}")


        except Exception as e:
            logging.error(f"Erro ao buscar DANFE do pedido {pedido_limpo}: {e}")
        finally:
            await context.close()

    return arquivos_gerados

if __name__ == "__main__":
    asyncio.run(main())

async def avancar_ordem_producao(pedido: str) -> str:
    if not validar_credenciais_erp():
        return "FALHA: Credenciais do ERP nao encontradas no .env."
    
    pedido_limpo = re.sub(r"\D+", "", str(pedido or ""))
    if not pedido_limpo:
        return "FALHA: Número do pedido inválido."

    logging.info(f"=== Ordem de Produção: Pedido {pedido_limpo} ===")
    user_data_dir = get_user_data_dir()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            **get_browser_options()
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            page.on("dialog", lambda dialog: (logging.info(f"Browser Dialog: [{dialog.type}] {dialog.message}"), dialog.accept()))

            if not await realizar_login_erp(page):
                return "FALHA: Nao foi possivel fazer login no ERP."

            logging.info("  [1/6] Navegando para tela 0102080100 (Ordem de Produção)...")
            await page.goto("https://erp.admsis.com/Home?eng_tela=0102080100", timeout=60000)
            await asyncio.sleep(2)
            await esperar_carregamento_erp(page)

            logging.info("  [2/6] Abrindo filtro de busca...")
            lupa = page.locator(".fa-search").first
            if await lupa.count() > 0 and await lupa.is_visible():
                await lupa.click()
                await asyncio.sleep(1)

            logging.info(f"  [3/6] Preenchendo pedido {pedido_limpo} no campo Número OP...")
            campo_op = page.locator('#opr_referencia').first
            if await campo_op.count() > 0 and await campo_op.is_visible():
                await campo_op.fill(pedido_limpo)
            else:
                await page.keyboard.type(pedido_limpo)

            logging.info("  [4/6] Clicando em Filtrar...")
            btn_filtrar = page.locator('button:has-text("Filtrar"), button:has-text("FILTRAR"), #ConfirmaFiltroII').first
            if await btn_filtrar.count() > 0:
                await btn_filtrar.click(timeout=30000)
            else:
                await page.keyboard.press("Enter")
            
            await asyncio.sleep(3)
            await esperar_carregamento_erp(page)

            logging.info("  [5/6] Acessando OP na lista...")
            link_item = page.locator("a[href*='javascript:EngNavegacao.selecionar']").first
            if await link_item.count() == 0:
                diag_path = os.path.join(BASE_DIR, "logs", f"debug_op_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Screenshot de diagnostico salvo: {diag_path}")
                return f"FALHA: Número de OP {pedido_limpo} não encontrado após filtro."
            
            await link_item.click()
            await asyncio.sleep(3)
            await esperar_carregamento_erp(page)
            
            logging.info("  [6/6] Selecionando o Componente dentro do Iframe...")
            frame_componentes = None
            for frame in page.frames:
                if "102080200" in frame.url or frame.name == "frmTela102080100":
                    frame_componentes = frame
                    break

            if frame_componentes:
                link_componente = frame_componentes.locator("a[href*='javascript:EngNavegacao.selecionar']").first
                if await link_componente.count() > 0:
                    txt_comp = (await link_componente.inner_text()).strip()
                    logging.info(f"    Componente localizado ('{txt_comp}'). Clicando...")
                    await link_componente.click()
                    await asyncio.sleep(2)
                    await esperar_carregamento_erp(page)
                else:
                    logging.warning("    Nenhum link de componente encontrado dentro do iframe, tentando prosseguir...")
            else:
                logging.warning("    Iframe de componentes não localizado, tentando prosseguir no frame principal...")
                link_componente = page.locator("a[href*='javascript:EngNavegacao.selecionar']").first
                if await link_componente.count() > 0:
                    await link_componente.click()
                    await asyncio.sleep(2)
                    await esperar_carregamento_erp(page)

            btn_concluido = page.locator("#btConcluido").first
            if await btn_concluido.count() > 0:
                await btn_concluido.click()
                await asyncio.sleep(1)

                # Clicar no botão 'Sim' do modal Bootstrap de confirmação
                btn_sim = page.locator('.modal-dialog button:has-text("Sim"), .bootbox button:has-text("Sim"), button:has-text("Sim")').first
                if await btn_sim.count() > 0 and await btn_sim.is_visible():
                    logging.info("    Modal de confirmação detectado. Clicando em 'Sim'...")
                    await btn_sim.click()
                    await asyncio.sleep(3)
                    await esperar_carregamento_erp(page)

                diag_path = os.path.join(BASE_DIR, "logs", f"op_concluido_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Ordem de produção concluída para o pedido {pedido_limpo}. Print: {diag_path}")
                return f"OK: Ordem de Produção do pedido {pedido_limpo} concluída com sucesso!"
            else:
                diag_path = os.path.join(BASE_DIR, "logs", f"debug_op_btn_{pedido_limpo}.png")
                await page.screenshot(path=diag_path)
                logging.info(f"  Screenshot de diagnostico salvo: {diag_path}")
                return "FALHA: Botão 'Concluído' não encontrado."

        except Exception as e:
            logging.error(f"Erro na ordem de produção do pedido {pedido_limpo}: {e}")
            return f"ERRO interno na automação: {e}"
        finally:
            await context.close()

