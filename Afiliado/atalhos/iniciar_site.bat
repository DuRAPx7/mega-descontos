@echo off
title Mega Descontos - Servidor local
cd /d "%~dp0.."

echo.
echo ==========================================
echo   Mega Descontos - Servidor local
echo ==========================================
echo.
echo Iniciando servidor local...
echo Pasta do projeto: %CD%
echo.
echo Site:  http://127.0.0.1:8000
echo Admin: http://127.0.0.1:8000/admin.html
echo Login: admin / admin123
echo.
echo Mantenha esta janela aberta enquanto usa o site.
echo Para parar o servidor, feche esta janela ou pressione CTRL+C.
echo.

start "" "http://127.0.0.1:8000"

set "HOST=127.0.0.1"
set "PORT=8000"

set "PYTHON_EXE="

if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE py -c "import sys" >nul 2>nul && set "PYTHON_EXE=py"
if not defined PYTHON_EXE python -c "import sys" >nul 2>nul && set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado. Instale Python ou execute pelo ambiente do Codex.
  pause
  exit /b 1
)

"%PYTHON_EXE%" server.py
