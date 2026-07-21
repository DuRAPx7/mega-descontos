@echo off
setlocal
title Mega Descontos - Iniciar todos os agentes
cd /d "%~dp0.."

echo ===============================================
echo  MEGA DESCONTOS - AGENTES WINDOWS
echo ===============================================
echo.
echo Este atalho abre os 3 agentes locais em janelas separadas:
echo - Mercado Livre
echo - Amazon
echo - Magalu
echo.
echo Deixe as janelas abertas ou minimizadas.
echo Depois entre no painel online e clique em:
echo   Rodar automacao completa
echo.

if not exist "config\automation_agent.json" (
  echo Configuracao principal nao encontrada.
  echo Vou abrir o instalador completo primeiro.
  echo.
  call "%CD%\atalhos\instalar_automacao_completa.bat"
)

echo Iniciando agente Mercado Livre...
start "Mega Descontos - Mercado Livre" cmd.exe /k call "%CD%\atalhos\iniciar_agente_mercado_livre.bat"

timeout /t 2 /nobreak >nul

echo Iniciando agente Amazon...
start "Mega Descontos - Amazon" cmd.exe /k call "%CD%\atalhos\iniciar_agente_amazon.bat"

timeout /t 2 /nobreak >nul

echo Iniciando agente Magalu...
start "Mega Descontos - Magalu" cmd.exe /k call "%CD%\atalhos\iniciar_agente_magalu.bat"

echo.
echo Pronto. Foram abertas 3 janelas de agentes.
echo Se alguma mostrar erro, tire print e mande para o Codex.
echo.
pause
