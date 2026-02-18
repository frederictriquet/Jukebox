le mix : ~/Music/000 My Mixes/House 20 minutes.mp3
la tracklist, dans cet ordre (il n'y a aucun autre morceau) :
* Blende - On a String
* Meloko, Baron (FR), Selim Sivade & Konvex (FR) - Me Gusta
* The Mekanism & II Faces - Café Con Leche
* Jungle - Holding On
* Ross from Friends - The One

uv run shazamix analyze ~/Music/000\ My\ Mixes/House\ 20\ minutes.mp3 -o cuesheet.txt
Compare le résultat dans cuesheet.txt avec la tracklist correcte.
Tant que tu ne parviens pas à fournir ce résultat, c'est que ton algorithme est incorrect.

Il y a aussi:
* ~/Music/000\ My\ Mixes/garden\ 2.mp3 et la cuesheet exacte ~/Music/000\ My\ Mixes/garden\ 2.cue
* ~/Music/000\ My\ Mixes/deep.mp3 et la cuesheet exacte ~/Music/000\ My\ Mixes/deep.cue
* ~/Music/000\ My\ Mixes/lgd.mp3 et la cuesheet exacte ~/Music/000\ My\ Mixes/lgd.cue


J'aimerais pouvoir corriger finement et manuellement les cuesheets générées :
  - pourvoir supprimer un faux positif (via une action sur la ligne de la cuesheet, PAS via le bouton Delete que tu as mis en dessous)
  - pouvoir insérer un morceau manquant entre 2 morceaux
  - pouvoir bouger précisément les timestamps de début et de fin de chaque morceau
  - pouvoir forcer facilement le début d'un morceau sur la fin du morceau précédent
  - pouvoir forcer facilement la fin d'un morceau sur le début du morceau suivant
  - voir en temps réel si mes modifications ont créé ou résolu des overlaps (apparition/disparition du symbole warning dans la première colonne)
  - voir s'il y a des gaps entre deux morceaux