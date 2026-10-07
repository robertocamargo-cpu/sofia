@echo off
title Renovando Sessao do Google - Previsao
echo ============================================================
echo   ABRINDO GOOGLE CHROME PARA LOGIN DA PREVISAO...
echo   1. Faca login na conta financeiro@nevine.com.br
echo   2. Quando a planilha carregar, feche esta janela do Chrome.
echo ============================================================
C:\PROGRA~1\Google\Chrome\Application\chrome.exe --user-data-dir="%LOCALAPPDATA%\Automacao_Previsao\sessao_nova" "https://docs.google.com/spreadsheets/d/1OHMAcfxKIS2UTntlB5J7Y8krmCK7JHT9miEHmbbmLE8/edit#gid=993064263"
echo.
echo Sessao salva com sucesso! Pressione qualquer tecla para sair...
pause
