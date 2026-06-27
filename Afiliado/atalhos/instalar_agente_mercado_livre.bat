@echo off
setlocal
title Instalar agente Mercado Livre
cd /d "%~dp0.."

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\MegaDescontosMercadoLivre.cmd"
set "AGENT=%CD%\atalhos\iniciar_agente_mercado_livre.bat"

echo.
echo Configurando o acesso do agente...
call "%AGENT%" --configure
if errorlevel 1 (
  echo.
  echo A configuracao nao foi concluida.
  pause
  exit /b 1
)

> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo start "Mega Descontos" /min cmd.exe /c call "%AGENT%"

echo.
echo Agente configurado para iniciar com o Windows.
echo Iniciando o agente agora...
start "Mega Descontos" /min cmd.exe /c call "%AGENT%"
pause
