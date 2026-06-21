@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Abrir gerador Shopee
cd /d "%~dp0.."

echo.
echo ==========================================
echo   Mega Descontos - Gerador Shopee
echo ==========================================
echo.

if not exist "shopee_linkbuilder_url.txt" (
  >shopee_linkbuilder_url.txt echo https://affiliate.shopee.com.br/offer/custom_link
)

set /p SHOPEE_LINKBUILDER_URL=<shopee_linkbuilder_url.txt

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
echo Entre na Shopee, deixe a tela do gerador aberta e execute:
echo gerar_links_shopee.bat
echo.
pause

