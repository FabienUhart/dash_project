# Dashboard

Dashboard web perso : page d'accueil de navigateur avec liens vers des services auto-hébergés (deux URLs possibles par service : publique + VPN/locale), catégories, mémos post-it, check de statut côté serveur, recherche instantanée, horloge + météo.

Stack : Flask + SQLite + `qrcode` (QR des liens de partage, SVG pur Python), servi par gunicorn dans un conteneur Docker. Front vanilla JS dans `templates/index.html` ; dépendances front auto-hébergées dans `static/` (Quill, GSAP, Leaflet, favicon) — aucun CDN au runtime.

Voir [IDEAS.md](IDEAS.md) pour le backlog d'évolutions.

## Lancer en local

```bash
docker compose up -d --build
```

UI : http://localhost:8099

## Interface

- **Sidebar gauche** : catégories avec compteurs ("Tous", catégories custom, "Sans catégorie"). Drag & drop d'une card vers une catégorie pour la déplacer. Sur mobile, devient une rangée de puces horizontales.
- **Centre** : cards des liens (favicon auto, description, mémo du lien, chips 🌐/🔒 avec statut). Drag & drop pour réordonner.
- **Colonne droite** : résumé des mémos en cours (post-its avec priorité et échéance). Ajout rapide (Entrée). Un clic ouvre la vue Mémos complète.
- **Vue Mémos** (sidebar → 📝 Mémos) : gestion de tâches façon Planify. Tuiles de filtres (En cours / Aujourd'hui / Planifiés / En retard / Terminés), sections par échéance, cases à cocher, priorités P1-P3 (bordure rouge/orange/bleue), sous-tâches avec progression, liens web cliquables, édition au clic. **Projets** : sous "Mémos" dans la sidebar (Inbox + projets colorés), drag & drop d'un mémo vers un projet, sélecteur de projet à l'ajout et dans le détail. **Images** : bouton 📎 dans le détail d'un mémo ou glisser-déposer un fichier image sur le mémo ; miniatures cliquables (visionneuse plein écran), suppression au survol en mode détail. **Texte riche** : cliquer sur le texte d'un mémo ouvre un éditeur WYSIWYG (Quill 2, auto-hébergé dans `static/`) — titres, gras/italique, couleurs, listes (puces, numérotées, **à cocher**), liens, citations, code. Les listes à cocher sont **cliquables directement sur la card** (et sur la page partagée) sans ouvrir l'éditeur — idéal listes de courses. Le HTML est sanitizé au rendu ; si `static/quill.min.js` manque, l'édition retombe sur une textarea simple.
- **Recherche** : `/` pour focus, filtre liens + mémos en tapant, Entrée ouvre le premier résultat, Échap efface. Taper `#tag` filtre par tag exact. **Portée** : sélecteur Tout / Liens / Mémos / Projets dans la barre, ou préfixes clavier `p#`, `l#`, `m#` (ex. `p#docker` cherche dans les projets et bascule le sélecteur). Une recherche qui matche des projets (nom ou tags) affiche une section "Projets" cliquable en haut de la vue Mémos, et inclut les mémos de ces projets dans les résultats.
- **Tags `#`** : champ tags sur les liens (chips cliquables sur les cards) et `#tags` libres dans le texte des mémos (rendus cliquables). Cliquer un tag ouvre la vue Mémos filtrée sur ce tag, avec un bandeau pour basculer vers les liens qui le portent — liens ↔ mémos reliés par leurs # communs.
- **⚙ Paramètres** : export/import JSON, gestion des catégories et projets (pop-in nom + couleur via ✎, suppression), refresh des statuts, fuseau horaire supplémentaire (l'heure de Paris s'affiche automatiquement quand l'appareil est sur un autre fuseau). Un **double-clic** sur un projet ou une catégorie dans la sidebar ouvre directement la pop-in de modification.
- **📍 Géolocalisation** : mémos et projets peuvent porter une position (`location` JSON lat/lng/label) — capture GPS "Ma position" **ou saisie d'adresse** (géocodage Nominatim, sélecteur si plusieurs résultats) dans le détail du mémo, la pop-in projet et la page partagée (invités validés). Le label est rempli automatiquement par géocodage inverse à la sauvegarde. Badge 📍 cliquable vers OpenStreetMap. **🗺 Carte** : bouton dans la vue Mémos (et tuile sur la page partagée) affichant tous les points du scope sur une carte Leaflet auto-hébergée (`static/leaflet.js` + `leaflet.css`, tuiles OSM, marqueurs colorés par priorité, popup titre + lieu). Export v13.

- **🗑 Corbeille** (sidebar) : supprimer un mémo ne l'efface pas — il part en corbeille, restaurable 7 jours puis purgé. Restaurer / supprimer définitivement / vider. La suppression et la duplication d'un mémo sont dans un **menu ⋯** en haut de la pop-in d'édition. De même, la suppression d'un **projet** est dans un menu ⋯ en haut de sa pop-in (le pied de page ne garde qu'Annuler / Enregistrer).
- **Mentions `@`** : dans l'éditeur d'un mémo et dans les commentaires, taper `@` propose les personnes (toi + invités + noms déjà utilisés, saisie libre) et insère `@Nom` (qui est aussi ajouté aux assignés). Un assigné/mention sans accès au partage apparaît en **ambre ⚠**.
- **Commentaires** : fil signé sous chaque mémo, avec **réponses** (↩), **priorité** P1/P2/P3 et **« 👁 vu par … »** (accusé de lecture auto à l'ouverture). Fonctionne aussi pour les invités sur la page partagée.
- **🔗 Partages** : QR code (▦) de chaque lien/accès (pop-in avec récap cible/droits/PIN/personnes), et bouton pour **ouvrir un projet supplémentaire à un invité existant** (pré-approuvé, lien + PIN générés).
- **Favicon** : `static/favicon.svg` (tuile aux couleurs du dashboard).
- **Header** : bouton 👁 pour **masquer entièrement la sidebar**, bouton ☰ pour la **replier en rail d'icônes** (64px) — les deux états sont indépendants et mémorisés (`localStorage` `sbHidden`/`sbRail`), animations GSAP backIn/backOut. Bouton 🌙/☀️ pour basculer le **thème clair / sombre** (mémorisé dans `localStorage` `theme`, appliqué avant le rendu pour éviter tout flash). Disponible aussi sur la page partagée.
- **Pop-ins partout** : aucune boîte de dialogue native du navigateur (`alert`/`confirm`/`prompt`). Confirmations et messages passent par des pop-ins maison (`notify()` / `confirmPopin()`), côté propriétaire **comme côté page partagée**.
- **Responsive mobile** : sous 900px, la sidebar devient une rangée de puces **collante** (épinglée sous le header), les badges des mémos passent sous le texte (pas de colonne écrasée), les actions de card sont visibles d'emblée (sans survol), la barre d'outils de l'éditeur tient sur une ligne défilable, et l'en-tête d'un projet expose un bouton **✎ Modifier** (le double-clic n'étant pas tactile). Le bouton « + Ajouter » du header (création de lien) est masqué hors de la vue Liens. Mêmes adaptations sur la page partagée.

## Modèle de données

Table `links` :

| Champ         | Type    | Notes                                  |
|---------------|---------|----------------------------------------|
| `id`          | INTEGER | Clé primaire auto                      |
| `name`        | TEXT    | Obligatoire                            |
| `descr`       | TEXT    | Description courte                     |
| `url_public`  | TEXT    | URL publique (🌐), optionnelle         |
| `url_local`   | TEXT    | URL VPN/locale (🔒), optionnelle       |
| `memo`        | TEXT    | Notes libres, multi-ligne              |
| `position`    | INTEGER | Ordre d'affichage (global)             |
| `category_id` | INTEGER | FK vers `categories`, NULL = sans catégorie |
| `uid`         | TEXT    | UUID stable, suit le lien à travers les exports/imports |
| `created_at`  | TEXT    | Date de création (ISO, UTC)            |
| `updated_at`  | TEXT    | Dernière modification (ISO, UTC)       |
| `tags`        | TEXT    | Tags normalisés (minuscules, sans #, séparés par espaces) |

Table `categories` : `id`, `name` (unique), `position`, `color` (hex, optionnel), `emoji` (optionnel — catégories, projets et mémos ont chacun un champ `emoji`, réglable via la pop-in d'édition ou le détail du mémo, affiché dans la sidebar, les cards et la page partagée).

Table `memos` : `id`, `content`, `position`, `created_at`, `uid`, `updated_at`, `done` (0/1), `due_date` (YYYY-MM-DD), `priority` (0 = aucune, 1-3 = P1-P3), `subtasks` (JSON `[{content, done}]`), `project_id` (FK vers `projects`, NULL = Inbox), `images` (JSON, noms de fichiers dans `data/uploads/`), `recurrence` ('' ou daily/weekly/monthly/quarterly/yearly), `title` (titre optionnel, affiché en gras — un mémo est valide avec un titre OU un contenu), `assignees` (JSON, liste de noms libres : on peut rattacher quelqu'un qui n'est pas encore invité, badges @nom), `deleted_at` ('' = actif, sinon date ISO = en **corbeille**). Supprimer un mémo pose `deleted_at` (suppression douce, restaurable) ; les mémos en corbeille sont exclus de `/api/memos`, du partage et de l'export. Purge définitive après `BACKUP_KEEP_DAYS` jours ou via la corbeille.

Table `memo_comments` : `id`, `memo_id`, `memo_uid`, `author` (« moi » ou « Nom <email> » pour un invité), `share_id` (NULL = propriétaire), `body` (texte brut), `created_at`, `parent_id` (réponse à un commentaire — un seul niveau, une réponse à une réponse est rattachée à la racine), `priority` (0 = aucune, 1-3). Fil signé sous chaque mémo (badge 💬 n), **mentions `@`**, **réponses imbriquées**, **pastille de priorité** ; les invités validés commentent depuis la page partagée, suppression réservée au propriétaire, commentaires invités comptés dans la cloche 🔔.

Table `comment_seen` : `id`, `comment_id`, `viewer` (« Fabien » pour le propriétaire, nom/email pour un invité), `seen_at`, unique (comment_id, viewer). **Accusés de lecture** : à l'ouverture d'un mémo (proprio) ou du partage (invité), tous ses commentaires sont marqués vus par la personne. Chaque commentaire affiche « 👁 vu par … » (en excluant soi-même).

Table `memo_history` : `id`, `memo_uid`, `content`, `project` (nom), `done_at` (ISO UTC). Une entrée par tâche cochée ; décocher retire l'entrée la plus récente du mémo. Conservé sans limite (purge manuelle dans Paramètres).

Table `priorities` : `id`, `name` (unique), `color`, `position`. Seedée au premier démarrage avec P1 rouge / P2 jaune / P3 vert, entièrement configurable dans Paramètres (ajout, renommage, couleur, suppression — les mémos repassent alors sans priorité). `memos.priority` référence `priorities.id` (0 = aucune).

**Récurrence** : cocher un mémo récurrent ne le termine pas — il est journalisé dans l'historique et sa `due_date` avance d'une période **calée sur l'échéance prévue** (pas sur le jour du cochage) ; s'il était très en retard, l'échéance saute jusqu'à la prochaine date future.

Table `projects` : `id`, `name` (unique), `color`, `position`, `tags` (même normalisation que les liens), `emoji`, `parent_id` (hiérarchie parent/enfants, anti-cycle), `description` (texte libre affiché sous le titre du board — éditable au clic — et sur la page partagée). Les projets organisent les mémos (façon Planify), indépendamment des catégories de liens. **Hiérarchie** : glisser un projet sur un autre dans la sidebar l'imbrique (le déposer sur "Mémos" le remet à la racine) ; l'arbre est indenté ; ouvrir un parent affiche aussi les mémos de ses descendants (badge du sous-projet) ; **partager un parent partage tout l'arbre** — un avertissement liste les sous-projets concernés à la création du lien. Supprimer un parent rend ses enfants racines.

Les URLs sans scheme sont préfixées automatiquement en `http://` au save. La migration des anciennes bases est automatique au démarrage (`init_db`).

## API

| Méthode | Endpoint                   | Description                                    |
|---------|----------------------------|------------------------------------------------|
| GET     | `/api/links`               | Liste les liens, triés par `position`          |
| POST    | `/api/links`               | Crée un lien                                   |
| PUT     | `/api/links/<id>`          | Met à jour un lien (dont `category_id`)        |
| DELETE  | `/api/links/<id>`          | Supprime un lien                               |
| POST    | `/api/links/reorder`       | `{ids: [...]}` — réécrit les positions         |
| GET     | `/api/links/status`        | `{id: {public, local}}` — ping côté serveur    |
| GET     | `/api/categories`          | Liste avec `link_count`                        |
| POST    | `/api/categories`          | Crée une catégorie (`{name}`)                  |
| PUT     | `/api/categories/<id>`     | Renomme                                        |
| DELETE  | `/api/categories/<id>`     | Supprime (les liens passent à NULL)            |
| POST    | `/api/categories/reorder`  | `{ids: [...]}`                                 |
| GET     | `/api/memos`               | Liste les mémos (avec `comment_count`)         |
| POST    | `/api/memos`               | Crée un mémo (`{content}` et/ou `{title}`, `assignees`) |
| PUT     | `/api/memos/<id>`          | Met à jour (contenu, titre, assignés…)         |
| DELETE  | `/api/memos/<id>`          | **Suppression douce** → corbeille (`deleted_at`) |
| POST    | `/api/memos/<id>/duplicate`| Duplique le mémo (sans images, `done`=0, titre + « (copie) ») |
| POST    | `/api/memos/reorder`       | `{ids: [...]}`                                 |
| GET     | `/api/trash`               | Mémos en corbeille                             |
| POST    | `/api/trash/<id>/restore`  | Restaure un mémo de la corbeille               |
| DELETE  | `/api/trash/<id>`          | Purge définitive d'un mémo (images + shares + commentaires) |
| DELETE  | `/api/trash`               | Vide la corbeille                              |
| GET     | `/api/memos/<id>/comments` | Fil de commentaires (avec `parent_id`, `priority`, `seen`) |
| POST    | `/api/memos/<id>/comments` | Ajoute un commentaire (`{body, priority?, parent_id?}`) |
| POST    | `/api/memos/<id>/comments/seen` | Marque les commentaires du mémo « vus » (propriétaire) |
| DELETE  | `/api/comments/<id>`       | Supprime un commentaire (propriétaire)         |
| GET     | `/api/qr?data=<url>`       | QR code du texte/URL, en SVG                   |
| GET     | `/api/projects`            | Liste avec `memo_count` (mémos en cours)       |
| POST    | `/api/projects`            | Crée un projet (`{name, color}`)               |
| PUT     | `/api/projects/<id>`       | Renomme / change la couleur                    |
| DELETE  | `/api/projects/<id>`       | Supprime (les mémos retournent dans l'Inbox)   |
| POST    | `/api/projects/reorder`    | `{ids: [...]}`                                 |
| GET     | `/api/priorities`          | Liste avec `memo_count`                        |
| POST    | `/api/priorities`          | Crée une priorité (`{name, color}`)            |
| PUT     | `/api/priorities/<id>`     | Renomme / change la couleur                    |
| DELETE  | `/api/priorities/<id>`     | Supprime (les mémos repassent sans priorité)   |
| GET     | `/api/history`             | Historique des tâches effectuées (récent d'abord) |
| DELETE  | `/api/history`             | Vide l'historique                              |
| POST    | `/api/memos/<id>/images`   | Upload multipart (`image`) — png/jpg/gif/webp, 16 Mo max |
| DELETE  | `/api/memos/<id>/images/<nom>` | Supprime l'image (fichier inclus)          |
| GET     | `/uploads/<nom>`           | Sert une image uploadée                        |
| GET     | `/api/favicon/<id>`        | Favicon du service, récupéré côté serveur (cache mémoire) |
| GET     | `/api/export`              | Sauvegarde JSON v15 (liens + catégories + projets hiérarchisés + priorités + mémos hors corbeille + historique + géoloc + commentaires avec priorité/réponses) |
| POST    | `/api/import`              | Réimporte une sauvegarde (voir Backup / restore) |

Le check de statut est fait côté Flask pour éviter le CORS. Renvoie `online` / `offline` / `unknown` (URL vide) par URL renseignée.

La météo est récupérée côté client depuis open-meteo.com (Bayonne, gratuit, sans clé). Les favicons sont récupérés par Flask via l'URL locale du service (ce qui contourne Authelia), avec fallback `icons.duckduckgo.com` puis initiale du nom.

## Partage par lien

Un mémo (bouton 🔗 dans son détail) ou un projet entier (bouton 🔗 à côté du titre du projet) peut être partagé avec des personnes **sans compte**, via un lien à jeton : `https://dash…/share/<token>`. À la création tu choisis **lecture seule** (👁) ou **modifiable** (✏️ — cocher, éditer le texte, cocher les sous-tâches ; sur un projet : ajouter des mémos). Les liens sont listés et révocables dans la même pop-in ; supprimer le mémo/projet révoque ses liens. La page partagée est minimale, scopée à la ressource (images comprises, servies par `/share/<token>/image/…`), `noindex`, et se rafraîchit toutes les 15 s. Ce rafraîchissement auto **ne reconstruit pas** le formulaire de connexion invité tant qu'il est à l'écran, donc il n'efface pas la saisie en cours (prénom/e-mail/code) ; un code PIN erroné affiche une erreur **inline** sans vider le prénom ni l'e-mail.

Table `shares` : `id`, `token` (unique, `secrets.token_urlsafe(24)`), `kind` (`memo`/`project`), `target_id`, `can_edit`, `created_at`. Les liens de partage ne sont **pas** inclus dans l'export JSON.

**Invités identifiés** : sur un lien modifiable, la consultation est libre mais **modifier exige de se connecter** : e-mail + prénom + **code PIN à 4 chiffres**. Le code est propre à chaque lien, visible et modifiable par le propriétaire (pop-in 🔗 et page Partages) — le transmettre à la personne vaut validation : code correct = invité validé d'office. Table `share_guests` (e-mail, `guest_token`, statut). Le propriétaire peut toujours refuser/supprimer un invité après coup.

**Page 🔗 Partages** (sidebar ou cloche du header) : vue dédiée regroupant les demandes en attente, tous les liens de partage (cible, droits, **PIN éditable**, URL à copier, invités du lien avec leurs statuts, révocation) et les **modifications groupées par invité** — chaque entrée dépliable en Avant/Après avec annulation et accès aux versions.

Un invité validé peut tout faire sur les mémos du partage : cocher/décocher (mémo, sous-tâches, cases des listes), ajouter des articles aux listes, éditer le texte, changer échéance et priorité, ajouter/supprimer des **photos** — limitées à JPG/PNG avec **vérification de la signature binaire** côté serveur (un zip renommé en .png est rejeté ; gif/webp restent réservés au propriétaire). Sur un projet partagé, il peut aussi **créer des mémos dans n'importe quel projet du scope** (sélecteur) et **créer des sous-projets** (`POST /share/<token>/projects`, parent forcé dans le scope, journalisé dans le fil). Tout est journalisé et attribué.

La page partagée d'un projet affiche une **sidebar** avec l'arborescence des projets du partage (indentée, compteurs, navigation par clic — "Tous" + chaque projet/sous-projet) et des **tuiles de filtres** (En cours / Aujourd'hui / Planifiés / En retard / Terminés) calculées sur la sélection. Les invités validés y gèrent la hiérarchie : **glisser un mémo sur un projet** le déplace, **glisser un sous-projet sur un autre** le réorganise, et **double-clic / clic droit sur un projet** ouvre la pop-in d'édition (nom, emoji, couleur — renommages journalisés dans le fil). La racine du partage est éditable mais indéplaçable ; parents et déplacements strictement limités au périmètre du partage, anti-cycle, noms uniques. Côté propriétaire, un **récap des invités connectés** (✏️ Marie en modification, 👁 ... en lecture) s'affiche sous le titre d'un projet partagé et dans le détail d'un mémo partagé. Le pied de page des deux interfaces affiche la version (`APP_VERSION` dans `app.py`, alignée sur la version d'export).

**Attribution & versions** : chaque modification (propriétaire ou invité) est journalisée dans `memo_revisions` (états avant/après en JSON, auteur, date). Le fil 🔔 Activité montre qui a fait quoi ; le bouton "🕘 Versions" dans le détail d'un mémo liste l'historique et permet — côté propriétaire uniquement, derrière Authelia — de **restaurer** n'importe quelle version (y compris l'état d'origine). La restauration est elle-même journalisée, donc réversible.

⚠️ **Authelia** : les routes `/share/*` doivent passer sans authentification. Ajouter dans `configuration.yml` d'Authelia, **avant** la règle générale du domaine :

```yaml
access_control:
  rules:
    - domain: dash.homebayonne.duckdns.org
      resources:
        - '^/share/.*$'
      policy: bypass
    # ... règle existante (one_factor/two_factor) ensuite
```

| Méthode | Endpoint                        | Description                              |
|---------|---------------------------------|------------------------------------------|
| GET     | `/api/shares`                   | Liste des liens de partage               |
| POST    | `/api/shares`                   | Crée un lien (`{kind, target_id, can_edit}`) |
| DELETE  | `/api/shares/<id>`              | Révoque                                  |
| GET     | `/share/<token>`                | Page publique                            |
| GET     | `/share/<token>/data`           | Données scopées (JSON)                   |
| PUT     | `/share/<token>/memo/<id>`      | Édition limitée (content/title/assignees/done/subtasks/date/priorité/position) si `can_edit` |
| DELETE  | `/share/<token>/memo/<id>`      | Met le mémo à la corbeille (invité approuvé) |
| POST    | `/share/<token>/memo/<id>/restore` | Restaure un mémo du périmètre depuis la corbeille |
| POST    | `/share/<token>/memo/<id>/seen` | Marque les commentaires du mémo « vus » par l'invité |
| POST    | `/share/<token>/memos`          | Ajout d'un mémo (projet + `can_edit`)    |
| POST    | `/share/<token>/memo/<id>/comments` | Commentaire signé d'un invité validé (`{body, priority?, parent_id?}`) |
| GET     | `/share/<token>/image/<nom>`    | Image d'un mémo du partage               |
| POST    | `/share/<token>/register`       | Demande d'accès invité (`{email, name}`) |
| GET     | `/share/<token>/me`             | Statut de l'invité (header `X-Guest-Token`) |
| GET     | `/api/guests`                   | Invités (toutes demandes)                |
| PUT     | `/api/guests/<id>`              | `{status: approved/rejected/pending}`    |
| DELETE  | `/api/guests/<id>`              | Supprime un invité                       |
| POST    | `/api/guests/grant`             | Ouvre un projet à un invité (`{email, name, project_id, can_edit}`) — réutilise un partage aux mêmes droits ou en crée un, pré-approuve, renvoie lien+PIN |
| GET     | `/api/activity`                 | Fil d'activité + compteur non-lus        |
| POST    | `/api/activity/seen`            | Marque l'activité comme lue              |
| GET     | `/api/memos/<id>/revisions`     | Versions d'un mémo (avant/après, auteur) |
| POST    | `/api/memos/<id>/restore`       | Restaure (`{revision_id, which}`)        |

## Backup / restore

Depuis l'UI : **⚙ Paramètres → Export JSON / Import JSON**. L'export (v15) contient liens (avec tags), catégories, projets (couleurs + tags + hiérarchie + descriptions + positions), mémos **hors corbeille** (titre/done/échéance/priorité/sous-tâches/projet/images/récurrence/emoji/position/assignés), l'historique des tâches effectuées et les commentaires (avec priorité + référence de réponse), chacun avec son `uid` et ses dates. À l'import :

1. **Même `uid` déjà en base** : si la version du fichier est plus récente (`updated_at`), le lien/mémo existant est **mis à jour** (c'est une évolution du même élément) ; sinon il est ignoré.
2. **Pas de `uid`** (anciennes sauvegardes v1/v2) : correspondance par nom + URLs pour un lien, contenu identique pour un mémo. Un lien correspondant **enrichit** les champs vides du lien existant (description, mémo, catégorie) au lieu d'être ignoré ; il n'écrase jamais un champ déjà rempli.

Rien n'est jamais supprimé par un import. Les catégories et projets sont rattachés par nom (créés si absents).

⚠️ **Images** : le JSON ne contient que les noms de fichiers, pas les images elles-mêmes. Les fichiers vivent dans `data/uploads/` — pour une sauvegarde complète, copier le dossier `data/` (qui contient déjà la base SQLite). À l'import, les noms d'images dont le fichier est absent sont ignorés.

En CLI :

```bash
# backup
curl http://localhost:8099/api/export > backup.json

# restore (sur la prod)
curl -X POST http://localhost:8099/api/import -H 'Content-Type: application/json' -d @backup.json
```

Les fichiers `backup*.json` sont gitignorés (potentiellement des infos perso) — transfère-les manuellement (scp, drag&drop, etc.).

## Sauvegardes automatiques

Un thread interne crée chaque jour dans `data/backups/` : un **export JSON** complet (version courante) et une **copie de la base SQLite** (via l'API backup, cohérente même à chaud). Rotation automatique (`BACKUP_KEEP_DAYS`, 7 jours par défaut). Bouton "💾 Sauvegarder maintenant" + liste des sauvegardes dans ⚙ Paramètres ; API : `GET/POST /api/backups`. Idempotent entre les workers gunicorn (une sauvegarde par jour). Les images de `data/uploads/` ne sont pas dupliquées — pour un backup externe complet, copier le dossier `data/`. Restauration : réimporter le JSON, ou remplacer `data/dashboard.db` par une copie.

## Persistance

La base SQLite vit dans `./data/dashboard.db`, monté en volume dans le conteneur.

## Pas d'auth

L'app n'a aucune authentification. En production, elle est servie derrière un reverse proxy Caddy avec `basic_auth`. Ne pas exposer directement.

## Déploiement Zimaboard

Le même `docker-compose.yml` tourne tel quel sur le Zimaboard : `git clone` + `docker compose up -d --build`. Le port 8099 y est déjà routé derrière Caddy.
