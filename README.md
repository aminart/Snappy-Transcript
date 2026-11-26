# Snappy Transcript

Transcription **entièrement locale**, dans la suite Studio Dock : en direct (micro, son du PC — Teams, Jabber, navigateur… —
ou les deux) ou depuis un fichier audio ou vidéo → [faster-whisper](https://github.com/SYSTRAN/faster-whisper) → texte, puis exports TXT / SRT / WAV,
identification des locuteurs et lecteur audio synchronisé mot à mot. Aucun audio n'est envoyé sur le réseau.

L'app suit le modèle d'app de la suite ([StudioDock-app-modele](https://github.com/aminart/StudioDock-app-modele)) : design
system Night Navy, lancement par Studio Dock (`--port`, `--no-browser`, `/health`), fabrication d'un `.exe`.
Elle remplace l'ancienne interface Streamlit (Audio Transcriber 1.5.7), dont elle reprend toutes les fonctions.

## Ce qu'elle fait

- **Sources** : microphone ; son d'une seule application (Teams, Zoom, navigateur… — WASAPI « process loopback »,
  Windows 10 2004 ou plus récent) ; tout le son de l'ordinateur (WASAPI loopback, sans pilote virtuel) ; le micro
  mélangé à l'une ou l'autre.
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
- **Résultat exploitable** : copier le texte en un clic, corriger une phrase, nommer les intervenants ; les fichiers
  téléchargés reprennent les corrections et les noms.
- **Historique** : chaque session est enregistrée (texte, audio, intervenants) et peut être rouverte plus tard.
- **Vu-mètre** pendant l'enregistrement et alerte si aucun son n'arrive.
- **Copie de récupération** du texte après chaque bloc, en cas de plantage.

### Synthèse dans DocAnalyser

Dans le résultat, **Exporter › Envoyer à DocAnalyser** dépose la transcription dans DocAnalyser (autre app de la
suite Studio Dock) et l'ouvre sur « Synthèse de transcription », prête à lancer. DocAnalyser doit être lancé sur le
poste ; Snappy le cherche à http://127.0.0.1:8020 (son port dans Studio Dock), ou à l'adresse de la variable
d'environnement `DOCANALYSER_URL`. Il faut une version de DocAnalyser qui sait recevoir un document (2.11 ou plus).

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

**Identifier les intervenants** est inclus d'office (PyTorch et pyannote, environ 1 Go de plus ;
`install.bat leger` pour s'en passer). Le modèle pyannote est fourni par l'équipe via **Studio Dock**
(Réglages › Modèles d'IA › Identification des intervenants) : rien à régler. Sans Studio Dock, indiquez dans
**Réglages avancés** le dossier d'un pipeline pyannote déjà sur le disque (par exemple
`speaker-diarization-community-1`, avec `config.yaml`, `embedding\`, `segmentation\` et `plda\`). L'app ne
télécharge aucun modèle et n'a besoin d'aucun jeton. Si son installation échoue, la transcription fonctionne quand même.

Le design system Night Navy est inclus dans le dépôt (`frontend/vendor/night-navy-1.2.1.tgz`) : npm n'a pas besoin
d'accéder à GitHub, souvent bloqué sur le réseau de l'entreprise. Pour passer à une nouvelle version de Night Navy :
`npm pack` dans le dépôt Design-system- à la bonne étiquette, remplacer le .tgz, mettre à jour `package.json`, puis
`npm install`.

### Sur Mac

Prérequis : Python 3.11 à 3.13 ([python.org](https://www.python.org/downloads/macos/) ou `brew install python@3.12`)
et Node.js 20+ ([nodejs.org](https://nodejs.org/), version LTS, ou `brew install node`).

1. Dans le Terminal, dans le dossier du projet : **`./install.sh`** (une seule fois, quelques minutes).
   L'identification des intervenants est incluse (Mac Apple Silicon uniquement : PyTorch n'est plus publié pour les
   Mac Intel ; `./install.sh leger` pour s'en passer). `./install.sh /chemin/companyCA.crt` derrière le proxy de l'entreprise.
2. **`./start.sh`** : le navigateur s'ouvre sur http://127.0.0.1:8110 ; Ctrl+C dans le Terminal pour arrêter.
   L'interface est refabriquée automatiquement après un `git pull`.

Dossier téléchargé en .zip et fichiers non exécutables : `sh install.sh` puis `sh start.sh`. Au premier
enregistrement, macOS demande l'accès au micro pour le Terminal. Sur Mac, la voix (micro) et les fichiers sont
transcrits ; le son d'une application ou de tout l'ordinateur ne peut être capté que sous Windows.

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

**`install.bat gpu`** installe cuBLAS 12 et cuDNN 9 dans le venv (pas de CUDA Toolkit système, environ 1 Go).
**Sans Internet** : déposez d'abord les deux fichiers `nvidia_cublas_cu12-…-win_amd64.whl` et
`nvidia_cudnn_cu12-…-win_amd64.whl` dans un dossier **`wheels`** à la racine du projet (à côté de `install.bat`) ;
ils sont alors utilisés à la place du téléchargement (dossier ignoré par git). Versions validées :
`backend/requirements-gpu.txt`. À la fin, l'installation affiche si la carte graphique est prête.
L'app les expose à son seul processus. **Automatique** essaie le GPU puis retombe sur le CPU ; **GPU NVIDIA** affiche une
erreur si CUDA n'est pas prêt ; **CPU** sert au diagnostic.

### Diarisation (optionnel)

`pip install -r backend/requirements-diarization.txt` (pyannote.audio et PyTorch : volumineux). Indiquez le dossier racine
d'un pipeline local qui contient `config.yaml` et ses modèles : l'app ne télécharge aucun modèle et n'a besoin d'aucun jeton.

> **Ne commitez jamais de jeton** (Hugging Face…) : `.gitignore` exclut `tokenpyannoteaudio.txt` et `*token*.txt`.

## Fabriquer l'exe

```
build_exe.bat                  exe avec transcription et identification des intervenants (pyannote / PyTorch : très gros)
build_exe.bat gpu              + runtimes CUDA
build_exe.bat leger            sans l'identification des intervenants (exe beaucoup plus petit)
```

L'exe est dans `dist\`. Sans option, le GPU n'est pas inclus et l'identification des intervenants l'est (son modèle
vient de Studio Dock) ; avec `leger`, l'interface signale qu'elle manque. Sur Mac :
`build_exe_mac.sh` (la capture du son du PC n'existe que sous Windows).

## L'ajouter à Studio Dock

Dans Studio Dock, **Préparer pour l'équipe › Applications** : type « S'ouvre dans le navigateur » (et non plus une app
tierce sur `localhost`), identifiant `snappy-transcript`, programme `SnappyTranscript`, port **8110**, icône
`icone/app.svg`, puis la fiche (à quoi elle sert, prise en main). Déposez `SnappyTranscript-X.Y.Z.exe` (dernière release
GitHub du dépôt, ou le zip si le téléchargement d'un .exe est bloqué) dans le sous-dossier de l'app du dossier de
l'équipe. Les modèles (transcription, intervenants) ne sont pas dans l'exe : Studio Dock les fournit.

### Publier une version

1. Noter les changements dans `CHANGELOG.md` (section « Non publié »), puis `python scripts/bump_version.py X.Y.Z`
   (ou `patch` / `minor` / `major`) et fusionner dans `main`.
2. Créer la release GitHub avec le tag **`vX.Y.Z`** (exactement `v` + la version). Quelques minutes plus tard
   (environ 20), `SnappyTranscript-X.Y.Z.exe` et `SnappyTranscript-X.Y.Z-windows.zip` sont joints à la release
   (workflow « Build Windows exe » : interface, exe avec intervenants, `--check`, `/health`).
3. Déposer l'exe dans Studio Dock comme ci-dessus.

`SnappyTranscript.exe --check` liste les briques embarquées (transcription, fichiers, micro, son du PC, intervenants)
et dit laquelle ne se charge pas : utile si une installation se comporte bizarrement.

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
