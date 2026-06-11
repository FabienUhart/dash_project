# CLAUDE.md

Contexte pour Claude Code. À lire avant toute modification ou commit.

## Le projet en une phrase

Dashboard perso auto-hébergé sur un Zimaboard (page d'accueil navigateur) : liens vers services self-hosted avec catégories, mémos post-it, statuts online/offline, recherche, horloge/météo.

## Architecture

- **`app.py`** : tout le backend. Flask + SQLite, pas d'ORM, pas de blueprint. La migration de schéma est dans `init_db()` (ALTER TABLE additifs + backfill, jamais destructif — ne JAMAIS dropper de colonne ou de données).
- **`templates/index.html`** : tout le frontend en un seul fichier (CSS + HTML + JS vanilla, pas de framework, pas de build). Layout "3 zones" : sidebar catégories / cards / colonne mémos.
- **`data/dashboard.db`** : SQLite, monté en volume Docker. Contient les vraies données de l'utilisateur — ne jamais la modifier ou supprimer dans un commit.
- **`data/uploads/`** : images des mémos (noms `uuid4().hex.ext`, validés par regex côté serveur). Même volume Docker, même règle : ne jamais y toucher dans un commit. Le JSON d'export ne contient que les noms de fichiers.
- Déploiement : `docker compose up -d --build` (gunicorn, port 8099, derrière Caddy + Authelia en prod).

## Invariants à respecter

1. **Compat ascendante des sauvegardes** : `/api/import` doit toujours accepter les exports v1 (liens seuls), v2 (+ catégories/mémos), v3 (+ uid/dates), v4 (+ done/due_date/priority/subtasks sur les mémos, color sur les catégories), v5 (+ projets de mémos, rattachés par nom), v6 (+ images sur les mémos, noms de fichiers seulement), v7 (+ tags sur les liens, normalisés minuscules sans #), v8 (+ tags sur les projets), v9 (+ `recurrence` sur les mémos et liste `history` des tâches effectuées, dédupliquée par (memo_uid, done_at)) et v10 (+ liste `priorities` ; `memos.priority` est remappé par NOM de priorité à l'import, jamais par id brut). Toute évolution du format incrémente `version` dans l'export et reste importable.
2. **L'import n'est jamais destructif** : il ajoute, met à jour (uid identique + `updated_at` plus récent) ou enrichit les champs vides (match nom+URLs sans uid). Il ne supprime ni n'écrase jamais un champ rempli avec une donnée plus ancienne.
3. **`uid`** : UUID stable qui suit chaque lien/mémo à travers exports/imports. Généré à la création et backfillé par `init_db()`. Ne jamais le régénérer pour une ligne existante.
4. **Les URLs locales** (`192.168.1.x`) servent au check de statut ET à la récupération des favicons côté serveur (contournement d'Authelia). Le cache favicon (`_favicon_cache`, en mémoire) doit être invalidé quand les URLs d'un lien changent.
5. **Pas d'auth dans l'app** : la sécurité est assurée par le reverse proxy. Ne pas ajouter de login. **Exception volontaire** : les routes `/share/<token>/...` sont publiques (règle bypass Authelia) et protégées uniquement par le jeton — elles ne doivent JAMAIS exposer autre chose que la ressource partagée (mémo ou projet ciblé, ses sous-tâches et ses images). Toute écriture via `/share/` exige en plus un invité **approuvé** (header `X-Guest-Token`, approbation obtenue par le code PIN du lien). Toute nouvelle route publique doit valider le token et rester dans ce périmètre. Les uploads d'images (propriétaire comme invité) passent par `_save_uploaded_image()` qui vérifie la **signature binaire** du fichier — ne jamais accepter un upload sans cette vérification.
6. **Un seul fichier HTML** : pas de séparation CSS/JS du code maison, pas de build. Dépendances front autorisées uniquement si **auto-hébergées dans `static/`** (actuellement : Quill 2 pour l'édition riche des mémos — l'UI doit dégrader proprement en textarea si le fichier manque). Pas de CDN au runtime, sauf les deux appels existants : open-meteo et icons.duckduckgo.com en fallback favicon.

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
- **Juin 2026 — vue Mémos façon Planify** : page dédiée (sidebar → Mémos) avec tuiles de filtres, sections par échéance (En retard / Aujourd'hui / À venir / Sans date / Terminés repliable), cases à cocher, priorités P1-P3, sous-tâches JSON, liens cliquables, couleurs de catégories (export v4), puis projets de mémos avec Inbox, couleurs et drag & drop depuis la sidebar (export v5), puis images sur les mémos (upload dans `data/uploads/`, miniatures + visionneuse, export v6), puis tags `#` reliant liens et mémos + pop-in de création projet/catégorie avec couleur (export v7), puis tags sur les projets + recherche scopée (sélecteur Tout/Liens/Mémos/Projets + préfixes `p#` `l#` `m#`) et remplacement de tous les confirm/alert natifs par des pop-ins (export v8), puis tâches récurrentes (cocher replanifie sur le rythme prévu, `_next_due()`) + historique des tâches effectuées (table `memo_history`, tuile 📜, purge manuelle) (export v9), puis priorités configurables (table `priorities` seedée P1 rouge/P2 jaune/P3 vert, couleurs dynamiques, gestion + pop-in dans Paramètres) (export v10), puis partage externe par lien à jeton (table `shares`, routes publiques `/share/<token>`, page `templates/share.html`, lecture seule ou modifiable, bypass Authelia requis — non inclus dans l'export), puis invités identifiés par e-mail validés par le propriétaire (table `share_guests`, header `X-Guest-Token`), attribution des modifications et versions restaurables (`memo_revisions` avant/après, fil 🔔 Activité, restauration owner-only via `/api/memos/<id>/restore`), puis attribution visible (badge 👤 sur les mémos touchés par un invité, champ `guest_editor` dans `/api/memos`) + rechargement auto du dashboard toutes les 15 s (sauf pop-in ouverte ou édition en cours), puis listes à cocher façon Evernote (Quill `list: check`, `li[data-list]` cliquables sur la card ET la page partagée, champ "+ Ajouter un article" pour les invités), droits invités complets (texte, date, priorité, photos JPG/PNG validées par **signature binaire** — `_looks_like_image()`, gif/webp réservés au propriétaire), puis code PIN à 4 chiffres par lien (`shares.pin`, généré/modifiable, code correct = invité approuvé d'office) et page 🔗 Partages (vue dédiée : liens + PIN éditables, invités, modifications groupées par invité avec avant/après dépliable — remplace la pop-in Activité), enfin double-clic/clic droit sur catégories-projets de la sidebar pour ouvrir la pop-in d'édition (avec bouton Supprimer).

## Backlog

Voir [IDEAS.md](IDEAS.md). Le README documente le modèle de données et l'API complète.
