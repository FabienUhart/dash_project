# === LANGUE ===

**Toujours répondre en français**, quelle que soit la langue des skills, prompts, plugins ou specs (AIDD et autres sont en anglais — ça ne change rien : la conversation avec l'utilisateur reste en français). Le code, les noms de variables et les messages de commit techniques peuvent rester en anglais si c'est la convention du projet, mais **toute explication adressée à l'utilisateur est en français**. Cela vaut **tout le temps** : récapitulatifs de fin de réalisation, messages d'avancement, plans, questions de clarification — **tout le dialogue avec l'utilisateur est en français**, sans exception.

# === MEMORY BANK ===

Une banque de mémoire vit dans `.claude/memory/`. Avant toute réponse importante ou modification de code :
1. Lire `.claude/memory/MEMORY.md` (résumé, stack réelle, état du projet, pointeurs).
2. Lire `.claude/memory/patterns.md` si pertinent (conventions transverses).
3. Consulter les ADR dans `docs/adr/`.

Ce `CLAUDE.md` reste la **source canonique** (invariants, format d'export, historique). La Memory Bank l'**indexe**, elle ne la duplique pas. Après une grosse réalisation ou décision d'archi, proposer une mise à jour de la Memory Bank ET de ce fichier, sans recopier le contenu de l'un dans l'autre.

# CLAUDE.md

Contexte pour Claude Code. À lire avant toute modification ou commit.

## Le projet en une phrase

Dashboard perso auto-hébergé sur un Zimaboard (page d'accueil navigateur) : liens vers services self-hosted avec catégories, mémos post-it, statuts online/offline, recherche, horloge/météo.

## Architecture

- **`app.py`** : tout le backend. Flask + SQLite, pas d'ORM, pas de blueprint. La migration de schéma est dans `init_db()` (ALTER TABLE additifs + backfill, jamais destructif — ne JAMAIS dropper de colonne ou de données).
- **`templates/index.html`** : tout le frontend en un seul fichier (CSS + HTML + JS vanilla, pas de framework, pas de build). Layout "3 zones" : sidebar catégories / cards / colonne mémos.
- **`data/dashboard.db`** : SQLite, monté en volume Docker. Contient les vraies données de l'utilisateur — ne jamais la modifier ou supprimer dans un commit.
- **`data/uploads/`** : images des mémos (noms `uuid4().hex.ext`, validés par regex côté serveur). Même volume Docker, même règle : ne jamais y toucher dans un commit. Le JSON d'export ne contient que les noms de fichiers.
- **`data/uploads/derived/`** : images DÉRIVÉES [IMAGE-THUMBS] générées par **Pillow** — `t_<nom>.jpg` (vignette ~400 px : cards, bande de vignettes, calque photo carte, section 📷) et `s_<nom>.jpg` (taille écran ~1600 px : image de la visionneuse), JPEG q82, orientation EXIF appliquée. **Originaux jamais modifiés** ; le bouton ⬇ télécharge toujours le brut. **Donnée dérivée re-calculable** depuis les originaux → **jamais exportée** (l'export ne porte que les noms d'images originales, compat v23 inchangée), **jamais à toucher dans un commit** (comme `data/uploads/`). Servies via **`?size=t|s`** sur les routes image EXISTANTES (`/uploads/<nom>`, `/share/<token>/image/<nom>` — scope invité inchangé, invariant 5) ; sans param, valeur inconnue, GIF, image plus petite que la cible, ou échec Pillow → **original servi** (jamais de 404). Génération à l'upload (`_save_uploaded_image`) + backfill daemon idempotent (`_backfill_derived`) ; purge en cascade avec l'original (`_delete_derived` via `_delete_image_files` + les 2 suppressions per-image).
- Déploiement : `docker compose up -d --build` (gunicorn, port 8099, derrière Caddy + Authelia en prod).

## Invariants à respecter

1. **Compat ascendante des sauvegardes** : `/api/import` doit toujours accepter les exports **v1 → v28**. Index : v1 liens seuls · v2 +catégories/mémos · v3 +`uid`/dates · v4 +done/due_date/priority/subtasks (mémos), color (catégories) · v5 projets de mémos (par nom) · v6 images mémos (noms de fichiers) · v7 tags liens · v8 tags projets · v9 `recurrence` + `history` · v10 `priorities` (remap par NOM) · v11 `emoji` · v12 `parent` projets (nom, 2 passes) · v13 `location` · v14 `title`/`assignees` mémos, `description` projets, `comments` · v15 `priority`/`parent_created_at` sur comments, corbeille exclue · v16 `marker_color` · v17 `map_groups` · v18 `due_time` · v19 `created_by` mémos · v20 `is_trip` projets (brut, hérité) · v21 `reactions` + palette `reaction_emojis` · v22 `attachments` mémos · v23 `attachments` projets · v24 `due_end` · v25 `uid`/`parent_uid` projets, `project_uid` mémos (noms uniques PAR PARENT, résolution uid-d'abord) · v26 `created_by` projets · v27 `memo_links` (par uid) · v28 `link_refs` (par uid). **Le détail de chaque version (champs, validation, règles d'import non destructif, exposition invités) est dans [`docs/EXPORT-FORMAT.md`](docs/EXPORT-FORMAT.md) — à lire AVANT tout changement de format ou d'import, et à compléter à chaque bump.** Toute évolution du format incrémente `version` dans l'export et reste importable.
2. **L'import n'est jamais destructif** : il ajoute, met à jour (uid identique + `updated_at` plus récent) ou enrichit les champs vides (match nom+URLs sans uid). Il ne supprime ni n'écrase jamais un champ rempli avec une donnée plus ancienne.
3. **`uid`** : UUID stable qui suit chaque lien/mémo à travers exports/imports. Généré à la création et backfillé par `init_db()`. Ne jamais le régénérer pour une ligne existante.
4. **Les URLs locales** (`192.168.1.x`) servent au check de statut ET à la récupération des favicons côté serveur (contournement d'Authelia). Le cache favicon (`_favicon_cache`, en mémoire) doit être invalidé quand les URLs d'un lien changent.
5. **Pas d'auth dans l'app** : la sécurité est assurée par le reverse proxy. Ne pas ajouter de login. **Exception volontaire** : les routes publiques invité vivent **toutes sous le préfixe `/share/...`** — le partage `/share/<token>/...` ET le hub `/share/hub/<hub_token>/...` (hub agrégé ; **déplacé de `/g/` vers `/share/hub/` en V19.8 précisément pour réutiliser le bypass `/share/*` existant**, sans toucher à Caddy). Elles sont publiques via la règle bypass Authelia `/share/*` (déjà en place) et protégées uniquement par le jeton (+ code PIN) — elles ne doivent JAMAIS exposer autre chose que la ressource partagée (mémo ou projet ciblé, ses sous-tâches et ses images). Toute écriture via `/share/` exige en plus un invité **approuvé** (header `X-Guest-Token`, approbation obtenue par le code PIN du lien). **Toute nouvelle route publique invité DOIT vivre sous `/share/...`** (pour être couverte par le bypass `/share/*` sans toucher au reverse proxy) et rester dans ce périmètre — **ne JAMAIS créer un préfixe de premier niveau** (ex. l'ancien `/g/`), ce qui obligerait à éditer la config Caddy du Zimaboard (HORS de ce repo) et a déjà piégé `/g/*` à sa sortie. **Vérification après tout ajout de route publique** : une requête **non authentifiée** (`fetch(path, {credentials:'omit', redirect:'manual'})`) doit **atteindre l'app** (réponse `basic`, ex. 404) et **pas** être redirigée vers Authelia (`opaqueredirect`/302). Les uploads d'images (propriétaire comme invité) passent par `_save_uploaded_image()` qui vérifie la **signature binaire** du fichier — ne jamais accepter un upload sans cette vérification.
6. **Sortie HTML auto-contenue, sans build** : la **page livrée** reste un HTML autonome (CSS + JS inlinés, pas d'étape de build, pas de dépendance runtime externe). Au niveau **source**, les **helpers purs et identiques** owner/invité vivent dans **`templates/partials/_shared.js.html`** (un seul `<script>`), inclus dans `index.html` ET `share.html` via `{% include 'partials/_shared.js.html' %}` au rendu Jinja — donc inlinés dans la sortie, sans asset servi à part (pas de `/share/assets`, invariant 5 non impacté), réf. **ADR-001 (Option C)** dans `docs/adr/`. **Règle** : n'y mettre que des fonctions **sans état, sans dépendance à `state`/`DATA`, et au corps strictement identique entre les deux pages** (vérifier par diff avant d'extraire) ; jamais de logique élargissant le périmètre invité. Le rendu lié aux données (`renderSidebar`, carte, vue Plan…) reste, lui, dupliqué pour l'instant (chantier ADR-001 items 4/6). Hors de ce partial : pas de séparation CSS/JS du code maison. Dépendances front autorisées uniquement si **auto-hébergées dans `static/`** (actuellement : Quill 2 pour l'édition riche des mémos — dégrade en textarea si le fichier manque ; `gsap.min.js` pour les animations — dégrade proprement si absent ; `leaflet.js`/`leaflet.css` ; **Leaflet.markercluster** (`leaflet.markercluster.js` + `MarkerCluster.css` + `MarkerCluster.Default.css`, vendorisé 1.5.3, [PHOTO-CLUSTER] — clustering du calque photo de la carte, dégrade en marqueurs simples si absent) ; **quill-table-better** (`quill-table-better.js` + `quill-table-better.css`, vendorisé 1.2.3 MIT, [MEMO-TABLES] — tableaux dans l'éditeur Quill des mémos, activé par le helper partagé `applyTableBetter()` du partial ; absent = no-op, éditeur sans bouton ⊞ et tableaux existants toujours rendus par Quill 2 core) ; `favicon.svg`). Pour les invités, ces fichiers sont servis par la route publique `/share/assets/<nom>` (liste blanche `SHARE_ASSETS`) car `/static/` est derrière Authelia. Pas de CDN au runtime, sauf les appels existants : open-meteo, icons.duckduckgo.com (fallback favicon), nominatim.openstreetmap.org (géocodage à la sauvegarde uniquement, échec silencieux), tile.openstreetmap.org (tuiles de la carte Leaflet, auto-hébergée dans `static/` : `leaflet.js` + `leaflet.css`, marqueurs vectoriels `circleMarker` donc aucune image Leaflet requise) et **api.frankfurter.app** (taux de change BCE du convertisseur ¥€ [FX-CONVERTER] — **appel SERVEUR uniquement, 1 fetch/jour maximum**, cache `app_state.fx_cache`, échec silencieux → dernier cache ; jamais depuis le navigateur).
7. **Suppression douce** : supprimer un mémo (UI propriétaire OU invité) ne fait JAMAIS de `DELETE` SQL — ça pose `memos.deleted_at` (corbeille). Les mémos en corbeille sont exclus de `/api/memos`, du scope partage et de l'export. La purge définitive (fichiers images + shares + commentaires) n'arrive QUE via la corbeille (routes `/api/trash`) ou la purge auto `_purge_trash()` après `BACKUP_KEEP_DAYS` jours. La restauration owner-only est `/api/trash/<id>/restore` (≠ `/api/memos/<id>/restore` qui restaure une *révision*). **[COMMENTS-V2 addendum]** Même doctrine pour un **commentaire** : le supprimer (owner *ou* auteur invité) ne fait plus de `DELETE` SQL — `memo_comments.deleted_at` (colonne additive) pose une **pierre tombale** : la ligne survit pour que **les réponses gardent leur contexte**, mais le **corps est VIDÉ en base** au même instant (réactions et accusés de lecture supprimés, vocal → **fichier purgé** + ligne système « 📎 a ajouté … » retirée). Une tombale n'a **aucune action** (réagir dessus est refusé serveur, 404) et ne compte ni dans 💬 ni dans 🔔. **Le serveur tranche qui peut supprimer** : owner partout (modération), invité **uniquement son propre message** (match par e-mail, `can_edit` NON requis — retirer ses mots n'est pas éditer) via `DELETE /share/<token>/comment/<id>` sous `/share/*` (invariant 5) ; le message d'un autre → **403**. **Les tombales sont EXCLUES de l'export** (comme les mémos en corbeille) : aucun champ nouveau ne sort ⇒ **pas de bump de format** ; conséquence assumée, après restauration sur base vierge une réponse dont le parent avait été supprimé remonte au premier niveau. **[IMAGE-TRASH addendum]** Même doctrine pour une **image de mémo** : la supprimer (owner *ou* invité, par les routes scopées EXISTANTES `/api/memos/<id>/images/<name>` et `/share/<t>/memo/<id>/images/<name>` — invariant 5) ne fait plus `os.remove` — le nom quitte `memos.images` (donc l'image disparaît des vues, du calque photo via `_project_photos`, du scope partage et de l'export) mais **le fichier et ses dérivées [IMAGE-THUMBS] restent sur le volume**, tracés par la table additive `image_trash` (`deleted_by` = pattern `created_by` v19 : `''` = propriétaire, sinon « Nom <email> »). La purge définitive n'arrive QUE via la corbeille owner-only (`/api/image-trash`, incl. cascade à la purge du mémo porteur) ou la purge auto `_purge_image_trash()` après **`IMAGE_TRASH_DAYS` = 30 jours** (délai PROPRE, distinct de `BACKUP_KEEP_DAYS`). Restaurer remet le nom en fin de `memos.images` et **refuse (410)** si le binaire a disparu (jamais de référence orpheline). Une suppression d'invité pose une entrée `memo_revisions` (share_id) → notification 🔔 + 🔗 Partages. `image_trash` n'est **PAS exportée** (le nom a déjà quitté `memos.images`) ⇒ **pas de bump de format** ; conséquence assumée, une image en corbeille ne survit pas à un cycle export/import, comme un mémo en corbeille.
8. **Animations** : ne JAMAIS animer un élément `<dialog>` lui-même via GSAP (`y`/`scale`/`autoAlpha`) — poser un transform GSAP sur un dialog le sort du top-layer Chromium et casse le centrage + le `::backdrop`. L'entrée des pop-ins est gérée en CSS (`@keyframes dlg-in`/`dlg-bd` sur `dialog[open]`, sous `prefers-reduced-motion`). GSAP n'anime que des éléments hors top-layer (cards, sidebar, tuiles) ou des enfants d'un dialog, jamais le dialog.
9. **Cohérence visuelle — réutiliser les classes existantes, pas de styles bespoke** : toute nouvelle UI (boutons, chips, pastilles, pop-ins) doit **réutiliser les classes/tokens du système existant** plutôt que d'inventer ses propres styles. Référence = les **cards** (« Voyage Japon ») : boutons d'action ronds via le style `.task .task-actions button` (rayon `9px`, `var(--panel-2)`/`var(--border)`, hover `var(--panel)`/`var(--muted)`, **action principale en accent** comme `.texp`/`.tedit`) ; petits chips/filtres via `.prio-btn` (sélectionné = `background:var(--accent);color:#10141a`) ou `.mfilter` ; pastilles texte via `.badge` ; suppression en danger (`var(--red)`, cf. `.thumb-del`). Couleurs **toujours** via les variables CSS (`--accent`, `--panel`, `--border`, `--muted`, `--red`…), jamais en dur. Si un composant a besoin d'un style à part (ex. `.iv-btn`, overlays sur photo), il **s'aligne** sur ces tokens et reste une exception justifiée — pas un nouveau langage visuel. But : une seule source de vérité du look, owner ET invité (composants partagés dans le partial — réf. ADR-001). **Boutons → style « Luciole »** (`docs/design/LUCIOLE-boutons.md`, baptisé le 30 juil. 2026) : **jamais d'aplat accent plein sur le chrome** (la couleur pleine est réservée aux DONNÉES), **le mouvement n'appartient qu'au geste** (lueur/lift au survol seulement, zéro animation permanente), **un état persistant se dit par la MATIÈRE et le LIBELLÉ** (bordure/fond/creux + « Détails » ⇄ « Réduire »), clair et sombre chacun juste dans son monde. Toute nouvelle UI de boutons s'y réfère ; dire « bouton Luciole » dans un brief = ce doc (helpers `mabGlowButton`/`lucioleize` dans `templates/partials/_shared.js.html`, CSS par page). Le danger reste **rouge** (`button.danger`), jamais en Luciole.

## Versionnage (SemVer projet `VX.Y.Z`)

Suivi des versions en `VX.Y.Z` (ex. `V19.1.123`) :

- **X** = version du **format d'export** (= invariant 1, `APP_VERSION` / `version` de l'export). Ne bouge **que** lors d'un changement de format de données. C'est le seul numéro qui fait foi pour la compat des sauvegardes. Actuellement **28**.
- **Y** = **mineure** : incrémentée à chaque nouvelle fonctionnalité ou lot cohérent, **même si le format d'export ne change pas** (beaucoup de features sont « export inchangé »).
- **Z** = **build / identifiant de réalisation** : **compteur continu global**, incrémenté à chaque entrée de `REALISATION.md` et **jamais remis à 0**.

Règles d'usage :
1. **`IDEAS.md` (planification)** : chaque tâche/concept est ciblé à cette granularité, ex. « Feature A → prévu pour **V19.1** ».
2. **`REALISATION.md` (journal)** : chaque accomplissement est consigné avec son tag `[VX.Y.Z]` au moment de sa complétion/livraison, ex. `- [V19.1.123] Implémentation du module X.` C'est la **source de vérité du compteur Z** (prendre le dernier Z + 1).
3. `APP_VERSION` et le footer suivent **X** (le format d'export). Un changement de format = bump de X **et** d'une entrée dans `docs/EXPORT-FORMAT.md` + l'index de l'invariant 1.

## Tests (pytest) & méthode TDD

Depuis **V27.38.230** le projet a une **suite de tests** (`tests/`, lancée par `pytest`),
une **batterie d'invariants** et un barrage CI. Commande unique :

`make test` (suite complète), `make test-back` / `test-front` / `test-invariants`, `make install` (une fois) — cibles dans le `Makefile`.

**Sûreté** : les tests back tournent sur des **bases SQLite temporaires** (fixtures de
`tests/conftest.py`), **jamais** `data/dashboard.db` ; le front lance un `live_server` sur
une base temp dédiée. `make test` ne touche donc jamais les vraies données.

**Batterie d'invariants** (`-m invariant`) = les garde-fous non négociables, qui encodent
les invariants ci-dessus : round-trip export→import sans perte ni doublon, v1 importable,
import non destructif, uid stable, corbeille hors export, écriture invitée sous `/share/*`
uniquement, format d'export figé v27. **Un rouge sur un invariant = pas de deploy.**

**Méthode = TDD (rouge → vert)** :
- Toute **nouvelle feature back** et **tout bugfix** commencent par un **test qui échoue**
  (pour un bug : un test qui **reproduit** le bug), puis le code jusqu'au vert. Un test qui
  passe sur un bug déjà corrigé ne prouve rien — le prouver rouge d'abord.
- Le **legacy** n'est pas réécrit : il est couvert par la **batterie d'invariants**, pas par
  une couverture rétroactive ligne à ligne (doctrine hybride).
- Le **front** grossit par petits parcours e2e, chacun avec l'assertion « zéro erreur
  console ».
- Boucle : **Fabien donne l'idée → Cowork cadre (le brief liste d'abord les tests + les
  invariants touchés) → CC écrit les tests rouges puis le code → passe Cowork → GO Fabien.**

Exploration manuelle toujours possible sur une **copie** de la base (jamais la vraie) :
`cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run -p 8099` —
mais `make test` est la source de vérité.

`backup*.json` est gitignoré (données perso) — ne jamais le committer.

## Process de fin de réalisation

Après **chaque réalisation** (un lot livré et testé — pas à chaque tour de conversation), Claude Code doit, dans l'ordre :

1. **Tester** : `make test` **vert** (back + front ; bases temporaires, jamais `data/dashboard.db`). Un bugfix a d'abord eu son test rouge (cf. § Tests & TDD). Le `py_compile` reste couvert par la CI.
2. **Journaliser** : ajouter l'entrée taggée `[VX.Y.Z]` dans `REALISATION.md` (Z = dernier + 1) et basculer l'item correspondant d'`IDEAS.md` en « Fait » (cf. § Versionnage).
3. **Rebuild local** : lancer **`docker compose up -d --build`** pour que la nouvelle version tourne sur `http://localhost:8099/` et soit immédiatement testable (par Fabien et par l'agent Cowork). Le rebuild local utilise la vraie base (`./data`) : la migration doit donc rester additive et non destructive (invariant 1).
4. **Mettre à jour le journal et le handoff** : la ligne `✅` dans `.claude/session-log.md` et `.claude/handoff.json`. **`status: ready` ne vaut que si le build ET `pytest -m "not e2e"` sont verts** — le hook Stop l'impose (sinon `tests_failed`, ou `tests_skipped` si les deps dev manquent) ; jamais `deployed`.
5. **S'ARRÊTER LÀ.** Fin du lot.

### ⛔ Règle permanente : CC ne déploie pas (actée par Fabien le 8 août 2026)

**Le lot s'arrête au rebuild local.** Pas de `git commit`, pas de `git tag`, pas de `git push`, donc pas de
**Deploy Zimaboard** — le workflow de déploiement se déclenche sur le push d'un tag, pousser *c'est* déployer.

L'ordre est : **coder → rebuild local → journal + handoff → STOP → passe Cowork → feu vert EXPLICITE de
Fabien → alors seulement commit + tag + push.**

**Pourquoi** : le 8 août 2026, un bug mobile ([MOBILE-POPIN-POLISH] V27.34.218 — croix de la pop-in
commentaires inatteignable) est parti en prod *avant* la passe Cowork ; les vrais invités auraient pu le
voir. La prod ne reçoit que du validé. Cette règle **révoque** la tolérance « deploy à la fin du lot »
qui s'était installée, et rétablit le workflow d'origine.

**Ce qui compte comme feu vert** : une demande explicite de Fabien dans la conversation (« commit »,
« déploie », « le train part », « GO »). Ni une passe Cowork verte, ni des tests verts, ni « le lot est
fini » ne valent autorisation. Dans le doute : proposer, ne pas pousser.

(Option « dure » équivalente : un hook `Stop` dans `.claude/settings.local.json` qui lance le rebuild automatiquement — voir le script fourni hors dépôt. Le présent process reste la source de vérité même si le hook n'est pas activé.)

### Les garde-fous : qui teste où

Quatre acteurs, une même règle « pas de rouge » :

1. **Hook Stop** (après chaque réalisation, sur le M4) — `pytest -m "not e2e"` (back rapide)
   → `handoff.json` `ready` seulement si vert. Boucle courte.
2. **Pre-commit** (`.githooks/pre-commit`, activé une fois par `make hooks`, sur le M4) —
   **suite complète** (back + front) avant que le commit n'existe ; rouge = commit refusé
   (`git commit --no-verify` = secours d'urgence seulement).
3. **Passe Cowork** — revue d'**honnêteté** des tests (le rouge-avant-vert est-il prouvé ?
   aucun bug figé en « comportement attendu » ?), en plus de la validation Chrome des features.
4. **CI GitHub** — `deploy.yml` porte `deploy: needs [tests]` → **rouge = pas de deploy**.
   C'est la garantie **portable** : elle suit le dépôt. Les hooks locaux (Stop, pre-commit)
   vivent sur la machine — sur une machine neuve, les réarmer par `make install` + `make hooks`
   (le hook Stop, dans `.claude/` gitignoré, est à réappliquer à la main).

Le Zimaboard ne lance **jamais** de tests : uniquement l'étape de déploiement.

## Historique des évolutions majeures

Déplacé dans **[`docs/HISTORIQUE.md`](docs/HISTORIQUE.md)** (chargé à la demande, pas à chaque session).
À lire quand il faut le contexte d'une feature ancienne ; la source de vérité des lots livrés reste
[`REALISATION.md`](REALISATION.md).

## Sauvegardes

Sauvegarde quotidienne automatique (`_backup_loop`) dans `data/backups/`, rotation `BACKUP_KEEP_DAYS`. Ne jamais committer `data/`.

## Backlog

Voir [IDEAS.md](IDEAS.md). Le README documente le modèle de données et l'API complète.

**Rythme de travail** : au début de chaque session, consulte la **FILE D'ATTENTE** en tête d'`IDEAS.md` ; **en l'absence de brief collé, le lot n° 1 est le travail en cours**. Un brief collé par Fabien **prime toujours** sur la file. À chaque fin de lot, retirer l'entrée réalisée pour que la file remonte.

**Journal de session partagé** — `.claude/session-log.md`, **append-only strict** : une ligne datée par événement, jamais d'édition ni de suppression d'une ligne existante (c'est un journal, pas un état). Partagé entre `[CC]` (Claude Code), `[COWORK]` et `[FABIEN]` ; format et emojis décrits dans l'en-tête du fichier. `.claude/` est gitignoré : rien ne part en prod.
- **Lire** : les ~30 dernières lignes au début de chaque session, en même temps que la FILE D'ATTENTE.
- **Écrire** : à chaque événement notable — `▶` début de lot, `✅` lot livré (avec `❓` si un arbitrage reste ouvert), `⚠` piège découvert, `🚀` commit/tag/déploiement. **Court** : le détail long reste dans `REALISATION.md`.
- **Automatisé** : le hook `Stop` (`.claude/hooks/post-stop-rebuild.sh`) rebuild le local **puis lance `pytest -m "not e2e"`** et écrit `handoff.json` avec le statut correspondant (`ready` = build + tests verts / `tests_failed` / `tests_skipped` si deps dev absentes / `build_failed`), en appendant la ligne `✅`/`⚠` au journal. Le `▶` et les `⚠`/`❓` restent **manuels** — c'est du jugement, pas de l'automatisme.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
