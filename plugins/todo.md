revoir le search
ajouter l'icone d'app
faire des raccourcis pour l'ajout à une playlist
comment les playlists vont-elles supporter le déplacement/renommage d'un fichier?

faire un module qui calcule la corrélation entre les stats du morceau et ma catégorisation pour essayer de la déduire pour les morceaux nouveaux
faire la génération de clips insta


dans la db, avoir la distinction entre les morceaux jukebox et les morceaux curating : la tracklist change quand on switche de mode. En curating, quand on copie un fichier, on l'ajoute automatiquement à la DB de jukebox (en fait c'est juste un flag et le path qui changent et on profite des stats déjà calculées). Quel que soit le mode, on peut demander le calcul des full-stats.
Voir s'il y a moyen de normaliser les morceaux moi-même (il faudrait un flag is_normalized dans la DB)

Chaque mode (jukebox/curating) charge automatiquement son répertoire configuré pour mettre à jour sa DB



Normalisation permanente des fichiers
Modifie physiquement les fichiers audio
Utilise pydub ou ffmpeg pour traiter les fichiers

