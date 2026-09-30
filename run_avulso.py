"""
====================================================================
  EXECUTOR CLI: PAGAMENTO AVULSO NO ERP ADMSIS
====================================================================
Permite lançar um pagamento avulso diretamente pelo terminal.

Uso:
  python run_avulso.py "EDUARDO LAURINDO" 760 429 "MANUTENÇÃO PREDIAL" 30/09/2026
  
Ou com argumentos nomeados:
  python run_avulso.py --fornecedor "EDUARDO LAURINDO" --valor 760 --filial 429 --ref "MANUTENÇÃO" --vencimento 30/09/2026
"""

import sys
import os
import argparse
import asyncio
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from avulso_launcher import lancar_pagamento_avulso

def parse_date(data_str: str) -> date:
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Formato de data inválido: '{data_str}'. Use DD/MM/AAAA.")

async def main():
    parser = argparse.ArgumentParser(description="Lançamento de Pagamento Avulso no ERP ADMSIS")
    parser.add_argument("fornecedor", nargs="?", help="Nome do Favorecido/Fornecedor")
    parser.add_argument("valor", nargs="?", type=float, help="Valor do título (ex: 760 ou 760.50)")
    parser.add_argument("filial", nargs="?", default="429", help="Filial do lançamento (padrão: 429)")
    parser.add_argument("referencia", nargs="?", help="Referência / Documento")
    parser.add_argument("vencimento", nargs="?", help="Data de Vencimento (DD/MM/AAAA)")
    parser.add_argument("--obs", dest="observacao", default=None, help="Observação opcional")

    args = parser.parse_args()

    fornecedor = args.fornecedor
    valor = args.valor
    filial = args.filial
    referencia = args.referencia
    vencimento_str = args.vencimento
    observacao = args.observacao

    # Modo interativo se faltar algum campo essencial
    if not fornecedor:
        fornecedor = input("Informe o Favorecido/Fornecedor: ").strip()
    if not valor:
        valor = float(input("Informe o Valor (R$): ").strip().replace(".", "").replace(",", "."))
    if not referencia:
        referencia = input("Informe a Referência: ").strip()
    if not vencimento_str:
        vencimento_str = input("Informe o Vencimento (DD/MM/AAAA ou 'hoje'): ").strip()

    if vencimento_str.lower() == "hoje":
        vencimento = date.today()
    else:
        vencimento = parse_date(vencimento_str)

    print("\nExecutando lançamento avulso...")
    res = await lancar_pagamento_avulso(
        fornecedor=fornecedor,
        valor=valor,
        filial=filial,
        referencia=referencia,
        vencimento=vencimento,
        observacao=observacao
    )

    if res["sucesso"]:
        print("\n✅ LANÇAMENTO AVULSO CONCLUÍDO COM SUCESSO!")
        print(f"Fornecedor : {res['fornecedor']}")
        print(f"Valor      : {res['valor_str']}")
        print(f"Filial     : {res['filial']}")
        print(f"Referência : {res['referencia']}")
        print(f"Vencimento : {res['vencimento']}")
        print(f"Observação : {res['observacao']}")
    else:
        print(f"\n❌ FALHA NO LANÇAMENTO: {res['mensagem']}")

if __name__ == "__main__":
    asyncio.run(main())
