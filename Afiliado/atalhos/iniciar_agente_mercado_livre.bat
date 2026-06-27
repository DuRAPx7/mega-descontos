@echo off
setlocal
title Mega Descontos - Agente Mercado Livre
cd /d "%~dp0.."

set "PYTHON_EXE="
where py >nul 2>nul && set "PYTHON_EXE=py"
if "%PYTHON_EXE%"=="" where python >nul 2>nul && set "PYTHON_EXE=python"
if "%PYTHON_EXE%"=="" if exist "C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado.
  pause
  exit /b 1
)

"%PYTHON_EXE%" -c "import playwright" >nul 2>nul
if errorlevel 1 "%PYTHON_EXE%" -m pip install -r requirements.txt

if not exist "config\automation_agent.json" (
  echo Primeira configuracao do agente.
  "%PYTHON_EXE%" bot\mercadolivre_automation_agent.py --configure
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo Agente ativo. Esta janela pode ficar minimizada.
"%PYTHON_EXE%" bot\mercadolivre_automation_agent.py
pause
