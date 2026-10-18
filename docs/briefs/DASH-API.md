# Brief CC — [DASH-API] lot A : une API v1 pour Claude, le terminal et le mobile — sécurité d'abord

> **Back majoritaire (`app.py` : blueprint `api/v1`, deux tables additives, une colonne additive → BUMP export
> v29 → v30, `APP_VERSION="30"`, tags `V30.x`), + un onglet Paramètres. Infra : UNE règle Authelia
> (CC a l'accès SSH, voir mémoire `dash-infra-zimaboard` / `docs/infra`).** Cible **V30.0.282**. Doctrine TDD.
> Sources : mémos prod 408 (plan en clair) et 410 (détails techniques, 11 sections), échanges Fabien du 18 oct.
> Lot **A** seulement : sécurité + lecture + écriture hors fichiers. **A2** (fichiers, from-url) et **B** (MCP)
> suivent avec leurs briefs. Spec vivante : ce fichier.

## 0. Pourquoi
[stated] Fabien veut que Claude (chat et Claude Code), un CLI et plus tard l'appli mobile lisent et écrivent
dans le dashboard sans passer par Chrome. Un seul utilisateur. Les humains continuent d'entrer par Authelia.

## 1. Sécurité (à faire EN PREMIER, tests d'invariant inclus)

### 1.1 La porte
- Authelia `access_control` : **une** règle `bypass` sur `resources: ['^/api/v1/.*', '^/mcp/.*']`, au-dessus de
  la règle `two_factor` du domaine, calquée sur `/share/.*`. `/pair/.*` reste protégé. Rien d'autre ne change.
- Décorateur `require_token(scope)` sur **toutes** les routes `/api/v1/*` : lit `Authorization: Bearer <jeton>`
  ; **jamais** le cookie de session (invariant 10). Inconnu / expiré / révoqué → **401** `{}` sans indice.
  Scope insuffisant → **403**. Un jeton valide met `last_used_at` à jour.
- Réponses : `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, JSON UTF-8.

### 1.2 Les jetons — table additive `api_tokens`
`id, name, token_hash (sha256 hex), scopes ('read' | 'read,write'), source ('claude-chat'|'claude-code'|'cli'|'flutter'|'other'),
created_at, expires_at (nullable), last_used_at, revoked_at`. Jeton en clair = `dash_` + 40 car. `secrets.token_urlsafe`,
**affiché une seule fois** à la création, jamais loggé, **exclu de l'export** (comme `session_token`). Comparaison
par hash en temps constant. `CREATE TABLE IF NOT EXISTS`.

### 1.3 Abus
- Compteur en mémoire par (jeton, minute) : **120 lectures/min, 30 écritures/min** → **429** + `Retry-After`.
  (Caddy n'a pas de rate limit sans plugin.) Par IP sans jeton : 20 tentatives/min → 429.
- fail2ban : la jail `caddy-auth` existante étendue aux **401** sur `/api/v1` et `/mcp` (5 en 10 min → 1 h).
  CC écrit le filtre ; Fabien valide le déploiement infra.
- Corps JSON ≤ 256 Ko (413). Contenu mémo ≤ même limite que l'UI.

### 1.4 Traçabilité — table additive `api_audit`
`id, token_id, at, method, route, memo_id (nullable), args_summary (≤ 200 car., jamais le contenu), ip, status`.
Non exportée, purge > 90 j au démarrage (comme `_og_sweep`). Chaque écriture ET chaque lecture de mémo y passe.

### 1.5 Provenance — colonne additive `memos.source`
`''` = UI (défaut), sinon la `source` du jeton. Posée à la création **et** à la dernière modification par API
(`source_updated`). Icône discrète sur la card (titre « créé via Claude Code »). **Export v30** : `source` émis
brut ; absent à l'import (v1→v29) = `''` → rendu identique (invariant 2). Entrée v30 dans `docs/EXPORT-FORMAT.md`
+ index `CLAUDE.md`. Ne PAS réutiliser `created_by` (non vide = invité).

### 1.6 Ce que l'API ne fait jamais
Partages, invités, jetons (hors `/me`), réglages, sauvegarde/import, suppression définitive, vidage de corbeille.
Les mémos **en corbeille ne sont jamais renvoyés** (404). Les dossiers d'invités sont renvoyés (c'est l'owner).

### 1.7 Invariant 10 (nouveau, `tests/back/test_invariants.py`)
« `/api/v1/*` n'accepte qu'un Bearer valide : le cookie de session → 401 ; un jeton révoqué → 401 ; un jeton
`read` sur une écriture → 403 ; aucune route `/api/v1/*` n'est enregistrée sans `require_token` (introspection
de `app.url_map`). » + « le jeton en clair n'apparaît ni dans l'export ni dans `api_audit` ».

### 1.8 UI — Paramètres › **Appareils connectés** (owner)
Liste (nom, source, droits, créé le, dernier usage, expiration, état), bouton **Créer** (nom, source, droits,
expiration optionnelle) → modale qui montre le jeton **une fois** + bouton Copier, bouton **Révoquer** (confirmation
douce), journal d'audit (50 dernières lignes, filtre par jeton). Luciole, pas de nouvelle lib.

## 2. Lecture (scope `read`)
- `GET /api/v1/me` → `{name, scopes, source, expires_at}`.
- `GET /api/v1/tree` → dossiers (id, uid, name, emoji, color, parent_id, counts) + mémos `{id, title, done, due_date, due_end, priority}` sans contenu.
- `GET /api/v1/memos?folder&subtree=1&filter&sort&limit≤200&cursor&since` → `{items, next_cursor}`. Chaque item =
  `_memo_dict` + `content_text` (HTML déshabillé) ; `filter ∈ open|today|scheduled|overdue|done|history`
  avec **exactement** les règles des tuiles ; `sort ∈ manual|newest|updated|due`.
- `GET /api/v1/memos/<id>` → mémo complet + `comments` + `urls` + noms des `attachments`/`images`.
- `GET /api/v1/counts?folder&subtree=1` → les six chiffres des tuiles.
- `GET /api/v1/search?q&folder&tag&due_from&due_to&created_from&created_to&limit` → texte foldé
  (`searchFold` porté en Python : NFD, accents, apostrophes, espaces) sur titre + contenu + sous-tâches + assignés
  + labels/URL ; la grammaire `p#/d#/#tag` reste front (lot à part).
- `GET /api/v1/plan` → la même structure que la vue Plan (CC identifie la source de données de la vue Plan).
- `GET /api/v1/export` → l'export JSON complet v30 (même fonction que Paramètres).
- `GET /api/v1/openapi.json` → OpenAPI 3.1 écrit à la main dans `api/v1/openapi.py` (dict Python), un test
  vérifie que chaque route enregistrée y figure.

**Règles des tuiles en Python** : `memo_due_end_day`, `memo_covers_day`, `visible_history` portés depuis
`_shared.js` l.152-160 et `index.html` `visibleHistory` ; **tests jumeaux** : une fixture JSON partagée
`tests/fixtures/tiles_cases.json` jouée côté pytest (Python) ET côté e2e (le board) → mêmes comptes.

## 3. Écriture (scope `write`) — mêmes validations que l'UI (`_clean_*`), même code d'insertion
- `POST /api/v1/memos` `{title, content|content_text, folder_id, due_date, due_end, due_time, priority, subtasks[], assignees[], tags[], urls[], position}` → 201 + mémo.
  `content_text` = texte brut converti en `<p>` échappés (jamais de HTML brut non nettoyé) ; `content` = HTML
  passé par le même nettoyeur que l'UI.
- `PATCH /api/v1/memos/<id>` : champs partiels. `POST …/append` `{content|content_text}` : ajoute à la fin.
- `POST …/move` `{folder_id}` ; `POST …/done` ; `POST …/undone` ; `POST …/subtasks` `{content}` ;
  `PATCH …/subtasks/<n>` `{done, content}` ; `POST …/urls` / `DELETE …/urls/<url_id>` (réutilise MEMO-URLS) ;
  `POST …/comments` `{content}` (auteur = owner) ; `DELETE /api/v1/memos/<id>` → **Corbeille** ; `POST …/restore`.
- `POST /api/v1/folders` `{name, parent_id, emoji, color}` ; `PATCH /api/v1/folders/<id>` (idem + `parent_id`, 409 si nom pris chez le parent).
- Hors lot A : attachments/images/from-url (A2).

## 4. Tests (TDD — rouges d'abord)
`tests/back/test_api_v1_auth.py` : 401 sans jeton / cookie seul / révoqué / expiré ; 403 scope ; 429 au-delà
du quota ; `last_used_at` ; jeton absent de l'export et de l'audit ; `url_map` tout protégé.
`tests/back/test_api_v1_read.py` : tree, memos (filtres 6 tuiles via fixture jumelle, tri, pagination, since),
memo, counts, search (accents), plan, export v30, openapi complet ; corbeille → 404.
`tests/back/test_api_v1_write.py` : create (text et HTML nettoyé, `source` posé), patch, append, move, done,
subtasks, urls, comment, delete→corbeille→restore, folders (409 doublon) ; audit rempli.
`tests/front/test_devices_settings.py` : créer → jeton affiché une fois → révoquer → 401 ; icône source sur card.
`tests/front/test_tiles_twin.py` : la fixture `tiles_cases.json` donne les mêmes comptes sur le board.
Mutations : require_token retiré d'une route → url_map rougit ; comparaison de hash non constante → revue ;
corbeille renvoyée → 404 rougit ; `source` non posé → rougit ; règle « en retard » décalée d'un jour → jumeau rougit.
Invariants 1/2 : import de tous les exports v1→v29 vert.

## 5. Livraison
`make test` vert ; `REALISATION.md` `[V30.0.282] feat(api) : **[DASH-API] lot A…**` ; `docs/EXPORT-FORMAT.md` v30 ;
`CLAUDE.md` (invariant 10 + index) ; IDEAS.md (retirer de la file, graines A2/B/C) ; `docs/infra` : la règle Authelia
et le filtre fail2ban proposés (NE PAS appliquer en prod avant GO) ; rebuild local complet ; smoke `curl` local
(401 / 200 / 429) ; handoff + ligne [CC] (TZ Paris) ; **STOP avant push**. Passe Cowork : Appareils connectés dans
Chrome + `curl` depuis le Mac de Fabien, puis GO, puis déploiement **avec** la règle Authelia, puis test
d'intrusion prod : sans jeton → page Authelia ; cookie seul → 401 ; jeton révoqué → 401.
