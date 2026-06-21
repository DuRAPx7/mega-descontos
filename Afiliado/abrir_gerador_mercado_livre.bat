@echo off
setlocal EnableDelayedExpansion
title Mega Descontos - Abrir gerador Mercado Livre
cd /d "%~dp0"

echo.
echo ===============================================
echo   Mega Descontos - Gerador Mercado Livre
echo ===============================================
echo.
echo Abrindo navegador em modo controlavel.
echo Se pedir login, entre no Mercado Livre e deixe a pagina aberta.
echo.

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
echo Depois que a pagina carregar e voce estiver logado, execute:
echo gerar_links_mercado_livre.bat
echo.
pause
