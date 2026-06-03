#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt

[ -f .env ] && set -a && source .env && set +a

echo "Telegram Manager Bot → polling"
exec python backend/telegram_bot.py
