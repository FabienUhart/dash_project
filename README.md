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
- **Colonne droite** : mémos post-it indépendants. Ajout rapide (Entrée), clic pour éditer, drag & drop pour réordonner. Repliée par défaut sur mobile.
- **Recherche** : `/` pour focus, filtre liens + mémos en tapant, Entrée ouvre le premier résultat, Échap efface.
- **⚙ Paramètres** : export/import JSON, gestion des catégories (renommer/supprimer), refresh des statuts.

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

Table `categories` : `id`, `name` (unique), `position`.

Table `memos` : `id`, `content`, `position`, `created_at`, `uid`, `updated_at`.

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
| GET     | `/api/favicon/<id>`        | Favicon du service, récupéré côté serveur (cache mémoire) |
| GET     | `/api/export`              | Sauvegarde JSON v3 (liens + catégories + mémos + uid/dates) |
| POST    | `/api/import`              | Réimporte une sauvegarde (voir Backup / restore) |

Le check de statut est fait côté Flask pour éviter le CORS. Renvoie `online` / `offline` / `unknown` (URL vide) par URL renseignée.

La météo est récupérée côté client depuis open-meteo.com (Bayonne, gratuit, sans clé). Les favicons sont récupérés par Flask via l'URL locale du service (ce qui contourne Authelia), avec fallback `icons.duckduckgo.com` puis initiale du nom.

## Backup / restore

Depuis l'UI : **⚙ Paramètres → Export JSON / Import JSON**. L'export (v3) contient liens, catégories et mémos, chacun avec son `uid` et ses dates. À l'import :

1. **Même `uid` déjà en base** : si la version du fichier est plus récente (`updated_at`), le lien/mémo existant est **mis à jour** (c'est une évolution du même élément) ; sinon il est ignoré.
2. **Pas de `uid`** (anciennes sauvegardes v1/v2) : correspondance par nom + URLs pour un lien, contenu identique pour un mémo. Un lien correspondant **enrichit** les champs vides du lien existant (description, mémo, catégorie) au lieu d'être ignoré ; il n'écrase jamais un champ déjà rempli.

Rien n'est jamais supprimé par un import. Les catégories sont rattachées par nom (créées si absentes).

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
