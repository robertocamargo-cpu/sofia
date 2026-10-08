#!/bin/bash
# ====================================================================
#   Script de Inicialização da Super SofIA (macOS / Linux)
# ====================================================================
cd "$(dirname "$0")"

# Ativa o ambiente virtual
source .venv/bin/activate

export PYTHONUNBUFFERED=1
mkdir -p logs src/logs src/locks inbox data

echo "=========================================================="
echo "  Iniciando Super SofIA - Central Administrativa & Bot    "
echo "=========================================================="

python sofia_bot.py
