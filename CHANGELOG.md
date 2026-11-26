# Historique des versions

## [Non publié]

- « Démarrer l'enregistrement » centré sur la hauteur de la carte (en haut quand les réglages avancés sont ouverts).
- Intervenants : interrupteur (au lieu d'une case à cocher) ; la question « Combien de personnes vont parler ? » est
  affichée dès que l'option est activée, avec « Je ne sais pas », 2 à 5 ou « 6 et plus » (compteur jusqu'à 20),
  au lieu d'un champ « 0 = je ne sais pas ».
- Microphone : textes d'aide retirés (casque, barre verte), la liste se suffit.

## [0.2.1] — 2026-11-26

- Exe Windows fabriqué par GitHub : inclut désormais les runtimes CUDA (`cuBLAS`, `cuDNN`) pour l'accélération GPU NVIDIA avec `faster-whisper` (tout en conservant le fonctionnement sur CPU).

## [0.2.0] — 2026-11-26

- Exe fabriqué par GitHub à chaque release (`SnappyTranscript-X.Y.Z.exe` et un zip joints à la release), avec
  l'identification des intervenants ; `SnappyTranscript.exe --check` vérifie que chaque brique se charge.

- « Exporter › Envoyer à DocAnalyser » : la transcription (titre, date, durée, intervenants, puis le texte horodaté
  avec les noms) est déposée dans DocAnalyser, qui s'ouvre dans un nouvel onglet sur « Synthèse de transcription »,
  prête à lancer. DocAnalyser doit être lancé (Studio Dock) ; adresse http://127.0.0.1:8020, ou `DOCANALYSER_URL`.
- Identification des intervenants intégrée : installée d'office par install.bat / install.sh et incluse dans l'exe
  (`leger` pour s'en passer ; un échec n'empêche pas de transcrire). Son modèle pyannote est fourni par l'équipe via
  Studio Dock (studiodock_ia.intervenants()) et utilisé sans rien régler ; un dossier choisi sur le poste reste possible.
- « Ouvrir le dossier » retiré (vue d'une transcription et menu de Mes transcriptions).
- Mes transcriptions : une transcription s'ouvre dans l'onglet (titre cliquable ou « Ouvrir ») et se ferme avec
  « Mes transcriptions » ou le bouton Précédent du navigateur ; recherche, filtre et position de la liste sont retrouvés.
- Point rouge « Enregistrement en cours » (avec la durée) dans la barre des onglets, sur toutes les pages ; un clic
  ramène à l'enregistrement.
- Retours d'utilisation : l'app s'ouvre toujours sur « En direct » ; « On écoute » tient sur une ligne, avec
  « Ma voix + une application » en premier et choisi par défaut (l'application de la visio en cours est prise
  d'office) ; précisions et cases rangées dans leur ligne ; liste des micros dédoublonnée (une ligne par appareil,
  nom complet, micro par défaut en premier, sans « Mixage stéréo ») avec un conseil pour choisir ; « Réglages
  avancés » en bouton dépliant ; aide pour ajouter l'identification des intervenants ; partie gauche alignée en haut.
- Mes transcriptions : filtres « Toutes / En direct / Depuis un fichier / Avec intervenants », « Libérer de la place »
  en bouton, et une transcription rouverte s'affiche sans quitter l'onglet (retour par « Mes transcriptions »).
- Résultat : « Nouvelle transcription » en bouton, « Exporter » en bouton principal, « Copier le texte » secondaire.
- Démarrage immédiat : le modèle de transcription se prépare dès l'ouverture de la page (« ✓ Modèle prêt ») et reste
  en mémoire d'une session à l'autre.
- Un seul texte à corriger : avec les intervenants dès qu'ils sont identifiés ; chaque correction est reportée dans le
  texte seul (toujours exportable). Ctrl+Z annule la dernière correction ou le dernier remplacement.
- Mes transcriptions plus rapide avec beaucoup de sessions (index), place occupée sur le poste, « Supprimer l'audio,
  garder le texte » pour une session et « Libérer de la place » pour les plus anciennes.
- Nouvel écran « Transcrire » : grand bouton d'enregistrement et liste « Prêt ? » (source, application, micro,
  langue, mots à bien reconnaître, intervenants) modifiable sur place ; la source est testée avant de démarrer
  (« On vous entend », « Teams est bien capté »). Les réglages techniques sont repliés dans « Réglages avancés ».
- Pendant l'enregistrement, mode concentration : chrono, niveau, « Marquer ce moment » (touche M), Pause, Arrêter ;
  le texte en colonne de lecture, « Revenir au direct » quand on remonte lire.
- Résultat : titre modifiable, phrases corrigées d'un clic, intervenants renommés en cliquant sur leur nom, lecteur
  avec forme d'onde colorée par intervenant et temps de parole, moments marqués (renommer, supprimer, réécouter),
  « Rechercher et remplacer » (Ctrl+F / Ctrl+H, tout remplacer annulable, ajout aux mots à bien reconnaître),
  menu « Exporter » avec le format Word.
- Mes transcriptions : titres modifiables, recherche dans le texte de toutes les sessions (accents ignorés) avec
  l'extrait trouvé, filtres, intervenants nommés, et « Récupérer le texte » d'une session interrompue.
  « Identifier les intervenants d'un enregistrement existant » (WAV + SRT) est retiré : un enregistrement existant
  s'importe dans Transcrire › Depuis un fichier, et devient une session complète.
- Menu simplifié : « Transcrire » et « Mes transcriptions » (ex-« Historique »). L'onglet « À propos » est retiré :
  la version s'affiche en pied de page.
- « Qu'est-ce qu'on écoute ? » : ma voix, une application, tout le son de l'ordinateur, ou ma voix + une application.
  Le son d'une seule application (Teams, Zoom, Chrome…) est capté sans les notifications ni la musique (Windows 10
  version 2004 ou plus récent) ; la liste montre les applications ouvertes, celles qui font du son d'abord, et
  « Ma voix + une application » est recommandé quand une visio est détectée. Sur un Windows plus ancien, l'interface
  le dit et propose tout le son de l'ordinateur.
- Vu-mètre pendant l'enregistrement, et alerte quand aucun son n'arrive depuis 10 secondes (micro coupé, mauvaise entrée).
- Barre d'actions toujours visible (Démarrer, Pause, Arrêter, durée, niveau), en bas de l'écran sur téléphone ;
  raccourcis Espace (pause / reprise) et Échap (arrêter) ; « La transcription prend du retard » quand c'est le cas.
- Réglages simplifiés : source, langue, mots à bien reconnaître et intervenants restent visibles ; le moteur, le modèle,
  le calcul, les blocs et le VAD sont dans « Réglages avancés ». Vocabulaire simplifié (texte seul, avec intervenants…).
- Résultat exploitable : « Copier le texte » (une réplique par intervenant), correction phrase par phrase, noms des
  intervenants (« SPEAKER_00 » → « Marie »), repris dans les fichiers téléchargés.
- Historique : chaque session est enregistrée avec son texte ; on peut la rouvrir (réécouter, corriger, nommer les
  intervenants), ouvrir son dossier ou la supprimer. Les sessions interrompues y apparaissent aussi.
- Petites améliorations : annulation de l'envoi d'un fichier, « Ouvrir le dossier », noms des micros sans numéro,
  option des intervenants décochée et expliquée quand elle n'est pas installée, texte en direct en police courante.

- Le modèle de transcription est fourni par Studio Dock (modèle de l'équipe) : plus aucun chemin à saisir au premier
  lancement. Un autre modèle reste possible sur le poste (« Utiliser un autre modèle »).
- Correction : sur un PC sans carte NVIDIA, la détection du GPU plantait (erreur Python affichée sous « Calcul ») et
  le moteur réel ne démarrait pas en mode « Automatique ». Le message dit maintenant que le calcul se fera sur le processeur.

- Transcription d'un fichier audio ou vidéo, dans son format d'origine (MP3, M4A, WAV, FLAC, OGG, Opus, WMA, AIFF… ;
  MP4, MOV, MKV, AVI, WMV, WebM, MPEG…) : glisser-déposer ou chemin sur le PC, progression et temps restant, pause, arrêt
  en gardant le texte obtenu ; ensuite exports, lecteur synchronisé et locuteurs comme pour une session en direct.
- Un fichier illisible (sans piste son, abîmé, protégé) affiche un message clair au lieu d'exports vides.

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
