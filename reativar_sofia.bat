@echo off
chcp 65001 >nul
echo ========================================================
echo   REATIVANDO SUPER SOFIA NESTA MAQUINA (WINDOWS)
echo ========================================================
echo.

echo 1. Reativando tarefa agendada do Windows (GNRE)...
schtasks /change /tn "GNRE Automacao Pipeline" /enable >nul 2>&1
echo    [OK] Tarefa agendada reativada!

echo.
echo 2. Puxando eventuais atualizacoes do GitHub feitas no MacBook...
git pull origin master

echo.
echo ========================================================
echo   Iniciando a Super SofIA agora...
echo ========================================================
echo.
call iniciar_super_sofia.bat
