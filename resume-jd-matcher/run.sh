#!/usr/bin/env bash
# One-command launcher: sets up the Python env (first run), builds the web UI and
# serves everything at http://127.0.0.1:${PORT:-8010}
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8010}"

cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  echo "==> Creating Python virtualenv (backend/.venv)"
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

cd "$ROOT/web"
if [ ! -d node_modules ]; then
  echo "==> Installing web dependencies"
  npm install --silent
fi
echo "==> Building web UI"
npm run build --silent

cd "$ROOT/backend"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "==> ANTHROPIC_API_KEY found: extraction + skill-gap chain will use Claude (${LLM_MODEL:-claude-opus-5-5})"
else
  echo "==> No ANTHROPIC_API_KEY: running in offline mode (heuristic extractor + offline chain)"
fi
echo "==> Starting API + UI on http://127.0.0.1:${PORT}  (first start downloads/loads embedding models)"
export TOKENIZERS_PARALLELISM=false
exec ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
