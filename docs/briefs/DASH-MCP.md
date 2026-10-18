# Brief CC — [DASH-MCP] lot B : un serveur MCP distant, façade de l'API v1, branché comme connecteur claude.ai

> **Nouveau worker dans le même conteneur (`mcp/`, FastMCP du SDK officiel `mcp`, transport Streamable HTTP, uvicorn
> sur 8100), zéro table, zéro bump (export 30 inchangé). Deux petits ajouts à l'API v1 (`X-Dash-Client`,
> `GET /client-versions`). Infra : Caddy route `/mcp*` → 8100 (proposition docs/infra, appliquée au GO).** Cible
> **V30.1.283**. Doctrine TDD. Sources : mémos prod 408/410, brief DASH-API § 1, décisions Fabien du 18 oct.

## 0. Pourquoi
[stated] Fabien veut que Claude (chat claude.ai et Claude Code) lise et écrive dans le dashboard sans passer par Chrome.
Le connecteur claude.ai appelle un serveur MCP distant par HTTPS ; il ne sait pas envoyer d'en-tête, d'où le jeton
dans le chemin. Le MCP ne contient **aucune règle métier** : c'est un client HTTP de `/api/v1` (invariant 10 respecté
par construction : tout passe par `require_token`, l'audit et les quotas de l'API).

## 1. Architecture
- `mcp/server.py` : `FastMCP("dash")`, app ASGI montée sous `/mcp`, lancée par `uvicorn mcp.server:app --port 8100`.
  **Un seul** chemin d'auth : le jeton est lu **dans l'URL** `/mcp/<jeton>/` (middleware ASGI qui l'extrait, le pose
  dans le contexte de requête, puis réécrit le chemin en `/mcp/`) **ou** dans `Authorization: Bearer` si présent
  (Claude Code, CLI). Jeton absent → 401 avant tout. Le MCP **ne valide pas** le jeton lui-même : il le transmet à
  l'API (`http://127.0.0.1:8099/api/v1/...`) ; un 401 de l'API devient une erreur d'outil « jeton invalide ou révoqué ».
- Chaque appel API porte `X-Dash-Client: mcp/<version> (<client déclaré>)` ; l'API (ajout lot B) range
  `client_name/client_version/last_seen_version` sur le jeton (colonnes additives `api_tokens`, non exportées) ;
  `GET /api/v1/client-versions` → `{mcp: "1.0.0", cli: null, extension: null}` depuis une constante `CLIENT_VERSIONS`.
- Logs du MCP : **jamais le chemin complet** (le jeton y est) : on logge `/mcp/***/`. `Cache-Control: no-store`.
- Dockerfile : `CMD` devient un script `bin/start.sh` qui lance gunicorn (8099) **et** uvicorn (8100) ; si l'un meurt,
  le conteneur s'arrête (restart compose). `EXPOSE 8100`. `requirements.txt` : `mcp`, `uvicorn`, `httpx` épinglés.
- Caddy (docs/infra/caddy-mcp.md, à appliquer au GO) : `handle /mcp* { reverse_proxy 127.0.0.1:8100 }` avant le
  `reverse_proxy` général, sur les deux domaines. Authelia : déjà en bypass (`^/mcp/.*`).
- Sécurité : taille des arguments bornée (contenu ≤ 256 Ko comme l'API), pas d'outil de suppression définitive,
  pas d'accès aux jetons/partages, `delete_memo` = Corbeille. Un jeton **dédié** « Claude chat » créé par Fabien,
  source `claude-chat`.

## 2. Outils (noms, arguments, ce qu'ils appellent)
Lecture : `get_tree()` → `/tree` ; `list_memos(filter?, folder_id?, subtree?, sort?, limit?, cursor?)` → `/memos` ;
`get_memo(id)` → `/memos/<id>` ; `search_memos(q, folder_id?, tag?, due_from?, due_to?, limit?)` → `/search` ;
`get_counts(folder_id?)` → `/counts` ; `get_plan()` → `/plan` ; `whoami()` → `/me` ;
**`get_context(keywords, limit=8)`** : recherche + derniers mémos modifiés + mémos du jour, dédoublonnés, renvoyés
en **texte compact** (titre, dossier, dates, 300 car. de contenu, sous-tâches) : l'outil pour « qu'est-ce que j'ai
sur l'iPad ? » en un appel.
Écriture : `create_memo(title, content_text?, content_html?, folder_id?, due_date?, due_end?, due_time?, priority?,
subtasks?, tags?, urls?)` ; `update_memo(id, …)` ; `append_to_memo(id, content_text)` ; `move_memo(id, folder_id)` ;
`complete_memo(id)` / `reopen_memo(id)` ; `add_subtask(id, content)` ; `toggle_subtask(id, index, done)` ;
`add_url(id, url, label?)` ; `add_comment(id, content)` ; `delete_memo(id)` (Corbeille) ; `restore_memo(id)` ;
`create_folder(name, parent_id?, emoji?, color?)`.
Chaque outil a une **description française d'une phrase** (c'est ce que Claude lit pour choisir), des types stricts,
et renvoie l'objet JSON de l'API (ou le texte compact pour `get_context`). Erreurs API → erreur d'outil lisible
(401 → « jeton invalide ou révoqué », 403 → « jeton en lecture seule », 404 → « mémo introuvable ou en corbeille »,
429 → « quota dépassé, réessaie dans N s »).
Hors lot : fichiers/images (A2), ressources `memo://`, templates.

## 3. Tests (TDD — rouges d'abord)
`tests/back/test_mcp_server.py` : serveur Flask de test + MCP en ASGI (`httpx.ASGITransport`) pointé dessus :
(1) `/mcp/` sans jeton → 401 ; (2) `/mcp/<jeton révoqué>/` → l'appel d'outil renvoie l'erreur « jeton invalide » ;
(3) `tools/list` contient les 21 outils avec descriptions non vides ; (4) `get_counts` = `/counts` ; (5) `create_memo`
→ mémo en base avec `source` du jeton et ligne d'audit ; (6) `delete_memo` → corbeille, `get_memo` → erreur 404 ;
(7) jeton `read` → `create_memo` renvoie l'erreur 403 ; (8) `get_context("ipad")` contient le titre du mémo attendu ;
(9) `X-Dash-Client` reçu par l'API → `last_seen_version` posé ; (10) le log du MCP ne contient pas le jeton.
Mutations : jeton non masqué dans le log → 10 ; `delete_memo` appelant une purge → 6 ; `get_context` sans dédup → 8.
Invariants : la batterie `url_map` reste verte (le MCP n'ajoute aucune route Flask hors `/client-versions`, protégée).

## 4. Livraison
`make test` vert ; `REALISATION.md` `[V30.1.283] feat(mcp) …` ; IDEAS.md (retirer de la file) ; docs/infra/caddy-mcp.md ;
`docs/MCP.md` (3 paragraphes : brancher dans claude.ai = Paramètres › Connecteurs › Ajouter un connecteur
personnalisé avec `https://dash.fabnode.dev/mcp/<jeton>/` ; dans Claude Code = `claude mcp add --transport http dash
https://dash.fabnode.dev/mcp/ --header "Authorization: Bearer …"` ; révoquer) ; rebuild local complet (**les deux
workers démarrent**) ; smoke local : `curl -X POST localhost:8099/mcp/<jeton>/ -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
via Caddy local s'il existe, sinon direct sur 8100 ; handoff + ligne [CC] (TZ Paris) ; **STOP avant push**.
Passe Cowork : outils via fetch depuis Chrome sur localhost:8100, puis après GO + Caddy : **Cowork branche le connecteur
dans sa propre conversation claude.ai** et lit/crée un mémo en prod sans Chrome.
