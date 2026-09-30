import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'src')
from main import build_entries

entries = build_entries('Recibo de Pagamento NEVINE.pdf')
for e in entries:
    print(f"{e['fornecedor']} | R$ {e['valor']:.2f} | {e['vencimento']} | tipo={e['tipo']} | ref={e['referencia']}")
