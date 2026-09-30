import os
import sys
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from relatorio_launcher import gerar_relatorio_titulos_pagar

async def main():
    # Se passou data como argumento: ex: python run_relatorio.py 03/07/2026
    data_arg = None
    filial_arg = None
    
    args = sys.argv[1:]
    for arg in args:
        if "/" in arg or "-" in arg:
            data_arg = arg.replace("-", "/")
        elif any(f in arg.lower() for f in ["302", "429", "551", "601", "nevine", "relevo"]):
            filial_arg = arg
            
    if not data_arg:
        data_arg = datetime.now().strftime("%d/%m/%Y")
        
    print(f"=== GERADOR DE RELATÓRIO DE CONTAS A PAGAR ===")
    print(f"Data: {data_arg}")
    if filial_arg:
        print(f"Filial: {filial_arg}")
        
    try:
        pdf_path, resumo = await gerar_relatorio_titulos_pagar(
            data_inicio=data_arg,
            data_fim=data_arg,
            filial=filial_arg
        )
        print("\n==============================================")
        print("  RELATÓRIO GERADO COM SUCESSO!")
        print("==============================================")
        print(f"Arquivo PDF: {pdf_path}")
        print(f"Período: {resumo.get('periodo', data_arg)}")
        print(f"Quantidade de Títulos: {resumo.get('qtd_titulos', 0)}")
        print(f"Valor Total a Pagar: {resumo.get('valor_total', 'R$ 0,00')}")
        
        totais_fil = resumo.get("totais_por_filial", {})
        if totais_fil:
            print("\nTotais por Filial:")
            for fil, tot in totais_fil.items():
                print(f"  - Filial {fil}: R$ {tot:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
        titulos = resumo.get("titulos", [])
        if titulos:
            print(f"\nTítulos Identificados ({len(titulos)}):")
            for t in titulos[:10]:
                print(f"  [{t['id']}] Filial {t['filial']} | {t['valor_str']} | {t['referencia']}")
            if len(titulos) > 10:
                print(f"  ... e mais {len(titulos) - 10} título(s) no PDF.")
        print("==============================================\n")
    except Exception as e:
        print(f"\n[ERRO] Falha ao gerar relatório: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
