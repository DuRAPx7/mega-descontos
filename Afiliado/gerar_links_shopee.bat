@echo off
title Mega Descontos - Gerar links Shopee
cd /d "%~dp0"

echo.
echo ==========================================
echo   Mega Descontos - Gerar links Shopee
echo ==========================================
echo.
echo Entrada: bot\links_shopee_promocoes_potenciais.txt
echo Saida:   bot\links_shopee_afiliados_gerados.csv
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
  echo Python nao encontrado.
  pause
  exit /b 1
)

if not exist "bot\links_shopee_promocoes_potenciais.txt" (
  echo Crie o arquivo bot\links_shopee_promocoes_potenciais.txt com um link Shopee por linha.
  pause
  exit /b 1
)

echo Verificando dependencia playwright...
"%PYTHON_EXE%" -c "import playwright" >nul 2>nul
if %errorlevel% neq 0 (
  echo Instalando dependencias...
  "%PYTHON_EXE%" -m pip install -r requirements.txt
)

set "SHOPEE_LINKBUILDER_URL=https://affiliate.shopee.com.br/"
if exist "shopee_linkbuilder_url.txt" (
  set /p SHOPEE_LINKBUILDER_URL=<shopee_linkbuilder_url.txt
)

"%PYTHON_EXE%" bot\shopee_linkbuilder_bot.py --linkbuilder-url "%SHOPEE_LINKBUILDER_URL%"

echo.
echo Pronto. Confira o CSV em bot\links_shopee_afiliados_gerados.csv
pause
