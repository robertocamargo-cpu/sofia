"""
====================================================================
  RUNNER CLI: ALTERAÇÃO DE TÍTULOS A PAGAR
====================================================================
Exemplos de uso:
  python run_alteracao.py "altere o plano de contas do favorecido Eduardo Laurindo para 41038"
  python run_alteracao.py "altere a data de vencimento do favorecido Eduardo Laurindo para 01/10/2026"
  python run_alteracao.py "altere a data de vencimento de TODOS os favorecidos de HOJE para 01/10/2026"
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from alteracao_launcher import (
    parse_alteracao_command,
    alterar_titulo_individual,
    alterar_titulos_lote
)

async def main():
    if len(sys.argv) < 2:
        print("\nUso: python run_alteracao.py \"comando em texto\"")
        print("Exemplo: python run_alteracao.py \"altere o plano de contas do favorecido Eduardo Laurindo para 41038\"\n")
        return

    comando = " ".join(sys.argv[1:])
    print(f"\n[CLI] Analisando comando: '{comando}'")
    dados = parse_alteracao_command(comando)
    print(f"[CLI] Dados interpretados: {dados}\n")

    if dados.get("erros"):
        print("[ERRO] Erros encontrados na interpretacao:")
        for err in dados["erros"]:
            print(f"  * {err}")
        return

    if dados["modo"] == "lote":
        print(f"[RUN] Iniciando alteracao EM LOTE de {dados['lote_origem_str']} para {dados['lote_destino_str']}...")
        res = await alterar_titulos_lote(
            data_origem=dados["lote_origem"],
            data_destino=dados["lote_destino"],
            filial=dados.get("filial_filtro")
        )
    else:
        print(f"[RUN] Iniciando alteracao INDIVIDUAL para {dados['fornecedor']}...")
        res = await alterar_titulo_individual(
            fornecedor=dados["fornecedor"],
            campos=dados["campos"]
        )

    print("\n" + "="*50)
    print(f"RESULTADO: {res}")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
