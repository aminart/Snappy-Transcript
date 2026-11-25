#!/bin/sh
# Installe Snappy Transcript pour le tester sur un Mac (ou Linux), une seule fois, puis ./start.sh.
#
#   ./install.sh                          installation normale (transcription en direct et depuis un fichier)
#   ./install.sh intervenants             ajoute l'identification des intervenants (PyTorch, ~2 Go)
#   ./install.sh /chemin/companyCA.crt    derrière le proxy de l'entreprise (certificat)
#   (les deux options peuvent se combiner, dans n'importe quel ordre)
#
# Prérequis : Python 3.11 à 3.13 et Node.js 20 ou plus. Sur Mac, le plus simple :
#   - Python : https://www.python.org/downloads/macos/  (ou : brew install python@3.12)
#   - Node.js : https://nodejs.org/  (version LTS)     (ou : brew install node)
# Si le fichier n'est pas exécutable (dossier téléchargé en .zip) : sh install.sh
set -e
cd "$(dirname "$0")"

INTERVENANTS=""
CERT=""
for arg in "$@"; do
  case "$arg" in
    intervenants|--intervenants) INTERVENANTS=1 ;;
    *) CERT="$arg" ;;
  esac
done

erreur() { echo; echo "L'installation n'a pas abouti : $1"; exit 1; }

if [ -n "$CERT" ]; then
  [ -f "$CERT" ] || erreur "certificat introuvable : $CERT"
  export PIP_CERT="$CERT"            # lu par pip (fonctionne aussi avec un chemin contenant des espaces)
  export NODE_EXTRA_CA_CERTS="$CERT" # lu par npm
fi

SYSTEME="$(uname -s)"
PROCESSEUR="$(uname -m)"

echo
echo "=== Snappy Transcript : installation ==="
echo

# --- Python 3.11 à 3.13 : on prend la version la plus récente disponible -------------------------------------
PYTHON=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)' 2>/dev/null; then
    PYTHON="$c"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11, 3.12 ou 3.13 est nécessaire."
  if command -v python3 >/dev/null 2>&1; then echo "Version trouvée : $(python3 --version 2>&1) (celle du Mac est trop ancienne)."; fi
  echo "Installez-le depuis https://www.python.org/downloads/macos/ (ou : brew install python@3.12), puis relancez."
  exit 1
fi

# --- Node.js 20 ou plus (pour fabriquer l'interface) ---------------------------------------------------------
command -v npm >/dev/null 2>&1 || erreur "Node.js est introuvable. Installez la version LTS depuis https://nodejs.org/ (ou : brew install node)."
NODE_MAJ="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[ "$NODE_MAJ" -ge 20 ] 2>/dev/null || erreur "Node.js 20 ou plus est nécessaire (version trouvée : $(node --version 2>/dev/null))."

echo "Python : $($PYTHON --version 2>&1) · Node.js : $(node --version) · $SYSTEME $PROCESSEUR"
echo

# --- Identification des intervenants : PyTorch récent, absent des Mac Intel ----------------------------------
if [ -n "$INTERVENANTS" ] && [ "$SYSTEME" = "Darwin" ] && [ "$PROCESSEUR" = "x86_64" ]; then
  echo "Note : l'identification des intervenants n'est pas disponible sur un Mac à processeur Intel"
  echo "(PyTorch n'y est plus mis à jour). La transcription, elle, fonctionne : on continue sans."
  echo
  INTERVENANTS=""
fi

# Un environnement créé avec une autre version de Python est refait
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)' 2>/dev/null; then
  echo "Ancien environnement Python incompatible : il est recréé."
  rm -rf .venv
fi

echo "[1/3] Environnement Python (.venv)…"
[ -x .venv/bin/python ] || "$PYTHON" -m venv .venv || erreur "impossible de créer l'environnement Python."

echo "[2/3] Dépendances Python (transcription comprise, quelques minutes la première fois)…"
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements-dev.txt || erreur "les dépendances Python ne se sont pas installées (voir le message ci-dessus)."
if [ -n "$INTERVENANTS" ]; then
  echo "      + identification des intervenants (PyTorch, plusieurs centaines de Mo)…"
  .venv/bin/python -m pip install -r backend/requirements-diarization.txt || erreur "l'identification des intervenants ne s'est pas installée."
fi

echo "[3/3] Interface…"
if ! (cd frontend && npm ci && npm run build); then
  echo
  echo "Si npm parle de ENOTFOUND ou de proxy : le registre npm n'est pas joignable depuis ce poste"
  echo "(derrière le proxy de l'entreprise : ./install.sh /chemin/companyCA.crt)."
  erreur "l'interface n'a pas pu être fabriquée."
fi
chmod +x start.sh 2>/dev/null || true

echo
echo "Installation terminée. Lancez ./start.sh pour ouvrir Snappy Transcript."
echo "Sans modèle de transcription : Réglages avancés › Moteur « Simulation »."
if [ "$SYSTEME" = "Darwin" ]; then
  echo
  echo "Sur Mac :"
  echo "  - au premier enregistrement, macOS demande l'accès au micro pour le Terminal : acceptez"
  echo "    (sinon : Réglages Système › Confidentialité et sécurité › Microphone › Terminal) ;"
  echo "  - « En direct » avec votre voix et « Depuis un fichier » fonctionnent ; le son d'une application"
  echo "    ou de tout l'ordinateur ne peut être capté que sous Windows."
fi
