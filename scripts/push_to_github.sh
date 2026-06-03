#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="https://github.com/ergenbasymbekov-erg/shymkent-rabota-manager.git"

git remote remove origin 2>/dev/null || true
git remote add origin "$REPO"
git branch -M main

if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "Pushing with GITHUB_TOKEN…"
  git push "https://${GITHUB_TOKEN}@github.com/ergenbasymbekov-erg/shymkent-rabota-manager.git" main
else
  echo "GitHub токен керек (пароль емес):"
  echo "  https://github.com/settings/tokens → Generate → repo"
  echo ""
  read -rsp "Token: " TOKEN
  echo ""
  git push "https://${TOKEN}@github.com/ergenbasymbekov-erg/shymkent-rabota-manager.git" main
fi

echo ""
echo "✅ GitHub-қа жүктелді. Келесі: Render.com → Blueprint → shymkent-rabota-manager"
