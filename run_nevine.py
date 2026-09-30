"""
Script para processar APENAS o Recibo de Pagamento NEVINE.pdf
e lançar os holerites no ERP.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main import build_entries
from erp_launcher import run_entries

PDF_PATH = os.path.join(os.path.dirname(__file__), "Recibo de Pagamento NEVINE.pdf")

if not os.path.isfile(PDF_PATH):
    print(f"ERRO: Arquivo nao encontrado: {PDF_PATH}")
    sys.exit(1)

entries = build_entries(PDF_PATH)

if not entries:
    print("Nenhum titulo valido extraido do PDF.")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"  NEVINE - {len(entries)} holerite(s) para lancar")
print(f"{'='*60}")
for i, e in enumerate(entries, 1):
    print(f"  {i}. {e['fornecedor']}")
    print(f"     Valor: R$ {e['valor']:.2f}")
    print(f"     Vencimento: {e['vencimento']}")
    print(f"     Referencia: {e['referencia']}")
    print()

resp = input("Deseja continuar com o lancamento? (s/n): ").strip().lower()
if resp != "s":
    print("Cancelado.")
    sys.exit(0)

print(f"\nLancando {len(entries)} titulo(s) no ERP...")
run_entries(entries)
print("\nConcluido!")
