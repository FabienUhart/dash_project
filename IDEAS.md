# Idées d'évolution

Backlog d'idées pour le dashboard, par ordre approximatif d'intérêt/effort.

## Fait (juin 2026)

- [x] Catégories (sidebar gauche, drag & drop d'un lien vers une catégorie)
- [x] Mémos post-it indépendants avec ajout rapide
- [x] Recherche instantanée (`/` pour focus, Entrée ouvre le premier résultat, Échap efface)
- [x] Favicons automatiques (DuckDuckGo icons, fallback lettre)
- [x] Horloge + météo Bayonne (open-meteo)
- [x] Drag & drop pour réorganiser liens et mémos
- [x] Paramètres : export/import JSON incluant liens + catégories + mémos (compatible anciennes sauvegardes)
- [x] Responsive mobile : catégories en puces horizontales, mémos repliables

## Quick wins

- **Raccourcis clavier 1-9** : ouvrir directement les 9 premiers liens de la catégorie active.
- **Compteur de clics** : colonne `clicks` sur `links`, tri optionnel "par usage" — les services les plus utilisés remontent tout seuls.
- **Mode édition verrouillable** : un cadenas dans le header qui masque les boutons éditer/supprimer/drag pour éviter les fausses manips (surtout sur mobile).
- **Badge favicon "service down"** : si un service est offline, changer le favicon de l'onglet (point rouge) — visible d'un coup d'œil quand le dash est la page d'accueil.
- **Couleurs de mémos** : 3-4 couleurs de post-it pour distinguer urgent / info / courses.

## Moyens

- **Bookmarklet "ajouter à mon dash"** : un lien à glisser dans la barre de favoris qui ouvre `dash/?add=<url>&title=<titre>` pré-rempli — capture d'un lien depuis n'importe quelle page.
- **Historique de disponibilité** : stocker les résultats du status check (table `status_history`) et afficher un mini sparkline uptime sur chaque card. Le Zimaboard devient aussi un mini-monitoring.
- **Mémos avec échéance** : date optionnelle sur un mémo, mise en avant (rouge) quand c'est dépassé. Transforme les post-its en mini-todo.
- **Épingler des liens** : section "Favoris" en haut, toujours visible quelles que soient les catégories.
- **Thèmes** : 2-3 palettes (sombre actuel, clair, AMOLED noir) en paramètre.

## Plus ambitieux

- **PWA** : manifest + service worker → installable sur mobile, icône sur l'écran d'accueil, cache hors-ligne de la dernière vue.
- **Widgets de services** : pour certains services connus, afficher une info en plus du statut (espace disque du NAS, nombre de téléchargements en cours, capteurs Home Assistant via leurs APIs).
- **Notes longues en Markdown** : un deuxième type de mémo "page" avec rendu markdown, pour de la doc perso (procédures de restore, config réseau...).
- **Multi-profils** : page d'accueil différente par navigateur/contexte (perso / boulot) via un paramètre `?profile=`.
- **Backup automatique planifié** : un cron dans le conteneur qui poste l'export JSON quotidien dans un dossier `data/backups/` avec rotation (7 jours), pour ne plus dépendre de l'export manuel.
