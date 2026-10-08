import re
from datetime import datetime, timedelta, time, date
from collections import defaultdict
import glob

def parse_iso_dt(s: str) -> datetime:
    clean = s.strip()
    if len(clean) >= 24 and (clean[-5] in ('+', '-')) and clean[-3] != ':':
        clean = clean[:-2] + ':' + clean[-2:]
    try:
        return datetime.fromisoformat(clean)
    except Exception:
        return datetime.strptime(clean[:19], '%Y-%m-%dT%H:%M:%S')

def encontrar_mais_recente():
    arquivos = glob.glob("00004004330216717*.txt")
    if not arquivos:
        print("Nenhum arquivo de marcações encontrado")
        return None
    return max(arquivos, key=lambda f: datetime.fromtimestamp(__import__('os').path.getmtime(f)))

def parse_marcacoes(arquivo):
    """Parse marcacoes lines, return list of dicts"""
    registros = []
    with open(arquivo, 'r', encoding='latin-1') as f:
        linhas = f.read().split('\n')
    
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith('0000000000') or linha.startswith('9999999999'):
            continue
        if linha.startswith('AIYFXMEL') or linha.startswith('AOV2ERIR') or linha.startswith('ABUAJ7ZJ'):
            continue
        
        # Try to extract sequence + timestamp + ID (with optional prefix A/I)
        # Normal: seq(10) + ts(25) + id(11)
        m = re.match(r'(\d{10})(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4})(\d{11})', linha)
        if m:
            registros.append({'seq': m.group(1), 'ts': m.group(2), 'emp_id': m.group(3), 'nome': None})
            continue
        
        # A prefix: seq + ts + A + id(11) + name
        m = re.match(r'(\d{10})(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4})A(\d{11})', linha)
        if m:
            registros.append({'seq': m.group(1), 'ts': m.group(2), 'emp_id': m.group(3), 'nome': None})
            continue
        
        # I prefix (biostar): seq + ts + I + id(11) + name
        m = re.match(r'(\d{10})(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4})I(\d{11})', linha)
        if m:
            registros.append({'seq': m.group(1), 'ts': m.group(2), 'emp_id': m.group(3), 'nome': None})
            continue
        
        # Skip malformed/truncated lines
        if re.match(r'\d{10}\d{4}-\d{2}-\d{2}T', linha) and len(linha) < 45:
            continue
    
    return registros

def normalizar_id(emp_id, colaboradores):
    """Normaliza ID de 11 para 12 digitos"""
    emp_id = emp_id.strip()
    for cid in colaboradores:
        if cid.endswith(emp_id) or cid.lstrip('0') == emp_id.lstrip('0'):
            return cid
    return None

def carregar_colaboradores(arquivo):
    cols = {}
    with open(arquivo, 'r', encoding='latin-1') as f:
        for linha in f:
            m = re.match(r'1\+1\+I\[(\d+)\[([^\[]+)', linha)
            if m:
                cid, nome = m.groups()
                cols[cid] = nome.strip()
    return cols

def gerar_html(registros, colaboradores, horario_ref=time(8, 0), tolerancia_min=5, data_inicio=None, data_fim=None, filtro_nomes=None):
    horario_limite = datetime.combine(datetime.today(), horario_ref) + timedelta(minutes=tolerancia_min)
    horario_limite = horario_limite.time()
    _tol = tolerancia_min  # used in atraso calc
    
    col_marcacoes = defaultdict(list)
    nao_encontrados = set()
    
    for reg in registros:
        cid = normalizar_id(reg['emp_id'], colaboradores)
        if not cid:
            nao_encontrados.add(reg['emp_id'])
            continue
        try:
            dt = parse_iso_dt(reg['ts'])
            reg['datetime'] = dt
        except:
            continue
        if data_inicio and dt.date() < data_inicio:
            continue
        if data_fim and dt.date() > data_fim:
            continue
        if filtro_nomes and colaboradores.get(cid, '').lower() not in [n.lower() for n in filtro_nomes]:
            continue
        col_marcacoes[cid].append(reg)
    
    for cid in col_marcacoes:
        col_marcacoes[cid].sort(key=lambda r: r['datetime'])
    
    total_cols = len(colaboradores)
    total_marc = len(registros) - len(nao_encontrados)
    
    # Collect all days data
    dias_data = []
    atrasos_linhas = ""
    total_atrasos = 0
    dias_4 = 0
    dias_2 = 0
    dias_outros = 0
    
    for cid in sorted(colaboradores.keys()):
        nome = colaboradores[cid]
        if cid not in col_marcacoes or not col_marcacoes[cid]:
            continue
        dias = defaultdict(list)
        for reg in col_marcacoes[cid]:
            dia = reg['datetime'].date()
            dias[dia].append(reg['datetime'])
        for dia in sorted(dias.keys()):
            horarios = sorted(dias[dia])
            entrada = horarios[0]
            saida = horarios[-1] if len(horarios) > 1 else None
            
            total_seg = 0
            for i in range(0, len(horarios)-1, 2):
                if i+1 < len(horarios):
                    total_seg += (horarios[i+1] - horarios[i]).total_seconds()
            horas = int(total_seg // 3600)
            mins = int((total_seg % 3600) // 60)
            
            eh_atraso = entrada.time() > horario_limite
            if eh_atraso:
                total_atrasos += 1
            
            qtd = len(horarios)
            if qtd == 4:
                dias_4 += 1
            elif qtd == 2:
                dias_2 += 1
            else:
                dias_outros += 1
            
            incompleto = qtd < 4
            cls = 'atraso' if eh_atraso else ('incompleto' if incompleto else '')
            
            # Split times for 4-markings view
            m1 = horarios[0].strftime('%H:%M') if len(horarios) > 0 else '-'
            m2 = horarios[1].strftime('%H:%M') if len(horarios) > 1 else '-'
            m3 = horarios[2].strftime('%H:%M') if len(horarios) > 2 else '-'
            m4 = horarios[3].strftime('%H:%M') if len(horarios) > 3 else '-'
            
            dias_data.append({
                'nome': nome, 'cid': cid, 'dia': dia,
                'qtd': qtd, 'cls': cls,
                'entrada': entrada, 'saida': saida,
                'horas': horas, 'mins': mins,
                'm1': m1, 'm2': m2, 'm3': m3, 'm4': m4,
                'eh_atraso': eh_atraso
            })
            
            # Atraso line
            if eh_atraso:
                ref_dt = datetime.combine(entrada.date(), horario_ref)
                if entrada.tzinfo:
                    ref_dt = ref_dt.replace(tzinfo=entrada.tzinfo)
                diff_min = int((entrada - ref_dt).total_seconds() / 60)
                atrasos_linhas += f"""<tr>
                    <td>{nome}</td>
                    <td>{dia}</td>
                    <td class="atraso">{entrada.strftime('%H:%M')}</td>
                    <td>{saida.strftime('%H:%M') if saida else '-'}</td>
                    <td>{diff_min} min</td>
                </tr>"""
    
    # Build main table
    linhas = ""
    linhas_4 = ""
    for d in dias_data:
        h_str = f"{d['horas']:02d}:{d['mins']:02d}"
        linhas += f"""<tr class="{d['cls']}">
            <td>{d['nome']}</td>
            <td>{d['dia']}</td>
            <td>{d['entrada'].strftime('%H:%M')}</td>
            <td>{d['saida'].strftime('%H:%M') if d['saida'] else '-'}</td>
            <td>{h_str}</td>
            <td>{d['qtd']}</td>
            <td>{d['m1']}</td>
            <td>{d['m2']}</td>
            <td>{d['m3']}</td>
            <td>{d['m4']}</td>
        </tr>"""
        if d['qtd'] == 4:
            linhas_4 += f"""<tr class="{d['cls']}">
                <td>{d['nome']}</td>
                <td>{d['dia']}</td>
                <td>{d['m1']}</td>
                <td>{d['m2']}</td>
                <td>{d['m3']}</td>
                <td>{d['m4']}</td>
                <td>{h_str}</td>
            </tr>"""
    
    qtd_col_com_marc = len(col_marcacoes)
    qtd_col_sem_marc = total_cols - qtd_col_com_marc
    
    nome_dispositivo = sys.argv[1].upper()
    periodo_str = f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}" if data_inicio and data_fim else f"22/06/2026 a 21/07/2026"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório de Ponto - {nome_dispositivo}</title>
<style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; color: #333; }}
    h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
    h2 {{ color: #2c3e50; margin-top: 30px; }}
    .cards {{ display: flex; gap: 15px; flex-wrap: wrap; margin: 20px 0; }}
    .card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); flex: 1; min-width: 140px; text-align: center; }}
    .card .numero {{ font-size: 2em; font-weight: bold; color: #3498db; }}
    .card .rotulo {{ font-size: 0.85em; color: #7f8c8d; margin-top: 5px; }}
    .card.alerta .numero {{ color: #e74c3c; }}
    .card.aviso .numero {{ color: #f39c12; }}
    .card.ok .numero {{ color: #27ae60; }}
    table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin: 15px 0; }}
    th {{ background: #3498db; color: white; padding: 10px 12px; text-align: left; font-weight: 600; font-size: 0.85em; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 0.85em; }}
    tr:hover {{ background: #f0f7ff; }}
    .atraso {{ background: #FFB6C1 !important; }}
    .incompleto {{ background: #FFF3CD !important; }}
    .footer {{ text-align: center; color: #95a5a6; margin-top: 40px; font-size: 0.85em; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; }}
    .badge-pink {{ background: #FFB6C1; color: #800; }}
    .badge-yellow {{ background: #FFF3CD; color: #856404; }}
    .badge-green {{ background: #D4EDDA; color: #155724; }}
</style>
</head>
<body>
<h1>Relatório de Ponto - {nome_dispositivo}</h1>
<p><strong>Dispositivo:</strong> {nome_dispositivo} | <strong>Período:</strong> {periodo_str} | <strong>Gerado em:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}{f' | <strong>Filtro:</strong> {", ".join(filtro)}' if filtro else ''}</p>
<p><strong>Referência:</strong> Entrada até {horario_ref.strftime('%H:%M')} (tolerância de {tolerancia_min} min) | Atraso: após {horario_limite.strftime('%H:%M')}</p>

<div class="cards">
    <div class="card"><div class="numero">{total_cols}</div><div class="rotulo">Colaboradores</div></div>
    <div class="card"><div class="numero">{qtd_col_com_marc}</div><div class="rotulo">Com Marcações</div></div>
    <div class="card"><div class="numero">{qtd_col_sem_marc}</div><div class="rotulo">Sem Marcações</div></div>
    <div class="card"><div class="numero">{total_marc}</div><div class="rotulo">Total Marcações</div></div>
    <div class="card alerta"><div class="numero">{total_atrasos}</div><div class="rotulo">Atrasos (>5min)</div></div>
    <div class="card ok"><div class="numero">{dias_4}</div><div class="rotulo">Dias c/ 4 marcações</div></div>
    <div class="card aviso"><div class="numero">{dias_2}</div><div class="rotulo">Dias c/ 2 marcações</div></div>
    <div class="card alerta"><div class="numero">{dias_outros}</div><div class="rotulo">Dias c/ outras</div></div>
</div>

<h2>Atrasos (>{tolerancia_min} min) <span class="badge badge-pink">{total_atrasos}</span></h2>
<table><thead><tr><th>Colaborador</th><th>Data</th><th>Entrada</th><th>Saída</th><th>Atraso</th></tr></thead><tbody>
{atrasos_linhas if atrasos_linhas else '<tr><td colspan="5" style="text-align:center;color:#999">Nenhum atraso registrado</td></tr>'}
</tbody></table>

<h2>Dias com 4 Marcações <span class="badge badge-green">{dias_4}</span></h2>
<p style="color:#666;font-size:0.9em">Entrada → Almoço → Volta → Saída</p>
<table><thead><tr><th>Colaborador</th><th>Data</th><th>Entrada</th><th>Almoço</th><th>Volta</th><th>Saída</th><th>Total</th></tr></thead><tbody>
{linhas_4 if linhas_4 else '<tr><td colspan="7" style="text-align:center;color:#999">Nenhum dia com 4 marcações</td></tr>'}
</tbody></table>

<h2>Jornada Completa</h2>
<p style="color:#666;font-size:0.9em"><span class="badge badge-pink">Rosa</span> = atraso &nbsp; <span class="badge badge-yellow">Amarelo</span> = &lt;4 marcações (incompleto)</p>
<table><thead><tr><th>Colaborador</th><th>Data</th><th>Entrada</th><th>Saída</th><th>Horas</th><th>Reg</th><th>M1</th><th>M2</th><th>M3</th><th>M4</th></tr></thead><tbody>
{linhas}
</tbody></table>

<div class="footer">Relatório gerado automaticamente a partir de {__import__('os').path.basename(arquivo_marc)}</div>
</body></html>"""
    
    return html


import sys

# Device configs
DEVICES = {
    "601": {
        "marc": "00004004330216717 (7).txt",
        "colab": "rep_colaborador (5).txt",
        "out": "ponto_601",
    },
    "nevine": {
        "marc": "00004004330212445 (2).txt",
        "colab": "rep_colaborador nevine.txt",
        "out": "ponto_nevine",
    },
}

def parse_args(argv):
    ini = fim = None
    filtro = []
    i = 1
    while i < len(argv):
        if argv[i] == '--ini' and i + 1 < len(argv):
            ini = date.fromisoformat(argv[i + 1])
            i += 2
        elif argv[i] == '--fim' and i + 1 < len(argv):
            fim = date.fromisoformat(argv[i + 1])
            i += 2
        else:
            filtro.append(argv[i])
            i += 1
    return ini, fim, filtro

if len(sys.argv) > 1 and sys.argv[1] in DEVICES:
    dev = DEVICES[sys.argv[1]]
    
    # Busca dinamicamente o arquivo mais recente baseado no prefixo do serial
    prefixo = dev["marc"].split(' ')[0] # Pega os primeiros digitos
    import glob
    arquivos = glob.glob(f"{prefixo}*.txt")
    if arquivos:
        arquivo_marc = max(arquivos, key=lambda f: __import__('os').path.getmtime(f))
    else:
        arquivo_marc = dev["marc"]
        
    arquivo_colab = dev["colab"]
    prefixo_saida = dev["out"]
    hoje = date.today()
    ini_arg, fim_arg, filtro_arg = parse_args(sys.argv[2:])
    if ini_arg:
        data_ini = ini_arg
        data_fim = fim_arg or hoje
    else:
        data_ini = date(hoje.year, 7, 1)
        data_fim = hoje
else:
    print("Uso: python gerar_ponto.py [601 | nevine]")
    print(f"Dispositivos: {', '.join(DEVICES.keys())}")
    exit(1)

print(f"Lendo {arquivo_marc}...")
registros = parse_marcacoes(arquivo_marc)
print(f"  {len(registros)} registros")

colaboradores = carregar_colaboradores(arquivo_colab)
print(f"  {len(colaboradores)} colaboradores")
for cid, nome in colaboradores.items():
    print(f"    {cid} - {nome}")

filtro = filtro_arg or None

html = gerar_html(registros, colaboradores, data_inicio=data_ini, data_fim=data_fim, filtro_nomes=filtro)

nome_saida = f"{prefixo_saida}.html"
with open(nome_saida, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✅ Relatório gerado: {nome_saida}")
print(f"   Abra com: start {nome_saida}")
