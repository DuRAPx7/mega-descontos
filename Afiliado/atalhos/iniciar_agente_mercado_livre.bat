@echo off
setlocal
title Mega Descontos - Agente Mercado Livre
cd /d "%~dp0.."

set "PYTHON_EXE="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE py -c "import sys" >nul 2>nul && set "PYTHON_EXE=py"
if not defined PYTHON_EXE python -c "import sys" >nul 2>nul && set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado.
  pause
  exit /b 1
)

if /I "%~1"=="--configure" (
  "%PYTHON_EXE%" bot\mercadolivre_automation_agent.py --configure
  if errorlevel 1 exit /b 1
  exit /b 0
)

"%PYTHON_EXE%" -c "import playwright" >nul 2>nul
if errorlevel 1 (
  echo Instalando somente a dependencia Playwright...
  "%PYTHON_EXE%" -m pip install "playwright>=1.44,<2"
  if errorlevel 1 (
    echo Nao foi possivel instalar o Playwright.
    pause
    exit /b 1
  )
)

if not exist "config\automation_agent.json" (
  echo Primeira configuracao do agente.
  call "%~f0" --configure
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo Agente ativo. Esta janela pode ficar minimizada.
"%PYTHON_EXE%" bot\mercadolivre_automation_agent.py
pause
