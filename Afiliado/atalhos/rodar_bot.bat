@echo off
setlocal
title Mega Descontos - Bot de ofertas
cd /d "%~dp0.."

set "SITE_URL=http://127.0.0.1:8000"
set "PYTHON_EXE="

echo.
echo ==========================================
echo   Mega Descontos - Bot de ofertas
echo ==========================================
echo.
echo Este atalho vai:
echo 1. Iniciar o site local, caso esteja fechado
echo 2. Rodar o bot usando o banco atual do site
echo 3. Abrir o site e a fila de revisao
echo 4. Abrir os arquivos de entrada e resultado
echo.

where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_EXE=py"

if "%PYTHON_EXE%"=="" (
  where python >nul 2>nul
  if %errorlevel%==0 set "PYTHON_EXE=python"
)

if "%PYTHON_EXE%"=="" (
  if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  )
)

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado. Instale Python ou execute pelo ambiente do Codex.
  pause
  exit /b 1
)

echo Verificando o site local...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%SITE_URL%/healthz' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if %errorlevel% neq 0 (
  echo Site fechado. Iniciando o servidor em uma janela minimizada...
  set "HOST=127.0.0.1"
  set "PORT=8000"
  set "RUN_INTERNAL_SCHEDULER=false"
  start "Mega Descontos - Servidor" /min "%PYTHON_EXE%" server.py

  echo Aguardando o servidor ficar pronto...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; 1..15 | ForEach-Object { try { Invoke-WebRequest -Uri '%SITE_URL%/healthz' -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if ($ok) { exit 0 } else { exit 1 }" >nul 2>nul
  if %errorlevel% neq 0 (
    echo Nao foi possivel iniciar o site local.
    pause
    exit /b 1
  )
) else (
  echo Site local ja esta aberto.
)

echo.
echo Rodando o bot e atualizando o banco do site...
"%PYTHON_EXE%" -c "from backend.server import run_bot_once; result=run_bot_once(); print('Ofertas geradas:', result.get('generatedOffers', 0)); print('Publicadas automaticamente:', result.get('autoPublished', 0)); print('Enviadas para revisao:', result.get('addedToReview', 0)); print(result.get('error', 'Bot concluido com sucesso.')); raise SystemExit(0 if result.get('ok') else 1)"
if %errorlevel% neq 0 (
  echo.
  echo O bot terminou com erro. O site sera aberto para voce conferir o status.
  start "" "%SITE_URL%/admin.html"
  if exist "bot\status.json" start "" notepad.exe "%CD%\bot\status.json"
  pause
  exit /b 1
)

echo.
echo Abrindo site, painel e arquivos de acompanhamento...
start "" "%SITE_URL%"
start "" "%SITE_URL%/admin-review.html"

if exist "bot\produtos_monitorados.json" start "" notepad.exe "%CD%\bot\produtos_monitorados.json"
if exist "bot\status.json" start "" notepad.exe "%CD%\bot\status.json"
if exist "bot\ofertas_geradas.json" start "" notepad.exe "%CD%\bot\ofertas_geradas.json"
if exist "bot\links_promocoes_potenciais.txt" start "" notepad.exe "%CD%\bot\links_promocoes_potenciais.txt"

echo.
echo Tudo pronto.
echo Site:   %SITE_URL%
echo Revisao: %SITE_URL%/admin-review.html
echo.
echo A janela minimizada do servidor deve permanecer aberta.
pause
