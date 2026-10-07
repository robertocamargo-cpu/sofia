import asyncio
import os
import re
import csv
import io
import zipfile
import json
import urllib.request
import argparse
from datetime import datetime, timedelta
import pandas as pd
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# ─── Configurações ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1OHMAcfxKIS2UTntlB5J7Y8krmCK7JHT9miEHmbbmLE8/edit#gid=993064263"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# ERP
ERP_URL = "https://erp.admsis.com/Home"
ERP_USER = os.getenv("ERP_USER")
ERP_PASS = os.getenv("ERP_PASS")

# Google
GOOGLE_USER = os.getenv("GOOGLE_USER")
GOOGLE_PASS = os.getenv("GOOGLE_PASS")

# Filiais a pesquisar
FILIAIS = ["302", "429", "551", "601", "Nevine"]
MAP_FILIAIS = {
    "302": 16,
    "429": 17,
    "551": 18,
    "601": 19,
    "Nevine": 20
}
MAP_F3_F7 = {
    "302": 3,
    "429": 4,
    "551": 5,
    "601": 6,
    "Nevine": 7
}

FERIADOS_PADRAO = [
    (1, 1),   # Confraternização Universal
    (21, 4),  # Tiradentes
    (1, 5),   # Dia do Trabalho
    (9, 7),   # Revolução Constitucionalista
    (7, 9),   # Independência do Brasil
    (12, 10), # Nossa Senhora Aparecida
    (2, 11),  # Finados
    (15, 11), # Proclamação da República
    (20, 11), # Dia da Consciência Negra
    (25, 12)  # Natal
]

def carregar_feriados():
    recorrentes = set(FERIADOS_PADRAO)
    especificos = set()
    path = os.path.join(BASE_DIR, "feriados.md")
    if not os.path.exists(path):
        print("feriados.md não encontrado; usando feriados padrão do código.")
        return recorrentes, especificos

    padrao_recorrente = re.compile(r"\b(\d{2})/(\d{2})\b")
    padrao_especifico = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m_especifico = padrao_especifico.search(line)
                if m_especifico:
                    ano, mes, dia = map(int, m_especifico.groups())
                    especificos.add(datetime(ano, mes, dia).date())
                    continue

                m_recorrente = padrao_recorrente.search(line)
                if m_recorrente:
                    dia, mes = map(int, m_recorrente.groups())
                    recorrentes.add((dia, mes))
    except Exception as e:
        print(f"Erro ao ler feriados.md; usando feriados padrão do código: {e}")
    return recorrentes, especificos

FERIADOS_RECORRENTES, FERIADOS_ESPECIFICOS = carregar_feriados()

def is_dia_util(d):
    if d.weekday() >= 5:
        return False
    data = d.date() if hasattr(d, "date") else d
    if data in FERIADOS_ESPECIFICOS:
        return False
    if (d.day, d.month) in FERIADOS_RECORRENTES:
        return False
    return True

def dia_util_anterior(d):
    d = d - timedelta(days=1)
    while not is_dia_util(d):
        d -= timedelta(days=1)
    return d

def proximo_dia_util(d):
    while not is_dia_util(d):
        d += timedelta(days=1)
    return d

def parse_data_aba(nome):
    partes = nome[:10].strip().split(" ")
    if len(partes) != 3:
        return None
    try:
        return datetime(int(partes[2]), int(partes[1]), int(partes[0]))
    except:
        return None

def selecionar_aba_origem(tab_names, hoje):
    melhor_nome = None
    melhor_tab = None
    melhor_data = None
    for nome, tab in tab_names:
        dt = parse_data_aba(nome)
        if dt and dt < hoje and (melhor_data is None or dt > melhor_data):
            melhor_nome = nome
            melhor_tab = tab
            melhor_data = dt
    return melhor_nome, melhor_tab

async def mover_aba_ativa_para_inicio(page):
    try:
        tabs = page.locator('.docs-sheet-tab')
        if await tabs.count() <= 1:
            return

        active_name = (await page.locator('.docs-sheet-active-tab .docs-sheet-tab-name').first.inner_text()).strip()
        active_tab = page.locator('.docs-sheet-active-tab').first
        first_tab = tabs.first
        active_box = await active_tab.bounding_box()
        first_box = await first_tab.bounding_box()
        if not active_box or not first_box:
            print("Não foi possível calcular a posição das abas para mover ao início.")
            return
        if active_box["x"] <= first_box["x"] + 2:
            print("Aba nova já está na primeira posição.")
            return

        print("Movendo aba nova para a primeira posição...")
        await page.mouse.move(
            active_box["x"] + active_box["width"] / 2,
            active_box["y"] + active_box["height"] / 2,
        )
        await page.mouse.down()
        await page.mouse.move(
            max(first_box["x"] + 2, 2),
            first_box["y"] + first_box["height"] / 2,
            steps=25,
        )
        await page.mouse.up()
        await asyncio.sleep(2)

        tab_names = [nome.strip() for nome in await page.locator(".docs-sheet-tab-name").all_inner_texts()]
        if tab_names and tab_names[0] == active_name:
            print("Aba nova movida para a primeira posição.")
            return

        try:
            idx = tab_names.index(active_name)
        except ValueError:
            print("Não foi possível localizar a aba ativa após o arraste.")
            return

        print(f"Arraste não colocou a aba no início; movendo {idx} posição(ões) para a esquerda pelo menu...")
        for i in range(idx):
            if i and i % 25 == 0:
                print(f"  Movimentos feitos: {i}/{idx}")
            await clicar_opcao_menu_aba_ativa(page, ["Mover para a esquerda", "Move left"])

        tab_names = [nome.strip() for nome in await page.locator(".docs-sheet-tab-name").all_inner_texts()]
        if tab_names and tab_names[0] == active_name:
            print("Aba nova está na primeira posição.")
        else:
            print("Aba nova não ficou na primeira posição após a movimentação automática.")
    except Exception as e:
        print(f"Não foi possível mover a aba para o início automaticamente: {e}")

async def clicar_opcao_menu_aba_ativa(page, textos):
    seletores = []
    for texto in textos:
        seletores.extend([
            f'.goog-menuitem:has-text("{texto}"):visible',
            f'.goog-menuitem-content:has-text("{texto}"):visible',
        ])

    async def tentar_clicar_opcao(timeout=3000):
        for seletor in seletores:
            opcao = page.locator(seletor).first
            try:
                await opcao.wait_for(state="visible", timeout=timeout)
                await opcao.click()
                return True
            except:
                pass
        return False

    await page.keyboard.press("Escape")
    await asyncio.sleep(0.3)
    active_tab = page.locator('.docs-sheet-active-tab').first
    await active_tab.hover()
    seta = page.locator('.docs-sheet-active-tab .docs-sheet-tab-dropdown').first
    try:
        await seta.wait_for(state="visible", timeout=5000)
        await seta.click(force=True)
    except:
        await page.locator('.docs-sheet-active-tab .docs-sheet-tab-name').first.click(button='right')
    await asyncio.sleep(1)

    if await tentar_clicar_opcao():
        return True

    await page.keyboard.press("Escape")
    await asyncio.sleep(0.3)
    await page.locator('.docs-sheet-active-tab .docs-sheet-tab-name').first.click(button='right')
    await asyncio.sleep(1)
    if await tentar_clicar_opcao():
        return True

    raise RuntimeError(f"Opção do menu da aba não encontrada: {', '.join(textos)}")

def calcular_datas(data_base=None):
    hoje = (data_base or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    data_inicio = hoje - timedelta(days=2)
    data_fim = hoje + timedelta(days=10)
    
    # Formato para preencher no ERP: dd/mm/yyyy
    str_inicio = data_inicio.strftime("%d/%m/%Y")
    str_fim = data_fim.strftime("%d/%m/%Y")
    
    # A aba base para copiar é a de HOJE
    aba_base = hoje.strftime("%d %m %Y")
    
    return str_inicio, str_fim, aba_base, data_inicio, data_fim

async def esperar_carregamento_erp(page):
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
        await esperar_carregamento_erp(page)
        print("Login ERP concluído.")
        return True
    except Exception as e:
        print(f"Erro no login ERP: {e}")
        return False

async def baixar_relatorio(page, relatorio_id, str_inicio, str_fim, nome_arquivo_saida):
    print(f"\nBaixando relatório {relatorio_id}...")
    
    try:
        await page.goto("https://erp.admsis.com/Home?eng_tela=0117030100", timeout=60000)
    except:
        print("Erro ao acessar URL direta do relatório.")
        return False
        
    await asyncio.sleep(5)
    await esperar_carregamento_erp(page)
    
    # 1. Selecionar o relatório
    try:
        await page.wait_for_selector('select#relatorio', timeout=30000)
        await page.select_option('select#relatorio', relatorio_id)
        await asyncio.sleep(2)
        await esperar_carregamento_erp(page)
    except Exception as e:
        print(f"Erro ao selecionar relatório {relatorio_id}: {e}")
        return False

    # Tipo de Nota Fiscal = Todos (sem filtro)
    # Removido filtro de NF-e para trazer todos os tipos

    # 2. Preencher datas
    print("Preenchendo datas de vencimento...")
    try:
        # A data tem máscara no ERP, então digitamos apenas os números
        str_inicio_num = str_inicio.replace("/", "")
        str_fim_num = str_fim.replace("/", "")
        
        # Limpar os campos via JS para garantir que a máscara não atrapalhe
        await page.evaluate('document.getElementById("data_vencimento_i").value = "";')
        await page.type('input#data_vencimento_i', str_inicio_num, delay=50)
        await asyncio.sleep(1)
        
        await page.evaluate('document.getElementById("data_vencimento_f").value = "";')
        await page.type('input#data_vencimento_f', str_fim_num, delay=50)
        await asyncio.sleep(1)
    except Exception as e:
        print(f"Erro ao preencher datas: {e}")
        return False
        
    # 3. Clicar em Gerar CSV e aguardar o download
    print("Gerando relatório...")
    caminho_salvar = os.path.join(BASE_DIR, nome_arquivo_saida)
    try:
        # Removemos o target='_blank' do formulário para evitar que abra em nova aba e trave o expect_download
        await page.evaluate('document.getElementById("Formulario").removeAttribute("target");')
        await asyncio.sleep(1)
        
        async with page.expect_download(timeout=120000) as download_info:
            await page.click('button#btRelatorioCSV')
        
        download = await download_info.value
        await download.save_as(caminho_salvar)
        print(f"Salvo em: {caminho_salvar}")
    except Exception as e:
        print(f"Erro ao fazer o download do arquivo CSV: {e}")
        return False
        
    return True

def clean_currency(x):
    if isinstance(x, str):
        return float(x.replace('.', '').replace(',', '.'))
    return x

def format_brl(val):
    """Formata número para padrão brasileiro: 1.234,56"""
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalizar_filial_dict(valores):
    normalizado = {}
    for filial, valor in valores.items():
        filial_str = str(int(float(filial))) if isinstance(filial, (int, float)) else str(filial)
        normalizado[filial_str] = valor
    return normalizado

def calcular_dias_alvo(dt_nova, quantidade=3):
    dias = []
    curr = dt_nova + timedelta(days=1)
    while len(dias) < quantidade:
        if is_dia_util(curr):
            dias.append(curr)
        curr += timedelta(days=1)
    return dias

def ler_csv_zip(path):
    df_list = []
    with zipfile.ZipFile(path, 'r') as z:
        for filename in z.namelist():
            if filename.endswith('.csv'):
                with z.open(filename) as f:
                    df_part = pd.read_csv(f, sep=';', encoding='latin-1', on_bad_lines='skip')
                    df_list.append(df_part)
    if not df_list:
        return pd.DataFrame()
    return pd.concat(df_list, ignore_index=True)

def somar_zip_por_data(path, date_col, value_col, filial_col, saldo_col, data_obj):
    try:
        df = ler_csv_zip(path)
        if df.empty:
            return {}
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df[value_col] = df[value_col].apply(clean_currency).fillna(0)
        df[saldo_col] = df[saldo_col].apply(clean_currency).fillna(0)
        df = df[df[saldo_col] > 0]
        mask = df[date_col] == pd.Timestamp(data_obj)
        valores = df[mask].groupby(filial_col)[value_col].sum().to_dict()
        return normalizar_filial_dict(valores)
    except Exception as e:
        print(f"Erro ao somar {path} em {data_obj.strftime('%d/%m/%Y')}: {e}")
        return {}

def somar_zip_por_data_ajustada(path, date_col, value_col, filial_col, saldo_col, data_obj, ajuste_fn):
    try:
        df = ler_csv_zip(path)
        if df.empty:
            return {}
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df[value_col] = df[value_col].apply(clean_currency).fillna(0)
        df[saldo_col] = df[saldo_col].apply(clean_currency).fillna(0)
        df = df[df[saldo_col] > 0].copy()
        df[date_col] = df[date_col].apply(ajuste_fn)
        mask = df[date_col] == pd.Timestamp(data_obj)
        valores = df[mask].groupby(filial_col)[value_col].sum().to_dict()
        return normalizar_filial_dict(valores)
    except Exception as e:
        print(f"Erro ao somar {path} com ajuste em {data_obj.strftime('%d/%m/%Y')}: {e}")
        return {}

def valor_filial(valores, filial):
    return valores.get(filial, 0)

def montar_atualizacoes_planilha(dt_nova, dados):
    dias_alvo = calcular_dias_alvo(dt_nova)
    file_pagar = os.path.join(BASE_DIR, "titulos a pagar.zip")
    file_receber = os.path.join(BASE_DIR, "titulos a receber.zip")

    dia_seguinte_b15 = dias_alvo[0].strftime("%d/%m")
    dia_seguinte_f15 = dias_alvo[1].strftime("%d/%m")
    dia_seguinte_j15 = dias_alvo[2].strftime("%d/%m")

    atualizacoes = [
        ("E1", dt_nova.strftime("%d/%m/%Y")),
        ("B15", dt_nova.strftime("%d/%m")),
        ("C15", dia_seguinte_b15),
        ("D15", f"{dt_nova.strftime('%d/%m')} a {dias_alvo[0].strftime('%d/%m')}"),
        ("F15", dias_alvo[0].strftime("%d/%m")),
        ("G15", dia_seguinte_f15),
        ("H15", f"{dias_alvo[0].strftime('%d/%m')} a {dias_alvo[1].strftime('%d/%m')}"),
        ("J15", dias_alvo[1].strftime("%d/%m")),
        ("K15", dia_seguinte_j15),
        ("L15", f"{dias_alvo[1].strftime('%d/%m')} a {dias_alvo[2].strftime('%d/%m')}"),
        ("C13", dia_seguinte_b15),
        ("F13", dias_alvo[0].strftime("%d/%m")),
        ("G13", dia_seguinte_f15),
        ("J13", dias_alvo[1].strftime("%d/%m")),
        ("K13", dia_seguinte_j15),
    ]

    valores_f = somar_zip_por_data_ajustada(file_receber, 'ttr_data_vencimento', 'ttr_valor_titulo', 'fil_descricao', 'ttr_saldo', dias_alvo[0], ajustar_data_receber)
    valores_g = somar_zip_por_data(file_pagar, 'ttp_data_vencimento', 'ttp_valor_titulo', 'fil_descricao', 'ttp_saldo', dias_alvo[1])
    valores_j = somar_zip_por_data_ajustada(file_receber, 'ttr_data_vencimento', 'ttr_valor_titulo', 'fil_descricao', 'ttr_saldo', dias_alvo[1], ajustar_data_receber)
    valores_k = somar_zip_por_data(file_pagar, 'ttp_data_vencimento', 'ttp_valor_titulo', 'fil_descricao', 'ttp_saldo', dias_alvo[2])
    valores_c = somar_zip_por_data(file_pagar, 'ttp_data_vencimento', 'ttp_valor_titulo', 'fil_descricao', 'ttp_saldo', dias_alvo[0])
    valores_m = somar_zip_por_data_ajustada(file_receber, 'ttr_data_vencimento', 'ttr_valor_titulo', 'fil_descricao', 'ttr_saldo', dt_nova, ajustar_data_receber)

    for filial, linha in MAP_FILIAIS.items():
        atualizacoes.extend([
            (f"F{linha}", valor_filial(valores_f, filial)),
            (f"G{linha}", valor_filial(valores_g, filial)),
            (f"J{linha}", valor_filial(valores_j, filial)),
            (f"K{linha}", valor_filial(valores_k, filial)),
            (f"C{linha}", valor_filial(valores_c, filial)),
            (f"M{linha}", valor_filial(valores_m, filial)),
        ])

    valores_pagar_hoje = dados.get(dt_nova.strftime("%d/%m/%Y"), {}).get('pagar', {})
    for filial, linha in MAP_F3_F7.items():
        atualizacoes.append((f"F{linha}", valor_filial(valores_pagar_hoje, filial)))

    return atualizacoes, dias_alvo

def formatar_valor_celula(valor):
    if isinstance(valor, (int, float)):
        return str(round(valor, 2)).replace('.', ',')
    return str(valor)

async def preencher_celula(page, celula, valor, delay=0.5):
    await page.keyboard.press("F5")
    await asyncio.sleep(delay)
    await page.keyboard.type(celula)
    await page.keyboard.press("Enter")
    await asyncio.sleep(delay)
    await page.keyboard.type(formatar_valor_celula(valor))
    await page.keyboard.press("Enter")
    await asyncio.sleep(delay)

async def preencher_celulas(page, atualizacoes):
    for celula, valor in atualizacoes:
        await preencher_celula(page, celula, valor)
        print(f"    {celula}: {formatar_valor_celula(valor)}")

def imprimir_dry_run(dt_nova, atualizacoes, dias_alvo):
    print("\nDRY-RUN: nenhuma alteração será feita na planilha.")
    print(f"Data da previsão: {dt_nova.strftime('%d/%m/%Y')}")
    print("Dias alvo:", ", ".join(d.strftime("%d/%m/%Y") for d in dias_alvo))
    print(f"Células calculadas: {len(atualizacoes)}")
    for celula, valor in atualizacoes:
        print(f"  {celula} = {formatar_valor_celula(valor)}")

def validar_mapa_atualizacoes(atualizacoes):
    obrigatorias = {"E1", "C13", "G13", "K13", "B15", "C15", "G15", "K15", "F16", "C16", "M16", "F3"}
    vistos = {}
    duplicadas = []
    vazias = []
    for celula, valor in atualizacoes:
        if celula in vistos:
            duplicadas.append(celula)
        vistos[celula] = valor
        if valor is None or valor == "":
            vazias.append(celula)

    faltantes = sorted(obrigatorias - set(vistos))
    if duplicadas or faltantes or vazias:
        partes = []
        if faltantes:
            partes.append(f"faltantes: {', '.join(faltantes)}")
        if duplicadas:
            partes.append(f"duplicadas: {', '.join(sorted(set(duplicadas)))}")
        if vazias:
            partes.append(f"vazias: {', '.join(vazias)}")
        raise ValueError("Mapa de preenchimento inválido (" + "; ".join(partes) + ")")

    print(f"Validação local OK: {len(atualizacoes)} células, sem duplicidades críticas.")

def ajustar_data_receber(d):
    """Finais de semana/Feriados → próximo dia útil."""
    if pd.isna(d):
        return d
    if not is_dia_util(d):
        return proximo_dia_util(d)
    return d

def ajustar_data_pagar(d):
    """Finais de semana/Feriados → dia útil anterior."""
    if pd.isna(d):
        return d
    if not is_dia_util(d):
        return dia_util_anterior(d)
    return d

def processar_csvs(d_inicio, d_fim):
    print("\nProcessando arquivos zipados...")
    file_pagar = os.path.join(BASE_DIR, "titulos a pagar.zip")
    file_receber = os.path.join(BASE_DIR, "titulos a receber.zip")
    
    if not os.path.exists(file_pagar) or not os.path.exists(file_receber):
        print("Arquivos ZIP não encontrados. Certifique-se de que o download funcionou.")
        return {}
    
    def get_csv_totals_sem_ajuste(d_inicio, d_fim):
        """Busca valores originais sem ajuste de data para 09-11/05"""
        import zipfile
        try:
            df_list = []
            with zipfile.ZipFile(file_receber, 'r') as z:
                for filename in z.namelist():
                    if filename.endswith('.csv'):
                        with z.open(filename) as f:
                            df_part = pd.read_csv(f, sep=';', encoding='latin-1', on_bad_lines='skip')
                            df_list.append(df_part)
            df = pd.concat(df_list, ignore_index=True)
            
            df['ttr_data_vencimento'] = pd.to_datetime(df['ttr_data_vencimento'], errors='coerce')
            df['ttr_valor_titulo'] = df['ttr_valor_titulo'].apply(clean_currency).fillna(0)
            df['ttr_saldo'] = df['ttr_saldo'].apply(clean_currency).fillna(0)
            
            # Filtrar apenas 09, 10 e 11/05 com saldo > 0 - SEM AJUSTE
            datas = [pd.Timestamp('2026-05-09'), pd.Timestamp('2026-05-10'), pd.Timestamp('2026-05-11')]
            mask = (df['ttr_data_vencimento'].isin(datas)) & (df['ttr_saldo'] > 0)
            df_filtered = df[mask].copy()
            
            # Agrupar por filial
            totals = df_filtered.groupby('fil_descricao')['ttr_valor_titulo'].sum().to_dict()
            return totals
        except Exception as e:
            print(f"Erro ao buscar dados originais: {e}")
            return {}
    
    # Buscar valores originais para M (sem ajuste)
    valores_originais = get_csv_totals_sem_ajuste(d_inicio, d_fim)
    print(f"Valores originais 09-11/05 (para M): {valores_originais}")
        
    def get_csv_totals(path, date_col, value_col, filial_col, saldo_col, ajuste_fn=None):
        import zipfile
        try:
            df_list = []
            with zipfile.ZipFile(path, 'r') as z:
                for filename in z.namelist():
                    if filename.endswith('.csv'):
                        with z.open(filename) as f:
                            df_part = pd.read_csv(f, sep=';', encoding='latin-1', on_bad_lines='skip')
                            df_list.append(df_part)
            if not df_list:
                return {}
            df = pd.concat(df_list, ignore_index=True)
            
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df[value_col] = df[value_col].apply(clean_currency).fillna(0)
            df[saldo_col] = df[saldo_col].apply(clean_currency).fillna(0)
            
            # Filtra o período e saldo > 0
            mask = (df[date_col] >= pd.Timestamp(d_inicio)) & (df[date_col] <= pd.Timestamp(d_fim)) & (df[saldo_col] > 0)
            df_filtered = df[mask].copy()
            
            # Ajuste de datas conforme regra de dia da semana
            if ajuste_fn:
                df_filtered[date_col] = df_filtered[date_col].apply(ajuste_fn)
            
            # Agrupa por Data (ajustada) e Filial
            df_filtered['data_str'] = df_filtered[date_col].dt.strftime('%d/%m/%Y')
            totals = df_filtered.groupby(['data_str', filial_col])[value_col].sum().to_dict()
            return totals
        except Exception as e:
            print(f"Erro processando {path}: {e}")
            return {}

    totals_receber = get_csv_totals(file_receber, 'ttr_data_vencimento', 'ttr_valor_titulo', 'fil_descricao', 'ttr_saldo', ajuste_fn=ajustar_data_receber)
    totals_pagar   = get_csv_totals(file_pagar,   'ttp_data_vencimento', 'ttp_valor_titulo', 'fil_descricao', 'ttp_saldo', ajuste_fn=ajustar_data_pagar)
    
    # Estruturar o dicionário final
    # formato: dados['29/04/2026']['receber']['302']
    dados_organizados = {}
    current_date = d_inicio
    while current_date <= d_fim:
        d_str = current_date.strftime('%d/%m/%Y')
        dados_organizados[d_str] = {'receber': {}, 'pagar': {}}
        
        # Preencher receber
        for key, val in totals_receber.items():
            if key[0] == d_str:
                filial_str = str(int(float(key[1]))) if isinstance(key[1], (int, float)) else str(key[1])
                dados_organizados[d_str]['receber'][filial_str] = val
                
        # Preencher pagar
        for key, val in totals_pagar.items():
            if key[0] == d_str:
                filial_str = str(int(float(key[1]))) if isinstance(key[1], (int, float)) else str(key[1])
                dados_organizados[d_str]['pagar'][filial_str] = val
                
        current_date += timedelta(days=1)
        
    print("Processamento concluído.")
    return dados_organizados, valores_originais

async def atualizar_planilha(page, dados, valores_originais, data_base=None):
    print("\nAtualizando Google Sheets...")
    
    # 1. Abrir planilha
    try:
        await page.goto(PLANILHA_URL, timeout=60000, wait_until="domcontentloaded")
    except:
        pass
    await asyncio.sleep(5)
    
    # Função auxiliar para verificar se a planilha realmente carregou
    def is_sheet_loaded():
        return page.url.startswith("https://docs.google.com") and "accounts.google.com" not in page.url

    # Lidar com login do Google se necessário
    if "accounts.google.com" in page.url:
        print("Login do Google detectado. Inserindo credenciais...")
        try:
            # 0. Tela "Choose an account" / Selecionar conta existente
            if "accountchooser" in page.url or await page.locator('text=/Choose an account|Escolha uma conta/i').count() > 0:
                print("Tela 'Escolha uma conta' detectada. Selecionando conta salva...")
                conta_existente = page.locator('div[data-identifier], div[data-email], [role="link"]:has-text("@"), li:has-text("@"), div:has-text("financeiro@nevine")').first
                try:
                    if await conta_existente.is_visible(timeout=5000):
                        await conta_existente.click()
                        await asyncio.sleep(4)
                        print("Conta selecionada. Aguardando tela de senha...")
                except Exception as e_acc:
                    print(f"Aviso ao selecionar conta: {e_acc}")

            # Tela "Confirme que é você" (confirmidentifier)
            if "confirmidentifier" in page.url:
                print("Tela 'Confirme que é você' detectada. Clicando em Avançar...")
                try:
                    avancar = page.locator('button:has-text("Avançar"), button:has-text("Next"), #identifierNext, #next').first
                    if await avancar.is_visible(timeout=8000):
                        await avancar.click()
                        await asyncio.sleep(4)
                        print("Avançar clicado. Aguardando tela de senha...")
                except Exception as e_avancar:
                    print(f"Aviso ao clicar em Avançar: {e_avancar}")

            # Tela de email: usar seletores robustos para campo visível
            email_selector = 'input[type="email"]:not([aria-hidden="true"]), #identifierId'
            email_field = page.locator(email_selector).first
            try:
                if await email_field.is_visible(timeout=5000):
                    await email_field.fill(GOOGLE_USER)
                    await page.click('#identifierNext')
                    await asyncio.sleep(4)
                    print("Email inserido. Aguardando tela de senha...")
            except Exception as e_email:
                print(f"Campo de email não visível (pulando): {e_email}")

            # Tela de senha: usar seletores robustos
            password_selector = 'input[type="password"], input[name="Passwd"]'
            password_field = page.locator(password_selector).first
            try:
                await password_field.wait_for(state="visible", timeout=20000)
                await password_field.fill(GOOGLE_PASS)
                await page.click('#passwordNext')
                print("Senha inserida. Aguardando redirecionamento...")
                await asyncio.sleep(5)
            except Exception:
                print("Aviso: Tela de senha não encontrada ou verificação manual/2FA solicitada pelo Google.")

            # Aguardar login manual / redirecionamento se não redirecionou automaticamente para a planilha
            if not is_sheet_loaded():
                print("Aguardando redirecionamento ou confirmação no navegador (até 90 segundos)...")
                for _ in range(90):
                    if is_sheet_loaded():
                        print("Login e redirecionamento detectados com sucesso!")
                        break
                    await asyncio.sleep(1)

        except Exception as e:
            print(f"Erro no login do Google: {e}")
    else:
        print("Sessão do Google já ativa ou não é necessário login.")
    
    # Espera adicional para garantir que a planilha carregue completamente após o login
    await asyncio.sleep(5)
    
    # Tentar recarregar a planilha se já estiver na URL do Docs
    if is_sheet_loaded():
        print("Planilha carregando...")
        try:
            await page.reload(timeout=120000, wait_until="domcontentloaded")
        except:
            pass
        await asyncio.sleep(5)
    
    # Esperar planilha carregar
    try:
        await page.wait_for_selector(".docs-sheet-tab-name", timeout=120000)
    except:
        try:
            await page.screenshot(path="erro_planilha.png")
            print(f"Print salvo em erro_planilha.png. URL atual: {page.url[:200]}")
        except:
            pass
        print("Planilha não carregou a tempo.")
        return False
        
    await asyncio.sleep(5)
    
    # 2. Calcular hoje e selecionar a aba de origem mais recente antes de hoje.
    # Mesmo quando ontem foi feriado, se a aba existir ela deve ser usada como base visual.
    hoje = (data_base or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    aba_hoje = hoje.strftime("%d %m %Y")
    
    print(f"Procurando a aba de hoje '{aba_hoje}' ou a base anterior para duplicar.")
    
    # 3. Encontrar todas as abas
    tabs = await page.query_selector_all(".docs-sheet-tab-name")
    
    aba_origem_tab = None
    aba_hoje_tab = None
    tab_names = []
    
    for tab in tabs:
        nome = await tab.inner_text()
        nome = nome.strip()
        print(f"  Aba encontrada: '{nome}'")
        tab_names.append((nome, tab))
        if nome == aba_hoje or nome.startswith(aba_hoje):
            aba_hoje_tab = tab
    
    aba_origem, aba_origem_tab = selecionar_aba_origem(tab_names, hoje)
    if aba_origem_tab is None:
        print("Nenhuma aba anterior disponível encontrada.")
        return False
    
    print(f"Aba origem encontrada: '{aba_origem}'")
    
    # 4. Se a aba de hoje já existe, preencher por cima. Se não existe, duplicar a base anterior.
    if aba_hoje_tab is not None:
        print(f"Aba '{aba_hoje}' já existe. Abrindo para sobrescrever os dados de hoje...")
        await aba_hoje_tab.click()
        await asyncio.sleep(2)
        await mover_aba_ativa_para_inicio(page)
    else:
        # 6. Ativar a aba origem e duplicar
        print(f"Ativando aba '{aba_origem}'...")
        await aba_origem_tab.click()
        await asyncio.sleep(2)
        print(f"Duplicando aba '{aba_origem}'...")
        await clicar_opcao_menu_aba_ativa(page, ["Duplicar", "Duplicate"])
        print("Aba duplicada. Aguardando processamento do Google Sheets...")
        await asyncio.sleep(8)

        # Tentar fechar modal se existir (Forçando remoção via JS)
        try:
            await page.evaluate('''
                document.querySelectorAll(".modal-dialog-bg, .modal-dialog").forEach(el => el.remove());
            ''')
            await asyncio.sleep(1)
        except:
            pass

        await asyncio.sleep(2)

        # 7. Renomear a aba duplicada para hoje
        print(f"Renomeando aba para '{aba_hoje}'...")
        await page.wait_for_selector('.docs-sheet-active-tab .docs-sheet-tab-name', state='visible', timeout=15000)
        nova_aba_tab = page.locator('.docs-sheet-active-tab .docs-sheet-tab-name')
        try:
            await nova_aba_tab.dblclick()
        except Exception:
            # fallback: right-click then choose rename
            await nova_aba_tab.click(button='right')
            await asyncio.sleep(0.5)
            renomear_opt = page.locator('.goog-menuitem:has-text("Renomear"), .goog-menuitem:has-text("Rename")').first
            await renomear_opt.click()
            await asyncio.sleep(0.5)
        # Clear existing name and type new name. Google Sheets on macOS needs Meta+A.
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Meta+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(aba_hoje)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        print(f"Aba renomeada para '{aba_hoje}'.")
        await mover_aba_ativa_para_inicio(page)
    
    dt_nova = hoje
    
    # 8. Preencher Cabeçalhos e Dados (Apenas os 3 próximos dias úteis)
    print(f"Iniciando preenchimento dos dados para a data {aba_hoje} via interface (Atalho F5)...")
    atualizacoes, dias_alvo = montar_atualizacoes_planilha(dt_nova, dados)
    validar_mapa_atualizacoes(atualizacoes)
    print(f"Preenchendo {len(atualizacoes)} células calculadas.")
    await preencher_celulas(page, atualizacoes)
    print("Preenchimento concluído.")
    return True
    

def enviar_aviso_discord(url):
    # Read webhook URL from environment, stripping any surrounding whitespace
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Webhook do Discord não configurado.")
        return
    webhook_url = webhook_url.strip()
    data = {"content": "✅ A previsão financeira de hoje foi gerada com sucesso e a planilha oficial foi atualizada!"}
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/nevine, 1.0)"
        },
    )
    try:
        urllib.request.urlopen(req)
        print("Notificação enviada ao Discord.")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("Erro ao enviar notificação: webhook inválido ou sem permissões (403). Verifique a URL.")
        else:
            print(f"Erro ao enviar notificação para o Discord: {e}")
    except Exception as e:
        print(f"Erro ao enviar notificação para o Discord: {e}")

def parse_args():
    parser = argparse.ArgumentParser(description="Automação de previsão financeira")
    parser.add_argument("--dry-run", action="store_true", help="Calcula e imprime as células sem abrir ERP ou Google Sheets")
    parser.add_argument("--data", help="Data base no formato YYYY-MM-DD; útil para dry-run e reprocessamentos controlados")
    parser.add_argument("--skip-erp", action="store_true", help="Pula o download do ERP e usa os ZIPs já existentes para preencher a planilha")
    parser.add_argument("--visible", action="store_true", help="Abre o navegador visível para inspeção ou login manual do Google")
    return parser.parse_args()

def parse_data_base(data_str):
    if not data_str:
        return None
    return datetime.strptime(data_str, "%Y-%m-%d")

async def executar_previsao(data_base_str=None, skip_erp=False, dry_run=False, visible=False) -> dict:
    print("Iniciando Robô de Previsão...")
    data_base = parse_data_base(data_base_str) if isinstance(data_base_str, str) else data_base_str
    str_inicio, str_fim, aba_base, d_inicio, d_fim = calcular_datas(data_base)
    hoje = (data_base or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    aba_hoje = hoje.strftime("%d %m %Y")

    print(f"Período de extração: {str_inicio} até {str_fim}")

    if dry_run:
        dados, valores_originais = processar_csvs(d_inicio, d_fim)
        data_previsao = data_base or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        atualizacoes, dias_alvo = montar_atualizacoes_planilha(data_previsao, dados)
        validar_mapa_atualizacoes(atualizacoes)
        imprimir_dry_run(data_previsao, atualizacoes, dias_alvo)
        return {
            "sucesso": True,
            "dry_run": True,
            "periodo": f"{str_inicio} até {str_fim}",
            "aba": aba_hoje,
            "celulas": len(atualizacoes)
        }

    import platform
    if platform.system() == "Darwin":
        local_app_data = os.path.expanduser("~/Library/Application Support")
    elif platform.system() == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        local_app_data = os.path.expanduser("~/.local/share")
    user_data_dir = os.path.join(local_app_data, "Automacao_Previsao", "sessao_nova")
    os.makedirs(user_data_dir, exist_ok=True)

    browser_args = ["--start-maximized"] if visible else []
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            channel="chrome",
            headless=not visible,
            viewport={"width": 1366, "height": 768},
            args=browser_args,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            # 1. ERP
            if skip_erp:
                print("--skip-erp ativo: pulando download do ERP e usando ZIPs existentes.")
            else:
                sucesso = await login_erp(page)
                if not sucesso:
                    return {"sucesso": False, "mensagem": "Falha no login do ERP ADMSIS."}
                print("Baixando Títulos a Receber (2004)...")
                await baixar_relatorio(page, "2004", str_inicio, str_fim, "titulos a receber.zip")

                print("Baixando Títulos a Pagar (2015)...")
                await baixar_relatorio(page, "2015", str_inicio, str_fim, "titulos a pagar.zip")

            # 2. Pandas
            dados, valores_originais = processar_csvs(d_inicio, d_fim)

            # 3. Google Sheets
            sucesso_planilha = await atualizar_planilha(page, dados, valores_originais, data_base=data_base)
            if sucesso_planilha is not False:
                enviar_aviso_discord(PLANILHA_URL)

            print("\nProcesso finalizado.")
            return {
                "sucesso": True,
                "periodo": f"{str_inicio} até {str_fim}",
                "aba": aba_hoje,
                "planilha_url": PLANILHA_URL,
                "mensagem": f"Previsão gerada com sucesso na aba '{aba_hoje}'."
            }
        finally:
            await context.close()

async def main():
    args = parse_args()
    res = await executar_previsao(data_base_str=args.data, skip_erp=args.skip_erp, dry_run=args.dry_run, visible=args.visible)
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
