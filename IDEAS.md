# Idées d'évolution

Backlog d'idées pour le dashboard, par ordre approximatif d'intérêt/effort.

## Fait (juin 2026)

- [x] Catégories (sidebar gauche, drag & drop d'un lien vers une catégorie)
- [x] Mémos post-it indépendants avec ajout rapide
- [x] Recherche instantanée (`/`, portée Tout/Liens/Mémos/Projets, préfixes `p#` `l#` `m#`)
- [x] Favicons automatiques (serveur via URL locale, fallback DuckDuckGo puis lettre)
- [x] Horloge + météo Bayonne (open-meteo)
- [x] Drag & drop pour réorganiser liens et mémos
- [x] Paramètres : export/import JSON v15 (liens, catégories, projets, priorités, mémos, historique, commentaires avec priorité/réponses)
- [x] Responsive mobile : catégories en puces horizontales, mémos repliables
- [x] Vue Mémos façon Planify : tuiles de filtres, sections par échéance, sous-tâches, projets colorés avec Inbox
- [x] Tags `#` reliant liens, mémos et projets
- [x] Tâches récurrentes (replanification auto) + historique des tâches effectuées 📜
- [x] Priorités configurables (P1 rouge / P2 jaune / P3 vert + ajout/couleurs)
- [x] Éditeur riche Quill (auto-hébergé) + listes à cocher cliquables sur la card
- [x] Images sur les mémos (upload, miniatures, visionneuse, validation par signature binaire)
- [x] Partage externe par lien à jeton + code PIN 4 chiffres, invités identifiés par e-mail
- [x] Page 🔗 Partages : gestion des liens/PIN/invités, modifications par invité (avant/après, annulation)
- [x] Versions des mémos avec restauration owner-only, rechargement auto 15 s
- [x] Projets imbriqués (parents/enfants, drag & drop, partage récursif avec avertissement)
- [x] Page partagée = mini-dashboard invité : sidebar hiérarchique, tuiles, Quill, créations (mémos/sous-projets), éditions de projets, drag & drop — scopé au partage
- [x] Vue Invités par personne (tous les accès, hiérarchie dépliée, droits, retrait ciblé)
- [x] Sauvegardes automatiques quotidiennes (JSON + SQLite, rotation 7 j, bouton manuel)
- [x] Horloges multi-fuseaux (🇫🇷 auto à l'étranger + fuseau choisi) et météo visible sur mobile
- [x] Géolocalisation mémos/projets : GPS + adresses (Nominatim, labels courts), carte Leaflet multi-points avec liste des points cliquable
- [x] Titres sur les mémos (mémo valide avec titre seul) + descriptions sur les projets
- [x] Assignés multiples @nom (saisie libre, même non-invités, suggestions) — owner et invités
- [x] Commentaires signés sous les mémos (💬, invités inclus, comptés dans la cloche 🔔)
- [x] Refonte visuelle + animations GSAP (cards/tuiles/intro ; pop-ins en CSS pour rester en top-layer) + favicon
- [x] Mentions `@` dans l'éditeur ET les commentaires (autocomplete, ajout aux assignés) ; signal ambre ⚠ si la personne n'a pas accès au partage
- [x] Corbeille : suppression douce des mémos (restaurable 7 j, purge auto), côté propriétaire et invités
- [x] Dupliquer un mémo ; menu ⋯ (Supprimer/Dupliquer) dans la pop-in d'édition
- [x] QR code des liens de partage (SVG, lib `qrcode`) + récap, et ouverture d'un projet à un invité existant depuis 🔗 Partages
- [x] Commentaires v2 : réponses imbriquées, priorité P1/P2/P3, accusés de lecture « 👁 vu par … » (export v15)
- [x] Carte alignée sur la liste filtrée (recherche/filtre) — fini les points fantômes
- [x] Thème clair / sombre (bascule 🌙/☀️ dans le header, mémorisé, anti-FOUC, dashboard + page partagée)
- [x] Sidebar repliable : 👁 masquer entièrement / ☰ replier en rail d'icônes 64px (états mémorisés, animations GSAP)
- [x] Pop-ins maison partout (plus aucun `alert`/`confirm`/`prompt` natif, y compris page partagée)
- [x] Fix formulaire d'accès invité : la saisie ne s'efface plus au refresh ; mauvais PIN = erreur inline sans tout retaper
- [x] Passe responsive mobile : barre de projets collante, badges/commentaires/vue Partages en pleine largeur (plus de colonne 1 caractère), actions de card visibles sans survol, ronds non déformés, barre Quill sur une ligne défilable, bouton ✎ Modifier projet, « + Ajouter » masqué hors vue Liens (dashboard + page partagée)

## Quick wins

- **Raccourcis clavier 1-9** : ouvrir directement les 9 premiers liens de la catégorie active.
- **Compteur de clics** : colonne `clicks` sur `links`, tri optionnel "par usage" — les services les plus utilisés remontent tout seuls.
- **Mode édition verrouillable** : un cadenas dans le header qui masque les boutons éditer/supprimer/drag pour éviter les fausses manips (surtout sur mobile).
- **Badge favicon "service down"** : si un service est offline, changer le favicon de l'onglet (point rouge) — visible d'un coup d'œil quand le dash est la page d'accueil.

## Moyens

- **Bookmarklet "ajouter à mon dash"** : un lien à glisser dans la barre de favoris qui ouvre `dash/?add=<url>&title=<titre>` pré-rempli — capture d'un lien depuis n'importe quelle page.
- **Historique de disponibilité** : stocker les résultats du status check (table `status_history`) et afficher un mini sparkline uptime sur chaque card. Le Zimaboard devient aussi un mini-monitoring.
- **Épingler des liens** : section "Favoris" en haut, toujours visible quelles que soient les catégories.
- **Notifications par e-mail** : envoyer un mail (via la messagerie auto-hébergée) quand un invité modifie un partage — résumé quotidien ou immédiat.
- **Thèmes** : clair/sombre faits ; reste une palette **AMOLED noir** (et éventuellement le suivi auto du thème système via `prefers-color-scheme`).
- **Vue graphe / constellation des tags** : un force-directed graph (lib `force-graph` de vasturiano, 2D canvas, à auto-héberger dans `static/` — invariant 6) montrant les liens ↔ mémos ↔ projets reliés par leurs `#tags` communs (et éventuellement les assignés). Clic sur un nœud = ouvrir/filtrer. À scoper comme **explorateur de relations** (surtout les tags, qui sont du many-to-many), pas comme un dump générique du graphe — l'arbre de projets se lit déjà en arbre. Voir discussion : utile si ciblé sur les tags.

## Plus ambitieux

- **PWA** : manifest + service worker → installable sur mobile, icône sur l'écran d'accueil, cache hors-ligne de la dernière vue. **Important (demande Fabien)** : gérer le hors-ligne en écriture — file d'attente locale (outbox IndexedDB) des modifications faites sans réseau, synchronisées automatiquement au retour de la connexion (cocher des courses dans un magasin sans 4G).
- **Audios sur les mémos** : bouton 🎤 (MediaRecorder), upload validé par signature comme les images, lecteur sur la card. Sans transcription (Zimaboard trop léger pour Whisper) — pièce jointe vocale simple.
- **Widgets de services** : pour certains services connus, afficher une info en plus du statut (espace disque du NAS, nombre de téléchargements en cours, capteurs Home Assistant via leurs APIs).
- **Multi-profils** : page d'accueil différente par navigateur/contexte (perso / boulot) via un paramètre `?profile=`.
- **Espace multi-utilisateur (via Authelia)** : de vrais comptes, chacun son dashboard, **sans casser l'invariant 5 (pas d'auth dans l'app)** — l'app lirait le header `Remote-User` qu'Authelia transmet déjà pour scoper les données. Implique de scoper **chaque** table par `owner_id` (liens, catégories, mémos, projets, priorités, shares…), de porter le scope dans l'export/import, et de le faire respecter partout. Gros chantier qui change la nature du produit (de « mon dashboard partagé » à « N dashboards ») — à ne lancer que s'il y a réellement plusieurs utilisateurs indépendants à servir ; sinon le système de partage/invités couvre déjà la collaboration.
- **Notifications push (PWA)** : en complément des notifs e-mail. Léger pour le Zimaboard (POST HTTPS vers le service push d'Apple/Google via `pywebpush`/VAPID, pas de connexion persistante). ⚠️ sur iPhone, push uniquement si le PWA est installé sur l'écran d'accueil (iOS 16.4+), et possible restriction UE (DMA) — à tester sur l'appareil avant de s'y fier ; les notifs e-mail restent le repli universel.
- **Backup automatique planifié** : un cron dans le conteneur qui poste l'export JSON quotidien dans un dossier `data/backups/` avec rotation (7 jours), pour ne plus dépendre de l'export manuel.
