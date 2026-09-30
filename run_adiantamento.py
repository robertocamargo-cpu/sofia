"""
Executador CLI para lançar os títulos de Adiantamento Salarial a partir dos PDFs.
Uso:
    python run_adiantamento.py "adiantamento_601.pdf"
    python run_adiantamento.py "adiantamento_nevine.pdf"
    python run_adiantamento.py "Recibo de Pagamento ADIANTAMENTO_601- JULHO.pdf"
    ou simplesmente:
    python run_adiantamento.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from adiantamento_launcher import processar_adiantamento_pdf

async def main():
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Padrão: processa adiantamento_601.pdf se existir
        pdf_path = "adiantamento_601.pdf"
        
    if not os.path.isfile(pdf_path):
        print(f"Erro: Arquivo '{pdf_path}' não encontrado!")
        sys.exit(1)
        
    print(f"\n[Adiantamento CLI] Processando arquivo: {pdf_path}...\n")
    resultado = await processar_adiantamento_pdf(pdf_path)
    
    print("\n" + "="*60)
    print("  RESULTADO DO LANÇAMENTO DE ADIANTAMENTO:")
    print("="*60)
    print(f"  Arquivo: {resultado['arquivo']}")
    print(f"  Filial: {resultado['filial']}")
    print(f"  Competência: {resultado['competencia']}")
    print(f"  Vencimento: {resultado['vencimento']}")
    print(f"  Total Colaboradores: {resultado['total_colaboradores']}")
    print(f"  Total Sucessos: {resultado['total_sucesso']}")
    print(f"  Total Falhas: {resultado['total_falhas']}")
    print(f"  Valor Total Lançado: R$ {resultado['valor_total_lancado']:,.2f}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
