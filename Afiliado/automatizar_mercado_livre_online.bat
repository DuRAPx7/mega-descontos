@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Automacao Mercado Livre Online
cd /d "%~dp0"

set "SITE_URL=https://mega-descontos.onrender.com"
set "ADMIN_URL=https://mega-descontos.onrender.com/login.html"

echo.
echo ==================================================
echo   Mega Descontos - Mercado Livre Online
echo ==================================================
echo.
echo Destino: %SITE_URL%
echo Admin:   %ADMIN_URL%
echo.
echo Este bot vai:
echo 1. Gerar promocoes em potencial
echo 2. Enviar os links para o gerador do Mercado Livre
echo 3. Salvar o CSV com links afiliados
echo 4. Cadastrar automaticamente no site online
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

echo Acordando o site online...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%SITE_URL%/healthz' -UseBasicParsing -TimeoutSec 45 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if %errorlevel% neq 0 (
  echo Nao consegui acessar %SITE_URL%/healthz agora.
  echo Abra o site no navegador e tente novamente em alguns segundos.
  pause
  exit /b 1
)

echo.
set /p ADMIN_USERNAME=Usuario admin do site online: 
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Read-Host 'Senha admin do site online' -AsSecureString; $b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($p); try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }"`) do set "ADMIN_PASSWORD=%%P"

if "%ADMIN_USERNAME%"=="" (
  echo Usuario admin vazio.
  pause
  exit /b 1
)

if "%ADMIN_PASSWORD%"=="" (
  echo Senha admin vazia.
  pause
  exit /b 1
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
    echo.
    echo Cole aqui o caminho completo do seu navegador .exe.
    echo Exemplo: C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
    set /p BROWSER_EXE=Caminho do navegador: 
  )

  set "BROWSER_EXE=!BROWSER_EXE:"=!"

  if not exist "!BROWSER_EXE!" (
    echo O caminho informado nao existe:
    echo !BROWSER_EXE!
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

echo Gerando links afiliados e cadastrando no site online...
"%PYTHON_EXE%" bot\mercadolivre_linkbuilder_bot.py --publish-site --site-url "%SITE_URL%" --admin-user "%ADMIN_USERNAME%" --admin-password "%ADMIN_PASSWORD%"
if %errorlevel% neq 0 (
  echo Falha ao gerar/cadastrar os links do Mercado Livre.
  pause
  exit /b 1
)

echo.
echo Tudo pronto.
echo CSV gerado: bot\links_afiliados_gerados.csv
echo Site online: %SITE_URL%
echo.
pause
