import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BATCH_FILE = os.path.join(DATA_DIR, "batch_history.json")

os.makedirs(DATA_DIR, exist_ok=True)

def carregar_historico_lotes() -> List[Dict[str, Any]]:
    """Carrega o histórico de lotes gravado em JSON."""
    if not os.path.exists(BATCH_FILE):
        return []
    try:
        with open(BATCH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[BatchLogger] Erro ao carregar historico: {e}")
        return []

def salvar_historico_lote(tipo: str, resumo: Dict[str, Any], arquivo: Optional[str] = None) -> Dict[str, Any]:
    """
    Grava a execução de um lote (VR, Adiantamento, Pagamento de Salários) no histórico persistente.
    """
    historico = carregar_historico_lotes()
    
    agora = datetime.now()
    batch_id = f"{tipo.lower()}_{agora.strftime('%Y%m%d_%H%M%S')}"
    
    # Normaliza lista de sucessos e falhas para não estourar tamanho caso tenham objetos complexos
    sucessos_simplificados = []
    for s in resumo.get("sucessos", []):
        if isinstance(s, dict):
            sucessos_simplificados.append({
                "colaborador": s.get("fornecedor") or s.get("nome"),
                "valor": s.get("valor"),
                "filial": s.get("filial")
            })
        else:
            sucessos_simplificados.append(str(s))
            
    falhas_simplificadas = []
    for f in resumo.get("falhas", []):
        if isinstance(f, dict):
            falhas_simplificadas.append({
                "colaborador": f.get("fornecedor") or f.get("nome"),
                "valor": f.get("valor"),
                "motivo": f.get("motivo", "Falha de gravação")
            })
        else:
            falhas_simplificadas.append(str(f))

    registro = {
        "id": batch_id,
        "timestamp": agora.isoformat(),
        "data_formatada": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "tipo": tipo.upper(),
        "filial": resumo.get("filial", "N/D"),
        "competencia": resumo.get("competencia") or resumo.get("mes", "N/D"),
        "vencimento": resumo.get("vencimento", "N/D"),
        "total_colaboradores": resumo.get("total_colaboradores", 0),
        "total_sucesso": resumo.get("total_sucesso", 0),
        "total_falhas": resumo.get("total_falhas", 0),
        "valor_total_lancado": resumo.get("valor_total_lancado", 0.0),
        "arquivo": arquivo or resumo.get("arquivo", "N/D"),
        "status": "SUCESSO" if resumo.get("total_falhas", 0) == 0 and resumo.get("total_sucesso", 0) > 0 else (
            "PARCIAL" if resumo.get("total_sucesso", 0) > 0 else "FALHA"
        ),
        "detalhes": {
            "sucessos": sucessos_simplificados,
            "falhas": falhas_simplificadas
        }
    }
    
    historico.insert(0, registro)  # Mais recente primeiro
    
    try:
        with open(BATCH_FILE, "w", encoding="utf-8") as f:
            json.dump(historico, f, indent=2, ensure_ascii=False)
        print(f"[BatchLogger] Lote {batch_id} salvo com sucesso em data/batch_history.json")
    except Exception as e:
        print(f"[BatchLogger] Erro ao salvar histórico: {e}")
        
    return registro

def consultar_historico_lotes(limite: int = 10, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
    """Consulta os últimos lotes executados com filtro opcional por tipo."""
    itens = carregar_historico_lotes()
    if tipo:
        itens = [i for i in itens if i.get("tipo") == tipo.upper()]
    return itens[:limite]
