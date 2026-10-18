# Infra — règle Authelia pour l'API v1 ([DASH-API], V30.0.282)

> **Proposition, NON appliquée.** La config Authelia vit sur le Zimaboard, hors dépôt
> (`/home/casaos/Documents/projects/authelia/config/configuration.yml`, root 600 → passer par
> `docker exec authelia`). À appliquer **uniquement sur GO explicite de Fabien**, au moment du déploiement
> de V30.0.282, puis test d'intrusion (§ 3).

## 1. La règle

Dans `access_control.rules`, **au-dessus** de la règle `two_factor` du domaine du dashboard, calquée sur la
règle existante `/share/.*` :

```yaml
access_control:
  default_policy: deny
  rules:
    # … règle /share/.* existante (bypass) …
    - domain: "dash.<ton-domaine>"
      policy: bypass
      resources:
        - "^/api/v1/.*"      # [DASH-API] lot A — jeton Bearer obligatoire côté app (invariant 10)
        - "^/mcp/.*"         # réservé lot B (MCP) : aucune route /mcp n'existe encore → 404 par Flask
    # … règle two_factor du domaine (inchangée) …
```

Rien d'autre ne change : `/pair/.*` (futur appairage, lot C) **reste protégé**, `/api/tokens` (gestion des
jetons) **reste derrière Authelia**, `/static/` aussi.

Pourquoi c'est sûr : chaque route `/api/v1/*` porte `@require_token` (la batterie d'invariants refuse une
route sans la marque), le cookie de session n'est **jamais** lu, un jeton inconnu/révoqué/expiré → 401 `{}`.

## 2. Appliquer (le jour du GO)

```bash
ssh -p 22 casaos@192.168.1.39
docker exec authelia sh -c 'cp /config/configuration.yml /config/configuration.yml.bak-$(date +%Y%m%d-%H%M%S)'
docker exec -it authelia vi /config/configuration.yml     # insérer la règle ci-dessus
docker exec authelia authelia validate-config --config /config/configuration.yml
docker restart authelia
```

## 3. Test d'intrusion prod (après déploiement + règle)

```bash
# sans jeton → on ATTEINT l'app (401 JSON), PAS la page Authelia (302/HTML)
curl -si https://dash.<domaine>/api/v1/me | head -1            # HTTP/2 401
# cookie de session seul → 401 (l'API ignore le cookie)
curl -si -H "Cookie: authelia_session=<cookie du navigateur>" https://dash.<domaine>/api/v1/me | head -1
# jeton valide → 200 ; jeton révoqué depuis Paramètres → 401
curl -s -H "Authorization: Bearer dash_…" https://dash.<domaine>/api/v1/me
# /api/tokens reste derrière Authelia → redirection vers Authelia (302) sans session
curl -si https://dash.<domaine>/api/tokens | head -1
```

## 4. fail2ban — étendre la jail `caddy-auth` aux 401 de l'API

Filtre proposé : `docs/infra/fail2ban-dash-api.conf` (à copier dans `/etc/fail2ban/filter.d/`), jail :

```ini
[dash-api]
enabled  = true
filter   = dash-api
logpath  = /var/log/caddy/access.log      # chemin réel du log d'accès Caddy (JSON)
maxretry = 5
findtime = 10m
bantime  = 1h
action   = iptables-allports[name=dash-api]
```

Rappel : le compteur **applicatif** (20 tentatives/min par IP sans jeton → 429) agit même sans fail2ban.
