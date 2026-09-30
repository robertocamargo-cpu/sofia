"""
Script para processar APENAS os 3 boletos da RELEVO
e lançar no ERP.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main import build_entries
from erp_launcher import run_entries

pdf_files = [
    "relevo_bol_0020076900042037_protegido_001.pdf",
    "relevo_bol_0020076900042038_protegido_002.pdf",
    "relevo_bol_0020076900042039_protegido_003.pdf"
]

entries = []
for pdf in pdf_files:
    pdf_path = os.path.join(os.path.dirname(__file__), pdf)
    if os.path.isfile(pdf_path):
        entries.extend(build_entries(pdf_path))

if not entries:
    print("Nenhum titulo valido extraido dos PDFs da RELEVO.")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"  RELEVO - {len(entries)} boleto(s) para lancar")
print(f"{'='*60}")
for i, e in enumerate(entries, 1):
    print(f"  {i}. {e['fornecedor']}")
    print(f"     Valor: R$ {e['valor']:.2f}")
    print(f"     Vencimento: {e['vencimento']}")
    print(f"     Referencia: {e['referencia']}")
    print()

print(f"\nLancando {len(entries)} titulo(s) no ERP...")
run_entries(entries)
print("\nConcluido!")
