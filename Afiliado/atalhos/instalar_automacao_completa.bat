@echo off
setlocal
title Mega Descontos - Configurar automacao completa
cd /d "%~dp0.."

set "PYTHON_EXE="
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ML_LAUNCHER=%STARTUP%\MegaDescontosMercadoLivre.cmd"
set "AMAZON_LAUNCHER=%STARTUP%\MegaDescontosAmazon.cmd"
set "MAGALU_LAUNCHER=%STARTUP%\MegaDescontosMagalu.cmd"
set "ML_AGENT=%CD%\atalhos\iniciar_agente_mercado_livre.bat"
set "AMAZON_AGENT=%CD%\atalhos\iniciar_agente_amazon.bat"
set "MAGALU_AGENT=%CD%\atalhos\iniciar_agente_magalu.bat"

echo.
echo ==================================================
echo   Mega Descontos - Automacao completa
echo ==================================================
echo.
echo Esta configuracao e feita somente uma vez.
echo Depois, o botao "Rodar bot agora" do painel executa
echo a coleta, gera os links e publica as ofertas.
echo.

if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE py -c "import sys" >nul 2>nul && set "PYTHON_EXE=py"
if not defined PYTHON_EXE python -c "import sys" >nul 2>nul && set "PYTHON_EXE=python"

if "%PYTHON_EXE%"=="" (
  echo Python nao encontrado.
  pause
  exit /b 1
)

echo Instalando as dependencias necessarias...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo Nao foi possivel instalar as dependencias.
  pause
  exit /b 1
)

echo.
echo Informe o mesmo usuario e senha usados no painel online.
call "%ML_AGENT%" --configure
if %errorlevel% neq 0 (
  echo A configuracao do Mercado Livre nao foi concluida.
  pause
  exit /b 1
)

"%PYTHON_EXE%" bot\amazon_automation_agent.py --configure
if %errorlevel% neq 0 (
  echo A configuracao da Amazon nao foi concluida.
  pause
  exit /b 1
)

"%PYTHON_EXE%" bot\magalu_automation_agent.py --configure
if %errorlevel% neq 0 (
  echo A configuracao do Magalu nao foi concluida.
  pause
  exit /b 1
)

if not exist "%STARTUP%" mkdir "%STARTUP%"

> "%ML_LAUNCHER%" echo @echo off
>> "%ML_LAUNCHER%" echo start "Mega Descontos - Mercado Livre" /min cmd.exe /c call "%ML_AGENT%"

> "%AMAZON_LAUNCHER%" echo @echo off
>> "%AMAZON_LAUNCHER%" echo start "Mega Descontos - Amazon" /min cmd.exe /c call "%AMAZON_AGENT%"

> "%MAGALU_LAUNCHER%" echo @echo off
>> "%MAGALU_LAUNCHER%" echo start "Mega Descontos - Magalu" /min cmd.exe /c call "%MAGALU_AGENT%"

echo.
echo Iniciando os agentes agora...
start "Mega Descontos - Mercado Livre" /min cmd.exe /c call "%ML_AGENT%"
start "Mega Descontos - Amazon" /min cmd.exe /c call "%AMAZON_AGENT%"
start "Mega Descontos - Magalu" /min cmd.exe /c call "%MAGALU_AGENT%"

echo.
echo Configuracao concluida.
echo.
echo Os agentes agora iniciam automaticamente com o Windows.
echo Na primeira janela do Mercado Livre, faca login uma vez.
echo Depois disso, use somente o botao "Rodar bot agora" no painel.
echo.
start "" "https://mega-descontos.onrender.com/admin.html"
pause
