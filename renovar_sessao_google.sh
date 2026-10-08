#!/bin/bash
# ====================================================================
#   Renovação de Sessão Google (macOS) - Super SofIA
# ====================================================================
CHROME_PROFILE="$HOME/Library/Application Support/Automacao_Previsao/sessao_nova"
mkdir -p "$CHROME_PROFILE"

echo "============================================================"
echo "  ABRINDO GOOGLE CHROME PARA SESSÃO DA PREVISÃO NO MAC...   "
echo "  1. Faça login com: financeiro@nevine.com.br"
echo "  2. Confirme o 2FA / verificação no Galaxy A15 5G."
echo "  3. Quando a planilha carregar, feche a janela do Chrome."
echo "============================================================"

# Usar open -n para forçar uma NOVA instância do Chrome com este perfil isolado
open -n -a "Google Chrome" --args \
  --user-data-dir="$CHROME_PROFILE" \
  "https://docs.google.com/spreadsheets/d/1OHMAcfxKIS2UTntlB5J7Y8krmCK7JHT9miEHmbbmLE8/edit#gid=993064263"

echo "Instância aberta! Quando terminar o login e abrir a planilha, feche o navegador."
