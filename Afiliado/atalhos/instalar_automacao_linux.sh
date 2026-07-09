#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
SYSTEM_PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Criando ambiente Python local em .venv..."
  "$SYSTEM_PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Instalando dependencias Python no .venv..."
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "Instalando navegador Chromium do Playwright..."
"$PYTHON_BIN" -m playwright install chromium || true

echo "Configurando agente principal..."
if [[ ! -f "config/automation_agent.json" ]]; then
  "$PYTHON_BIN" bot/mercadolivre_automation_agent.py --configure
fi

echo "Configurando Amazon..."
if [[ ! -f "config/amazon_automation_agent.json" ]]; then
  "$PYTHON_BIN" bot/amazon_automation_agent.py --configure
fi

echo "Configurando Magalu..."
if [[ ! -f "config/magalu_automation_agent.json" ]]; then
  "$PYTHON_BIN" bot/magalu_automation_agent.py --configure
fi

chmod +x "$SCRIPT_DIR"/*_linux.sh
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/mega-descontos-mercado-livre.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Mega Descontos - Mercado Livre
Exec=$SCRIPT_DIR/iniciar_agente_mercado_livre_linux.sh
X-KDE-autostart-after=panel
DESKTOP

cat > "$AUTOSTART_DIR/mega-descontos-amazon.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Mega Descontos - Amazon
Exec=$SCRIPT_DIR/iniciar_agente_amazon_linux.sh
X-KDE-autostart-after=panel
DESKTOP

cat > "$AUTOSTART_DIR/mega-descontos-magalu.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Mega Descontos - Magalu
Exec=$SCRIPT_DIR/iniciar_agente_magalu_linux.sh
X-KDE-autostart-after=panel
DESKTOP

echo "Iniciando agentes agora..."
"$SCRIPT_DIR/iniciar_agente_mercado_livre_linux.sh" &
"$SCRIPT_DIR/iniciar_agente_amazon_linux.sh" &
"$SCRIPT_DIR/iniciar_agente_magalu_linux.sh" &

echo "Pronto. No KDE Plasma, os agentes tambem vao iniciar junto com a sessao."
echo "Na primeira abertura do navegador, faca login no Mercado Livre se o Link Builder pedir."
