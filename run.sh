#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt

[ -f .env ] && set -a && source .env && set +a

PORT="${PORT:-8790}"
echo "AI Recruiter v2 → http://localhost:${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --app-dir backend --reload
