@echo off
title Mega Descontos - Bot de ofertas
cd /d "%~dp0"

echo.
echo ==========================================
echo   Mega Descontos - Bot de ofertas
echo ==========================================
echo.
echo Entrada: bot\produtos_monitorados.json
echo Saida:   bot\ofertas_geradas.json
echo Site:    data\offers_db.json
echo.

set "PYTHON_EXE="

where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_EXE=py"

if "%PYTHON_EXE%"=="" (
  where python >nul 2>nul
  if %errorlevel%==0 set "PYTHON_EXE=python"
)

if "%PYTHON_EXE%"=="" (
  if exist "C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "PYTHON_EXE=C:\Users\Borges\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  )
)

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado. Instale Python ou execute pelo ambiente do Codex.
  pause
  exit /b 1
)

"%PYTHON_EXE%" bot\discount_bot.py --purge-missing

echo.
echo Se o servidor estiver aberto, atualize o site no navegador para ver as ofertas.
pause
