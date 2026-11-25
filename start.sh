#!/bin/sh
# Lance Snappy Transcript et ouvre le navigateur (http://127.0.0.1:8110). Ctrl+C pour arrêter.
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Snappy Transcript n'est pas encore installé : lancez d'abord ./install.sh."; exit 1; }
[ -f frontend/dist/index.html ] || (cd frontend && npm run build)
exec .venv/bin/python backend/launcher.py "$@"
