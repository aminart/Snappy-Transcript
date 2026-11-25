# Historique des versions

## [Non publié]

## [0.1.0]

- Première version dans la suite Studio Dock, créée depuis le modèle d'app. Reprend les fonctions d'Audio Transcriber 1.5.7 :
  micro, son du PC (WASAPI) ou les deux ; faster-whisper local (CPU, GPU NVIDIA) avec glossaire ; pause et reprise ;
  exports TXT / SRT / WAV immédiats ; diarisation locale pyannote en arrière-plan avec progression ; lecteur audio
  synchronisé mot à mot ; reprise après coup à partir d'un WAV et d'un SRT ; copie de récupération anti-crash.
- Interface refaite avec le design system Night Navy (clair et sombre) ; l'interface Streamlit est remplacée.
- Les exports sont écrits par le serveur dès la fin de la transcription, même si le navigateur est fermé.
- « Conserver l'enregistrement WAV » décoché : le WAV est réellement supprimé en fin de session (il ne l'était pas).
- Le lecteur et les téléchargements n'ont plus de limite de taille (plus de serveur média annexe).
- Corrections reprises de la revue : arrêt qui pouvait échouer, statuts pause / terminé, répétitions légitimes supprimées
  par la déduplication, mode simulation (voir l'historique git de la branche de corrections).
