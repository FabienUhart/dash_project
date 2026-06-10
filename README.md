# Dashboard

Dashboard web perso : page d'accueil de navigateur avec liens vers des services auto-hébergés (deux URLs possibles par service : publique + VPN/locale), catégories, mémos post-it, check de statut côté serveur, recherche instantanée, horloge + météo.

Stack : Flask + SQLite, servi par gunicorn dans un conteneur Docker. Front vanilla JS dans `templates/index.html`.

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
- **Vue Mémos** (sidebar → 📝 Mémos) : gestion de tâches façon Planify. Tuiles de filtres (En cours / Aujourd'hui / Planifiés / En retard / Terminés), sections par échéance, cases à cocher, priorités P1-P3 (bordure rouge/orange/bleue), sous-tâches avec progression, liens web cliquables, édition au clic. **Projets** : sous "Mémos" dans la sidebar (Inbox + projets colorés), drag & drop d'un mémo vers un projet, sélecteur de projet à l'ajout et dans le détail. **Images** : bouton 📎 dans le détail d'un mémo ou glisser-déposer un fichier image sur le mémo ; miniatures cliquables (visionneuse plein écran), suppression au survol en mode détail. **Texte riche** : cliquer sur le texte d'un mémo ouvre un éditeur WYSIWYG (Quill 2, auto-hébergé dans `static/`) — titres, gras/italique, couleurs, listes, liens, citations, code. Le HTML est sanitizé au rendu ; si `static/quill.min.js` manque, l'édition retombe sur une textarea simple.
- **Recherche** : `/` pour focus, filtre liens + mémos en tapant, Entrée ouvre le premier résultat, Échap efface. Taper `#tag` filtre par tag exact. **Portée** : sélecteur Tout / Liens / Mémos / Projets dans la barre, ou préfixes clavier `p#`, `l#`, `m#` (ex. `p#docker` cherche dans les projets et bascule le sélecteur). Une recherche qui matche des projets (nom ou tags) affiche une section "Projets" cliquable en haut de la vue Mémos, et inclut les mémos de ces projets dans les résultats.
- **Tags `#`** : champ tags sur les liens (chips cliquables sur les cards) et `#tags` libres dans le texte des mémos (rendus cliquables). Cliquer un tag ouvre la vue Mémos filtrée sur ce tag, avec un bandeau pour basculer vers les liens qui le portent — liens ↔ mémos reliés par leurs # communs.
- **⚙ Paramètres** : export/import JSON, gestion des catégories et projets (pop-in nom + couleur via ✎, suppression), refresh des statuts. Un **double-clic** sur un projet ou une catégorie dans la sidebar ouvre directement la pop-in de modification.

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

Table `categories` : `id`, `name` (unique), `position`, `color` (hex, optionnel).

Table `memos` : `id`, `content`, `position`, `created_at`, `uid`, `updated_at`, `done` (0/1), `due_date` (YYYY-MM-DD), `priority` (0 = aucune, 1-3 = P1-P3), `subtasks` (JSON `[{content, done}]`), `project_id` (FK vers `projects`, NULL = Inbox), `images` (JSON, noms de fichiers dans `data/uploads/`).

Table `projects` : `id`, `name` (unique), `color`, `position`, `tags` (même normalisation que les liens). Les projets organisent les mémos (façon Planify), indépendamment des catégories de liens.

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
| GET     | `/api/memos`               | Liste les mémos                                |
| POST    | `/api/memos`               | Crée un mémo (`{content}`)                     |
| PUT     | `/api/memos/<id>`          | Met à jour le contenu                          |
| DELETE  | `/api/memos/<id>`          | Supprime                                       |
| POST    | `/api/memos/reorder`       | `{ids: [...]}`                                 |
| GET     | `/api/projects`            | Liste avec `memo_count` (mémos en cours)       |
| POST    | `/api/projects`            | Crée un projet (`{name, color}`)               |
| PUT     | `/api/projects/<id>`       | Renomme / change la couleur                    |
| DELETE  | `/api/projects/<id>`       | Supprime (les mémos retournent dans l'Inbox)   |
| POST    | `/api/projects/reorder`    | `{ids: [...]}`                                 |
| POST    | `/api/memos/<id>/images`   | Upload multipart (`image`) — png/jpg/gif/webp, 16 Mo max |
| DELETE  | `/api/memos/<id>/images/<nom>` | Supprime l'image (fichier inclus)          |
| GET     | `/uploads/<nom>`           | Sert une image uploadée                        |
| GET     | `/api/favicon/<id>`        | Favicon du service, récupéré côté serveur (cache mémoire) |
| GET     | `/api/export`              | Sauvegarde JSON v8 (liens + catégories + projets + mémos, tags inclus) |
| POST    | `/api/import`              | Réimporte une sauvegarde (voir Backup / restore) |

Le check de statut est fait côté Flask pour éviter le CORS. Renvoie `online` / `offline` / `unknown` (URL vide) par URL renseignée.

La météo est récupérée côté client depuis open-meteo.com (Bayonne, gratuit, sans clé). Les favicons sont récupérés par Flask via l'URL locale du service (ce qui contourne Authelia), avec fallback `icons.duckduckgo.com` puis initiale du nom.

## Backup / restore

Depuis l'UI : **⚙ Paramètres → Export JSON / Import JSON**. L'export (v7) contient liens (avec tags), catégories, projets (avec couleurs) et mémos (avec done/échéance/priorité/sous-tâches/projet/images), chacun avec son `uid` et ses dates. À l'import :

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

## Persistance

La base SQLite vit dans `./data/dashboard.db`, monté en volume dans le conteneur.

## Pas d'auth

L'app n'a aucune authentification. En production, elle est servie derrière un reverse proxy Caddy avec `basic_auth`. Ne pas exposer directement.

## Déploiement Zimaboard

Le même `docker-compose.yml` tourne tel quel sur le Zimaboard : `git clone` + `docker compose up -d --build`. Le port 8099 y est déjà routé derrière Caddy.
