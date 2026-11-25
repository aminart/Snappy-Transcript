# Snappy Transcript

Transcription **entièrement locale**, dans la suite Studio Dock : en direct (micro, son du PC — Teams, Jabber, navigateur… —
ou les deux) ou depuis un fichier audio ou vidéo → [faster-whisper](https://github.com/SYSTRAN/faster-whisper) → texte, puis exports TXT / SRT / WAV,
identification des locuteurs et lecteur audio synchronisé mot à mot. Aucun audio n'est envoyé sur le réseau.

L'app suit le modèle d'app de la suite ([StudioDock-app-modele](https://github.com/aminart/StudioDock-app-modele)) : design
system Night Navy, lancement par Studio Dock (`--port`, `--no-browser`, `/health`), fabrication d'un `.exe`.
Elle remplace l'ancienne interface Streamlit (Audio Transcriber 1.5.7), dont elle reprend toutes les fonctions.

## Ce qu'elle fait

- **Sources** : microphone ; audio système Windows (WASAPI loopback, sans pilote virtuel) ; micro + audio système mélangés.
- **Transcription** : faster-whisper en local, CPU (`int8`) ou GPU NVIDIA (`float16`) avec repli automatique ; glossaire métier
  (mots favorisés pendant le décodage) ; blocs de 3 à 15 s avec recouvrement dédupliqué ; ignorer les silences (VAD).
- **Fichiers audio et vidéo**, dans leur format d'origine, sans conversion : MP3, WAV, M4A, AAC, FLAC, OGG, Opus, WMA, AIFF,
  AMR, AC3… et les vidéos MP4, MOV, MKV, AVI, WMV, WebM, MPEG, TS, 3GP, FLV (la piste son est lue directement). Le fichier est
  glissé dans la page, ou indiqué par son chemin sur le PC (très gros fichiers : lu sur place, sans copie). Progression avec
  temps restant, pause, arrêt en gardant le texte déjà obtenu. Les longs fichiers sont traités par fenêtres de 10 minutes
  coupées dans un silence : la mémoire reste bornée, même pour une réunion de plusieurs heures.
- **Pause / reprise** sans fermer le WAV ; arrêt propre.
- **Exports immédiats** à l'arrêt : TXT, SRT bruts et WAV, écrits par le serveur même si le navigateur est fermé.
- **Locuteurs** (optionnel) : diarisation locale pyannote Community-1 lancée en arrière-plan après l'arrêt, avec progression ;
  exports « avec locuteurs » séparés.
- **Lecteur synchronisé** : clic sur une phrase pour y aller, phrase et mot lu surlignés ; bascule brute / avec locuteurs.
- **Reprise après coup** : locuteurs d'une réunion déjà enregistrée à partir d'un WAV et d'un SRT (chemins locaux).
- **Résultat exploitable** : copier le texte en un clic, corriger une phrase, nommer les intervenants ; les fichiers
  téléchargés reprennent les corrections et les noms.
- **Historique** : chaque session est enregistrée (texte, audio, intervenants) et peut être rouverte plus tard.
- **Vu-mètre** pendant l'enregistrement et alerte si aucun son n'arrive.
- **Copie de récupération** du texte après chaque bloc, en cas de plantage.

## Où sont les données

Dossier `SnappyTranscript` dans `%LOCALAPPDATA%` (Windows), `~/Library/Application Support` (Mac) ou `~/.local/share` (Linux) ;
variable `SNAPPY_DATA` pour le déplacer.

| Chemin | Contenu |
|---|---|
| `settings.json` | Réglages mémorisés (modèle, GPU, glossaire…) |
| `sessions/<date>/` | `recording_….wav`, exports `transcript_…_raw.txt/.srt` et `…_diarized.txt/.srt`, texte de travail `transcript_raw.json` / `transcript_diarized.json` (avec les horaires des mots), fiche `session.json` (historique, noms des intervenants) |
| `cache/transcript_<date>.txt` | Copie de récupération du texte, réécrite de façon atomique après chaque bloc |
| `uploads/` | Fichiers glissés dans la page, le temps de leur lecture (supprimés ensuite, et au bout d'un jour au plus tard) |

Les sessions de l'ancien Audio Transcriber sont dans `AudioTranscriber\` (même dossier parent) : elles ne sont pas migrées.

## Tester rapidement

Prérequis : Python 3.11+ et Node.js 20+.

1. Double-cliquez sur **`install.bat`** (une seule fois). Derrière le proxy de l'entreprise, lancez-le depuis une invite
   de commandes avec le certificat : `install.bat "C:\…\companyCA.crt"`.
2. Double-cliquez sur **`start.bat`** : le navigateur s'ouvre sur http://127.0.0.1:8110. Fermez la fenêtre noire pour
   arrêter l'application.

Sans modèle de transcription, choisissez **Réglages avancés › Moteur › Simulation** pour tout essayer.

**Identifier les intervenants** (optionnel, plus de 1 Go) : `install.bat intervenants`, puis, dans la section
Intervenants, le dossier d'un pipeline pyannote déjà sur le disque (par exemple
`speaker-diarization-community-1`, avec `config.yaml`, `embedding\`, `segmentation\` et `plda\`). L'app ne
télécharge aucun modèle et n'a besoin d'aucun jeton.

Le design system Night Navy est inclus dans le dépôt (`frontend/vendor/night-navy-1.2.1.tgz`) : npm n'a pas besoin
d'accéder à GitHub, souvent bloqué sur le réseau de l'entreprise. Pour passer à une nouvelle version de Night Navy :
`npm pack` dans le dépôt Design-system- à la bonne étiquette, remplacer le .tgz, mettre à jour `package.json`, puis
`npm install`. Sur Mac :
`./install.sh` puis `./start.sh`.

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

**Dans l'équipe, rien à régler** : le modèle est fourni par Studio Dock. L'administratrice le déclare une fois dans
Préparer pour l'équipe et dépose son .zip dans le dossier partagé ; Studio Dock l'installe chez chacun, et Snappy le lit
avec `studiodock_ia.transcription()` (voir le README de Studio Dock, « Modèle de transcription de l'équipe »).

Sans Studio Dock, ou pour essayer un autre modèle : **Transcription › Utiliser un autre modèle sur ce poste**, puis le
dossier d'un modèle déjà converti (CTranslate2 : `config.json`, `model.bin`, `tokenizer.json`), par exemple
`faster-whisper-small`. L'app ne télécharge jamais rien. Sans modèle, le moteur « Simulation » permet de tout essayer.

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
| `backend/snappy/media.py`, `file_session.py` | Lecture des fichiers (PyAV / FFmpeg) → WAV 16 kHz, transcription d'un fichier |
| `backend/snappy/audio/`, `transcription/`, `diarization.py` | Sources audio, faster-whisper / CUDA, pyannote |
| `frontend/src/` | Interface React + Tailwind + Night Navy |
| `tests/` | Contrat Studio Dock, API de bout en bout (source factice), session, exports, diarisation |
