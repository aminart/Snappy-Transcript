# Snappy Transcript

Transcription en direct, **entièrement locale**, dans la suite Studio Dock : micro, son du PC (Teams, Jabber, navigateur…) ou
les deux → [faster-whisper](https://github.com/SYSTRAN/faster-whisper) → texte en direct, puis exports TXT / SRT / WAV,
identification des locuteurs et lecteur audio synchronisé mot à mot. Aucun audio n'est envoyé sur le réseau.

L'app suit le modèle d'app de la suite ([StudioDock-app-modele](https://github.com/aminart/StudioDock-app-modele)) : design
system Night Navy, lancement par Studio Dock (`--port`, `--no-browser`, `/health`), fabrication d'un `.exe`.
Elle remplace l'ancienne interface Streamlit (Audio Transcriber 1.5.7), dont elle reprend toutes les fonctions.

## Ce qu'elle fait

- **Sources** : microphone ; audio système Windows (WASAPI loopback, sans pilote virtuel) ; micro + audio système mélangés.
- **Transcription** : faster-whisper en local, CPU (`int8`) ou GPU NVIDIA (`float16`) avec repli automatique ; glossaire métier
  (mots favorisés pendant le décodage) ; blocs de 3 à 15 s avec recouvrement dédupliqué ; ignorer les silences (VAD).
- **Pause / reprise** sans fermer le WAV ; arrêt propre.
- **Exports immédiats** à l'arrêt : TXT, SRT bruts et WAV, écrits par le serveur même si le navigateur est fermé.
- **Locuteurs** (optionnel) : diarisation locale pyannote Community-1 lancée en arrière-plan après l'arrêt, avec progression ;
  exports « avec locuteurs » séparés.
- **Lecteur synchronisé** : clic sur une phrase pour y aller, phrase et mot lu surlignés ; bascule brute / avec locuteurs.
- **Reprise après coup** : locuteurs d'une réunion déjà enregistrée à partir d'un WAV et d'un SRT (chemins locaux).
- **Copie de récupération** du texte après chaque bloc, en cas de plantage.

## Où sont les données

Dossier `SnappyTranscript` dans `%LOCALAPPDATA%` (Windows), `~/Library/Application Support` (Mac) ou `~/.local/share` (Linux) ;
variable `SNAPPY_DATA` pour le déplacer.

| Chemin | Contenu |
|---|---|
| `settings.json` | Réglages mémorisés (modèle, GPU, glossaire…) |
| `sessions/<date>/` | `recording_….wav`, `transcript_…_raw.txt/.srt`, `transcript_…_diarized.txt/.srt` |
| `cache/transcript_<date>.txt` | Copie de récupération du texte, réécrite de façon atomique après chaque bloc |

Les sessions de l'ancien Audio Transcriber sont dans `AudioTranscriber\` (même dossier parent) : elles ne sont pas migrées.

## Développer

Prérequis : Python 3.11+, Node.js 20+.

```
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..
start_dev.bat
```

Sur Mac : `python backend/launcher.py --no-browser` dans un terminal, `cd frontend && npm run dev` dans un autre.
L'interface est sur http://localhost:5173 (l'API sur le port 8110). Tests : `python -m pytest`.

### Modèle faster-whisper

Un dossier de modèle déjà converti (CTranslate2), avec `config.json`, `model.bin` et `tokenizer.json`, par exemple
`faster-whisper-small`. L'app ne télécharge jamais rien : renseignez le dossier dans **Transcription › Dossier du modèle**.
Sans modèle, le moteur « Simulation » permet de tout essayer.

### GPU NVIDIA (Windows, optionnel)

`pip install -r backend/requirements-gpu.txt` installe cuBLAS 12 et cuDNN 9 dans le venv (pas de CUDA Toolkit système).
L'app les expose à son seul processus. **Automatique** essaie le GPU puis retombe sur le CPU ; **GPU NVIDIA** affiche une
erreur si CUDA n'est pas prêt ; **CPU** sert au diagnostic.

### Diarisation (optionnel)

`pip install -r backend/requirements-diarization.txt` (pyannote.audio et PyTorch : volumineux). Indiquez le dossier racine
d'un pipeline local qui contient `config.yaml` et ses modèles : l'app ne télécharge aucun modèle et n'a besoin d'aucun jeton.

> **Ne commitez jamais de jeton** (Hugging Face…) : `.gitignore` exclut `tokenpyannoteaudio.txt` et `*token*.txt`.

## Fabriquer l'exe

```
build_exe.bat                  exe avec transcription faster-whisper
build_exe.bat gpu              + runtimes CUDA
build_exe.bat diarisation      + pyannote / PyTorch (exe très gros)
```

L'exe est dans `dist\`. Sans option, la diarisation et le GPU ne sont pas inclus : l'interface le signale. Sur Mac :
`build_exe_mac.sh` (la capture du son du PC n'existe que sous Windows).

## L'ajouter à Studio Dock

Dans Studio Dock, **Préparer pour l'équipe › Applications** : type « S'ouvre dans le navigateur » (et non plus une app
tierce sur `localhost`), identifiant `snappy-transcript`, programme `SnappyTranscript`, port **8110**, icône
`icone/app.svg`, puis la fiche (à quoi elle sert, prise en main). Déposez `SnappyTranscript-0.1.0.exe` dans le sous-dossier
de l'app du dossier de l'équipe. Nouvelle version : noter les changements dans `CHANGELOG.md`,
`python scripts/bump_version.py 0.2.0`, fabriquer l'exe.

## Organisation du code

| Chemin | Rôle |
|---|---|
| `backend/app_info.py`, `launcher.py`, `studiodock_ia.py` | Contrat de Studio Dock, identité : **à ne pas modifier** (modèle de la suite) |
| `backend/main.py` | Serveur : `/health`, API, interface compilée, arrêt propre de la session en cours |
| `backend/snappy/api.py` | Routes `/api/…` |
| `backend/snappy/service.py` | Session active, exports, diarisation en arrière-plan, reprise après coup |
| `backend/snappy/session.py` | Capture → WAV + blocs → STT (threads), pause, déduplication du recouvrement |
| `backend/snappy/audio/`, `transcription/`, `diarization.py` | Sources audio, faster-whisper / CUDA, pyannote |
| `frontend/src/` | Interface React + Tailwind + Night Navy |
| `tests/` | Contrat Studio Dock, API de bout en bout (source factice), session, exports, diarisation |
