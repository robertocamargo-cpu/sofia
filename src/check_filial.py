import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from pdf_parser import extract_text_from_pdf

base = os.path.dirname(os.path.dirname(__file__))

pdfs = [
    "Recibo de Pagamento ADIANTAMENTO_429- JULHO.pdf",
    "Recibo de Pagamento NEVINE.pdf"
]

for pdf_name in pdfs:
    pdf_path = os.path.join(base, pdf_name)
    text = extract_text_from_pdf(pdf_path)
    print(f"\n========== {pdf_name} ==========")
    print(text[:2000])
    print("...")
