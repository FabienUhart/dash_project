# Brief CC — [NOTIF-CENTER] : la cloche devient un vrai centre de notifications, owner ET invités

> **Back + front 3 pages, table additive `notifications`, export v30 INCHANGÉ (la table est volatile,
> comme `activity_seen_at`).** Cible **V30.3.285** (après [CI-HYGIENE] V30.2.284). Doctrine TDD : rouges
> d'abord, mutations tuées, `make test` vert, STOP avant push, GO explicite de Fabien.
> Demande Fabien (mémo prod 411, 15 → 18 oct. 2026) : « quand j'appuie sur la cloche il y a du paramétrage
> des invités et des notifications, je ne m'y retrouve pas » ; « je veux savoir quand un utilisateur me
> notifie et quand un nouvel utilisateur est sur l'application » ; « le point 1 doit être clair aussi pour
> les invités, dans leur dossier » ; « l'onglet Activité discret c'est pas mal » ; « les invités ont la même
> cloche, limitée à leur partage ».
> **Maquette validée** (3 écrans cliquables, 18 oct. 20h30) : https://claude.ai/artifact/5KFwLFZcZCbZ4tyMA9Mh2S
> — owner mobile, invité mobile (cloche + chip « n pour toi » sur la card), owner ordinateur (panneau 760 px).

## 0. Contexte — à relire avant de coder

- Aujourd'hui `#activity-btn` (🔔, `index.html` l.~2394) ouvre `openSharesView()` : la vue Partages
  (invités, rôles, demandes, actes des délégués, « MODIFICATIONS PAR INVITÉ »). Le badge = `/api/activity`
  → `pending_guests + unseen`, où `unseen` mélange révisions de mémos par invité, commentaires d'invités et
  actes de délégués, tous comparés à UN seul `activity_seen_at` global (`app_state`). Ouvrir la vue marque
  tout vu d'un coup. C'est ce mélange que Fabien ne comprend plus.
- Côté invité (`share.html`, `hub.html`) : aucune cloche. Les commentaires ont `comment_seen` (par viewer)
  et un compteur 💬 sur la card, rien de plus.
- Ce qui existe et qu'on RÉUTILISE comme sources d'événements : `memo_comments` (+ `data-mention` dans le
  HTML des commentaires et du corps, `_owner_name()` l.~7217), `memo_revisions` (`_log_revision`, share_id
  non nul = invité), `image_trash` (`deleted_by`), `role_requests`, `admin_actions`, `share_guests`
  (`created_at`), `guest_hubs.last_seen_at`, `memo_votes`/`votes`, `memos.source` (écritures API/MCP),
  `api_audit`. On ne recalcule PAS un flux à la volée depuis ces tables à chaque poll : on **écrit une
  ligne de notification au moment de l'événement** (fan-out par destinataire), c'est la seule façon d'avoir
  un « non lu » par personne et des compteurs justes.
- Invariant 5 : un invité ne voit JAMAIS une notification hors de son partage ; aucune route publique
  nouvelle hors `/share/<token>/*`. Invariant 8 : panneau sans GSAP. Invariant 9 : gabarits existants
  (`#search-sheet` en mobile, `.cover-seg` pour les onglets, Luciole pour les boutons). ADR-001 : le rendu
  d'une entrée est un helper partagé dans `_shared.js.html` (3 pages).

## 1. Modèle

### 1.1 Table (additive, `CREATE TABLE IF NOT EXISTS`, jamais destructive, HORS export)
```
notifications (id INTEGER PK, uid TEXT, recipient TEXT NOT NULL,   -- '' = owner, sinon 'g:<share_guests.id>'
               level TEXT NOT NULL,         -- 'me' | 'activity'
               kind TEXT NOT NULL,          -- voir §1.2
               actor TEXT NOT NULL,         -- nom affiché ('' owner → nom owner ; invité → name/email ; API → client_name)
               actor_kind TEXT NOT NULL,    -- 'owner' | 'guest' | 'api'
               share_id INTEGER, project_id INTEGER, memo_id INTEGER, memo_uid TEXT, comment_id INTEGER,
               title TEXT DEFAULT '',       -- titre du mémo / nom du dossier au moment de l'événement (snapshot)
               excerpt TEXT DEFAULT '',     -- ≤ 240 car., texte brut (commentaire, option votée…), JAMAIS de HTML
               created_at TEXT NOT NULL, read_at TEXT)
INDEX (recipient, level, read_at), INDEX (memo_id)
```
- `excerpt` toujours passé par le strip HTML existant + coupe à 240. Pas de PII supplémentaire (pas d'IP).
- **Purge** : la boucle quotidienne supprime les lues > 90 j et les non lues > 365 j (constante
  `NOTIF_KEEP_DAYS`). Un mémo purgé définitivement → ses notifications supprimées (cascade dans
  `_purge_memo_row`). Mémo en corbeille → notifications masquées (JOIN memos.deleted_at), conservées.
- `app_state.activity_seen_at` reste pour la compat de l'ancien badge le temps du lot, puis mort.

### 1.2 Catalogue des événements (qui reçoit quoi)

**Niveau `me` (« Pour moi », compte dans le badge)** — destinataire = la personne visée :
| kind | déclencheur | owner reçoit | invité X reçoit |
|---|---|---|---|
| `comment` | commentaire posé par A sur mémo M | si A ≠ owner | si A ≠ X et (X a créé M, ou X est assigné sur M, ou X a déjà commenté M) |
| `mention` | `data-mention` vers P dans un commentaire ou dans le corps à l'enregistrement | si P = owner | si P = X |
| `reply` | commentaire dont `parent_id`/réponse vise un commentaire de P (si pas de parent : commentaire posé juste après un commentaire de P sur le même mémo, dans les 24 h) | | idem |
| `vote` | vote/cœur d'un invité sur un mémo ou une option | oui | non (V1) |
| `guest_new` | première visite d'un invité (création `share_guests` auto-approuvée, ou premier `last_seen_at` d'un hub) | oui | non |
| `role_request` | demande de rôle | oui (avec `excerpt` = rôle demandé) | non |
| `role_granted` | rôle accordé/modifié pour X (owner ou délégué) | si par un délégué (= actuel `admin_actions`) | oui (X) |
Règle anti-doublon : un même événement ne produit qu'UNE ligne par destinataire (une mention dans une
réponse → `mention` seulement, pas `reply` + `mention`). L'auteur ne se notifie jamais lui-même.

**Niveau `activity` (onglet discret, ne compte PAS dans le badge)** :
| kind | déclencheur | owner | invité X |
|---|---|---|---|
| `edit` | `_log_revision` avec share_id (texte/titre/dates modifiés par un invité) | oui | oui si dans son partage et auteur ≠ X |
| `memo_create` / `memo_move` / `memo_delete` | par un invité, ou par l'owner dans un partage | oui si invité | oui si dans son partage et auteur ≠ X |
| `image_delete` | `image_trash` | oui si invité | idem |
| `api_write` | écriture via `/api/v1` ou MCP (memo create/update/complete/delete), `actor` = `client_name` du jeton | oui | **non** (jamais côté invité) |
Le front **regroupe** les entrées consécutives même `actor` + même `kind` + même dossier dans la même
heure : « Claude chat a créé 7 mémos — Dash ». Le regroupement est à l'affichage, pas en base.

### 1.3 Points d'écriture (`_notify(db, recipients, level, kind, ...)`, un seul helper)
`add_comment` / `share_add_comment` / `api_v1` comments ; enregistrement du corps (mentions) owner + share ;
`_log_revision` (edit) ; création/déplacement/suppression de mémo sous `/share/*` et sous `/api/v1/*`
(`source` ≠ '') ; `image_trash` insert ; votes ; `share_guests` insert auto-approuvé + premier
`last_seen_at` hub ; `role_requests` insert ; `decide_role_request` + actes délégués. Résolution des
destinataires invités = `share_guests` du partage englobant le mémo (`_guest_caps` sait déjà remonter
dossier → partage) ; le fan-out se fait dans la même transaction que l'événement.

## 2. Routes

**Owner (derrière Authelia)**
- `GET /api/notifications?level=me|activity&cursor=&limit=30` → `{items:[…], next_cursor, unread_me}` ;
  items = colonnes de la table + `memo_title` courant + `project_name` + `memo_deleted` bool.
- `POST /api/notifications/read` `{ids:[…]}` ou `{level:'me'|'activity', all:true}` → `{unread_me}`.
- `GET /api/activity` : conserve `role_requests`, `admin_actions`, `revisions`, `data_version`,
  `build_version` (consommés par la vue Partages et l'auto-refresh) ; **`unseen` devient
  `unread_me`** (compat : `unseen` = même valeur pendant le lot, retiré en V2). `pending_guests` inchangé.
**Invité (scopé, invariant 5)**
- `GET /share/<token>/notifications?level=&cursor=` et `POST /share/<token>/notifications/read` : le
  destinataire est DÉDUIT du token/cookie (`g:<id>`), jamais passé en paramètre ; les items sont filtrés
  `share_id = partage du token` en plus du recipient (double ceinture, testée). Hub : `/share/hub/<token>/…`
  agrège les partages du hub, même règle.
- `GET /share/<token>/data` (et hub) gagne `unread_me` + `memo_unread: {memo_id: n}` pour le chip de card.
**API v1** (scope `read`) : `GET /api/v1/notifications?level=&since=` → même payload que l'owner, lecture
seule ; `POST /api/v1/notifications/read` (scope `write`). Outil MCP `get_notifications` (lecture) ajouté
à `dash_mcp/server.py` + `docs/MCP.md` + OpenAPI. Invariant 10 : jeton obligatoire, test `url_map` étendu.

## 3. Front

**Owner (`index.html`)**
- `#activity-btn` n'ouvre plus la vue Partages : il ouvre le **panneau Notifications**. Badge = `unread_me`
  seul (jamais l'activité). La vue Partages reste accessible : sidebar « 🔗 Partages » (inchangé) et un lien
  « Partages et invités → Paramètres » en tête du panneau ; `openSharesView()` ne marque plus rien « vu ».
- **Panneau** : desktop ≥ 901 px = popover 760 px ancré sous la cloche (`position:fixed`, fermeture clic
  dehors + Échap, `aria-expanded`), mobile = bottom-sheet gabarit `#search-sheet` plein écran. Entrée CSS
  seulement (invariant 8). Onglets « Pour moi (n) » / « Activité · n » en `.cover-seg`. « Tout marquer lu »
  par onglet. Liste paginée (cursor, « Voir plus »). Entrée = `notifRow(item)` partagé (ADR-001) : avatar
  initiales (couleur dérivée du nom, comme les assignés), **qui + quoi**, chemin dossier + titre mémo
  **en entier** (pas d'ellipsis en desktop ; 2 lignes max en mobile), citation en italique bordure gauche
  pour `comment`/`mention`/`reply`/`role_request`, date relative, point orange non lu.
- Clic sur une entrée : marque lue (POST), ferme le panneau, `scrollToMemo` + ouvre la card avec le fil de
  commentaires déplié (helper existant de [MEMO-CARD-CLICK]) ; `guest_new`/`role_request` → ouvre la vue
  Partages sur la bonne ligne ; mémo en corbeille → toast « ce mémo est dans la Corbeille » + lien.
- Poll : `refreshActivityBadge()` continue (même cadence), lit `unread_me`.

**Invité (`share.html`, `hub.html`)**
- Cloche dans l'en-tête (même gabarit `.icon` + badge), panneau identique via le partial, onglets
  identiques, « Seulement ce qu'on t'adresse dans « <dossier> » » en pied (texte de la maquette).
- **Chip « n pour toi »** (orange, `.count` gabarit) sur la card d'un mémo ayant des `me` non lues pour ce
  viewer ; disparaît quand les entrées du mémo sont lues (ouvrir la card les marque lues, comme
  `_mark_comments_seen`).
- Hub : la cloche agrège tous ses partages, chaque entrée porte le nom du partage.

## 4. Tests (rouges d'abord)

Back (`tests/back/test_notifications.py`) :
1. Commentaire d'un invité sur un mémo owner → 1 ligne `me/comment` recipient '' ; l'invité auteur n'en a pas.
2. Mention `@Nono` dans un commentaire owner → `me/mention` pour `g:<nono>` seulement ; mention dans une
   réponse → pas de ligne `reply` en plus (anti-doublon).
3. Réponse à un commentaire de l'owner → `me/reply` owner.
4. Nouvel invité auto-approuvé → `me/guest_new` owner ; 2e visite → rien.
5. Demande de rôle → `me/role_request` ; accord par délégué → `me/role_granted` invité + owner.
6. Révision par invité → `activity/edit` owner ET aux autres invités du partage, pas à l'auteur.
7. Écriture via `/api/v1` avec jeton « Claude chat » → `activity/api_write` owner, `actor`= client_name,
   **aucune** ligne pour un invité.
8. **Invariant 5** : `GET /share/<token>/notifications` ne renvoie jamais une ligne d'un autre partage,
   même avec `recipient` identique (invité présent sur 2 partages) ; `POST …/read` avec un id d'un autre
   partage → 404, rien modifié.
9. Compteurs : `unread_me` ignore `activity` ; `read all level=me` ne touche pas `activity`.
10. Mémo en corbeille → masqué des listes, compteur exclu ; purge définitive → lignes supprimées.
11. Export v30 : `notifications` absente ; import d'un export v30 → aucune ligne créée.
12. Invariant 10 : `/api/v1/notifications` sans jeton → 401 `{}`, cookie session → 401.
13. Purge quotidienne : lue > 90 j supprimée, non lue < 365 j conservée.
E2E (`tests/front/test_notifications_e2e.py`) : owner badge = `me` seulement ; clic cloche → panneau,
onglets, entrée longue lisible sans ellipsis en 1280 px ; clic entrée → card ouverte, fil déplié, point
disparu, badge décrémenté ; Échap ferme ; mobile 390 px → bottom-sheet ; invité : cloche + chip « 1 pour
toi » qui disparaît à l'ouverture de la card ; vue Partages toujours accessible depuis la sidebar et
n'affecte plus le badge. Mutations à poser : retirer le filtre `share_id` côté invité (test 8 rougit),
compter `activity` dans `unread_me` (test 9 rougit), retirer l'anti-doublon (test 2 rougit).

## 5. Livraison

`REALISATION.md` [V30.3.285] ; `docs/EXPORT-FORMAT.md` : note « table volatile non exportée » ; `docs/MCP.md`
+ OpenAPI pour `get_notifications` ; IDEAS.md : [NOTIF-CENTER] retiré de la file, graines
`[NOTIF-CENTER-V2]` (préférences par type, digest, canaux → [REMINDERS]) ; `.claude/handoff.json` pour la
passe Cowork (owner desktop + mobile, invité Demo invité 142 / share 87 PIN 8235 en LOCAL). STOP avant
commit/tag/push, GO Fabien.

**Hors périmètre** : envoi push/Telegram/mail (= [REMINDERS]), préférences par type, notifications pour les
votes côté invité, regroupement en base.
