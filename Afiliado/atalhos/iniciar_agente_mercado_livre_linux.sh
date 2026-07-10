#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

if [[ ! -f "config/automation_agent.json" ]]; then
  "$PYTHON_BIN" bot/mercadolivre_automation_agent.py --configure
fi

"$PYTHON_BIN" bot/mercadolivre_automation_agent.py
