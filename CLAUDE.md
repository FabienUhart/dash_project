# CLAUDE.md

Contexte pour Claude Code. À lire avant toute modification ou commit.

## Le projet en une phrase

Dashboard perso auto-hébergé sur un Zimaboard (page d'accueil navigateur) : liens vers services self-hosted avec catégories, mémos post-it, statuts online/offline, recherche, horloge/météo.

## Architecture

- **`app.py`** : tout le backend. Flask + SQLite, pas d'ORM, pas de blueprint. La migration de schéma est dans `init_db()` (ALTER TABLE additifs + backfill, jamais destructif — ne JAMAIS dropper de colonne ou de données).
- **`templates/index.html`** : tout le frontend en un seul fichier (CSS + HTML + JS vanilla, pas de framework, pas de build). Layout "3 zones" : sidebar catégories / cards / colonne mémos.
- **`data/dashboard.db`** : SQLite, monté en volume Docker. Contient les vraies données de l'utilisateur — ne jamais la modifier ou supprimer dans un commit.
- Déploiement : `docker compose up -d --build` (gunicorn, port 8099, derrière Caddy + Authelia en prod).

## Invariants à respecter

1. **Compat ascendante des sauvegardes** : `/api/import` doit toujours accepter les exports v1 (liens seuls), v2 (+ catégories/mémos) et v3 (+ uid/dates). Toute évolution du format incrémente `version` dans l'export et reste importable.
2. **L'import n'est jamais destructif** : il ajoute, met à jour (uid identique + `updated_at` plus récent) ou enrichit les champs vides (match nom+URLs sans uid). Il ne supprime ni n'écrase jamais un champ rempli avec une donnée plus ancienne.
3. **`uid`** : UUID stable qui suit chaque lien/mémo à travers exports/imports. Généré à la création et backfillé par `init_db()`. Ne jamais le régénérer pour une ligne existante.
4. **Les URLs locales** (`192.168.1.x`) servent au check de statut ET à la récupération des favicons côté serveur (contournement d'Authelia). Le cache favicon (`_favicon_cache`, en mémoire) doit être invalidé quand les URLs d'un lien changent.
5. **Pas d'auth dans l'app** : la sécurité est assurée par le reverse proxy. Ne pas ajouter de login.
6. **Un seul fichier HTML** : pas de séparation CSS/JS, pas de dépendance front externe (sauf les deux appels réseau existants : open-meteo et icons.duckduckgo.com en fallback).

## Comment tester avant de commit

```bash
# syntaxe
python3 -m py_compile app.py

# lancer sur une COPIE de la base (jamais sur data/dashboard.db directement)
cp data/dashboard.db /tmp/test.db
DB_PATH=/tmp/test.db flask --app app run -p 8099

# scénarios critiques à vérifier :
# 1. la migration passe sur une base existante (l'app démarre, GET /api/links OK)
# 2. ré-import d'un export complet → 0 ajout, tout en "skipped"
# 3. import v1 sans uid → pas de doublon, champs vides enrichis
# 4. CRUD catégories/mémos + reorder
```

`backup*.json` est gitignoré (données perso) — ne jamais le committer.

## Historique des évolutions majeures

- **v1 (origine)** : liste de liens à plat, 2 URLs par lien, statut, mémo par lien, export/import basique.
- **Juin 2026 — refonte "3 zones"** : catégories (table + sidebar + drag & drop), mémos indépendants (table `memos`, colonne post-its), recherche instantanée (`/`), favicons via serveur, horloge + météo, panneau Paramètres (export/import/gestion catégories), responsive mobile, import anti-doublons puis import avec `uid` + dates (mise à jour des éléments connus au lieu de dupliquer).

## Backlog

Voir [IDEAS.md](IDEAS.md). Le README documente le modèle de données et l'API complète.
