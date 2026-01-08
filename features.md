Je voudrais faire une application "Jukebox" qui permettra d'écouter ma musique (fichiers mp3, flac, aiff), éventuellement des flux audio (streaming). La plupart des fonctionnalités ci-dessous ne s'appliquent qu'aux fichiers mais pas aux flux de streaming.

Les fichiers de musique seront stockés dans une ou plusieurs arborescences du disque (ou d'un partage réseau, mais cela ne doit pas être important pour les choix techniques). Les flux de streaming seront configurés dans un fichier de conf (yaml).

Le jukebox aura une base de données locale (sqlite) pour garder trace de l'historique d'écoute des morceaux (le fichier sera configuré dans le fichier de conf).

Le jukebox doit pouvoir lire et écrire les tags ID3v2.

Le jukebox doit avoir 2 modes de fonctionnement (avec donc deux interfaces différentes mais qui se ressemblent) :
- un mode jukebox simple qui permet d'écouter la musique de la base de morceaux
- un mode "curating" dans lequel j'écoute des morceaux que je ne connais pas, et que je décide de garder (et le jukebox déplace le morceau dans un répertoire spécifié), ou que je décide de ne pas garder (le jukebox déplace le morceau vers une poubelle)

Le jukebox doit gérer un système de modules internes qui auront un rôle central dans le fonctionnement : plutôt que de développer "en dur" des fonctionnalités dans le coeur du jukebox, je veux que ces fonctionnalités soient mises dans des modules "simples".
Les modules pourront ajouter des éléments dans l'interface graphique (boutons, inputs, etc) et définir eux-mêmes le code associé à ces items graphiques. Les modules pourront aussi capter les touches du clavier et modifier les items graphiques existants.


Pour cela, ils devront avoir accès à la liste complète des morceaux chargés (tags ID3, filename, path, bitrate, durée, ...), à la base de données sqlite, aux informations de replay (quel morceau est en cours d'écoute, pouvoir avancer ou reculer dans le morceau).

Un module permettra de filtrer les morceaux en se basant sur une recherche full text (en utilisant donc FTS5 de sqlite https://sqlite.org/fts5.html).

Un module permettra d'identifier les doublons.

Un module fera le rendu en 3 waveforms du morceau en cours d'écoute, ce traitement pouvant être un peu long, il faudra qu'il soit fait en arrière plan pour ne pas bloquer l'interface graphique. Le résultat du calcul des waveforms pourra être stocké dans la base sqlite pour éviter des recalculs inutiles.


Grâce à la base de données sqlite (qui stocke entre autre l'historique d'écoute des morceaux), on aura un module qui proposera d'écouter des morceaux qu'on n'a pas écoutés depuis longtemps.

