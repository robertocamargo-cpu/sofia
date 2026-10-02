"""
Pipeline completo de automacao GNRE:
1. Le planilha Google Sheets
2. Identifica pedidos pendentes (GNRE Status != OK/SIM)
3. Extrai dados do ERP Admsis (pedido + DANFE)
4. Gera GNRE no site www.gnre.pe.gov.br
5. Baixa PDF
6. Atualiza planilha

Uso:
    python gnre_pipeline.py                    # Processa todos os pendentes
    python gnre_pipeline.py --pedido 1760      # Processa um pedido especifico
    python gnre_pipeline.py --modo-check       # So verifica pendentes, nao gera GNRE
    python gnre_pipeline.py --continuar        # Pula pedidos ja com PDF baixado
"""

import sys
import os
import csv
import re
import tempfile
import urllib.request
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from PyPDF2 import PdfReader
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
import database
from gnre_automation import processar_gnre, get_uf_path, enviar_alerta_discord

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
ERP_URL = 'https://erp.admsis.com/'
ERP_USER = os.getenv("ERP_USER")
ERP_PASS = os.getenv("ERP_PASS")
SHEET_ID = os.getenv("GNRE_SHEET_ID") or "1pVnhOWvuGKn66CmXNhEZNTPpsiQMcBUpyrYtHMcmp-g"
SHEET_GID = os.getenv("GNRE_SHEET_GID") or "600128813"
SHEET_URL = os.getenv("GNRE_SHEET_URL", f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}")
SAVE_PATH = os.getenv("GNRE_SAVE_PATH") or os.path.dirname(os.path.abspath(__file__))
PEDIDOS_BAIXADOS = os.path.join(SAVE_PATH, 'pedidos_baixados')

os.makedirs(PEDIDOS_BAIXADOS, exist_ok=True)

# IE do destinatário por pedido (ERP nao extrai automaticamente)
PEDIDO_IE = {
    "2253": "4280010705",  # DROPS VALE DOS SINOS SPE LTDA (RS)
    "2541": "202535100",   # Vitrine Empreendimentos Ltda (RN)
    "2845": "067634915",   # CARMEL TAIBA EXCLUSIVE RESORT HOTEIS LTDA (CE)
}

PEDIDO_CLIENTE_DADOS = {
    "2845": {
        "cliente_cnpj": "27.708.448/0001-10",
        "cliente_municipio": "SAO GONCALO DO AMARANTE",
        "cliente_uf": "CE",
        "cliente_cep": "62670000",
        "cliente_endereco": "RUA CAPITAO INACIO PRATA, 900",
    },
}

PEDIDO_CHAVE = {
    "2683": "35260705393606000158550000000547521053936060",
}

FILIAIS = {
    "NEVINE": {"cnpj": "71.883.656/0001-48", "razao_social": "NEVINE COMERCIO", "endereco": "RUA CUBATAO, 601", "cep": "04013042"},
    "429": {"cnpj": "05.393.606/0001-58", "razao_social": "429 COMERCIO", "endereco": "RUA DO GLICERIO, 557", "cep": "01514001"},
    "302": {"cnpj": "28.375.701/0001-24", "razao_social": "302 COMERCIO", "endereco": "AV. BRIGADEIRO FARIA LIMA, 1811", "cep": "01452001"},
    "551": {"cnpj": "26.509.080/0001-07", "razao_social": "551 COMERCIO", "endereco": "RUA DO GLICERIO 557 SALA 1", "cep": "01514001"},
    "601": {"cnpj": "52.803.025/0001-27", "razao_social": "601 COMERCIO", "endereco": "RUA SANTA CRUZ, 2187 SALA 10", "cep": "04121002"},
}
DADOS_BASE = {
    "cnpj": "71.883.656/0001-48",
    "uf_emitente": "SP",
    "municipio": "3550308",
    "telefone": "1155723945",
    "receita": "100099",
}

HOJE = datetime.now()
AMANHA = HOJE + timedelta(days=1)


# ============================================================
# 1. PLANILHA
# ============================================================
def baixar_planilha(ultimas_n=None):
    import socket
    socket.setdefaulttimeout(30)
    tmp = os.path.join(tempfile.gettempdir(), 'planilha_gnre.csv')
    try:
        urllib.request.urlretrieve(SHEET_URL, tmp)
    except Exception as e:
        print(f"  [ERRO] Falha ao baixar planilha Google Sheets ({e}).")
        enviar_alerta_discord(f"⚠️ GNRE: Falha ao baixar planilha Google Sheets: {e}")
        return [], []

    with open(tmp, encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    pedidos = []
    for i, row in enumerate(rows):
        if i < 2:
            continue
        if len(row) < 11:
            continue
        pedido = row[2].strip()
        nota = row[9].strip()
        uf = row[10].strip()
        cliente = row[11].strip() if len(row) > 11 else ''
        gnre_status = row[17].strip() if len(row) > 17 else ''
        if pedido:
            pedido_clean = pedido.split('/')[0].strip()
            nota_clean = nota.split('/')[0].strip()
            pedidos.append({
                'pedido': pedido,
                'pedido_clean': pedido_clean,
                'nota': nota,
                'nota_clean': nota_clean,
                'uf': uf.upper(),
                'cliente': cliente,
                'gnre_status': gnre_status.upper(),
            })
    # Filter: linhas que tenham NF e nao sejam SP
    com_nf = [p for p in pedidos if p['nota_clean']]
    if ultimas_n is not None and len(com_nf) > ultimas_n:
        com_nf = com_nf[-ultimas_n:]
    fora_sp = [p for p in com_nf if p['uf'] and not p['uf'].startswith('SP')]
    return fora_sp, com_nf


def precisa_gnre(pedido):
    status = pedido['gnre_status'].upper()
    return status == 'S'


def filtrar_pendentes(pedidos):
    pendentes = [p for p in pedidos if precisa_gnre(p)]
    return pendentes


def resumo_pedido(p):
    return f"{p['pedido']:16} | NF {p['nota_clean']:6} | {p['uf']:22} | {p['cliente'][:40]:40} | {p['gnre_status']:8}"


# ============================================================
# 2. ERP - EXTRACAO DE DADOS
# ============================================================
def login_erp(page):
    if not ERP_USER or not ERP_PASS:
        raise RuntimeError("Configure ERP_USER e ERP_PASS antes de acessar o ERP.")
    page.goto(ERP_URL)
    page.wait_for_timeout(3000)
    page.fill('input[type="text"]', ERP_USER)
    page.fill('input[type="password"]', ERP_PASS)
    page.click('button:has-text("Acessar")')
    page.wait_for_timeout(3000)


def normalizar_ie(valor):
    valor = (valor or "").strip()
    digits = re.sub(r"\D", "", valor)
    if not digits or len(digits) < 6:
        return ""
    return digits


def extrair_ie_texto_danfe(texto):
    texto = texto or ""
    texto_norm = re.sub(r"\s+", " ", texto)
    padroes = [
        r"INSCRI[CÇ][AÃ]O\s+ESTADUAL\s+([0-9.\-/]{6,18})",
        r"INSC\.?\s*ESTADUAL\s+([0-9.\-/]{6,18})",
        r"\bI\.?E\.?\s*:?\s*([0-9.\-/]{6,18})",
    ]
    candidatos = []
    for pat in padroes:
        for match in re.finditer(pat, texto_norm, flags=re.I):
            ie = normalizar_ie(match.group(1))
            if ie:
                candidatos.append((match.start(), ie))
    if not candidatos:
        return ""

    # Na DANFE, a IE do destinatário costuma aparecer depois do bloco DESTINATARIO.
    pos_dest = texto_norm.upper().find("DESTINAT")
    if pos_dest >= 0:
        depois_dest = [item for item in candidatos if item[0] >= pos_dest]
        if depois_dest:
            return depois_dest[0][1]
    return candidatos[-1][1]


def extrair_texto_pdf(pdf_path):
    texto = []
    reader = PdfReader(pdf_path)
    for page_pdf in reader.pages:
        try:
            texto.append(page_pdf.extract_text() or "")
        except Exception:
            pass
    return "\n".join(texto)


def extrair_ie_xml_nfe(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
        for elem in root.iter():
            if elem.tag.split("}")[-1] != "dest":
                continue
            for child in elem:
                if child.tag.split("}")[-1] == "IE":
                    return normalizar_ie(child.text)
    except Exception:
        pass
    texto = xml_bytes.decode("utf-8", "ignore")
    match = re.search(r"<dest\b.*?</dest>", texto, flags=re.I | re.S)
    bloco_dest = match.group(0) if match else texto
    match_ie = re.search(r"<IE>(.*?)</IE>", bloco_dest, flags=re.I | re.S)
    return normalizar_ie(match_ie.group(1)) if match_ie else ""


def extrair_ie_cliente_pedido(page):
    for frame in page.frames:
        for selector in (
            "#cli_inscricao_estadual",
            "#lbl_cli_inscricao_estadual",
            'input[id*="inscricao_estadual" i]',
            'input[name*="inscricao_estadual" i]',
        ):
            try:
                loc = frame.locator(selector).first
                if loc.count() == 0:
                    continue
                ie = normalizar_ie(loc.input_value(timeout=2000))
                if ie:
                    print(f"  IE destinatário extraída do pedido: {ie}")
                    return ie
            except Exception:
                continue

    try:
        dados_ie = []
        for frame in page.frames:
            dados_ie.extend(frame.evaluate("""() => {
            function norm(s) {
                return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toUpperCase().trim();
            }
            function visivel(el) {
                if (!el) return false;
                var st = getComputedStyle(el);
                var r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }
            function contexto(el) {
                var partes = [el.id || '', el.name || '', el.getAttribute('placeholder') || '', el.getAttribute('title') || ''];
                if (el.id) {
                    var lab = document.querySelector('label[for="' + el.id + '"]');
                    if (lab) partes.push(lab.innerText || lab.textContent || '');
                }
                var p = el.parentElement;
                for (var i = 0; p && i < 3; i++, p = p.parentElement) {
                    partes.push(p.innerText || p.textContent || '');
                }
                return norm(partes.join(' '));
            }
            var candidatos = [];
            Array.from(document.querySelectorAll('input, select, textarea')).forEach(function(el) {
                var value = (el.value || '').trim();
                if (!value) return;
                var ctx = contexto(el);
                if (!/(INSCR|ESTADUAL|\\bIE\\b|CACEAL)/.test(ctx)) return;
                var digits = value.replace(/\\D/g, '');
                if (digits.length < 6 || digits.length > 14) return;
                candidatos.push({
                    id: el.id || '',
                    name: el.name || '',
                    value: value,
                    digits: digits,
                    context: ctx.slice(0, 180)
                });
            });
            Array.from(document.querySelectorAll('label, span, div, td, th')).forEach(function(label) {
                if (!visivel(label)) return;
                var labelText = norm(label.innerText || label.textContent || '');
                if (!/(^|\\s)(I\\.?E\\.?|INSCRICAO ESTADUAL|INSC ESTADUAL|CACEAL)\\s*:?($|\\s)/.test(labelText)) return;
                var lr = label.getBoundingClientRect();
                var controle = Array.from(document.querySelectorAll('input, select, textarea'))
                    .filter(function(el) {
                        if (!visivel(el)) return false;
                        var value = (el.value || '').trim();
                        if (!value) return false;
                        var digits = value.replace(/\\D/g, '');
                        if (digits.length < 6 || digits.length > 14) return false;
                        var r = el.getBoundingClientRect();
                        return Math.abs(r.top - lr.top) < 12 && r.left > lr.right;
                    })
                    .sort(function(a, b) {
                        return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
                    })[0];
                if (controle) {
                    candidatos.push({
                        id: controle.id || '',
                        name: controle.name || '',
                        value: controle.value || '',
                        digits: (controle.value || '').replace(/\\D/g, ''),
                        context: labelText.slice(0, 180)
                    });
                }
            });
            var body = norm(document.body.innerText || document.body.textContent || '');
            var regex = /(INSCRICAO ESTADUAL|INSCR\\. ESTADUAL|INSC ESTADUAL|\\bIE\\b|CACEAL)[^0-9]{0,40}([0-9.\\/-]{6,18})/g;
            var m;
            while ((m = regex.exec(body)) !== null) {
                var digits = (m[2] || '').replace(/\\D/g, '');
                if (digits.length >= 6 && digits.length <= 14) {
                    candidatos.push({
                        id: '',
                        name: '',
                        value: m[2],
                        digits: digits,
                        context: m[0].slice(0, 180)
                    });
                }
            }
            return candidatos.slice(0, 20);
        }"""))
    except Exception as e:
        print(f"  [AVISO] Falha ao extrair IE do pedido: {e}")
        return ""

    if dados_ie:
        print(f"  Candidatos de IE no pedido: {dados_ie}")

    for item in dados_ie or []:
        ctx = item.get("context", "")
        if any(palavra in ctx for palavra in ("TRANSPORT", "EMITENTE", "VENDEDOR", "REPRESENTANTE")):
            continue
        ie = normalizar_ie(item.get("digits") or item.get("value"))
        if ie:
            print(f"  IE destinatário extraída do pedido: {ie}")
            return ie
    return ""


def extrair_tributacao_pedido(page, num_pedido):
    num_pedido_safe = re.sub(r"['\"\\\n]", "", str(num_pedido))
    page.goto('https://erp.admsis.com/Home?eng_tela=0101060100', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(2000)
    page.fill('input[placeholder="Nr. Pedido"]', num_pedido_safe, timeout=30000)
    page.wait_for_timeout(500)
    page.click('button:has-text("Filtrar")')
    page.wait_for_timeout(1500)
    page.wait_for_selector('table tbody tr a', timeout=15000)
    page.locator('table tbody tr').first.locator('a').first.click()
    page.wait_for_timeout(1500)
    try:
        page.click('#tab_btn_101060200', timeout=5000)
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  [AVISO] Aba Cliente do pedido: {e}")
    ie_destinatario = extrair_ie_cliente_pedido(page)
    try:
        page.click('text="Tributação"', timeout=5000)
    except:
        try:
            page.click('text="Tributacao"', timeout=5000)
        except:
            page.click(':has-text("ribut")', timeout=5000)
    page.wait_for_timeout(1500)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    page.wait_for_timeout(1000)
    # Extract from hidden fields (mais confiavel que texto visivel)
    valores = page.evaluate('''() => {
        var result = {};
        var inputs = document.querySelectorAll('input[type="hidden"]');
        inputs.forEach(function(inp) {
            var name = inp.name || inp.id || '';
            result[name] = inp.value;
        });
        return result;
    }''')
    icms_valor = valores.get('vda_icms_substituicao_1', '') or '0,00'
    fcp_valor = valores.get('vda_fcp_st_1', '') or '0,00'
    if fcp_valor == '0,00':
        fcp_valor = valores.get('vda_fcp_1', '') or '0,00'
    def normalizar(val):
        val = val.replace(' ', '')
        if ',' in val:
            partes = val.split(',')
            inteiro = partes[0].replace('.', '')
            decimal = partes[1][:2].ljust(2, '0')
            return f'{inteiro},{decimal}'
        val = val.replace('.', '')
        if len(val) > 2:
            return val[:-2] + ',' + val[-2:]
        return '0,' + val.zfill(2)
    icms_valor = normalizar(icms_valor)
    fcp_valor = normalizar(fcp_valor)
    if not ie_destinatario:
        ie_destinatario = extrair_ie_cliente_pedido(page)
    return icms_valor, fcp_valor, {"ie_destinatario": ie_destinatario}


def extrair_dados_danfe(page, context, num_nf):
    num_nf_safe = re.sub(r"['\"\\\n]", "", str(num_nf))
    page.goto('https://erp.admsis.com/Home?eng_tela=0103050100', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(2000)
    try:
        campo_nota = page.locator('input[placeholder="Nr"], input[name="numero"], input[placeholder="NR"]').first
        if campo_nota.count() > 0:
            campo_nota.fill(num_nf_safe)
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            try:
                page.click('button:has-text("Filtrar"), button:has-text("FILTRAR")', timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  [AVISO] Filtro NF {num_nf_safe}: {e}")

    texto = page.locator('body').inner_text()
    dados_danfe = {"chave_dfe": "", "ie_destinatario": ""}
    linhas = texto.split('\n')
    for linha in linhas:
        if num_nf_safe in linha:
            chaves = re.findall(r'\d{44}', linha)
            if chaves:
                dados_danfe["chave_dfe"] = chaves[0]
                break
    chaves = re.findall(r'\d{44}', texto)
    if chaves and not dados_danfe["chave_dfe"]:
        dados_danfe["chave_dfe"] = chaves[0]

    try:
        xml_link = page.evaluate("""(numNf) => {
            var linhas = Array.from(document.querySelectorAll('tr'));
            for (var tr of linhas) {
                if (!(tr.innerText || '').includes(numNf)) continue;
                var link = Array.from(tr.querySelectorAll('a')).find(function(a) {
                    return /Baixar XML/i.test(a.innerText || a.textContent || '') || /ErpDownload\\/NFE/i.test(a.href || '');
                });
                if (link) return link.href;
            }
            return '';
        }""", num_nf_safe)
        if xml_link:
            response = page.context.request.get(xml_link, timeout=30000)
            xml_bytes = response.body()
            ie_xml = extrair_ie_xml_nfe(xml_bytes)
            if ie_xml:
                dados_danfe["ie_destinatario"] = ie_xml
                print(f"  IE destinatário extraída da DANFE/XML: {ie_xml}")
    except Exception as e:
        print(f"  [AVISO] Não foi possível ler XML da NF-e para IE: {e}")

    if not dados_danfe.get("ie_destinatario"):
        try:
            resultado_nota = page.locator("tr").filter(has_text=num_nf_safe).first
            if resultado_nota.count() > 0:
                resultado_nota.click(timeout=5000)
                page.wait_for_timeout(500)
                try:
                    resultado_nota.dblclick(timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(500)
            page.click('button:has-text("DANFE"), a:has-text("DANFE")', timeout=10000)
            page.wait_for_timeout(500)
            with page.expect_download(timeout=20000) as download_info:
                page.click('button:has-text("BAIXAR"), button:has-text("Baixar"), a:has-text("BAIXAR"), a:has-text("Baixar")', timeout=10000)
            download = download_info.value
            danfe_path = os.path.join(tempfile.gettempdir(), f"DANFE_{num_nf_safe}.pdf")
            download.save_as(danfe_path)
            texto_pdf = extrair_texto_pdf(danfe_path)
            chaves_pdf = re.findall(r'\d{44}', re.sub(r"\D", "", texto_pdf))
            if chaves_pdf and not dados_danfe["chave_dfe"]:
                dados_danfe["chave_dfe"] = chaves_pdf[0]
            ie_pdf = extrair_ie_texto_danfe(texto_pdf)
            if ie_pdf:
                dados_danfe["ie_destinatario"] = ie_pdf
                print(f"  IE destinatário extraída da DANFE: {ie_pdf}")
        except Exception as e:
            print(f"  [AVISO] Não foi possível baixar/ler DANFE para IE: {e}")

    if not dados_danfe["chave_dfe"]:
        print('  [AVISO] Nenhuma chave de 44 digitos encontrada na pagina NF/DANFE')
    return dados_danfe



def extrair_dados_pedido(page, context, pedido):
    num_pedido = pedido['pedido_clean']
    num_nf = pedido['nota_clean']
    uf_fav = pedido['uf'][:2]
    print(f"\n{'='*60}")
    print(f"Processando pedido {num_pedido} - NF {num_nf} - {uf_fav}")
    print(f"{'='*60}")
    icms_valor, fcp_valor, dados_cliente_pedido = extrair_tributacao_pedido(page, num_pedido)
    print(f"  ICMS/ST: {icms_valor}  |  FCP: {fcp_valor}")
    if icms_valor == '0,00' and fcp_valor == '0,00':
        print(f"  [AVISO] Pedido {num_pedido}: ICMS/ST e FCP = 0,00. GNRE pode nao ser necessaria.")
    dados_danfe = extrair_dados_danfe(page, context, num_nf)
    chave_dfe = dados_danfe.get("chave_dfe", "")
    if len(chave_dfe) != 44 and num_pedido in PEDIDO_CHAVE:
        chave_dfe = PEDIDO_CHAVE[num_pedido]
        print("  Chave DFe: usando override cadastrado para o pedido.")
    print(f"  Chave DFe: {chave_dfe[:10]}...{chave_dfe[-4:] if len(chave_dfe) > 14 else ''}")
    cnpj_chave = ""
    if len(chave_dfe) == 44:
        cnpj_raw = chave_dfe[6:20]
        cnpj_chave = f"{cnpj_raw[:2]}.{cnpj_raw[2:5]}.{cnpj_raw[5:8]}/{cnpj_raw[8:12]}-{cnpj_raw[12:]}"
        print(f"  CNPJ Emitente pela chave: {cnpj_chave}")
    else:
        print(f"  [AVISO] Chave DFe invalida ({len(chave_dfe)} chars).")
    nota_full = pedido.get('nota', '')
    filial = nota_full.split('/')[-1].strip().upper() if '/' in nota_full else 'NEVINE'
    filial = filial if filial in FILIAIS else 'NEVINE'
    filial_data = FILIAIS[filial]
    print(f"  Filial: {filial} -> {filial_data['razao_social']}")
    cnpj_emit = filial_data.get("cnpj") or cnpj_chave or DADOS_BASE["cnpj"]
    if cnpj_chave and cnpj_chave != cnpj_emit:
        print(f"  [AVISO] CNPJ da chave ({cnpj_chave}) difere da filial {filial} ({cnpj_emit}). Usando CNPJ da filial.")
    dados = dict(DADOS_BASE)
    dados.update({
        "cnpj": cnpj_emit,
        "razao_social": filial_data["razao_social"],
        "endereco": filial_data["endereco"],
        "cep": filial_data["cep"],
        "uf_favorecida": uf_fav,
        "chave_dfe": chave_dfe,
        "valor_icms_st": icms_valor,
        "valor_fcp": fcp_valor,
        "data_emissao": HOJE.strftime("%d/%m/%Y"),
        "data_vencimento": AMANHA.strftime("%d/%m/%Y"),
        "data_pagamento": AMANHA.strftime("%d/%m/%Y"),
        "info_complementares": f"Pedido {pedido['pedido']} - NF {num_nf}",
        "numero_nf": num_nf,
        "cliente_razao": pedido.get("cliente", ""),
        "ie_destinatario": (
            dados_cliente_pedido.get("ie_destinatario")
            or dados_danfe.get("ie_destinatario")
            or PEDIDO_IE.get(num_pedido)
        ),
    })
    dados.update(PEDIDO_CLIENTE_DADOS.get(num_pedido, {}))
    if uf_fav in ("PR", "BA", "DF", "CE"):
        dados["tipo_doc_origem"] = "10"
    return dados


def validar_regras_uf(dados):
    uf = dados.get("uf_favorecida", "")
    icms_str = (dados.get("valor_icms_st") or "0").replace(".", "").replace(",", ".").strip()
    fcp_str = (dados.get("valor_fcp") or "0").replace(".", "").replace(",", ".").strip()
    try:
        val_icms = float(icms_str)
    except ValueError:
        val_icms = 0.0
    try:
        val_fcp = float(fcp_str)
    except ValueError:
        val_fcp = 0.0

    if val_icms <= 0 and val_fcp <= 0:
        return False, "Valores de ICMS-ST e FCP sao R$ 0,00 (pedido nao exige emissao de guia GNRE)."

    if uf == "AL" and not dados.get("ie_destinatario"):
        return False, "AL exige IE do destinatario; ERP nao retornou IE no pedido."
    return True, ""


# ============================================================
# 3. ATUALIZACAO DA PLANILHA
# ============================================================
def atualizar_planilha(pedido, status="OK"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    google_email = os.getenv("GOOGLE_EMAIL") or os.getenv("GOOGLE_USER")
    google_pass = os.getenv("GOOGLE_PASS")
    if not google_email or not google_pass:
        print("  [AVISO] GOOGLE_EMAIL/GOOGLE_USER e GOOGLE_PASS nao configurados; planilha nao sera atualizada.")
        return False
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={SHEET_GID}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            page.goto(sheet_url)
            page.wait_for_timeout(3000)
            page.fill('input[type="email"]', google_email)
            page.click('button:has-text("Próxima"), button:has-text("Next")')
            page.wait_for_timeout(2000)
            page.fill('input[type="password"]', google_pass)
            page.click('button:has-text("Próxima"), button:has-text("Next")')
            page.wait_for_timeout(10000)
            page.goto(sheet_url)
            page.wait_for_timeout(5000)
            page.keyboard.press('Control+f')
            page.wait_for_timeout(1000)
            page.keyboard.type(pedido['pedido'])
            page.wait_for_timeout(2000)
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
            page.keyboard.press('Tab')
            page.wait_for_timeout(500)
            for _ in range(5):
                page.keyboard.press('Tab')
                page.wait_for_timeout(200)
            page.keyboard.type(status)
            page.wait_for_timeout(1000)
            page.keyboard.press('Enter')
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  [AVISO] Falha ao atualizar planilha: {e}")
            browser.close()
            return False
        browser.close()
    return True


def gerar_gnre_com_tentativas(dados, pedido, max_tentativas=5):
    num_pedido = pedido['pedido_clean']
    num_nf = pedido['nota_clean']
    ultimo_erro = ""
    for tentativa in range(1, max_tentativas + 1):
        print(f"  Tentativa {tentativa}/{max_tentativas} para pedido {num_pedido} / NF {num_nf}...")
        try:
            pdf_path = processar_gnre(dados, use_camoufox=True)
            if pdf_path and os.path.exists(pdf_path):
                return pdf_path, None
            ultimo_erro = "processo terminou sem confirmar PDF local"
            print(f"  [AVISO] Tentativa {tentativa}/{max_tentativas} sem PDF confirmado.")
        except Exception as e:
            ultimo_erro = str(e)
            print(f"  [ERRO] Tentativa {tentativa}/{max_tentativas} falhou: {e}")

    mensagem = (
        "ERRO GNRE: 5 tentativas sem gerar PDF.\n"
        f"Pedido: {num_pedido}\n"
        f"NF: {num_nf}\n"
        f"UF: {dados.get('uf_favorecida', '')}\n"
        f"Cliente: {pedido.get('cliente', '')}\n"
        f"Ultimo erro: {ultimo_erro or 'PDF nao confirmado'}"
    )
    enviar_alerta_discord(mensagem)
    return None, ultimo_erro or "PDF nao confirmado apos 5 tentativas"


# ============================================================
# 4. PIPELINE PRINCIPAL
# ============================================================
def executar_pipeline(pedido_especifico=None, modo_check=False, continuar=False, dry_run=False):
    print("=" * 60)
    print("  PIPELINE AUTOMACAO GNRE (aba vigente)")
    print("=" * 60)
    fora_sp, todas = baixar_planilha()
    print(f"\nTotal: {len(todas)} pedidos encontrados")
    print(f"Fora de SP: {len(fora_sp)}")
    if pedido_especifico:
        pendentes = [p for p in todas if p['pedido_clean'] == pedido_especifico]
        if not pendentes:
            print(f"  Pedido {pedido_especifico} nao encontrado nas ultimas 3 linhas.")
            return False
    else:
        pendentes = filtrar_pendentes(fora_sp)
        print(f"Pendentes (sem GNRE): {len(pendentes)}")
    if not pendentes:
        print("Nenhum pedido pendente encontrado!")
        from datetime import datetime
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        enviar_alerta_discord(f"✅ GNRE verificada às {agora} — Nenhum pedido pendente.")
        return True
    print("\nPedidos a processar:")
    print("-" * 125)
    for p in pendentes:
        print(f"  {resumo_pedido(p)}")
    print("-" * 125)
    if modo_check:
        print("\nModo check: apenas visualizei. Nenhuma GNRE gerada.")
        return True
    if not pedido_especifico:
        print(f"\nProcessando {len(pendentes)} pedido(s)...")
    import subprocess
    from playwright.sync_api import sync_playwright

    def extrair_erp():
        with sync_playwright() as pw:
            browser = None
            # Tenta 1: Chromium (rápido)
            try:
                browser = pw.chromium.launch(headless=True, timeout=12000)
            except Exception as e:
                print(f"  [AVISO] Chromium falhou para ERP ({e}). Tentando Firefox...")

            # Tenta 2: Firefox
            if not browser:
                try:
                    browser = pw.firefox.launch(headless=True, timeout=12000)
                except Exception as e:
                    print(f"  [AVISO] Firefox falhou para ERP ({e}). Tentando Camoufox...")

            # Tenta 3: Camoufox (fallback final)
            if not browser:
                try:
                    from camoufox import NewBrowser
                    browser = NewBrowser(pw, headless=True)
                except Exception as e:
                    msg_erro = f"❌ GNRE: Todos os navegadores falharam para extração ERP: {e}"
                    print(f"  [ERRO] {msg_erro}")
                    enviar_alerta_discord(msg_erro)
                    return []

            try:
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    accept_downloads=True,
                    ignore_https_errors=True,
                )
                page = context.new_page()
                print("\n1. Login ERP...")
                login_erp(page)
                resultados = []
                for i, pedido in enumerate(pendentes):
                    num_pedido = pedido['pedido_clean']
                    num_nf = pedido['nota_clean']
                    pdf_path = os.path.join(get_uf_path(pedido['uf'][:2]), f"GNRE NF {num_nf}.pdf")
                    if continuar and os.path.exists(pdf_path):
                        print(f"\n  [{i+1}/{len(pendentes)}] Pulando pedido {num_pedido} (PDF ja existe)")
                        continue
                    print(f"\n  [{i+1}/{len(pendentes)}] Processando pedido {num_pedido}...")
                    dados = extrair_dados_pedido(page, context, pedido)
                    if dados:
                        resultados.append((pedido, dados))
                    if pedido_especifico:
                        break
            finally:
                browser.close()
            return resultados
    print("\nExtrando dados do ERP...")
    resultados = extrair_erp()
    if dry_run:
        print("\nDry-run: dados extraidos, nenhuma GNRE gerada.")
        for pedido, dados in resultados:
            print(
                f"  Pedido {pedido['pedido_clean']} | NF {dados.get('numero_nf')} | "
                f"UF {dados.get('uf_favorecida')} | ICMS {dados.get('valor_icms_st')} | "
                f"FCP {dados.get('valor_fcp')} | IE {dados.get('ie_destinatario') or '-'} | "
                f"Chave {dados.get('chave_dfe')}"
            )
        return True
    falhas_pdf = []
    for pedido, dados in resultados:
        num_pedido = pedido['pedido_clean']
        num_nf = pedido['nota_clean']
        regras_ok, erro_regra = validar_regras_uf(dados)
        if not regras_ok:
            print(f"\n  [ERRO] Pedido {num_pedido} bloqueado: {erro_regra}")
            enviar_alerta_discord(f"⚠️ GNRE pedido {num_pedido}/NF {num_nf} bloqueada: {erro_regra}")
            falhas_pdf.append(num_pedido)
            continue
        print(f"\n  Gerando GNRE para pedido {num_pedido}...")
        pdf_path, erro = gerar_gnre_com_tentativas(dados, pedido)
        if pdf_path and os.path.exists(pdf_path):
            print(f"  GNRE gerada com sucesso para pedido {num_pedido}!")
            try:
                database.registrar_emissao_gnre(num_pedido, dados.get("uf_favorecida", ""), "OK")
            except Exception as e:
                print(f"  [AVISO BD] Falha ao registrar GNRE no banco de dados: {e}")
            print(f"  Atualizando planilha...")
            if not atualizar_planilha(pedido, "OK"):
                print(f"  [AVISO] PDF salvo, mas planilha nao confirmou atualizacao para pedido {num_pedido}.")
        else:
            print(f"  [ERRO] Pedido {num_pedido} sem PDF depois de 5 tentativas: {erro}")
            falhas_pdf.append(num_pedido)
    if falhas_pdf:
        print("\n=== PIPELINE CONCLUIDO COM FALHA ===")
        print("Pedidos sem PDF confirmado: " + ", ".join(falhas_pdf))
        return False
    print("\n=== PIPELINE CONCLUIDO ===")
    return True


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline automacao GNRE")
    parser.add_argument("--pedido", help="Processar apenas um pedido especifico")
    parser.add_argument("--modo-check", action="store_true", help="So listar pendentes sem gerar GNRE")
    parser.add_argument("--continuar", action="store_true", help="Pular pedidos com PDF ja baixado")
    parser.add_argument("--dry-run", action="store_true", help="Extrair dados do ERP sem gerar GNRE")
    args = parser.parse_args()
    sucesso = executar_pipeline(
        pedido_especifico=args.pedido,
        modo_check=args.modo_check,
        continuar=args.continuar,
        dry_run=args.dry_run,
    )
    sys.exit(0 if sucesso else 1)
