@echo off
setlocal
title Instalar agente Mercado Livre
cd /d "%~dp0.."

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\MegaDescontosMercadoLivre.cmd"
set "AGENT=%CD%\atalhos\iniciar_agente_mercado_livre.bat"

> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo start "Mega Descontos" /min "%AGENT%"

echo Agente configurado para iniciar com o Windows.
echo Na primeira execucao, informe seu usuario e senha administrativa.
start "Mega Descontos" /min "%AGENT%"
pause
