import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pdf_parser import extract_invoice_data
from erp_launcher import run_entries

pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Recibo de Pagamento NEVINE.pdf")
data = extract_invoice_data(pdf_path)
results = data if isinstance(data, list) else [data]

print("Funcionarios encontrados no Recibo de Pagamento NEVINE.pdf:")
print("-" * 60)
for d in results:
    if d.get("fornecedor"):
        print(f'{d["fornecedor"]} - R$ {d["valor"]:.2f} - Venc: {d["vencimento"]}')
print("-" * 60)
print(f"Total: {len(results)} funcionario(s)")
print()

entries = []
for r in results:
    if r.get("fornecedor"):
        r["filial"] = "Nevine"
        r["pdf_path"] = pdf_path
        r["referencia"] = "REF-Holerit Adiantamento Salarial - Julho/26"
        entries.append(r)

if entries:
    print(f"Lancando {len(entries)} titulo(s) no ERP...")
    run_entries(entries)
