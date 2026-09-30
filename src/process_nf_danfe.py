import os
import sys
import argparse
from datetime import datetime

from danfe_ocr import extract_from_jpeg
from erp_launcher import run_entries

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def main():
    parser = argparse.ArgumentParser(description="Processa DANFE (JPEG) e lança no ERP")
    parser.add_argument("jpeg", nargs="?", help="Caminho do arquivo JPEG da DANFE")
    parser.add_argument("--emitente", help="Nome do emitente/fornecedor")
    parser.add_argument("--destinatario", help="Nome do destinatário (filial)")
    parser.add_argument("--nf", help="Número da Nota Fiscal")
    parser.add_argument("--valor", type=float, help="Valor total da nota")
    parser.add_argument("--vencimento", help="Data de vencimento (dd/mm/aaaa)")

    args = parser.parse_args()

    jpeg_path = args.jpeg
    if jpeg_path and not os.path.isabs(jpeg_path):
        jpeg_path = os.path.join(PROJECT_ROOT, jpeg_path)

    if not jpeg_path or not os.path.isfile(jpeg_path):
        jpeg_paths = [os.path.join(PROJECT_ROOT, f) for f in os.listdir(PROJECT_ROOT)
                      if f.lower().endswith(('.jpeg', '.jpg'))]
        if jpeg_paths:
            jpeg_path = jpeg_paths[0]
            print(f"Usando: {jpeg_path}")
        else:
            print("Nenhum JPEG encontrado na pasta. Informe os dados manualmente.")

    if all([args.emitente, args.destinatario, args.nf, args.valor is not None, args.vencimento]):
        dados = DanfeData(
            emitente=args.emitente,
            destinatario=args.destinatario,
            numero_nf=args.nf,
            valor_total=args.valor,
            data_vencimento=args.vencimento,
        )
    elif jpeg_path and os.path.isfile(jpeg_path):
        dados = extract_from_jpeg(jpeg_path)
    else:
        print("Dados insuficientes. Use --emitente, --destinatario, --nf, --valor, --vencimento")
        return

    try:
        venc = datetime.strptime(dados.data_vencimento, "%d/%m/%Y").date()
    except:
        venc = datetime.today().date()

    entry = {
        "fornecedor": dados.emitente,
        "valor": dados.valor_total,
        "vencimento": venc,
        "filial": dados.destinatario,
        "referencia": f"NF {dados.numero_nf}",
    }
    run_entries([entry])

if __name__ == "__main__":
    main()
