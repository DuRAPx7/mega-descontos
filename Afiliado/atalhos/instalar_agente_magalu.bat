@echo off
setlocal
title Instalar agente Magalu
cd /d "%~dp0.."

if not exist "config\automation_agent.json" (
  echo Configure primeiro a automacao completa.
  echo Execute: atalhos\instalar_automacao_completa.bat
  pause
  exit /b 1
)

set "PYTHON_EXE="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE py -c "import sys" >nul 2>nul && set "PYTHON_EXE=py"
if not defined PYTHON_EXE python -c "import sys" >nul 2>nul && set "PYTHON_EXE=python"

"%PYTHON_EXE%" bot\magalu_automation_agent.py --configure
if errorlevel 1 (
  pause
  exit /b 1
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\MegaDescontosMagalu.cmd"
set "AGENT=%CD%\atalhos\iniciar_agente_magalu.bat"

> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo start "Mega Descontos Magalu" /min cmd.exe /c call "%AGENT%"

echo Agente Magalu configurado para iniciar com o Windows.
start "Mega Descontos Magalu" /min cmd.exe /c call "%AGENT%"
pause
