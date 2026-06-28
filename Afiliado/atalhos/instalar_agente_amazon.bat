@echo off
setlocal
title Instalar agente Amazon
cd /d "%~dp0.."

if not exist "config\automation_agent.json" (
  echo Configure primeiro o agente principal do Mercado Livre.
  echo Execute: atalhos\instalar_agente_mercado_livre.bat
  pause
  exit /b 1
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\MegaDescontosAmazon.cmd"
set "AGENT=%CD%\atalhos\iniciar_agente_amazon.bat"

> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo start "Mega Descontos Amazon" /min cmd.exe /c call "%AGENT%"

echo Agente Amazon configurado para iniciar com o Windows.
echo Tag utilizada: megadesco0304-20
start "Mega Descontos Amazon" /min cmd.exe /c call "%AGENT%"
pause
