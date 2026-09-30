import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime
from pdf_parser import HoleritParser
from erp_launcher import run_entries

pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Recibo de Pagamento ADIANTAMENTO_429- JULHO.pdf")

from pdf_parser import extract_text_from_pdf, clean_garbled, deduplicate_chars
text = extract_text_from_pdf(pdf_path)
text = clean_garbled(text)
if text:
    text = deduplicate_chars(text)

parser = HoleritParser()
results = parser.extract(text)

entries = []
for r in results:
    if r.get("fornecedor") and "PAULO" in r["fornecedor"].upper():
        r["filial"] = "429"
        r["pdf_path"] = pdf_path
        r["referencia"] = f"REF-Holerit Adiantamento Salarial - Julho/26"
        entries.append(r)

if entries:
    print(f"Entries: {len(entries)}")
    for e in entries:
        print(f"  {e['fornecedor']} - R$ {e['valor']:.2f}")
    run_entries(entries)
else:
    print("Nenhum funcionario encontrado no PDF")
