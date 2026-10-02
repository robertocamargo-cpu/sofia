import re, json, sys, glob, os
from datetime import datetime, timedelta, time, date
from collections import defaultdict

BASE_PONTO_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_marc(arquivo):
    with open(arquivo, 'r', encoding='latin-1') as f:
        linhas = f.read().split('\n')
    regs = []
    for linha in linhas:
        linha = linha.strip()
        if not linha: continue
        if linha.startswith('0000000000') or linha.startswith('9999999999'): continue
        if linha.startswith('AIYFXMEL') or linha.startswith('AOV2ERIR') or linha.startswith('ABUAJ7ZJ'): continue
        m = re.match(r'(\d{10})(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4})(\d{11})', linha)
        if m: regs.append({'ts': m.group(2), 'emp_id': m.group(3)})
        else:
            m = re.match(r'(\d{10})(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4})[AI](\d{11})', linha)
            if m: regs.append({'ts': m.group(2), 'emp_id': m.group(3)})
    return regs

def load_colabs(arquivo):
    cols = {}
    with open(arquivo, 'r', encoding='latin-1') as f:
        for linha in f:
            m = re.match(r'1\+1\+I\[(\d+)\[([^\[]+)', linha)
            if m: cols[m.group(1)] = m.group(2).strip()
    return cols

def normalizar(eid, colabs):
    eid = eid.strip()
    for cid in colabs:
        if cid.endswith(eid) or cid.lstrip('0') == eid.lstrip('0'):
            return cid
    return None

def gerar_espelho_ponto_consolidado(d_ini=None, d_fim=None, output_path=None) -> str:
    devices = {
        "601": {"prefix": "00004004330216717", "marc_default": "00004004330216717 (7).txt", "colab": "rep_colaborador (5).txt"},
        "NEVINE": {"prefix": "00004004330212445", "marc_default": "00004004330212445 (2).txt", "colab": "rep_colaborador nevine.txt"},
    }

    for dev_name, dev in devices.items():
        arquivos = glob.glob(os.path.join(BASE_PONTO_DIR, f"{dev['prefix']}*.txt"))
        if arquivos:
            dev["marc"] = max(arquivos, key=lambda f: os.path.getmtime(f))
        else:
            dev["marc"] = os.path.join(BASE_PONTO_DIR, dev["marc_default"])
        dev["colab"] = os.path.join(BASE_PONTO_DIR, dev["colab"])

    hoje = date.today()
    if not d_ini:
        d_ini = date(hoje.year, 7, 1)
    if not d_fim:
        d_fim = hoje

    hr = time(8, 0)
    hr_lim = time(8, 5)

    # Expected schedules (both devices same)
    PREV = {
        0: 9*60,  # Seg = 9h
        1: 9*60,  # Ter = 9h
        2: 9*60,  # Qua = 9h
        3: 9*60,  # Qui = 9h
        4: 8*60,  # Sex = 8h
        5: 0,     # Sab
        6: 0,     # Dom
    }
    PREV_HM = {0: '09:00', 1: '09:00', 2: '09:00', 3: '09:00', 4: '08:00', 5: '-', 6: '-'}
    TOLERANCIA = 10  # CLT art.58 §1

    all_colabs = {}

    for dev_name, dev in devices.items():
        colabs = load_colabs(dev["colab"])
        regs = parse_marc(dev["marc"])
        
        # Register all colaboradores first (even with no markings)
        for cid, nome in colabs.items():
            key = nome.lower().strip()
            if key not in all_colabs:
                all_colabs[key] = {"nome": nome, "device": dev_name, "dias": {}}
            elif dev_name not in all_colabs[key]["device"]:
                all_colabs[key]["device"] = "AMBOS"
        
        # Build per-colaborador per-day data
        col_data = defaultdict(lambda: defaultdict(list))
        for r in regs:
            dt = datetime.fromisoformat(r['ts']).date()
            if d_ini <= dt <= d_fim:
                col_data[r['emp_id']][dt].append(r['ts'])
        
        for eid, dias in col_data.items():
            cid = normalizar(eid, colabs)
            if not cid: continue
            nome = colabs[cid]
            key = nome.lower().strip()
            for dt, tss in dias.items():
                tss.sort()
                all_colabs[key]["dias"][str(dt)] = tss

    # Build JSON structure for frontend
    out_colabs = []
    for key, c in all_colabs.items():
        dias_out = {}
        curr = d_ini
        while curr <= d_fim:
            curr_str = str(curr)
            dow = curr.weekday()
            prev_m = PREV[dow]
            prev_hm = PREV_HM[dow]
            
            tss = c["dias"].get(curr_str, [])
            h_list = [datetime.fromisoformat(t).strftime('%H:%M') for t in tss]
            
            trab_m = 0
            if len(tss) >= 2:
                for i in range(0, len(tss) - 1, 2):
                    t1 = datetime.fromisoformat(tss[i])
                    t2 = datetime.fromisoformat(tss[i+1])
                    trab_m += int((t2 - t1).total_seconds() / 60)
            
            trab_hm = f"{trab_m//60:02d}:{trab_m%60:02d}" if trab_m > 0 else "-"
            
            atraso = False
            atraso_str = ""
            if prev_m > 0 and len(tss) > 0:
                t_prim = datetime.fromisoformat(tss[0]).time()
                if t_prim > hr_lim:
                    atraso = True
                    diff = (datetime.combine(curr, t_prim) - datetime.combine(curr, hr)).total_seconds() / 60
                    atraso_str = f"-{int(diff)//60:02d}:{int(diff)%60:02d}"
            
            extra_str = ""
            falta = False
            if prev_m > 0:
                if trab_m == 0:
                    falta = True
                else:
                    saldo_m = trab_m - prev_m
                    if abs(saldo_m) > TOLERANCIA:
                        if saldo_m > 0:
                            extra_str = f"+{saldo_m//60:02d}:{saldo_m%60:02d}"
                        elif not atraso_str:
                            atraso_str = f"-{abs(saldo_m)//60:02d}:{abs(saldo_m)%60:02d}"
            
            dias_out[curr_str] = {
                "h": h_list,
                "qtd": len(h_list),
                "trab": trab_hm,
                "prev": prev_hm,
                "atraso": atraso,
                "atraso_val": atraso_str,
                "extra_val": extra_str,
                "falta": falta,
            }
            curr += timedelta(days=1)
        
        out_colabs.append({
            "nome": c["nome"],
            "device": c["device"],
            "dias": dias_out,
        })

    sorted_colabs = sorted(out_colabs, key=lambda x: x["nome"])
    dados_json = json.dumps(sorted_colabs, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Espelho de Ponto Consolidado (601 + NEVINE)</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a1a; display: flex; height: 100vh; }}
#sidebar {{ width: 280px; background: #2c3e50; color: white; display: flex; flex-direction: column; flex-shrink: 0; }}
#sidebar-header {{ padding: 16px; border-bottom: 1px solid #34495e; }}
#sidebar-header h1 {{ font-size: 1.1em; font-weight: 600; margin-bottom: 4px; }}
#sidebar-header p {{ font-size: 0.75em; color: #95a5a6; }}
#search {{ width: 100%; padding: 8px 12px; margin-top: 10px; border-radius: 6px; border: none; font-size: 0.85em; background: #34495e; color: white; outline: none; }}
#search::placeholder {{ color: #7f8c8d; }}
#dev-filter {{ display: flex; gap: 4px; margin-top: 8px; }}
.btn-f {{ flex: 1; padding: 4px 6px; font-size: 0.7em; border-radius: 4px; border: none; cursor: pointer; background: #34495e; color: #bdc3c7; }}
.btn-f.active {{ background: #3498db; color: white; }}
#colab-list {{ overflow-y: auto; flex: 1; }}
.colab-item {{ padding: 10px 16px; cursor: pointer; border-bottom: 1px solid #34495e; font-size: 0.82em; transition: background 0.15s; display: flex; justify-content: space-between; align-items: center; }}
.colab-item:hover {{ background: #34495e; }}
.colab-item.active {{ background: #2980b9; color: white; font-weight: 600; }}
.badge {{ font-size: 0.7em; padding: 2px 6px; border-radius: 10px; font-weight: normal; }}
.badge-601 {{ background: #e67e22; color: white; }}
.badge-nevine {{ background: #9b59b6; color: white; }}
.badge-ambos {{ background: #27ae60; color: white; }}
#main {{ flex: 1; overflow-y: auto; padding: 24px; }}
#card {{ background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 24px; max-width: 1000px; margin: 0 auto; }}
#card h2 {{ font-size: 1.3em; margin-bottom: 4px; color: #2c3e50; }}
.cards-row {{ display: flex; gap: 12px; margin: 16px 0; }}
.stat-card {{ flex: 1; background: #f8f9fa; border-radius: 8px; padding: 12px; text-align: center; border: 1px solid #e9ecef; }}
.stat-card .num {{ font-size: 1.4em; font-weight: 700; color: #2c3e50; }}
.stat-card .lbl {{ font-size: 0.72em; color: #7f8c8d; text-transform: uppercase; margin-top: 2px; }}
.stat-card.alerta .num {{ color: #e74c3c; }}
.stat-card.ok .num {{ color: #27ae60; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; margin-top: 16px; }}
th {{ background: #2c3e50; color: white; padding: 8px 10px; text-align: left; font-weight: 600; font-size: 0.85em; }}
td {{ padding: 7px 10px; border-bottom: 1px solid #ecf0f1; }}
tr:hover {{ background: #f8f9fa; }}
.atraso-row {{ background: #fff0f0 !important; }}
.incompleto-row {{ background: #fffbe6; }}
.tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; font-weight: 600; }}
.tag-pink {{ background: #fce4ec; color: #c2185b; }}
.tag-yellow {{ background: #fff9c4; color: #f57f17; }}
</style>
</head>
<body>
<div id="sidebar">
    <div id="sidebar-header">
        <h1>Espelho de Ponto</h1>
        <p>Consolidado: 601 + NEVINE</p>
        <input id="search" type="text" placeholder="Buscar colaborador..." oninput="filtrar()">
        <div id="dev-filter">
            <button class="btn-f active" onclick="setDev('TODOS', this)">TODOS</button>
            <button class="btn-f" onclick="setDev('601', this)">601</button>
            <button class="btn-f" onclick="setDev('NEVINE', this)">NEVINE</button>
        </div>
    </div>
    <div id="colab-list"></div>
</div>
<div id="main"><div id="card"><p style="color:#7f8c8d;text-align:center;padding:60px 0">Selecione um colaborador no menu lateral</p></div></div>

<script>
const DATA = {dados_json};
let selectedIdx = 0;
let devFilter = 'TODOS';

function setDev(dev, btn) {{
    devFilter = dev;
    document.querySelectorAll('.btn-f').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filtrar();
}}

function renderList() {{
    const q = document.getElementById('search').value.toLowerCase();
    const list = document.getElementById('colab-list');
    list.innerHTML = '';
    DATA.forEach((c, idx) => {{
        if (devFilter !== 'TODOS' && c.device !== devFilter && c.device !== 'AMBOS') return;
        if (q && !c.nome.toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.className = 'colab-item' + (idx === selectedIdx ? ' active' : '');
        div.onclick = () => selectColab(idx);
        const badgeCls = c.device === '601' ? 'badge-601' : (c.device === 'NEVINE' ? 'badge-nevine' : 'badge-ambos');
        div.innerHTML = `<span>${{c.nome}}</span><span class="badge ${{badgeCls}}">${{c.device}}</span>`;
        list.appendChild(div);
    }});
}}

function selectColab(idx) {{
    selectedIdx = idx;
    renderList();
    renderCard(DATA[idx]);
}}

function renderCard(c) {{
    let total_trab = 0, total_prev = 0, total_atraso = 0, total_extra = 0, dias = 0, total_marc = 0;
    let linhas = '';
    for (const [diaStr, d] of Object.entries(c.dias)) {{
        if (d.qtd === 0 && d.prev === '-') continue;
        dias++;
        total_marc += d.qtd;
        const dia = diaStr.split('-').reverse().slice(0,2).reverse().join('/');
        const m1 = d.h[0] || '-', m2 = d.h[1] || '-', m3 = d.h[2] || '-', m4 = d.h[3] || '-';
        let pontos = m1;
        if (m2 !== '-') pontos += ` ${{m2}}`;
        if (m3 !== '-' || m4 !== '-') {{
            if (m3 !== '-') pontos += ` | ${{m3}}`;
            if (m4 !== '-') pontos += ` ${{m4}}`;
        }}
        const cls = d.atraso ? 'atraso-row' : (d.qtd < 4 ? 'incompleto-row' : '');
        linhas += `<tr class="${{cls}}">
            <td>${{dia}}</td>
            <td>${{pontos}}</td>
            <td>${{d.trab}}</td>
            <td>-</td>
            <td>${{d.prev}}</td>
            <td>${{d.atraso_val || ''}}</td>
            <td>${{d.extra_val || ''}}</td>
            <td>${{d.falta ? 'F' : ''}}</td>
        </tr>`;
        const t = d.trab.split(':');
        if (t.length === 2 && t[0] !== '-') total_trab += parseInt(t[0])*60 + parseInt(t[1]);
        if (d.prev !== '-') {{
            const p = d.prev.split(':');
            total_prev += parseInt(p[0])*60 + parseInt(p[1]);
        }}
        if (d.atraso_val) {{
            const a = d.atraso_val.replace('-','').split(':');
            total_atraso += parseInt(a[0])*60 + parseInt(a[1]);
        }}
        if (d.extra_val) {{
            const e = d.extra_val.split(':');
            total_extra += parseInt(e[0])*60 + parseInt(e[1]);
        }}
    }}
    function fmt(m) {{ return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0'); }}
    const saldo = total_trab - total_prev;

    document.getElementById('card').innerHTML = `
        <h2>${{c.nome}} <span style="font-weight:normal;font-size:0.7em;color:#7f8c8d">(${{c.device}})</span></h2>
        <div class="cards-row">
            <div class="stat-card"><div class="num">${{dias}}</div><div class="lbl">Dias</div></div>
            <div class="stat-card"><div class="num">${{total_marc}}</div><div class="lbl">Marca&ccedil;&otilde;es</div></div>
            <div class="stat-card"><div class="num">${{fmt(total_trab)}}</div><div class="lbl">Trabalhadas</div></div>
            <div class="stat-card"><div class="num">${{fmt(total_prev)}}</div><div class="lbl">Previstas</div></div>
            <div class="stat-card alerta"><div class="num">${{total_atraso ? '-'+fmt(total_atraso) : '00:00'}}</div><div class="lbl">Atrasos</div></div>
            <div class="stat-card ok"><div class="num">${{fmt(total_extra)}}</div><div class="lbl">Extras</div></div>
        </div>
        <p style="color:#666;font-size:0.8em;margin-bottom:10px"><strong>Saldo:</strong> ${{saldo < 0 ? '-' : '+'}}${{fmt(Math.abs(saldo))}} &nbsp;|&nbsp; <span class="tag tag-pink">Rosa</span> = atraso &nbsp; <span class="tag tag-yellow">Amarelo</span> = &lt;4 marca&ccedil;&otilde;es</p>
        <table><thead><tr><th>DIA</th><th>PONTOS</th><th>TRAB</th><th>ABONO</th><th>PREV</th><th>ATRASO</th><th>EXTRAS</th><th>FALTAS</th></tr></thead><tbody>${{linhas}}</tbody></table>
    `;
}}

function filtrar() {{ renderList(); }}

const nomeCount = {{}};
DATA.forEach(c => {{ nomeCount[c.nome] = (nomeCount[c.nome] || 0) + 1; }});
DATA.forEach(c => {{ if (nomeCount[c.nome] > 1) c.device = 'AMBOS'; }});

renderList();
if (DATA.length > 0) renderCard(DATA[0]);
</script>
</body>
</html>"""

    destino = output_path or os.path.join(BASE_PONTO_DIR, "ponto_consolidado.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Consolidado gerado: {destino} ({len(sorted_colabs)} colaboradores)")
    return destino

if __name__ == "__main__":
    hoje = date.today()
    d_ini = date(hoje.year, 7, 1)
    d_fim = hoje
    if '--ini' in sys.argv:
        d_ini = date.fromisoformat(sys.argv[sys.argv.index('--ini') + 1])
    if '--fim' in sys.argv:
        d_fim = date.fromisoformat(sys.argv[sys.argv.index('--fim') + 1])
    gerar_espelho_ponto_consolidado(d_ini, d_fim)
