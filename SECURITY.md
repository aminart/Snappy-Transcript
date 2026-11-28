# Sécurité

Snappy Transcript tourne sur le poste : le serveur n'écoute que sur `127.0.0.1`, rien ne part sur Internet, les
transcriptions et l'audio restent dans le dossier de données de l'utilisateur. Ce document liste ce qui protège
l'application et ce qui reste à la charge de l'équipe.

## Protections en place

| Risque | Protection |
| --- | --- |
| Une page web ouverte dans le navigateur envoie des requêtes à `127.0.0.1:8110` (lancer un enregistrement, effacer l'audio, charger un faux modèle) | Les requêtes qui modifient (POST, PUT, DELETE…) ne sont acceptées que depuis l'interface de Snappy (en-têtes `Origin` / `Sec-Fetch-Site`). |
| « DNS rebinding » : un site fait pointer son domaine vers 127.0.0.1 pour lire les transcriptions | En-tête `Host` limité à `127.0.0.1`, `localhost`, `::1`. |
| Snappy affiché dans une page tierce pour piéger des clics, fichiers (audio) lus depuis un autre site | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `Cross-Origin-Resource-Policy: same-origin`, `nosniff`, `no-referrer`. |
| Dossier de modèle d'intervenants piégé : `config.yaml` désigne la classe que pyannote instancie | Seules les classes `pyannote.audio.pipelines.*` sont acceptées. |
| Chemins fabriqués (`../`) vers les sessions, les envois, l'interface | Identifiants vérifiés par expression régulière ; fichiers de l'interface confinés à leur dossier. |
| Texte injecté dans les exports (Word) ou l'interface | Échappement XML pour le .docx ; React échappe tout le texte affiché (aucun `innerHTML`). |

## À la charge de l'équipe

- **Dossier partagé de Studio Dock** : qui peut y écrire peut remplacer l'exe ou un modèle, donc exécuter du code sur
  tous les postes (les fichiers de poids PyTorch peuvent contenir du code). N'y donner l'écriture qu'aux personnes qui
  préparent les versions ; ne déposer que des modèles venant de sources sûres (Hugging Face officiel, équipe).
- **Exe non signé** : Windows SmartScreen le signale. Une signature de code (certificat de l'entreprise) supprimerait
  l'alerte et prouverait l'origine de l'exe.
- **Données au repos** : transcriptions, audio et copies de récupération sont en clair dans le profil de l'utilisateur
  (`%LOCALAPPDATA%`), protégés par la session Windows. Pour des réunions sensibles, préférer un poste chiffré
  (BitLocker) et utiliser « Supprimer l'audio, garder le texte ».
- **« Envoyer à DocAnalyser »** : le texte part vers `127.0.0.1:8020` (ou `DOCANALYSER_URL`). Un programme local qui
  occuperait ce port et répondrait comme DocAnalyser le recevrait ; c'est le même poste, donc déjà compromis.
- **Fichiers audio et vidéo importés** : décodés par FFmpeg (PyAV). Garder les dépendances à jour (nouvelle version
  de Snappy) pour bénéficier des correctifs de sécurité de FFmpeg.

## Signaler un problème

Ouvrir une issue privée (« Security advisory ») sur le dépôt GitHub, sans détail public avant correction.
