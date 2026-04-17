# Photo Trier

Application desktop minimaliste pour trier rapidement des photos et vidéos avec des raccourcis clavier sur macOS.

## Fonctionnalités

- Détecte automatiquement les fichiers à classer dans le dossier `à trier/`
- Associe les sous-dossiers à des touches AZERTY Mac
- Déplace le média courant vers le bon dossier avec une seule touche
- Verrouille le dernier dossier utilisé pour les séries de photos
- Lit les vidéos principales dans l'application
- Son désactivé par défaut, activable à la demande
- Barre de progression pendant le tri
- Persistance des associations touche → dossier

## Dépendances

- Python 3.11+
- [Pillow](https://python-pillow.org/)
- `ffmpeg`
- `ffplay`
- `ffprobe`

Sur macOS avec Homebrew :

```bash
brew install ffmpeg
python3 -m pip install -r requirements.txt
```

## Lancer l'application

```bash
python3 trier.py
```

Au premier lancement, l'application crée automatiquement le dossier `à trier/` si besoin.

## Utilisation

1. Déposer les photos et vidéos à trier dans `à trier/`
2. Créer dans `à trier/` les sous-dossiers de destination
3. Lancer l'application
4. Utiliser les raccourcis affichés dans la colonne de gauche

### Raccourcis

- `& é " ' ( § è ! ç à )` : envoyer le média dans le dossier associé
- `Espace` : répéter le dernier dossier
- `Tab` : verrouiller ou retirer le verrou sur le dernier dossier
- `M` : activer ou couper le son de la vidéo courante
- `N` : créer un nouveau sous-dossier
- `Flèche droite` ou `Entrée` : passer au média suivant
- `Supprimer` : annuler le dernier déplacement
- `Échap` : recharger les dossiers et médias

## Formats pris en charge

L'application gère le tri des formats image et vidéo courants, dont :

- Images : `jpg`, `jpeg`, `png`, `gif`, `bmp`, `tiff`, `webp`, `heic`, `heif`, `avif`
- Vidéos : `mp4`, `mov`, `m4v`, `avi`, `mkv`, `webm`, `mpeg`, `mpg`, `mts`, `m2ts`, `3gp`

Le tri repose sur l'extension du fichier. L'aperçu dépend des capacités de Pillow pour les images et de `ffmpeg` pour les vidéos.

## Notes

- Le dossier `à trier/` est ignoré par Git pour éviter de publier des médias personnels.
- Les associations de touches sont enregistrées dans `.photo_trier_keys.json`, également ignoré par Git.
- L'application est pensée pour un usage personnel local et ne dépend pas d'un service distant.
