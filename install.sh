#!/bin/sh
# Installe Snappy Transcript pour le tester (Mac ou Linux), une seule fois, puis ./start.sh.
#   ./install.sh                       installation normale
#   ./install.sh /chemin/companyCA.crt derrière le proxy de l'entreprise
# Prérequis : Python 3.11+ (python3) et Node.js 20+.
set -e
cd "$(dirname "$0")"
CERT="${1:-}"
PIP_CERT=""
if [ -n "$CERT" ]; then
  [ -f "$CERT" ] || { echo "Certificat introuvable : $CERT"; exit 1; }
  PIP_CERT="--cert $CERT"
  export NODE_EXTRA_CA_CERTS="$CERT"
fi
command -v python3 >/dev/null || { echo "Python 3.11 ou plus est nécessaire (python3 introuvable)."; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11 ou plus est nécessaire ($(python3 --version))."; exit 1; }
command -v npm >/dev/null || { echo "Node.js 20 ou plus est nécessaire (npm introuvable)."; exit 1; }

echo "[1/3] Environnement Python (.venv)…"
[ -x .venv/bin/python ] || python3 -m venv .venv
echo "[2/3] Dépendances Python (transcription comprise)…"
.venv/bin/python -m pip install --upgrade pip $PIP_CERT >/dev/null
.venv/bin/python -m pip install -r requirements-dev.txt $PIP_CERT
echo "[3/3] Interface…"
(cd frontend && npm ci && npm run build)
echo
echo "Installation terminée. Lancez ./start.sh pour ouvrir Snappy Transcript."
echo "Sans modèle de transcription : Réglages avancés, Moteur « Simulation »."
