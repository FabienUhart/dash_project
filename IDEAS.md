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
- [x] Nom du propriétaire configurable (Paramètres → Identité, `app_state`/`/api/settings`) — mentions, assignations, accusés de lecture
- [x] Renommer un invité depuis 🔗 Partages (✎, par e-mail, tous ses accès — cosmétique, sans toucher à sa connexion)
- [x] Couleur du point de carte configurable : défaut global (Paramètres → Carte) + override par mémo/projet (`marker_color`, éditable depuis le détail du mémo ET la pop-in carte, owner + invités `can_edit`) (export v16)
- [x] Groupes de points sur la carte : étiquettes `map_groups` par mémo, cocher des points → grouper, chips de focus afficher/masquer, partage inclus (export v17)
- [x] Filtre par sous-projet sur la carte d'un projet parent ([MAP-SUBFILTER], focus grisé/cliquable, cumul avec les groupes, persisté par projet, carte seule)
- [x] Provenance dans la liste de la carte : regroupement par projet d'origine (en-têtes + pastilles couleur, repli quasi-noir → palette stable), suffixe projet retiré de la liste
- [x] Sidebar façon Evernote ([SIDEBAR-EVERNOTE]) : sections repliables « Liens »/« Projets » (chevron + ＋), arbre des projets façon `tree` (`├──`/`└──`/`│`), projets repliables, états persistés ; troncature ellipsis des noms, masqué proprement en rail/mobile
- [x] Vue Plan ([TREE-OUTLINE]) : page arbre projets → sous-projets → mémos (feuilles), connecteurs `tree`, repli persisté + tout déplier/replier, colonnes méta desktop (échéance/assignés/lieu), clic mémo = détail / clic projet = board
- [x] Fix compteurs sidebar : `/api/projects` et `/api/priorities` excluent les mémos en corbeille (`deleted_at`) — invariant 7
- [x] Parité page invité ([GUEST-PARITY], `share.html`) : sidebar façon Evernote (arbre `tree` + chevrons repliables `shareSbProjOpen:<token>:<id>`), vue Plan (toggle « 🌳 Plan », `renderShareTreeView`, repli `shareTreeOpen:<token>:<id>`, colonnes méta desktop), chevrons agrandis — strictement scopé au partage (invariant 5)

## Quick wins

- **[MEMO-TIME] Heure optionnelle sur les mémos** : à côté du `due_date` (`<input type="date">`), ajouter un `<input type="time">` facultatif. Stockage **additif et non destructif** : nouvelle colonne `memos.due_time` (`TEXT DEFAULT ''`, format `"HH:mm"` ou `""` = pas d'heure), jamais toucher au `due_date` existant. Affichage : « 📅 6 nov · 14h30 » quand l'heure est présente, « 📅 6 nov » sinon. Tri intra-journée par heure dans les sections (Aujourd'hui/À venir). Export/import **v18** additif (compat v1→v17 : champ absent = `""`, upsert non destructif comme les autres champs). Ne pas changer la récurrence (reste basée sur la date ; l'heure peut être recopiée telle quelle par `_next_due`). Le plus rapide des trois ci-dessous, et prérequis utile pour l'agenda.

- **Raccourcis clavier 1-9** : ouvrir directement les 9 premiers liens de la catégorie active.
- **Compteur de clics** : colonne `clicks` sur `links`, tri optionnel "par usage" — les services les plus utilisés remontent tout seuls.
- **Mode édition verrouillable** : un cadenas dans le header qui masque les boutons éditer/supprimer/drag pour éviter les fausses manips (surtout sur mobile).
- **Badge favicon "service down"** : si un service est offline, changer le favicon de l'onglet (point rouge) — visible d'un coup d'œil quand le dash est la page d'accueil.

## Dette technique / architecture

- **[SHARED-HELPERS] Mutualiser les helpers front owner/invité** (voir [docs/adr/ADR-001](docs/adr/ADR-001-mutualisation-helpers-front.md), **accepté — Option C**) : ~31 fonctions JS dupliquées entre `index.html` et `share.html` (cause : invariant 6). Extraire les helpers purs/sans état dans un partial unique `templates/partials/_shared.js.html` inclus au rendu (`{% include %}`) dans les deux templates ; mettre à jour l'invariant 6 (distinguer *source* et *sortie livrée*). 2e passe : factoriser la logique de rendu carte (`draw`/`renderSubbar`/`memoRow`). Le backend (`app.py`) est déjà factorisé (owner et invité partagent `_perform_memo_update`, etc.) — la dette est frontend only.

## Confort / UX (rendre l'app agréable)

Gains rapides à fort effet :

- **[UNDO-DELETE] « Annuler » après suppression** : quand un mémo part à la corbeille, toast « Mémo supprimé — Annuler » pendant ~5 s. Réutilise la suppression douce (`deleted_at`) + la route de restauration existante → annulation quasi gratuite. Le geste qui rassure le plus à l'usage. Frontend + un appel restore.
- **[SAVE-INDICATOR] Indicateur « enregistré »** : petit ✓ discret pendant ~1 s à chaque `patch` de mémo (titre, date, priorité) — aujourd'hui les sauvegardes sont silencieuses. Frontend pur.
- **[EMPTY-STATES] États vides soignés** : projet sans mémo, carte sans point, recherche sans résultat → message amical + bouton d'action (« Ajouter le premier mémo »). Beaucoup de polish pour peu de code, frontend pur.
- **[SHORTCUT-HELP] Aide raccourcis (`?`)** : overlay listant les raccourcis (`/`, à venir Cmd/K, 1-9…) + focus `/` plus visible. Discoverability quasi nulle aujourd'hui. Frontend pur.

Moins de clics :

- **[CMD-K] Palette de commandes (Cmd/Ctrl+K)** : sauter à n'importe quel projet/mémo/lien ou créer un mémo, au clavier. Le plus gros saut de confort pour un usage quotidien intensif. Frontend, effort moyen, autonome.
- **[INLINE-TITLE] Édition inline du titre** d'un mémo sur la carte (double-clic) sans ouvrir la pop-in.
- **[MOVE-MENU] « Déplacer vers… »** dans le menu au survol d'un mémo (en plus de dupliquer), pour éviter le drag & drop.

Petites touches de plaisir :

- **[VIEW-TRANSITIONS] Transitions entre vues** (Liens ↔ Mémos ↔ Plan) en léger fondu GSAP — cohérent avec les animations cards/tuiles existantes (invariant 8 : jamais sur un `<dialog>`).
- **[PROJECT-DONE] Micro-célébration** quand tous les mémos d'un projet passent à « terminé » (petite animation discrète, pas de confetti envahissant).
- **[RELATIVE-DATES] Dates relatives partout** (« dans 3 j », « il y a 2 j ») en complément de la date — déjà partiel via `dueInfo`, à généraliser.

## Moyens

- ✅ **[MAP-SUBFILTER] FAIT (juin 2026)** — Filtrer les sous-projets sur la carte d'un projet parent : la carte d'un parent affiche récursivement les points de ses descendants (cf. inclusion récursive de la vue/partage d'un parent). But : dans la pop-in carte du dashboard (`openMapDialog`), ajouter un filtre **par sous-projet** sur le même modèle que les groupes de carte (`map_groups` / focus). Implémenté dans `index.html` (`#map-subbar`, `subActive`/`isSubFocused`, persisté `mapSubFilter:<projet>`) et répliqué dans `share.html` (`shareMapSubFilter:<token>:<PFILTER>`). Frontend uniquement, aucun changement d'export.
  - **Granularité** : un chip (ou case) **par sous-projet descendant** (récursif) + un pour les points propres au parent ; cliquer = activer/désactiver l'affichage de ce sous-projet.
  - **Grisé, pas masqué** : un point dont le sous-projet est désactivé reste affiché **grisé et cliquable** sur la carte ET la liste latérale, comme les groupes hors focus (aucun chip actif = tout normal ; `fitBounds` se recale sur les points en avant).
  - **Cumul avec les groupes existants** : le filtre `map_groups` continue de marcher et **se combine** — un point est « en avant » seulement s'il satisfait les deux (son sous-projet est activé ET au moins un groupe actif, ou aucun groupe en focus). Les groupes restent attachés aux points des sous-projets et filtrables comme aujourd'hui.
  - **Persistance par projet** en localStorage (modèle `mapFocus:<projet>` → `mapSubFilter:<projet>`).
  - **Contraintes** : filtre **carte uniquement** (la liste/board ne change pas) ; **aucun changement du format d'export** (la provenance vient déjà de `memos.project_id`) ; code maison dans le seul `templates/index.html` ; respecter l'invariant 8 (ne pas animer le `<dialog>` via GSAP). Optionnel : répliquer dans `openShareMap` (`share.html`) pour les invités d'un projet parent partagé.

- ✅ **[SIDEBAR-EVERNOTE] FAIT (juin 2026)** — sidebar en sections repliables « Liens » et « Projets » (en-tête chevron ▸/▾ + ＋), arbre des projets rendu **façon `tree`** (connecteurs `├──`/`└──`/`│`, classe `.sb-tree` monospace), projets parents repliables (chevron `.sb-proj-chev`, `sbProjOpen:<id>`), états persistés (`sbSection:<nom>`, `sbProjOpen:<id>`). Partages + Corbeille restent fixes en haut. Compatible rail/eye (en rail tout est déplié, headers/connecteurs masqués). « Partagés avec moi » et la section « Étiquettes » [TAG-NAV] **non implémentés** (gardés ci-dessous). Détail original :
- **[SIDEBAR-EVERNOTE] Navigation latérale façon Evernote** : organiser la sidebar en **sections repliables** avec en-tête (chevron ▸/▾) et un **＋** par section, comme Evernote (Carnets / Étiquettes / Partagés avec moi). Concrètement : un en-tête « Projets » (≈ Carnets) repliable au-dessus de l'arbre de projets existant (déjà parent/enfant), un en-tête « Étiquettes » (voir [TAG-NAV]) et un en-tête « Partagés avec moi » regroupant les projets/mémos auxquels on a accès via un partage (côté invité) ou que l'on a partagés. État replié/déplié **persisté en localStorage** par section. **Frontend uniquement** (`renderSidebar`), aucun changement de schéma ni d'export ; cohérent avec la sidebar repliable existante (👁/☰) et l'invariant 8. À tester en regardant le rendu réel sur l'app.

- **[TAG-NAV] Section « Étiquettes » dans la sidebar (navigation par tag)** : les tags existent déjà (sur liens, mémos et projets, normalisés minuscules sans `#`, recherche scopée `l#`/`m#`/`p#`) mais ne sont pas navigables depuis la sidebar. Ajouter une section **Étiquettes** listant tous les tags présents (dédupliqués, triés, avec compteur), chacun cliquable pour **filtrer/parcourir** tout ce qui le porte (réutilise la recherche scopée existante). Optionnel : repli/dépli, et petites pastilles de couleur. **Frontend uniquement** (agrège `state.links`/`state.memos`/`state.projects`), aucun changement d'export. Brique d'Evernote ([SIDEBAR-EVERNOTE]) — l'utilisateur aime ce modèle « par étiquette ».

- ✅ **[TREE-OUTLINE] FAIT (juin 2026)** — Vue Plan : item sidebar « 🌳 Plan » → `state.view='tree'`, `#tree-board` rendu par `renderTreeView()`. Arbre projets → sous-projets → mémos (feuilles), connecteurs `tree` (`.tree-pre`), chevrons de repli persistés `treeOpen:<id>` (+ nœud Inbox), bouton Tout déplier/replier, colonnes méta desktop (📅 échéance / 👤 assignés / 📍 lieu, masquées en mobile), clic mémo = détail, clic projet = board. Lecture seule (pas d'édition inline/D&D). Détail original :
- **[TREE-OUTLINE] Vue Plan / arbre des projets + mémos** : page dédiée (item sidebar) affichant **projets → sous-projets → mémos en feuilles** sous forme d'arbre `tree` repliable, pour la navigation/vue d'ensemble (≠ sidebar qui ne montre que les projets, ≠ board groupé par échéance). Clic mémo = ouvre son détail ; clic projet = ouvre son board. Édition reste dans le board/détail. Frontend pur (réutilise `projectChildren`/`projectDescendants` + les connecteurs `.sb-tree`), aucun changement schéma/export. Repli par projet persisté ; desktop-first, version aplatie/repliée sur mobile (cf. [SIDEBAR-EVERNOTE]). Invariants 6/8.

- **[AGENDA] Page Agenda / calendrier** : nouvelle vue dans la sidebar (sous Mémos) affichant les mémos placés sur une grille **mensuelle** par `due_date` (et `due_time` si [MEMO-TIME] est fait). Clic sur un jour = liste des mémos du jour ; clic sur un mémo = ouvre la pop-in de détail existante. **Frontend uniquement** : réutilise `state.memos` et `due_date`, aucun changement de schéma ni d'export. Couleurs par priorité/projet déjà dispo. Version rapide possible : commencer par une grille mois simple (ou une vue « semaine »/agenda-liste groupée par jour) avant d'ajouter le drag pour déplacer une échéance. Respecter l'invariant 6 (un seul fichier HTML, pas de lib calendrier externe non auto-hébergée — faisable en CSS grid maison) et l'invariant 8.

- **[ATTACHMENTS] Pièces jointes (pdf, texte, image, audio) téléchargeables, invités inclus** : généraliser l'upload d'images existant (`_save_uploaded_image`, `UPLOAD_DIR`, validation par **signature binaire** — invariant 5) à d'autres types. Réutiliser au maximum l'infra en place (table images / `data/uploads/`, routes `/uploads/<name>` et `/share/<token>/image/<name>`, upload invité `/share/<token>/memo/<id>/images`).
  - **Types & validation** : PDF (signature `%PDF-`, facile), images (déjà fait). Audio (signatures mp3/`ID3`, m4a/`ftyp`, ogg/`OggS`, wav/`RIFF`…`WAVE`) — plus de cas + fichiers lourds, attention à la taille. **Texte** (`.txt`) : pas de signature fiable → valider par extension + plafond de taille + servir en **téléchargement** (`Content-Disposition: attachment`), jamais en inline (anti-XSS). Garder une **liste blanche d'extensions** et une **taille max** par type.
  - **Téléchargement** : route owner + route publique `/share/...` renvoyant le fichier en pièce jointe ; les invités **approuvés** peuvent télécharger (pas seulement voir), dans le strict périmètre du partage (invariant 5). Ne jamais servir un type exécutable/HTML inline.
  - **Modèle & export** : soit étendre la table images en table `attachments` générique (colonne `kind`/`mime`), soit une table dédiée. Export/import **vN additif** : **noms de fichiers seulement** (comme les images v6), compat ascendante, upsert non destructif. Les fichiers eux-mêmes restent dans le volume `data/uploads/` (jamais committés, jamais dans le JSON).
  - **Note** : recoupe l'item « Audios sur les mémos » plus bas — à fusionner si on fait l'audio ici. Découpage conseillé : livrer d'abord **PDF + image** (collent à l'infra actuelle), puis **audio**, puis **texte**.

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
