# Dashboard

Dashboard web perso minimaliste : une liste de liens vers des services auto-hébergés, avec deux URLs possibles par service (publique + VPN/locale), check de statut côté serveur, et mémo libre.

Stack : Flask + SQLite, servi par gunicorn dans un conteneur Docker.

## Lancer en local

```bash
docker compose up -d --build
```

UI : http://localhost:8099

## Modèle de données

Table `links` :

| Champ        | Type     | Notes                                 |
|--------------|----------|---------------------------------------|
| `id`         | INTEGER  | Clé primaire auto                     |
| `name`       | TEXT     | Obligatoire                           |
| `descr`      | TEXT     | Description courte                    |
| `url_public` | TEXT     | URL publique (🌐), optionnelle        |
| `url_local`  | TEXT     | URL VPN/locale (🔒), optionnelle      |
| `memo`       | TEXT     | Notes libres, multi-ligne             |
| `position`   | INTEGER  | Ordre d'affichage                     |

Les URLs sans scheme (`http://` ou `https://`) sont préfixées automatiquement en `http://` au save.

## API

| Méthode | Endpoint                  | Description                                   |
|---------|---------------------------|-----------------------------------------------|
| GET     | `/api/links`              | Liste tous les liens, triés par `position`    |
| POST    | `/api/links`              | Crée un lien                                  |
| PUT     | `/api/links/<id>`         | Met à jour un lien                            |
| DELETE  | `/api/links/<id>`         | Supprime un lien                              |
| POST    | `/api/links/reorder`      | `{ids: [...]}` — réécrit les positions        |
| GET     | `/api/links/status`       | `{id: {public, local}}` — ping côté serveur   |

Le check de statut est fait côté Flask pour éviter le CORS. Renvoie `online` / `offline` / `unknown` (URL vide) par URL renseignée.

## Persistance

La base SQLite vit dans `./data/dashboard.db`, monté en volume dans le conteneur.

## Pas d'auth

L'app n'a aucune authentification. En production, elle est servie derrière un reverse proxy Caddy avec `basic_auth`. Ne pas exposer directement.

## Déploiement Zimaboard

Le même `docker-compose.yml` tourne tel quel sur le Zimaboard : `git clone` + `docker compose up -d --build`. Le port 8099 y est déjà routé derrière Caddy.
