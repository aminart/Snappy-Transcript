# Audio Transcriber V1.5.3.1

Correctif Windows COM/WASAPI : SoundCard est initialisé dans chaque thread qui utilise Media Foundation, ce qui corrige notamment `0x800401f0` sous Streamlit. L’énumération des sorties ne fait plus planter l’application en cas d’indisponibilité. Aucun nouveau paquet ni droit administrateur requis.

# Audio Transcriber V1.5.1

Application Streamlit Windows locale : microphone → faster-whisper → transcription live → WAV/TXT/SRT.

## Nouveautés V1.5.1

- **Cache TXT anti-crash** : après chaque consolidation STT, une copie est écrite atomiquement dans `%LOCALAPPDATA%/AudioTranscriber/cache/` (ou dans le profil utilisateur si `LOCALAPPDATA` n'existe pas). Le cache reste présent après une session normale pour permettre la récupération.
- **Timestamps mot à mot** : `faster-whisper` est appelé avec `word_timestamps=True`.
- **Player mot à mot** : pendant la lecture du WAV, le mot courant est surligné lorsque Whisper a fourni son timing.
- **Diarisation Community-1 réellement intégrée** : post-traitement local, chargement du snapshot depuis disque, sans téléchargement automatique.
- **Fusion mot/locuteur** : chaque mot Whisper est rapproché de la timeline pyannote et un segment est scindé lorsqu'un changement de locuteur intervient. Community-1 utilise `exclusive_speaker_diarization` quand l'API installée l'expose, avec fallback compatible.
- Le chemin faster-whisper reste mémorisé comme en V1.4.

## Installation STT

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-stt.txt
.\venv\Scripts\python.exe -m streamlit run app.py
```

## Diarisation optionnelle

La transcription et le cache fonctionnent sans diarisation. Pour l'activer :

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-diarization.txt
```

Puis fournir dans l'interface le **dossier racine d'un pipeline pyannote local** contenant `config.yaml` et ses modèles nécessaires. Cette installation peut être volumineuse et dépend de la compatibilité de PyTorch avec la version Python/Windows de l'entreprise. Aucun téléchargement automatique de modèle de diarisation n'est déclenché par le code V1.5.

Après STOP, cliquer sur **Lancer / relancer la diarisation locale**. `0` locuteur laisse le pipeline estimer le nombre ; une valeur > 0 fixe le nombre attendu.

## Récupération après crash

Chercher le fichier le plus récent dans :

```text
%LOCALAPPDATA%\AudioTranscriber\cache\transcript_YYYY-MM-DD_HH-MM-SS.txt
```

Le fichier est remplacé atomiquement après chaque résultat STT consolidé, afin d'éviter autant que possible un cache partiellement écrit.

## Confidentialité

Le chemin microphone reste PCM16 → NumPy → faster-whisper local. Le player utilise le WAV en mémoire. La diarisation V1.5.1 est conçue pour un pipeline local fourni par l'utilisateur. Aucun audio n'est envoyé par l'application vers un service cloud.

## V1.5.2 — longues réunions et reprise après coup
- Le microphone est spoulé directement vers un WAV local sous `%LOCALAPPDATA%\\AudioTranscriber\\sessions\\<session>` : l'audio complet n'est plus conservé en RAM.
- Les gros WAV (>100 MiB) ne sont plus injectés dans le navigateur ni dans un composant HTML/Base64. Cela évite la limite WebSocket Streamlit observée vers 200 MiB.
- L'affichage live est borné aux ~50 000 derniers caractères ; le cache texte complet continue d'être écrit atomiquement.
- Une section **Reprise / diarisation après coup** accepte des chemins locaux WAV + SRT et produit `*_diarized.txt` et `*_diarized.srt` sans refaire le STT.
- La diarisation reste locale avec Community-1. Pour la reprise SRT, l'attribution est au niveau du segment SRT ; les timestamps mot-à-mot ne peuvent pas être reconstruits depuis un SRT standard.
- Pour les longues réunions, le player utilise `st.audio` avec le fichier local plutôt qu'un WAV Base64. L'ancien `st.components.v1.html` n'est plus utilisé par `app.py`.

## V1.5.3
- La section « Reprise / diarisation après coup » est placée après la transcription live.
- La diarisation affiche la phase pyannote, la progression disponible, le temps écoulé et une ETA estimée lorsque pyannote fournit completed/total.
- Capture Windows ajoutée via WASAPI loopback (`soundcard`) sans pilote virtuel : `Audio système` et `Micro + audio système`.
- Le mode mixte additionne micro et sortie Windows en PCM16 mono avant WAV/STT. Avec des haut-parleurs, le micro peut réentendre les participants distants : un casque reste préférable pour éviter le doublonnage acoustique.
- Teams/Jabber ne sont pas intégrés directement : la capture vise la sortie audio Windows utilisée par ces applications.

Après mise à jour, réinstaller les dépendances applicatives pour ajouter SoundCard :
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## V1.5.4
- La diarisation locale pyannote est sélectionnée par défaut. Si le pipeline local est valide au START, la session mémorise ce choix et lance automatiquement la diarisation après STOP et finalisation STT.
- La diarisation de la session courante peut être relancée après coup sans passer par l'outil de récupération WAV + SRT.
- Les timestamps mot à mot de faster-whisper sont préservés lors de la fusion avec les speakers.
- Le player synchronisé mot à mot est restauré. Pour éviter la régression WebSocket des longues réunions, le WAV n'est plus encodé en Base64 : un petit serveur média local lié à `127.0.0.1` fournit le fichier au navigateur avec support HTTP Range/seek. Aucun audio n'est exposé sur le réseau de l'entreprise.

## V1.5.7 — GPU NVIDIA optionnel (Windows)

Le mode **Automatique** tente faster-whisper sur NVIDIA CUDA en `float16`, puis revient sur CPU `int8` si CUDA n'est pas prêt. Le mode **GPU NVIDIA** est strict et affiche une erreur plutôt que de masquer un problème CUDA. Le mode **CPU** permet le diagnostic.

Les runtimes peuvent rester entièrement dans le venv (pas de CUDA Toolkit système) :

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-gpu.txt --cert "C:\Users\...\.continue\companyCA.crt"
```

L'application expose les dossiers `nvidia/cublas/bin` et `nvidia/cudnn/bin` uniquement au processus Python. La diarisation pyannote reste indépendante et utilise CPU tant que PyTorch CUDA n'est pas disponible.

## Correctif V1.5.7 — lecteur stable après STOP

Le rafraîchissement Streamlit à 1 seconde est désormais limité à la capture et à la finalisation STT. La diarisation automatique s’exécute uniquement après STOP, puis le lecteur audio synchronisé est rendu dans une vue statique sans `run_every`, afin de préserver play/pause, la position de lecture et la surbrillance mot à mot.


## V1.5.7

- Pause / Reprise sans fermer le WAV : l’audio reçu pendant la pause est ignoré et la timeline enregistrée reste continue.
- STOP ferme/finalise le WAV et le STT.
- TXT/SRT RAW sont figés et écrits sur disque immédiatement après finalisation STT.
- La diarisation automatique s’exécute ensuite dans un thread de fond et produit des fichiers `*_diarized.txt` / `*_diarized.srt` séparés.
- Le lecteur RAW reste statique pendant le suivi de diarisation.
- Champ de glossaire métier persistant transmis à faster-whisper via `hotwords` et `initial_prompt`. Utiliser surtout noms propres, acronymes et jargon spécifique.
