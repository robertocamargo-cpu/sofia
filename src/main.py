import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

from pdf_parser import extract_invoice_data
from erp_launcher import run_entries

load_dotenv()

FILIAL_FIXA = os.getenv("FILIAL_PADRAO", "429")

def get_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PDF_DIR = os.path.join(get_project_root())
os.makedirs(PDF_DIR, exist_ok=True)

def ajustar_vencimento(data: date) -> date:
    d = data - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

PDF_PASSWORD = os.getenv("PDF_PASSWORD", "")

def build_entries(pdf_path: str) -> list[dict]:
    invoices_data = extract_invoice_data(pdf_path, password=PDF_PASSWORD or None)
    if isinstance(invoices_data, dict):
        invoices_data = [invoices_data]
    
    entries = []
    for invoice in invoices_data:
        fornecedor = invoice.get("fornecedor") or "DESCONHECIDO"
        venc_original = invoice.get("vencimento") or datetime.today().date()
        tipo = invoice.get("tipo")

        if tipo == "GNRE" or tipo == "Holerit":
            vencimento = venc_original
        else:
            vencimento = ajustar_vencimento(venc_original)

        doc = invoice.get("documento")
        if doc:
            referencia = f"REF-{tipo or 'AUTO'} {doc}"
        else:
            referencia = f"REF-{tipo or 'AUTO'}"

        filial = invoice.get("filial") or FILIAL_FIXA
        entry = {
            "fornecedor": fornecedor,
            "valor": invoice.get("valor") or 0.0,
            "vencimento": vencimento,
            "filial": filial,
            "pdf_path": pdf_path,
            "referencia": referencia,
            "tipo": tipo,
            "nf_numero": invoice.get("nf_numero"),
            "parcela_atual": invoice.get("parcela_atual"),
            "total_parcelas": invoice.get("total_parcelas"),
        }
        uf = invoice.get("uf")
        if uf:
            entry["uf"] = uf
        entries.append(entry)
    
    return entries

def main():
    pdf_files = [os.path.join(PDF_DIR, f) for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("Nenhum PDF encontrado para processar.")
        return

    entries = []
    for pdf_path in pdf_files:
        try:
            new_entries = build_entries(pdf_path)
            for entry in new_entries:
                entries.append(entry)
                print(f"PDF: {os.path.basename(pdf_path)} -> {entry['fornecedor']} R$ {entry['valor']:.2f} venc {entry['vencimento']}")
        except Exception as exc:
            print(f"Erro ao processar {pdf_path}: {exc}")

    if entries:
        print(f"\nLançando {len(entries)} título(s) no ERP...")
        run_entries(entries)
    else:
        print("Nenhum título válido para lançar.")

if __name__ == "__main__":
    main()
