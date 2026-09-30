import os
import sys
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import pdfplumber

sys.path.insert(0, os.path.dirname(__file__))
from erp_launcher import login, BrowserLauncher

TELA_RELATORIOS_URL = "https://erp.admsis.com/Home?eng_tela=0117030100"

# Mapeamento de Filiais para tela de relatórios se necessário
MAPA_FILIAIS_RELATORIO = {
    "302": "302",
    "429": "429",
    "551": "551",
    "601": "601",
    "nevine": "Nevine",
    "relevo": "Relevo"
}

def extrair_resumo_pdf_titulos_pagar(pdf_path: str) -> Dict[str, Any]:
    """
    Lê o PDF gerado (Relatório 2015) e extrai métricas resumo:
    - Quantidade de títulos
    - Valor total a pagar
    - Período
    - Totais por Filial
    - Títulos parseados
    """
    resumo = {
        "qtd_titulos": 0,
        "valor_total": "R$ 0,00",
        "periodo": "",
        "totais_por_filial": {},
        "titulos": []
    }
    
    if not os.path.exists(pdf_path):
        return resumo
        
    try:
        texto_completo = ""
        totais_filiais = {}
        lista_titulos = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                texto_completo += txt + "\n"
                for line in txt.split("\n"):
                    m = re.match(
                        r"^(\d{5,7})\s+(\d{3}|Nevine|Relevo)\s+(.*?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(?:Boleto\s+|Cheque\s+|Transfer[eê]ncia\s+|Pix\s+)?([\d\.,]+)\s+",
                        line
                    )
                    if m:
                        tid, fil, ref, dt_venc, dt_emiss, val_raw = m.groups()
                        try:
                            val_num = float(val_raw.replace(".", "").replace(",", "."))
                        except Exception:
                            val_num = 0.0
                        totais_filiais[fil] = totais_filiais.get(fil, 0.0) + val_num
                        lista_titulos.append({
                            "id": tid,
                            "filial": fil,
                            "referencia": ref.strip(),
                            "vencimento": dt_venc,
                            "valor": val_num,
                            "valor_str": f"R$ {val_raw}"
                        })
                
        # Procura período
        m_periodo = re.search(r"Vencimento de (\d{2}/\d{2}/\d{4}),\s*Vencimento at[ée]\s*(\d{2}/\d{2}/\d{4})", texto_completo)
        if m_periodo:
            resumo["periodo"] = f"{m_periodo.group(1)} até {m_periodo.group(2)}"
            
        # Procura linha de Total oficial: "Total 20 33.200,00"
        m_total = re.search(r"Total\s+(\d+)\s+([\d\.,]+)", texto_completo)
        if m_total:
            resumo["qtd_titulos"] = int(m_total.group(1))
            resumo["valor_total"] = f"R$ {m_total.group(2)}"
        else:
            resumo["qtd_titulos"] = len(lista_titulos)
            tot_calc = sum(t["valor"] for t in lista_titulos)
            resumo["valor_total"] = f"R$ {tot_calc:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
        resumo["totais_por_filial"] = totais_filiais
        resumo["titulos"] = lista_titulos
            
    except Exception as e:
        print(f"[extrair_resumo_pdf_titulos_pagar] Erro analisando PDF: {e}")
        
    return resumo


async def gerar_relatorio_titulos_pagar(
    data_inicio: str,
    data_fim: Optional[str] = None,
    filial: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Acessa a tela 0117030100 no ERP ADMSIS, seleciona o relatório 2015
    (Relatório de Títulos a Pagar), preenche o intervalo de vencimento,
    gera e captura o PDF oficial.
    
    Retorna (caminho_pdf, dicionario_resumo).
    """
    if not data_fim:
        data_fim = data_inicio
        
    # Limpa digitos das datas (ex: 03/07/2026 -> 03072026)
    digits_ini = re.sub(r"\D", "", data_inicio)
    digits_fim = re.sub(r"\D", "", data_fim)
    
    if len(digits_ini) != 8 or len(digits_fim) != 8:
        raise ValueError(f"Datas inválidas: início={data_inicio}, fim={data_fim}. Use formato DD/MM/AAAA.")
        
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_dest_name = f"contas_a_pagar_{digits_ini}_{digits_fim}_{timestamp_str}.pdf"
    pdf_dest_path = os.path.join(output_dir, pdf_dest_name)
    
    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        pdf_url = None
        pdf_bytes = None
        
        async def on_response(response):
            nonlocal pdf_url
            ct = response.headers.get("content-type", "")
            if "pdf" in ct.lower() or "pdf" in response.url.lower():
                pdf_url = response.url
                
        page.on("response", on_response)
        context.on("response", on_response)
        
        try:
            print("[Relatório] Realizando login...")
            await login(page)
            
            print(f"[Relatório] Navegando para tela {TELA_RELATORIOS_URL}...")
            await page.goto(TELA_RELATORIOS_URL, timeout=60000)
            await page.wait_for_selector("#relatorio", timeout=15000)
            
            print("[Relatório] Selecionando Relatório 2015 (Títulos a Pagar)...")
            await page.select_option("#relatorio", value="2015")
            await page.evaluate("""() => {
                const sel = document.querySelector('#relatorio');
                if (sel) sel.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            await asyncio.sleep(2)
            
            # Preenche datas de vencimento
            print(f"[Relatório] Preenchendo data vencimento: {data_inicio} até {data_fim}...")
            # Data Inicial
            el_i = await page.query_selector("#data_vencimento_i")
            if el_i:
                await el_i.click(force=True)
                await el_i.fill("")
                await el_i.type(digits_ini, delay=30)
                await el_i.evaluate("e => { e.dispatchEvent(new Event('change', {bubbles:true})); e.dispatchEvent(new Event('blur', {bubbles:true})); }")
                
            # Data Final
            el_f = await page.query_selector("#data_vencimento_f")
            if el_f:
                await el_f.click(force=True)
                await el_f.fill("")
                await el_f.type(digits_fim, delay=30)
                await el_f.evaluate("e => { e.dispatchEvent(new Event('change', {bubbles:true})); e.dispatchEvent(new Event('blur', {bubbles:true})); }")
                
            # Filtro opcional de Filial se selecionado
            if filial:
                filial_norm = filial.strip().lower()
                for key, val in MAPA_FILIAIS_RELATORIO.items():
                    if key in filial_norm:
                        print(f"[Relatório] Aplicando filtro de filial: {val}")
                        try:
                            await page.select_option("#filial", label=val)
                        except Exception as e_filial:
                            print(f"[Relatório] Aviso ao filtrar filial {val}: {e_filial}")
                        break
                        
            await asyncio.sleep(1)
            
            print("[Relatório] Clicando em #btRelatorioPDF...")
            await page.click("#btRelatorioPDF")
            
            # Aguarda a interceptação da URL do PDF
            for _ in range(40):
                if pdf_url:
                    break
                await asyncio.sleep(0.5)
                
            if not pdf_url:
                raise TimeoutError("Tempo esgotado aguardando geração do PDF pelo ERP.")
                
            print(f"[Relatório] URL interceptada: {pdf_url}")
            print("[Relatório] Baixando PDF diretamente pela sessão...")
            res = await context.request.get(pdf_url)
            if res.status != 200:
                raise RuntimeError(f"Falha no download do PDF. Status HTTP: {res.status}")
                
            pdf_bytes = await res.body()
            print(f"[Relatório] PDF obtido com sucesso ({len(pdf_bytes)} bytes)!")
            
            with open(pdf_dest_path, "wb") as f:
                f.write(pdf_bytes)
                
            # Extrai resumo do PDF
            resumo = extrair_resumo_pdf_titulos_pagar(pdf_dest_path)
            return pdf_dest_path, resumo
            
        finally:
            await browser.close()


def extrair_resumo_pdf_titulos_receber(pdf_path: str) -> Dict[str, Any]:
    """
    Lê o PDF gerado (Relatório 2004 - Relação de Títulos a Receber em Aberto)
    e extrai métricas resumo:
    - Quantidade de títulos
    - Valor total a receber
    - Período
    - Totais por Filial
    - Clientes e títulos
    """
    resumo = {
        "qtd_titulos": 0,
        "valor_total": "R$ 0,00",
        "periodo": "",
        "totais_por_filial": {},
        "titulos": []
    }
    
    if not os.path.exists(pdf_path):
        return resumo
        
    try:
        texto_completo = ""
        totais_filiais = {}
        lista_titulos = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                texto_completo += txt + "\n"
                for line in txt.split("\n"):
                    m_row = re.match(
                        r"^(\d{2}/\d{2}/\d{4})\s+(\d{3}|Nevine|Relevo)\s+(.*?)\s+(\d{2}/\d{2}/\d{4})\s+(.*?)\s+([\d\.,]+)\s+",
                        line
                    )
                    if m_row:
                        dt_emiss, fil, ref, dt_venc, cliente, val_raw = m_row.groups()
                        try:
                            val_num = float(val_raw.replace(".", "").replace(",", "."))
                        except Exception:
                            val_num = 0.0
                        totais_filiais[fil] = totais_filiais.get(fil, 0.0) + val_num
                        lista_titulos.append({
                            "emissao": dt_emiss,
                            "filial": fil,
                            "referencia": ref.strip(),
                            "vencimento": dt_venc,
                            "cliente": cliente.strip(),
                            "valor": val_num,
                            "valor_str": f"R$ {val_raw}"
                        })
                        
        m_periodo = re.search(r"DATA DE VENCIMENTO DE (\d{2}/\d{2}/\d{4}),\s*DATA DE VENCIMENTO AT[ÉE]\s*(\d{2}/\d{2}/\d{4})", texto_completo)
        if m_periodo:
            resumo["periodo"] = f"{m_periodo.group(1)} até {m_periodo.group(2)}"
            
        m_total_geral = re.search(r"Total Geral\s+([\d\.,]+)", texto_completo)
        if m_total_geral:
            resumo["valor_total"] = f"R$ {m_total_geral.group(1)}"
            resumo["qtd_titulos"] = len(lista_titulos)
        else:
            m_total = re.search(r"Total\s+([\d\.,]+)", texto_completo)
            if m_total:
                resumo["valor_total"] = f"R$ {m_total.group(1)}"
                resumo["qtd_titulos"] = len(lista_titulos)
            else:
                tot_calc = sum(t["valor"] for t in lista_titulos)
                resumo["valor_total"] = f"R$ {tot_calc:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                resumo["qtd_titulos"] = len(lista_titulos)
                
        resumo["totais_por_filial"] = totais_filiais
        resumo["titulos"] = lista_titulos
    except Exception as e:
        print(f"[extrair_resumo_pdf_titulos_receber] Erro analisando PDF: {e}")
        
    return resumo


async def gerar_relatorio_titulos_receber(
    data_inicio: str,
    data_fim: Optional[str] = None,
    filial: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Acessa a tela 0117030100 no ERP ADMSIS, seleciona o relatório 2004
    (Relação de Títulos a Receber em Aberto), preenche o intervalo de vencimento,
    gera e captura o PDF oficial.
    
    Retorna (caminho_pdf, dicionario_resumo).
    """
    if not data_fim:
        data_fim = data_inicio
        
    digits_ini = re.sub(r"\D", "", data_inicio)
    digits_fim = re.sub(r"\D", "", data_fim)
    
    if len(digits_ini) != 8 or len(digits_fim) != 8:
        raise ValueError(f"Datas inválidas: início={data_inicio}, fim={data_fim}. Use formato DD/MM/AAAA.")
        
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_dest_name = f"contas_a_receber_{digits_ini}_{digits_fim}_{timestamp_str}.pdf"
    pdf_dest_path = os.path.join(output_dir, pdf_dest_name)
    
    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        pdf_url = None
        pdf_bytes = None
        
        async def on_response(response):
            nonlocal pdf_url
            ct = response.headers.get("content-type", "")
            if "pdf" in ct.lower() or "pdf" in response.url.lower():
                pdf_url = response.url
                
        page.on("response", on_response)
        context.on("response", on_response)
        
        try:
            print("[Relatório Receber] Realizando login...")
            await login(page)
            
            print(f"[Relatório Receber] Navegando para tela {TELA_RELATORIOS_URL}...")
            await page.goto(TELA_RELATORIOS_URL, timeout=60000)
            await page.wait_for_selector("#relatorio", timeout=15000)
            
            print("[Relatório Receber] Selecionando Relatório 2004 (Títulos a Receber em Aberto)...")
            await page.select_option("#relatorio", value="2004")
            await page.evaluate("""() => {
                const sel = document.querySelector('#relatorio');
                if (sel) sel.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            await asyncio.sleep(2)
            
            # Preenche datas de vencimento
            print(f"[Relatório Receber] Preenchendo data vencimento: {data_inicio} até {data_fim}...")
            el_i = await page.query_selector("#data_vencimento_i")
            if el_i:
                await el_i.click(force=True)
                await el_i.fill("")
                await el_i.type(digits_ini, delay=30)
                await el_i.evaluate("e => { e.dispatchEvent(new Event('change', {bubbles:true})); e.dispatchEvent(new Event('blur', {bubbles:true})); }")
                
            el_f = await page.query_selector("#data_vencimento_f")
            if el_f:
                await el_f.click(force=True)
                await el_f.fill("")
                await el_f.type(digits_fim, delay=30)
                await el_f.evaluate("e => { e.dispatchEvent(new Event('change', {bubbles:true})); e.dispatchEvent(new Event('blur', {bubbles:true})); }")
                
            if filial:
                filial_norm = filial.strip().lower()
                for key, val in MAPA_FILIAIS_RELATORIO.items():
                    if key in filial_norm:
                        print(f"[Relatório Receber] Aplicando filtro de filial: {val}")
                        try:
                            await page.select_option("#filial", label=val)
                        except Exception as e_filial:
                            print(f"[Relatório Receber] Aviso ao filtrar filial {val}: {e_filial}")
                        break
                        
            await asyncio.sleep(1)
            
            print("[Relatório Receber] Clicando em #btRelatorioPDF...")
            await page.click("#btRelatorioPDF")
            
            for _ in range(40):
                if pdf_url:
                    break
                await asyncio.sleep(0.5)
                
            if not pdf_url:
                raise TimeoutError("Tempo esgotado aguardando geração do PDF 2004 pelo ERP.")
                
            print(f"[Relatório Receber] URL interceptada: {pdf_url}")
            print("[Relatório Receber] Baixando PDF diretamente pela sessão...")
            res = await context.request.get(pdf_url)
            if res.status != 200:
                raise RuntimeError(f"Falha no download do PDF 2004. Status HTTP: {res.status}")
                
            pdf_bytes = await res.body()
            print(f"[Relatório Receber] PDF obtido com sucesso ({len(pdf_bytes)} bytes)!")
            
            with open(pdf_dest_path, "wb") as f:
                f.write(pdf_bytes)
                
            resumo = extrair_resumo_pdf_titulos_receber(pdf_dest_path)
            return pdf_dest_path, resumo
            
        finally:
            await browser.close()
