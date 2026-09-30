"""
Executador CLI para testar a Sofia localmente sem depender do Discord:
Uso:
    python run_sofia.py "GNRE NF 54949.pdf"
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sofia_core import processar_documento

async def main():
    if len(sys.argv) > 1:
        pdf_name = sys.argv[1]
    else:
        pdf_name = "GNRE NF 54949.pdf"

    pdf_path = pdf_name if os.path.isabs(pdf_name) else os.path.join(os.path.dirname(__file__), pdf_name)
    print(f"\n[SOFIA CLI] Processando arquivo: {pdf_path}")
    
    # Permitir ignorar_duplicidade se passar --force
    ignorar_dup = "--force" in sys.argv
    resultado = await processar_documento(pdf_path, ignorar_duplicidade=ignorar_dup)

    print("\n" + "="*60)
    print("  RESULTADO DO PROCESSAMENTO DA SOFIA:")
    print("="*60)
    print(f"  Sucesso: {resultado.get('sucesso')}")
    if resultado.get("mensagem"):
        print(f"  Mensagem: {resultado.get('mensagem')}")
    if resultado.get("autorizacoes_pdf"):
        print(f"  PDFs de Autorizacao de Pagamento gerados:")
        for pdf in resultado["autorizacoes_pdf"]:
            print(f"    -> {pdf}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
