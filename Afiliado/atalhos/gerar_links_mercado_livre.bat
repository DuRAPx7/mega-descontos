@echo off
title Mega Descontos - Gerar links Mercado Livre
cd /d "%~dp0.."

echo.
echo ===============================================
echo   Mega Descontos - Gerar links Mercado Livre
echo ===============================================
echo.
echo Entrada: bot\links_promocoes_potenciais.txt
echo Saida:   bot\links_afiliados_gerados.csv
echo Site:    http://127.0.0.1:8000
echo.
echo Antes de continuar:
echo 1. Execute abrir_gerador_mercado_livre.bat
echo 2. Faca login no Mercado Livre
echo 3. Deixe a pagina do gerador aberta
echo 4. Deixe o site local aberto se quiser publicar automaticamente
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

echo Verificando dependencia playwright...
"%PYTHON_EXE%" -c "import playwright" >nul 2>nul
if %errorlevel% neq 0 (
  echo Instalando dependencias...
  "%PYTHON_EXE%" -m pip install -r requirements.txt
)

"%PYTHON_EXE%" bot\mercadolivre_linkbuilder_bot.py --publish-site

echo.
echo Pronto. Confira o CSV em bot\links_afiliados_gerados.csv
pause

