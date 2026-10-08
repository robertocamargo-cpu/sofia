from __future__ import annotations
import os
import sys
import hashlib
import json
from datetime import datetime, date
from typing import Dict, Any, Tuple

sys.path.insert(0, os.path.dirname(__file__))

from pdf_parser import extract_invoice_data
from erp_launcher import run_entries
import run_gnre

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

HASHES_FILE = os.path.join(DATA_DIR, "processed_hashes.json")

def _calcular_hash(caminho_arquivo: str) -> str:
    sha = hashlib.sha256()
    with open(caminho_arquivo, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()

def _carregar_hashes(a_partir_de: str = "2026-10-07") -> dict:
    if os.path.exists(HASHES_FILE):
        try:
            with open(HASHES_FILE, "r", encoding="utf-8") as f:
                hashes = json.load(f)
                if a_partir_de:
                    return {k: v for k, v in hashes.items() if (v.get("timestamp") or "") >= a_partir_de}
                return hashes
        except:
            return {}
    return {}

def _salvar_hash(file_hash: str, info: dict):
    hashes = _carregar_hashes(a_partir_de=None)
    hashes[file_hash] = {
        "timestamp": datetime.now().isoformat(),
        **info
    }
    with open(HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2, ensure_ascii=False)

def _buscar_autorizacao_recente(doc_id: str = None) -> str | None:
    try:
        arquivos = [
            os.path.join(LOGS_DIR, f) for f in os.listdir(LOGS_DIR)
            if f.startswith("autorizacao_pagamento_") and f.endswith(".pdf")
        ]
        if not arquivos:
            return None
        # Ordena pelo mais recente
        arquivos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        if doc_id:
            for arq in arquivos[:5]:
                if str(doc_id) in os.path.basename(arq):
                    return arq
        return arquivos[0]
    except Exception as e:
        print(f"Erro buscando autorizacao recente: {e}")
        return None

def verificar_duplicidade(caminho_arquivo: str) -> Tuple[bool, dict | None]:
    file_hash = _calcular_hash(caminho_arquivo)
    hashes = _carregar_hashes(a_partir_de=None)
    if file_hash in hashes:
        return True, hashes[file_hash]
    backup_file = os.path.join(DATA_DIR, "processed_hashes_backup_pre_07102026.json")
    if os.path.exists(backup_file):
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                b_hashes = json.load(f)
                if file_hash in b_hashes:
                    return True, b_hashes[file_hash]
        except:
            pass
    return False, None

def validar_e_extrair(caminho_arquivo: str, password: str = None) -> list[dict]:
    if not os.path.isfile(caminho_arquivo):
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho_arquivo}")
    
    dados = extract_invoice_data(caminho_arquivo, password=password)
    if not dados:
        raise ValueError("Nenhum dado financeiro pode ser extraido do documento. Verifique a legibilidade do arquivo.")

    entradas = dados if isinstance(dados, list) else [dados]
    
    # Validacao Fail-Fast
    for i, e in enumerate(entradas):
        valor = e.get("valor")
        venc = e.get("vencimento")
        forn = e.get("fornecedor")
        
        if not valor or valor <= 0:
            raise ValueError(f"Documento #{i+1}: Valor invalido ou nao detectado ({valor}).")
        if not venc:
            raise ValueError(f"Documento #{i+1}: Data de vencimento nao detectada.")
        if not forn:
            raise ValueError(f"Documento #{i+1}: Favorecido/Fornecedor nao identificado.")
            
        e["pdf_path"] = caminho_arquivo
        if not e.get("filial"):
            e["filial"] = os.getenv("FILIAL_PADRAO", "429")

    return entradas

async def processar_documento(caminho_arquivo: str, ignorar_duplicidade: bool = False) -> dict:
    """
    Funcao principal da Sofia para processar qualquer documento de pagamento recebido.
    Executa:
      1. Verificacao de duplicidade (Idempotencia).
      2. Validacao Fail-Fast e extracao dos dados.
      3. Classificacao e lancamento no ERP.
      4. Anexo do documento no GED.
      5. Emissao e captura da Autorizacao de Pagamento (#ImprAutPagto).
    """
    caminho_arquivo = os.path.abspath(caminho_arquivo)
    
    # 1. Checagem de Duplicidade
    if not ignorar_duplicidade:
        duplicado, info_anterior = verificar_duplicidade(caminho_arquivo)
        if duplicado:
            return {
                "sucesso": False,
                "motivo": "DUPLICADO",
                "mensagem": f"Este documento ja foi lancado anteriormente em {info_anterior.get('timestamp')[:19]}.\n"
                            f"Fornecedor: {info_anterior.get('fornecedor')} | Valor: R$ {info_anterior.get('valor', 0):.2f}",
                "dados": info_anterior
            }

    # 2. Validacao e Extracao
    try:
        entradas = validar_e_extrair(caminho_arquivo, password=os.getenv("PDF_PASSWORD", "05393"))
    except Exception as exc:
        return {
            "sucesso": False,
            "motivo": "VALIDACAO_FALHOU",
            "mensagem": f"Falha na leitura do documento: {str(exc)}"
        }

    resultado_final = {
        "sucesso": False,
        "lancamentos": [],
        "autorizacoes_pdf": []
    }

    # 3. Lançamento por tipo especializado
    for entry in entradas:
        tipo = entry.get("tipo", "")
        
        if tipo == "GNRE":
            res = await run_gnre.run_gnre_process(caminho_arquivo)
            ok = res[0] if isinstance(res, tuple) else res
            entry_ret = res[1] if isinstance(res, tuple) else entry
            entry = entry_ret if entry_ret else entry
            
            if ok:
                resultado_final["sucesso"] = True
                # Fallback to search logs/ if autorizacao_pdf is not in entry
                aut_pdf = entry.get("autorizacao_pdf")
                if not aut_pdf or not os.path.exists(aut_pdf):
                    aut_pdf = _buscar_autorizacao_recente(entry.get("documento"))
                    if aut_pdf:
                        entry["autorizacao_pdf"] = aut_pdf

                resultado_final["lancamentos"].append(entry)
                if aut_pdf:
                    resultado_final["autorizacoes_pdf"].append(aut_pdf)
            else:
                resultado_final["sucesso"] = False
                resultado_final["mensagem"] = "Falha no lancamento da GNRE no ERP."
                return resultado_final
        elif tipo == "Adiantamento":
            from adiantamento_launcher import processar_adiantamento_pdf
            res_ad = await processar_adiantamento_pdf(caminho_arquivo)
            if res_ad["total_sucesso"] > 0:
                resultado_final["sucesso"] = True
                resultado_final["tipo"] = "Adiantamento"
                resultado_final["resumo_adiantamento"] = res_ad
                resultado_final["lancamentos"] = res_ad["sucessos"]
            else:
                resultado_final["sucesso"] = False
                resultado_final["mensagem"] = f"Nenhum título de adiantamento pôde ser lançado para a filial {res_ad.get('filial')}."
            return resultado_final
        elif tipo == "Pagamento":
            from pagamento_launcher import processar_pagamento_pdf
            res_pag = await processar_pagamento_pdf(caminho_arquivo)
            if res_pag["total_sucesso"] > 0:
                resultado_final["sucesso"] = True
                resultado_final["tipo"] = "Pagamento"
                resultado_final["resumo_pagamento"] = res_pag
                resultado_final["lancamentos"] = res_pag["sucessos"]
            else:
                resultado_final["sucesso"] = False
                resultado_final["mensagem"] = f"Nenhum título de pagamento de salário pôde ser lançado para a filial {res_pag.get('filial')}."
            return resultado_final
        else:
            # Boletos (Relevo, genericos) e Holerites via erp_launcher
            from erp_launcher import launch_erp
            res_erp = await launch_erp([entry])
            if entry.get("sucesso"):
                resultado_final["sucesso"] = True
                
                aut_pdf = entry.get("autorizacao_pdf")
                if not aut_pdf or not os.path.exists(aut_pdf):
                    aut_pdf = _buscar_autorizacao_recente(entry.get("documento") or entry.get("nf_numero"))
                    if aut_pdf:
                        entry["autorizacao_pdf"] = aut_pdf

                resultado_final["lancamentos"].append(entry)
                if aut_pdf:
                    resultado_final["autorizacoes_pdf"].append(aut_pdf)
            else:
                resultado_final["sucesso"] = False
                resultado_final["mensagem"] = entry.get("erro") or (res_erp.get("erros")[0] if res_erp.get("erros") else "Falha ao gravar título do boleto no ERP ADMSIS.")
                return resultado_final

    # Salva hash para impedir duplicidade futura SOMENTE em caso de sucesso
    if resultado_final.get("sucesso"):
        file_hash = _calcular_hash(caminho_arquivo)
        primeira = entradas[0]
        _salvar_hash(file_hash, {
            "arquivo": os.path.basename(caminho_arquivo),
            "fornecedor": primeira.get("fornecedor"),
            "valor": primeira.get("valor"),
            "vencimento": str(primeira.get("vencimento")),
            "filial": primeira.get("filial"),
            "autorizacao_pdf": primeira.get("autorizacao_pdf")
        })

    return resultado_final
