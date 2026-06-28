@echo off
setlocal
title Mega Descontos - Agente Amazon
cd /d "%~dp0.."

set "PYTHON_EXE="
if exist "C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if "%PYTHON_EXE%"=="" where py >nul 2>nul && set "PYTHON_EXE=py"
if "%PYTHON_EXE%"=="" where python >nul 2>nul && set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado.
  pause
  exit /b 1
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

if not exist "config\amazon_automation_agent.json" (
  "%PYTHON_EXE%" bot\amazon_automation_agent.py --configure
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo Agente Amazon ativo. Esta janela pode ficar minimizada.
"%PYTHON_EXE%" bot\amazon_automation_agent.py
pause
