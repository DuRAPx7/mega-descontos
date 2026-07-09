#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/iniciar_agente_mercado_livre_linux.sh" &
"$SCRIPT_DIR/iniciar_agente_amazon_linux.sh" &
"$SCRIPT_DIR/iniciar_agente_magalu_linux.sh" &

wait
