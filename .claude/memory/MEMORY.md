# MEMORY BANK — dash_project

**Dernière mise à jour :** 18 octobre 2026 — **prod V30.1.283** (train du 18 oct. : [DASH-API] lot A V30.0.282 = **format d'export v30**, puis [DASH-MCP] lot B V30.1.283), **680 tests** verts (2 skips connus). Le détail lot par lot vit dans `REALISATION.md` : ce fichier ne le recopie pas.
**Nature :** index de mémoire. La **source canonique** reste `CLAUDE.md` (racine) ; ce fichier pointe, il ne duplique pas (ADR-001).

## Résumé global

Dashboard personnel auto-hébergé sur un **Zimaboard**, page d'accueil du navigateur : liens vers services self-hosted (catégories, statuts, favicons), mémos/tâches façon Planify (dossiers imbriqués, priorités, échéances, sous-tâches, récurrence, liens attachés), carte Leaflet, partage externe par lien à jeton + PIN (invités, droits, commentaires). Depuis le 18 oct. 2026 : **une API v1 à jeton Bearer** et **un serveur MCP** — Claude (chat et Claude Code) lit et écrit le dashboard **sans Chrome**.

## Stack technique (réelle — PAS Django/Dash)

- **Backend :** Flask + SQLite **sans ORM**, tout dans `app.py` (12 600 lignes) ; **une exception** : le blueprint `api_v1` (`/api/v1`, dans `app.py`) + le paquet `api/v1/openapi.py` (OpenAPI 3.1 écrite à la main). Migration additive dans `init_db()`.
- **MCP :** `dash_mcp/server.py` (paquet nommé `dash_mcp`, pas `mcp` : collision avec le SDK) — FastMCP (SDK `mcp==1.30.0`) stateless + JSON, **uvicorn sur 8100** dans le **même conteneur** (`bin/start.sh` lance gunicorn 8099 ET uvicorn 8100 ; l'un meurt → le conteneur redémarre). Façade pure de `/api/v1` : aucune règle métier, garde `_api_path` (rien hors `/api/v1`), jeton dans l'URL `/mcp/<jeton>/` (connecteur claude.ai) ou Bearer, chemin journalisé masqué `/mcp/***/`. 21 outils, descriptions françaises, `get_context` en texte compact (dates Europe/Paris).
- **Frontend :** JS vanilla, pas de build. Un fichier par page (`index.html`, `share.html`, `hub.html`) + helpers purs dans `templates/partials/_shared.js.html` (ADR-001). Deps auto-hébergées dans `static/`.
- **Données :** SQLite (`data/dashboard.db`) + uploads, en volume Docker. Export/import JSON **v1 → v30**, rétro-compatible, non destructif. `api_tokens` / `api_audit` **jamais exportées**.
- **Prod :** Caddy (Caddyfile **hôte** `/home/casaos/Documents/projects/caddy/Caddyfile`, monté `:ro`) + Authelia (bypass `/share/.*`, `^/api/v1/.*$`, `^/mcp/.*$`) + fail2ban (`caddy-auth` : tout 401 du log Caddy, `ignoreip` = loopback, LAN, IP publique du jour, `homebayonne.duckdns.org`). Deux domaines : `dash.fabnode.dev`, `dash.homebayonne.duckdns.org`. SSH `casaos@192.168.1.39` ; `sudo` interactif seulement (CC ne peut pas : fail2ban, `/etc/`).
- **Tests :** `make test` = back (unit + invariants) + front (Playwright), bases SQLite temp. Doctrine **TDD** : rouge d'abord, mutations posées et tuées, smoke réel avant « fini ». Tests MCP : vrai client SDK (`httpx.ASGITransport`) ↔ MCP ↔ Flask de test (`httpx.WSGITransport`), instance fraîche par cas (`build_app()`).

## Sources canoniques

- **`CLAUDE.md`** — architecture, **10 invariants** (le 10 = API v1 Bearer, `url_map` introspecté), index du format d'export, process de fin de lot, règle « CC ne déploie pas ».
- **`docs/EXPORT-FORMAT.md`** — chaque version v1 → v30. **`docs/adr/`** — ADR-001. **`docs/MCP.md`** — brancher Claude (claude.ai, Claude Code, révoquer).
- **`docs/infra/`** — `authelia-api-v1.md` (règle appliquée 18/10), `caddy-mcp.md` (route appliquée 18/10, piège `:ro`), `fail2ban-incident-20261018.md`, `fail2ban-dash-api.conf` (proposition redondante).
- **`patterns.md`** (ici) — conventions transverses. **`dash-cicd-setup.md`** (ici) — runner self-hébergé, workflows `ci.yml`/`deploy.yml`, release par tag = tête de `REALISATION.md`.

## Canaux de travail (Fabien ↔ Cowork ↔ CC)

- **`IDEAS.md`** — en tête, la **FILE D'ATTENTE** ordonnée (n° 1 = travail en cours sans brief collé) ; graines et dettes en dessous ; index mémos ↔ idées (dossier Dash en prod).
- **`docs/briefs/<LOT>.md`** — le brief Cowork d'un lot (tests + invariants d'abord). Un brief collé par Fabien prime sur la file.
- **`.claude/session-log.md`** — journal append-only `[CC]`/`[COWORK]`/`[FABIEN]`, heure de **Paris** ; lire les ~30 dernières lignes au début de chaque session (Cowork y laisse des ⚠ « à corriger avant commit »).
- **`.claude/handoff.json`** — état du dernier lot (`ready` = build + tests verts), écrit par CC et par le hook Stop.
- Boucle : idée Fabien → brief Cowork → CC (tests rouges → code → mutations → `make test` → rebuild local → smoke → journal/handoff → **STOP**) → passe Cowork → **GO explicite** de Fabien → commit + tag + push (= deploy) → infra sur GO, **contrôles prod depuis le Zimaboard**.

## État actuel (18 octobre 2026)

- **Prod V30.1.283**, export **v30** (`memos.source` : `''` = UI, sinon source du jeton API). Sauvegarde fraîche v30 à garder.
- **API v1** (`/api/v1/*`, hors Authelia) : jetons créés dans **Paramètres › Appareils connectés** (empreinte sha256 seule, clair montré une fois, révocation douce, audit 50 lignes), 401 `{}` sans indice, 403 scope, quotas 120/30/20 par minute (**par worker gunicorn**, donc ×2 — dette), fixture jumelle des tuiles `tests/fixtures/tiles_cases.json` jouée par pytest ET le board.
- **MCP** validé de bout en bout : connecteur claude.ai « Dash » branché par Fabien le 18/10 15:22 (jeton « Claude chat », read+write), `get_context("iPad réparation")` rend le mémo 402. Cowork crée des mémos via le connecteur (411–416).
- **Leçon fail2ban du 18/10** : un test d'intrusion depuis le Mac (12 × 401 via l'IP publique, hairpin absent, `ignoreip` périmé) a **banni la box une heure** (443 refusé, 80 OK). Désormais : **contrôles prod depuis le Zimaboard** avec `curl --resolve dash.fabnode.dev:443:127.0.0.1`, jamais depuis le Mac ; vérifier `ignoreip` avant tout test ; les 429 ne comptent pas, les 401 oui.
- Pièges du train : FastMCP répond **421 Invalid Host** hors localhost (protection DNS-rebinding désactivée, Host = dash.fabnode.dev) ; le gestionnaire de sessions ne démarre qu'une fois par instance ; `_live_memo` ne rend que 3 colonnes ; le `+` d'un fuseau en query string arrive en espace ; le hook RTK tronque curl/grep (passer par `rtk proxy` ou Python).

## File d'attente (tête de `IDEAS.md`, ordre acté le 18 oct.)

1. **[CI-HYGIENE] V30.2.284** — zéro avertissement, zéro skip : `DeprecationWarning streamable_http_client` (test MCP), les 2 skips de `test_invariants` (fixture export v1 réel ; `DELETE /api/shares/<id>` doit purger `share_guests` & co.), actions GitHub Node 20. Dette décrite dans `IDEAS.md`.
2. **[DASH-API-A2]** — fichiers et liens par l'API/MCP (attachments, images, from-url, même `_save_uploaded_image`).
3. **[BROWSER-EXT]** — extension Opera/Chrome de capture façon Evernote, appairage sans copie de jeton (mémo 413).
Puis la file produit : [MEMO-READ], [EDITOR-BUBBLE], [MEMO-TYPES] (v31), [IMAGE-INLINE], [MEMO-PDF], [EXPORT-MEDIA-BUNDLE]… Graines récentes : [TITLE-OVERFLOW] (titre collé > 200 car. tronqué — mémo 415), [NOTIF-CENTER], [GUEST-AVATAR]/[GUEST-WALL], [DASH-API-C] CLI, [MOBILE-POLISH], [SORT-SELECT], dette [TREE-ITEM-FACTOR].

## Instructions pour Claude

- Avant une modif importante : `CLAUDE.md` (10 invariants + index d'export), `docs/EXPORT-FORMAT.md` si le format bouge, `docs/adr/`, puis ce fichier et `patterns.md`.
- **Une seule session CC active par lot** (`ListAgents` + fin du journal avant de coder).
- Toute route `/api/v1/*` porte `@require_token` ; tout outil MCP passe par `_acall` (jamais une route owner). Le MCP ne valide pas le jeton : l'API tranche.
- Infra (Authelia, Caddy, fail2ban) : **hors dépôt**, proposer dans `docs/infra/`, appliquer **seulement sur GO**, sauvegarder avant, valider avant de recharger ; Caddyfile côté hôte (le conteneur le monte en lecture seule).
- Purger tout décor de smoke (mémos → corbeille → `/api/trash/<id>`, jetons smoke + leurs lignes d'audit ; `DELETE /api/projects/<id>` détache les mémos sans les supprimer).
- Après une grosse feature : proposer la mise à jour de cette Memory Bank **et** de `CLAUDE.md`, sans dupliquer.
