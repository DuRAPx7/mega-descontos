@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Automacao Shopee Online
cd /d "%~dp0.."

set "SITE_URL=https://mega-descontos.onrender.com"
set "ADMIN_URL=https://mega-descontos.onrender.com/login.html"

echo.
echo ==========================================
echo   Mega Descontos - Shopee Online
echo ==========================================
echo.
echo Destino: %SITE_URL%
echo Admin:   %ADMIN_URL%
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

if not exist "shopee_linkbuilder_url.txt" (
  >shopee_linkbuilder_url.txt echo https://affiliate.shopee.com.br/offer/custom_link
)

set /p SHOPEE_LINKBUILDER_URL=<shopee_linkbuilder_url.txt

echo Verificando navegador controlavel da Shopee...
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

  if "!BROWSER_EXE!"=="" if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  )

  if "!BROWSER_EXE!"=="" if exist "browser_path.txt" (
    set /p BROWSER_EXE=<browser_path.txt
  )

  if "!BROWSER_EXE!"=="" (
    echo Cole aqui o caminho completo do seu navegador .exe.
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
  start "" "!BROWSER_EXE!" --remote-debugging-port=9222 --user-data-dir="%CD%\browser-shopee-profile" "!SHOPEE_LINKBUILDER_URL!"
  echo.
  echo Entre na Shopee, deixe a tela do gerador aberta e pressione qualquer tecla.
  pause >nul
)

echo Buscando links de produtos da Shopee...
"%PYTHON_EXE%" bot\shopee_discovery_bot.py --limit 25
if %errorlevel% neq 0 (
  echo Nao consegui encontrar links de produtos da Shopee automaticamente.
  echo.
  echo Se quiser, edite manualmente:
  echo bot\links_shopee_promocoes_potenciais.txt
  echo.
  echo Ou adicione mais paginas em:
  echo bot\shopee_discovery_sources.txt
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$links = Get-Content 'bot\links_shopee_promocoes_potenciais.txt' | Where-Object { $_ -match '^https://.*shopee' -and $_ -notmatch '^\s*#' }; if ($links.Count -gt 0) { exit 0 } else { exit 1 }" >nul 2>nul
if %errorlevel% neq 0 (
  echo Nenhum link real de produto da Shopee foi encontrado.
  pause
  exit /b 1
)

echo Gerando links afiliados Shopee e cadastrando no site online...
"%PYTHON_EXE%" bot\shopee_linkbuilder_bot.py --publish-site --site-url "%SITE_URL%" --admin-user "%ADMIN_USERNAME%" --admin-password "%ADMIN_PASSWORD%" --linkbuilder-url "%SHOPEE_LINKBUILDER_URL%"
if %errorlevel% neq 0 (
  echo Falha ao gerar/cadastrar os links da Shopee.
  pause
  exit /b 1
)

echo.
echo Tudo pronto.
echo CSV gerado: bot\links_shopee_afiliados_gerados.csv
echo Site online: %SITE_URL%
echo.
pause

