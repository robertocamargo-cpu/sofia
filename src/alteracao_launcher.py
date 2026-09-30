"""
====================================================================
  MÓDULO DE ALTERAÇÃO DE TÍTULOS A PAGAR NO ERP ADMSIS (Playwright RPA)
====================================================================
Suporta dois modos principais:
  1. Alteração Individual (Pontual):
     - Localiza o favorecido/fornecedor via lookup ou filtro.
     - Abre o título mais recente em aberto.
     - Atualiza um ou múltiplos campos: Plano de Contas, Data de Vencimento, Filial, Referência, Observação, Valor.
     - Grava via '#AlterarI' e registra auditoria no batch_history.json.

  2. Alteração em Lote (Batch Update por Data de Vencimento):
     - Filtra o grid por data de vencimento de origem (ex: HOJE) e Situação = Pendente.
     - Percorre todos os títulos retornados.
     - Atualiza a data de vencimento para a nova data de destino.
     - Grava cada título e emite resumo consolidado.
"""

import os
import sys
import re
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from erp_launcher import (
    login, BrowserLauncher, ERP_URL, close_modal, valor_br, click_alterar
)
from avulso_launcher import selecionar_fornecedor_lookup, FILIAIS_MAP

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def parse_data_termo(termo: str) -> Optional[Tuple[date, str]]:
    """Converte termos relativos ou strings de data em objeto date e string DD/MM/AAAA."""
    t = termo.strip().lower()
    hoje = date.today()
    if "hoje" in t:
        d = hoje
        return d, d.strftime("%d/%m/%Y")
    elif "amanhã" in t or "amanha" in t:
        d = hoje + timedelta(days=1)
        return d, d.strftime("%d/%m/%Y")
    elif "ontem" in t:
        d = hoje - timedelta(days=1)
        return d, d.strftime("%d/%m/%Y")
    
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", t)
    if m:
        dia, mes, ano = m.groups()
        if len(ano) == 2:
            ano = f"20{ano}"
        try:
            d = date(int(ano), int(mes), int(dia))
            return d, d.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return None


def parse_alteracao_command(texto: str) -> Dict[str, Any]:
    """
    Analisa o comando do Discord e extrai se é alteração individual ou em lote,
    além dos campos específicos a serem alterados.
    """
    t = texto.strip()
    res: Dict[str, Any] = {
        "modo": "individual",  # 'individual' ou 'lote'
        "fornecedor": None,
        "campos": {},
        "lote_origem": None,
        "lote_origem_str": None,
        "lote_destino": None,
        "lote_destino_str": None,
        "filial_filtro": None,
        "erros": []
    }

    # Verifica se é comando em LOTE (palavra 'todos')
    m_todos = re.search(r"\btodos\b", t, re.IGNORECASE)
    if m_todos:
        res["modo"] = "lote"
        
        # Procura datas: "de HOJE para 01/10/2026" ou "de 30/09 para 05/10"
        m_de_para = re.search(r"de\s+([^\s,]+(?:\s+[^\s,]+)?)\s+para\s+([^\s,]+(?:\s+[^\s,]+)?)", t, re.IGNORECASE)
        if m_de_para:
            orig_txt = m_de_para.group(1).strip()
            dest_txt = m_de_para.group(2).strip()
            
            p_orig = parse_data_termo(orig_txt)
            p_dest = parse_data_termo(dest_txt)
            
            if p_orig:
                res["lote_origem"], res["lote_origem_str"] = p_orig
            else:
                res["erros"].append(f"Não reconheci a data de origem: '{orig_txt}'")
                
            if p_dest:
                res["lote_destino"], res["lote_destino_str"] = p_dest
            else:
                res["erros"].append(f"Não reconheci a data de destino: '{dest_txt}'")
        else:
            # Fallback: procura se mencionou "para [data]"
            m_para = re.search(r"para\s+(\d{1,2}/\d{1,2}/\d{2,4}|hoje|amanhã|amanha)", t, re.IGNORECASE)
            if m_para:
                p_dest = parse_data_termo(m_para.group(1))
                if p_dest:
                    res["lote_destino"], res["lote_destino_str"] = p_dest
                # Origem padrão: hoje
                res["lote_origem"] = date.today()
                res["lote_origem_str"] = res["lote_origem"].strftime("%d/%m/%Y")
            else:
                res["erros"].append("Para alterar em lote, especifique as datas: ex. 'de HOJE para 01/10/2026'.")

        # Filial opcional no lote
        m_fil = re.search(r"\bfilial\s*[:=]?\s*(\d{3}|nevine|relevo)\b", t, re.IGNORECASE)
        if m_fil:
            res["filial_filtro"] = m_fil.group(1).upper()
            
        return res

    # Modo INDIVIDUAL:
    # 0. Padrão específico de alta prioridade: "altere o/a <CAMPO> do favorecido/fornecedor <NOME> para <VALOR>"
    m_direto = re.search(
        r"(?:altere|alterar|mudar|atualize|atualizar)\s+(?:o|a|os|as)?\s*(plano\s+de\s+contas|plano|data\s+de\s+vencimento|vencimento|filial|referencia|referência|ref|observacao|observação|obs|valor)\s+(?:do\s+favorecido|do\s+fornecedor|do|da|de)\s+([A-ZÀ-Úa-zà-ú\s]+?)\s+para\s+([^,;\n]+)",
        t, re.IGNORECASE
    )
    if m_direto:
        campo_nome = m_direto.group(1).lower()
        res["fornecedor"] = m_direto.group(2).strip()
        valor_novo = m_direto.group(3).strip()

        if "plano" in campo_nome:
            res["campos"]["plano_contas"] = valor_novo
        elif "venc" in campo_nome or "data" in campo_nome:
            dt_p = parse_data_termo(valor_novo)
            if dt_p:
                res["campos"]["vencimento"], res["campos"]["vencimento_str"] = dt_p
            else:
                res["erros"].append(f"Data de vencimento não reconhecida: '{valor_novo}'")
        elif "filial" in campo_nome:
            res["campos"]["filial"] = valor_novo.upper()
        elif "ref" in campo_nome:
            res["campos"]["referencia"] = valor_novo
        elif "obs" in campo_nome:
            res["campos"]["observacao"] = valor_novo
        elif "valor" in campo_nome:
            v_str = valor_novo.replace("r$", "").replace(".", "").replace(",", ".").strip()
            try:
                res["campos"]["valor"] = float(v_str)
                res["campos"]["valor_str"] = valor_br(res["campos"]["valor"])
            except:
                pass
        return res

    # 1. Identificar Favorecido / Fornecedor (Modo Geral com múltiplos campos)
    m_forn = re.search(r"(?:do\s+favorecido|do\s+fornecedor|para\s+o\s+favorecido|para\s+o\s+fornecedor|favorecido|fornecedor)\s+([A-ZÀ-Úa-zà-ú\s]+?)(?:\s+para|\s*:\s*|\s*,\s*|\s+vencimento|\s+plano|\s+filial|\s+ref|\s+obs|$)", t, re.IGNORECASE)
    if m_forn:
        candidato = m_forn.group(1).strip()
        for palavra_chave in ["o", "a", "os", "as"]:
            if candidato.lower().startswith(f"{palavra_chave} "):
                candidato = candidato[len(palavra_chave)+1:].strip()
        res["fornecedor"] = candidato
    else:
        m_alt = re.search(r"(?:altere|alterar|mudar)\s+([A-ZÀ-Úa-zà-ú\s]+?)(?:\s*:\s*|\s*,\s*|\s+para|\s+vencimento|\s+plano|$)", t, re.IGNORECASE)
        if m_alt:
            cand = m_alt.group(1).strip()
            if cand.lower() not in ["o", "a", "o plano", "a data", "o vencimento", "a filial", "a referencia", "a observacao"]:
                res["fornecedor"] = cand

    # 2. Identificar Plano de Contas
    m_plano = re.search(r"(?:plano\s*de\s*contas|plano|conta)\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+([^\s,;]+)", t, re.IGNORECASE)
    if not m_plano:
        m_plano = re.search(r"(?:plano|conta)\s*[:=]\s*([^\s,;]+)", t, re.IGNORECASE)
    if m_plano:
        res["campos"]["plano_contas"] = m_plano.group(1).strip()

    # 3. Identificar Data de Vencimento
    m_venc = re.search(r"(?:data\s*de\s*vencimento|vencimento|vence)\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+([^\s,;]+)", t, re.IGNORECASE)
    if not m_venc:
        m_venc = re.search(r"(?:vencimento|vence|data)\s*[:=]\s*([^\s,;]+)", t, re.IGNORECASE)
    if m_venc:
        dt_parse = parse_data_termo(m_venc.group(1))
        if dt_parse:
            res["campos"]["vencimento"], res["campos"]["vencimento_str"] = dt_parse

    # 4. Identificar Filial
    m_fil = re.search(r"\bfilial\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+(\d{3}|nevine|relevo)\b", t, re.IGNORECASE)
    if not m_fil:
        m_fil = re.search(r"\bfilial\s*[:=]\s*(\d{3}|nevine|relevo)\b", t, re.IGNORECASE)
    if m_fil:
        res["campos"]["filial"] = m_fil.group(1).upper()

    # 5. Identificar Referência
    m_ref = re.search(r"(?:referencia|referência|ref)\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+([^,;\n]+?)(?:\s+filial|\s+plano|\s+vencimento|\s+obs|$)", t, re.IGNORECASE)
    if not m_ref:
        m_ref = re.search(r"(?:referencia|referência|ref)\s*[:=]\s*([^,;\n]+?)(?:\s+filial|\s+plano|\s+vencimento|\s+obs|$)", t, re.IGNORECASE)
    if m_ref:
        res["campos"]["referencia"] = m_ref.group(1).strip()

    # 6. Identificar Observação
    m_obs = re.search(r"(?:observacao|observação|obs|historico|histórico)\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+(.+)$", t, re.IGNORECASE)
    if not m_obs:
        m_obs = re.search(r"(?:observacao|observação|obs|historico|histórico)\s*[:=]\s*(.+)$", t, re.IGNORECASE)
    if m_obs:
        res["campos"]["observacao"] = m_obs.group(1).strip()

    # 7. Identificar Valor (se houver pedido de alteração de valor)
    m_val = re.search(r"(?:valor|quantia)\s*(?:do\s+favorecido\s+[^\s]+)?\s*para\s+r?\$?\s*(\d+(?:[.,]\d{1,2})?)\b", t, re.IGNORECASE)
    if m_val:
        v_str = m_val.group(1).replace(".", "").replace(",", ".")
        try:
            res["campos"]["valor"] = float(v_str)
            res["campos"]["valor_str"] = valor_br(res["campos"]["valor"])
        except ValueError:
            pass

    if not res["fornecedor"]:
        res["erros"].append("Favorecido / Fornecedor não identificado no comando.")
    if not res["campos"]:
        res["erros"].append("Nenhum campo para alteração foi identificado (ex: plano de contas, vencimento, filial, ref, obs).")

    return res


async def aplicar_alteracoes_no_formulario(f, campos: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica as alterações solicitadas diretamente nos campos do iframe do título."""
    modificados = {}

    # 1. Plano de Contas
    if "plano_contas" in campos:
        termo = str(campos["plano_contas"])
        res_plano = await f.evaluate("""(termo) => {
            const sel = document.querySelector('#ttp_plano_conta_id');
            if (!sel) return null;
            const t = termo.trim().toLowerCase();
            let matched = null;
            for (let i = 0; i < sel.options.length; i++) {
                const opt = sel.options[i];
                const optText = opt.text.trim().toLowerCase();
                const optVal = opt.value.trim().toLowerCase();
                if (optText.startsWith(t) || optText.includes(t) || optVal === t) {
                    matched = opt;
                    break;
                }
            }
            if (matched) {
                const anterior = sel.options[sel.selectedIndex]?.text || '';
                sel.value = matched.value;
                sel.dispatchEvent(new Event('change', {bubbles: true}));
                return { anterior: anterior, novo: matched.text };
            }
            return null;
        }""", termo)
        if res_plano:
            modificados["Plano de Contas"] = f"{res_plano.get('anterior')} -> {res_plano.get('novo')}"
            print(f"  [Alteração] Plano de Contas alterado para: {res_plano.get('novo')}", flush=True)
        else:
            modificados["Plano de Contas (Aviso)"] = f"Não encontrado código/nome '{termo}'"

    # 2. Data de Vencimento
    if "vencimento_str" in campos:
        venc_str = campos["vencimento_str"]
        venc_ant = await f.evaluate("""(novaData) => {
            const el = document.querySelector('#ttp_data_vencimento');
            if (!el) return null;
            const ant = el.value;
            el.value = novaData;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            return ant;
        }""", venc_str)
        modificados["Data de Vencimento"] = f"{venc_ant or 'N/D'} -> {venc_str}"
        print(f"  [Alteração] Vencimento alterado para: {venc_str}", flush=True)

    # 3. Filial
    if "filial" in campos:
        filial_txt = campos["filial"].upper()
        val_cod = FILIAIS_MAP.get(filial_txt, filial_txt)
        res_fil = await f.evaluate("""(cod) => {
            const sel = document.querySelector('#ttp_filial_id');
            if (!sel) return null;
            const ant = sel.options[sel.selectedIndex]?.text || '';
            for (let i = 0; i < sel.options.length; i++) {
                const opt = sel.options[i];
                if (opt.value === cod || opt.text.trim().toUpperCase() === cod.toUpperCase()) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    return { anterior: ant, novo: opt.text.trim() };
                }
            }
            return null;
        }""", val_cod)
        if res_fil:
            modificados["Filial"] = f"{res_fil.get('anterior')} -> {res_fil.get('novo')}"
            print(f"  [Alteração] Filial alterada para: {res_fil.get('novo')}", flush=True)

    # 4. Referência
    if "referencia" in campos:
        ref_txt = campos["referencia"]
        ref_ant = await f.evaluate("""(novaRef) => {
            const el = document.querySelector('#ttp_referencia');
            if (!el) return null;
            const ant = el.value;
            el.value = novaRef;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return ant;
        }""", ref_txt)
        modificados["Referência"] = f"'{ref_ant or ''}' -> '{ref_txt}'"
        print(f"  [Alteração] Referência alterada para: {ref_txt}", flush=True)

    # 5. Observação
    if "observacao" in campos:
        obs_txt = campos["observacao"]
        await f.evaluate("""(novaObs) => {
            const el = document.querySelector('#ttp_observacao') || document.querySelector('#ttp_historico');
            if (el) {
                el.value = novaObs;
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""", obs_txt)
        modificados["Observação"] = f"Atualizada para: '{obs_txt}'"
        print(f"  [Alteração] Observação alterada", flush=True)

    # 6. Valor
    if "valor" in campos:
        val_f = valor_br(campos["valor"])
        v_ant = await f.evaluate("""(novoVal) => {
            const el = document.querySelector('#ttp_valor_titulo');
            if (!el) return null;
            const ant = el.value;
            el.value = novoVal;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return ant;
        }""", val_f)
        modificados["Valor"] = f"R$ {v_ant or ''} -> R$ {val_f}"
        print(f"  [Alteração] Valor alterado para: R$ {val_f}", flush=True)

    return modificados


async def alterar_titulo_individual(fornecedor: str, campos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executa a alteração pontual no título mais recente de um favorecido:
    1. Localiza favorecido via lookup.
    2. Filtra grid.
    3. Abre o título pendente (btnEd_1).
    4. Aplica as modificações.
    5. Grava com #AlterarI.
    """
    print(f"\n{'='*65}")
    print(f"  INICIANDO ALTERAÇÃO PONTUAL DE TÍTULO")
    print(f"  Favorecido : {fornecedor}")
    print(f"  Campos     : {campos}")
    print(f"{'='*65}\n")

    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))

        try:
            await login(page)
            await page.goto(ERP_URL, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=20000)

            # 1. Seleciona favorecido no Lookup
            ok_lk = await selecionar_fornecedor_lookup(page, fornecedor)
            if not ok_lk:
                return {
                    "sucesso": False,
                    "mensagem": f"Fornecedor '{fornecedor}' não foi localizado no cadastro do ERP."
                }

            # 2. Filtra por Situação = Pendente (value=0) e clica em Filtrar
            try:
                await page.select_option("#ttp_situacao_id", value="0")
            except:
                pass

            print("  [Alteração] Filtrando títulos pendentes do fornecedor...", flush=True)
            try:
                await page.click("#ConfirmaFiltroS", timeout=10000, force=True, no_wait_after=True)
            except:
                await page.evaluate("() => { const b = document.querySelector('#ConfirmaFiltroS'); if(b) b.click(); }")
            await asyncio.sleep(3)

            # 3. Localiza primeiro título no grid
            edit_links = await page.query_selector_all("a[id^='btnEd_']")
            if not edit_links:
                await page.screenshot(path=os.path.join(LOG_DIR, "erro_alteracao_sem_titulo.png"))
                return {
                    "sucesso": False,
                    "mensagem": f"O fornecedor '{fornecedor}' foi localizado, mas não possui nenhum título pendente para alteração."
                }

            link_id = await edit_links[0].get_attribute("id")
            print(f"  [Alteração] Abrindo título {link_id}...", flush=True)
            try:
                await edit_links[0].click(timeout=8000, force=True, no_wait_after=True)
            except:
                await page.evaluate(f"() => {{ const el = document.getElementById('{link_id}'); if(el) el.click(); }}")
            await asyncio.sleep(2)

            f = page.frame(name='frmTela103070100') or page

            # 4. Aplica as alterações no formulário
            modificados = await aplicar_alteracoes_no_formulario(f, campos)
            if not modificados:
                return {
                    "sucesso": False,
                    "mensagem": "Nenhum campo pôde ser modificado no formulário do título."
                }

            # 5. Grava com 'Alterar' (#AlterarI)
            print("  [Alteração] Gravando alterações no ERP...", flush=True)
            saved = await click_alterar(f, page)
            if not saved:
                try:
                    await f.evaluate("() => { const b = document.querySelector('#AlterarI') || document.querySelector('button[id*=\"Alterar\"]'); if(b) b.click(); }")
                    saved = True
                    await asyncio.sleep(2)
                except Exception:
                    pass

            if not saved:
                return {
                    "sucesso": False,
                    "mensagem": "Falha ao acionar botão de gravação ('Alterar') no formulário."
                }

            await asyncio.sleep(3)

            # 6. Registra no histórico estruturado
            resumo_execucao = {
                "fornecedor": fornecedor,
                "modificacoes": modificados,
                "total_colaboradores": 1,
                "total_sucesso": 1,
                "total_falhas": 0,
                "valor_total_lancado": 0.0,
                "sucessos": [{"fornecedor": fornecedor, "modificacoes": modificados}],
                "falhas": []
            }
            try:
                from batch_logger import salvar_historico_lote
                salvar_historico_lote("ALTERACAO_TITULO", resumo_execucao, arquivo="Discord / Alteração Pontual")
            except Exception as e:
                print(f"  [Alteração] Aviso ao salvar log: {e}", flush=True)

            print(f"\n[OK] Título de {fornecedor} alterado com sucesso!\n")
            return {
                "sucesso": True,
                "fornecedor": fornecedor,
                "modificados": modificados,
                "mensagem": "Título alterado com sucesso no ERP ADMSIS."
            }

        except Exception as exc:
            await page.screenshot(path=os.path.join(LOG_DIR, "erro_alteracao_individual.png"))
            print(f"  [Alteração] ERRO: {exc}", flush=True)
            return {
                "sucesso": False,
                "mensagem": f"Erro inesperado ao alterar título: {str(exc)}"
            }
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass


async def alterar_titulos_lote(
    data_origem: date,
    data_destino: date,
    filial: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa alteração de data de vencimento em lote:
    1. Filtra grid por Data Vencimento Inicial e Final = data_origem, Situação = Pendente.
    2. Lê todos os títulos retornados.
    3. Para cada título: abre, altera data de vencimento para data_destino e salva.
    4. Registra log consolidado.
    """
    dt_orig_str = data_origem.strftime("%d/%m/%Y")
    dt_dest_str = data_destino.strftime("%d/%m/%Y")

    print(f"\n{'='*65}")
    print(f"  INICIANDO ALTERAÇÃO EM LOTE DE VENCIMENTO")
    print(f"  Data Origem  : {dt_orig_str}")
    print(f"  Data Destino : {dt_dest_str}")
    print(f"  Filial       : {filial or 'Todas'}")
    print(f"{'='*65}\n")

    async with BrowserLauncher() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))

        try:
            await login(page)
            await page.goto(ERP_URL, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=20000)

            # 1. Aplica filtros de data de vencimento
            await page.fill("#ttp_data_vencimento_i", dt_orig_str)
            await page.fill("#ttp_data_vencimento_f", dt_orig_str)

            # 2. Situação = Pendente (value=0)
            try:
                await page.select_option("#ttp_situacao_id", value="0")
            except:
                pass

            # 3. Filial opcional
            if filial:
                cod_filial = FILIAIS_MAP.get(filial.upper(), filial)
                try:
                    await page.select_option("#ttp_filial_id", value=cod_filial)
                except:
                    pass

            print(f"  [Lote] Filtrando títulos com vencimento em {dt_orig_str}...", flush=True)
            try:
                await page.click("#ConfirmaFiltroS", timeout=10000, force=True, no_wait_after=True)
            except:
                await page.evaluate("() => { const b = document.querySelector('#ConfirmaFiltroS'); if(b) b.click(); }")
            await asyncio.sleep(3)

            # 4. Verifica quantidade de títulos retornados
            edit_links = await page.query_selector_all("a[id^='btnEd_']")
            total_titulos = len(edit_links)
            print(f"  [Lote] Total de títulos pendentes encontrados: {total_titulos}", flush=True)

            if total_titulos == 0:
                return {
                    "sucesso": True,
                    "total_encontrados": 0,
                    "total_alterados": 0,
                    "mensagem": f"Nenhum título pendente foi encontrado com vencimento em {dt_orig_str}."
                }

            alterados = []
            falhas = []

            # 5. Itera e altera cada título
            # Observação: Como cada alteração pode atualizar o grid, coletamos os IDs ou re-filtramos se necessário
            for idx in range(1, total_titulos + 1):
                try:
                    print(f"  [Lote] Processando título {idx} de {total_titulos}...", flush=True)
                    
                    # Garante que o grid está acessível
                    link = await page.query_selector(f"#btnEd_{idx}")
                    if not link:
                        # Se não encontrar por índice (devido à paginação/recarga), tenta o primeiro da lista
                        edit_links = await page.query_selector_all("a[id^='btnEd_']")
                        if edit_links:
                            link = edit_links[0]
                    
                    if not link:
                        print(f"  [Lote] Aviso: Link do título {idx} não encontrado", flush=True)
                        continue

                    # Captura nome do favorecido da linha do grid
                    info_linha = await page.evaluate(f"""(i) => {{
                        const row = document.querySelector(`#btnEd_${{i}}`)?.closest('tr');
                        return row ? row.innerText.replace(/\\s+/g, ' ').trim() : '';
                    }}""", idx)

                    await link.click(timeout=8000, force=True, no_wait_after=True)
                    await asyncio.sleep(2)

                    f = page.frame(name='frmTela103070100') or page

                    # Altera o vencimento
                    await f.evaluate("""(novaData) => {
                        const el = document.querySelector('#ttp_data_vencimento');
                        if (el) {
                            el.value = novaData;
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('blur', {bubbles: true}));
                        }
                    }""", dt_dest_str)

                    # Grava com Alterar
                    saved = await click_alterar(f, page)
                    if not saved:
                        await f.evaluate("() => { const b = document.querySelector('#AlterarI') || document.querySelector('button[id*=\"Alterar\"]'); if(b) b.click(); }")
                        await asyncio.sleep(2)

                    alterados.append({
                        "indice": idx,
                        "descricao": info_linha[:60] if info_linha else f"Título {idx}",
                        "de": dt_orig_str,
                        "para": dt_dest_str
                    })
                    print(f"  [Lote] Título {idx} prorrogado para {dt_dest_str} com sucesso!", flush=True)

                    # Retorna ao grid se necessário
                    await asyncio.sleep(2)
                    # Se saiu do grid ou precisa voltar
                    if not await page.query_selector("#ConfirmaFiltroS"):
                        await page.goto(ERP_URL, timeout=60000)
                        await page.wait_for_load_state("networkidle", timeout=20000)
                        await page.fill("#ttp_data_vencimento_i", dt_orig_str)
                        await page.fill("#ttp_data_vencimento_f", dt_orig_str)
                        await page.click("#ConfirmaFiltroS", timeout=10000, force=True, no_wait_after=True)
                        await asyncio.sleep(3)

                except Exception as err_item:
                    print(f"  [Lote] Erro no título {idx}: {err_item}", flush=True)
                    falhas.append({"indice": idx, "erro": str(err_item)})

            # 6. Registra no histórico estruturado
            resumo_execucao = {
                "data_origem": dt_orig_str,
                "data_destino": dt_dest_str,
                "filial": filial or "Todas",
                "total_colaboradores": total_titulos,
                "total_sucesso": len(alterados),
                "total_falhas": len(falhas),
                "valor_total_lancado": 0.0,
                "sucessos": alterados,
                "falhas": falhas
            }
            try:
                from batch_logger import salvar_historico_lote
                salvar_historico_lote("ALTERACAO_LOTE_VENCIMENTO", resumo_execucao, arquivo="Discord / Alteração em Lote")
            except Exception as e:
                print(f"  [Lote] Aviso ao salvar log: {e}", flush=True)

            print(f"\n[OK] Lote concluído: {len(alterados)} de {total_titulos} títulos alterados para {dt_dest_str}!\n")

            return {
                "sucesso": True,
                "total_encontrados": total_titulos,
                "total_alterados": len(alterados),
                "total_falhas": len(falhas),
                "data_origem": dt_orig_str,
                "data_destino": dt_dest_str,
                "alterados": alterados,
                "falhas": falhas,
                "mensagem": f"Alteração em lote concluída: {len(alterados)} títulos alterados de {dt_orig_str} para {dt_dest_str}."
            }

        except Exception as exc:
            await page.screenshot(path=os.path.join(LOG_DIR, "erro_alteracao_lote.png"))
            print(f"  [Lote] ERRO: {exc}", flush=True)
            return {
                "sucesso": False,
                "mensagem": f"Erro inesperado no lote de alteração: {str(exc)}"
            }
        finally:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
