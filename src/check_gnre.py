import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from pdf_parser import extract_invoice_data

base = os.path.dirname(os.path.dirname(__file__))

for pdf_name in ["GNRE_17072026_3014 - 302.pdf", "GNRE_17072026_29049 - 551.pdf"]:
    pdf_path = os.path.join(base, pdf_name)
    if not os.path.exists(pdf_path):
        print(f"{pdf_name}: ARQUIVO NAO ENCONTRADO")
        continue
    data = extract_invoice_data(pdf_path)
    results = data if isinstance(data, list) else [data]
    print(f"\n=== {pdf_name} ===")
    for d in results:
        for k, v in d.items():
            print(f"  {k}: {v}")
