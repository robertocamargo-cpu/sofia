@echo off
chcp 65001 >nul
echo ========================================================
echo   PAUSANDO SUPER SOFIA NESTA MAQUINA (WINDOWS)
echo ========================================================
echo.

echo 1. Encerrando processo sofia_bot.py...
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%%' AND CommandLine LIKE '%%sofia_bot.py%%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host \"   Processo encerrado (PID $($_.ProcessId))\" }"

echo 2. Desabilitando tarefa agendada do Windows (GNRE)...
schtasks /change /tn "GNRE Automacao Pipeline" /disable >nul 2>&1

echo.
echo ========================================================
echo   [OK] Super SofIA PAUSADA com sucesso nesta maquina!
echo   Liberado para rodar e testar no MacBook sem conflito.
echo.
echo   Para voltar para este PC no futuro, basta executar:
echo   reativar_sofia.bat
echo ========================================================
pause
