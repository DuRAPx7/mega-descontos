@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Amazon Online
cd /d "%~dp0.."

set "SITE_URL=https://mega-descontos.onrender.com"
set "ADMIN_URL=https://mega-descontos.onrender.com/login.html"
set "DEFAULT_AMAZON_TAG=megadesco0304-20"

echo.
echo ==================================================
echo   Mega Descontos - Amazon Online
echo ==================================================
echo.
echo Destino: %SITE_URL%
echo Admin:   %ADMIN_URL%
echo.
echo Este bot vai:
echo 1. Abrir a Amazon em um navegador controlavel
echo 2. Procurar ofertas em paginas publicas da Amazon
echo 3. Montar links com sua tag de associado
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

echo.
set /p AMAZON_TAG=Tag Amazon Associados [%DEFAULT_AMAZON_TAG%]: 
if "%AMAZON_TAG%"=="" set "AMAZON_TAG=%DEFAULT_AMAZON_TAG%"

echo Verificando navegador controlavel da Amazon...
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
  start "" "!BROWSER_EXE!" --remote-debugging-port=9222 --user-data-dir="%CD%\browser-amazon-profile" "https://www.amazon.com.br/deals"
  echo.
  echo Se aparecer login/captcha na Amazon, resolva e pressione qualquer tecla.
  pause >nul
)

echo Buscando ofertas e cadastrando no site online...
"%PYTHON_EXE%" bot\amazon_discovery_bot.py --publish-site --site-url "%SITE_URL%" --admin-user "%ADMIN_USERNAME%" --admin-password "%ADMIN_PASSWORD%" --associate-tag "%AMAZON_TAG%"
if %errorlevel% neq 0 (
  echo Falha ao buscar/cadastrar ofertas da Amazon.
  pause
  exit /b 1
)

echo.
echo Tudo pronto.
echo CSV gerado: bot\links_amazon_afiliados_gerados.csv
echo Site online: %SITE_URL%
echo.
pause
