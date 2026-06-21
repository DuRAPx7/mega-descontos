@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Automacao Mercado Livre
cd /d "%~dp0"

echo.
echo ==================================================
echo   Mega Descontos - Automacao Mercado Livre
echo ==================================================
echo.
echo Este bot vai:
echo 1. Gerar promocoes em potencial
echo 2. Enviar os links para o gerador do Mercado Livre
echo 3. Salvar o CSV com links afiliados
echo 4. Cadastrar automaticamente no site local
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
  if %errorlevel% neq 0 (
    echo Nao consegui instalar as dependencias.
    pause
    exit /b 1
  )
)

echo Verificando site local...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/healthz' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if %errorlevel% neq 0 (
  echo Site local nao esta aberto. Iniciando em segundo plano...
  set "HOST=127.0.0.1"
  set "PORT=8000"
  start "Mega Descontos - Servidor" /min "%PYTHON_EXE%" server.py
  timeout /t 4 /nobreak >nul
)

echo Gerando arquivo de promocoes em potencial...
"%PYTHON_EXE%" bot\discount_bot.py --purge-missing
if %errorlevel% neq 0 (
  echo Falha ao gerar as promocoes em potencial.
  pause
  exit /b 1
)

if not exist "bot\links_promocoes_potenciais.txt" (
  echo O arquivo bot\links_promocoes_potenciais.txt nao foi encontrado.
  pause
  exit /b 1
)

for %%A in ("bot\links_promocoes_potenciais.txt") do set "CANDIDATE_SIZE=%%~zA"
if "%CANDIDATE_SIZE%"=="0" (
  echo Nenhum link novo de promocao em potencial foi encontrado agora.
  pause
  exit /b 0
)

echo Verificando navegador controlavel do Mercado Livre...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if %errorlevel% neq 0 (
  echo Nao encontrei navegador controlavel. Vou abrir agora.
  set "BROWSER_EXE="

  if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "browser_path.txt" (
    set /p BROWSER_EXE=<browser_path.txt
  )

  if "!BROWSER_EXE!"=="" (
    echo Navegador Brave, Chrome ou Edge nao encontrado.
    echo Caminhos testados:
    echo - %LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe
    echo - %ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe
    echo - %LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
    echo - %ProgramFiles%\Google\Chrome\Application\chrome.exe
    echo - %ProgramFiles%\Microsoft\Edge\Application\msedge.exe
    echo.
    echo Cole aqui o caminho completo do seu navegador .exe.
    echo Exemplo: C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
    set /p BROWSER_EXE=Caminho do navegador: 
  )

  set "BROWSER_EXE=!BROWSER_EXE:"=!"

  if not exist "!BROWSER_EXE!" (
    echo O caminho informado nao existe:
    echo !BROWSER_EXE!
    echo.
    echo Dica: abra o navegador, clique com botao direito no icone da barra de tarefas,
    echo depois botao direito no nome do navegador, Propriedades, e copie o Destino.
    pause
    exit /b 1
  )

  >browser_path.txt echo !BROWSER_EXE!

  echo Abrindo navegador: !BROWSER_EXE!
  start "" "!BROWSER_EXE!" --remote-debugging-port=9222 --user-data-dir="%CD%\browser-ml-profile" "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
  echo.
  echo Faca login no Mercado Livre, deixe a pagina do gerador aberta e pressione qualquer tecla.
  pause >nul
)

echo Gerando links afiliados e cadastrando no site...
"%PYTHON_EXE%" bot\mercadolivre_linkbuilder_bot.py --publish-site
if %errorlevel% neq 0 (
  echo Falha ao gerar/cadastrar os links do Mercado Livre.
  pause
  exit /b 1
)

echo.
echo Tudo pronto.
echo CSV gerado: bot\links_afiliados_gerados.csv
echo Site local: http://127.0.0.1:8000
echo.
pause
