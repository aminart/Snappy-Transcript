#!/bin/sh
# Lance Snappy Transcript (Mac ou Linux) et ouvre le navigateur sur http://127.0.0.1:8110.
# Laissez cette fenêtre ouverte pendant l'utilisation ; Ctrl+C pour arrêter.
#   ./start.sh                  port 8110
#   ./start.sh --port 8120      autre port (si 8110 est déjà pris)
# Si le fichier n'est pas exécutable : sh start.sh
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "Snappy Transcript n'est pas encore installé : lancez d'abord ./install.sh"; exit 1; }

# Interface absente, ou plus ancienne que ses sources (après un git pull) : on la refabrique
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html 2>/dev/null | head -1)" ]; then
  echo "Mise à jour de l'interface…"
  (cd frontend && npm run build) || { echo "L'interface n'a pas pu être fabriquée : relancez ./install.sh"; exit 1; }
fi

echo "Snappy Transcript démarre… (le navigateur s'ouvre tout seul ; Ctrl+C pour arrêter)"
exec .venv/bin/python backend/launcher.py "$@"
