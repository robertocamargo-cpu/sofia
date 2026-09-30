"""
Executador CLI para lançar os títulos de Vale Refeição (VR) a partir da Planilha VR.xlsx.
Uso:
    python run_vr.py "outubro"
    python run_vr.py "setembro 2026"
    ou simplesmente:
    python run_vr.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from vr_launcher import processar_vr_lote

async def main():
    mes = sys.argv[1] if len(sys.argv) > 1 else "outubro 2026"
    print(f"\n[VR CLI] Iniciando lançamento da competência: {mes}...\n")
    
    resultado = await processar_vr_lote(mes)
    
    print("\n" + "="*60)
    print("  RESULTADO DO LANÇAMENTO DE VR:")
    print("="*60)
    print(f"  Competência: {resultado['competencia']}")
    print(f"  Vencimento: {resultado['vencimento']}")
    print(f"  Total Colaboradores na Planilha: {resultado['total_colaboradores']}")
    print(f"  Total Sucessos: {resultado['total_sucesso']}")
    print(f"  Total Falhas: {resultado['total_falhas']}")
    print(f"  Valor Total Lançado: R$ {resultado['valor_total_lancado']:,.2f}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
