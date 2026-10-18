# Infra — règle Authelia pour l'API v1 ([DASH-API], V30.0.282)

> **APPLIQUÉE le 18 oct. 2026 à 13:38 (Paris), sur GO explicite de Fabien**, après le déploiement de V30.0.282
> (Authelia v4.39.20). Sauvegarde : `/config/configuration.yml.bak-20261018-133837` (dans le conteneur).
> Les deux lignes ont été ajoutées aux `resources` des DEUX domaines dash (`dash.fabnode.dev` et
> `dash.homebayonne.duckdns.org`), juste sous `^/share/.*$`. `authelia config validate` : « parsed and loaded
> successfully without errors », `Startup complete`, conteneur `healthy`. Test d'intrusion § 3 : voir
> `REALISATION.md` [V30.0.282] et le journal de session du 18 oct.
>
> La config Authelia vit sur le Zimaboard, hors dépôt (`/home/casaos/Documents/projects/authelia/config/`,
> root 600 → passer par `docker exec authelia`). Toute modification future = même procédure (§ 2), sur GO.

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

## 4. fail2ban — les 401 de l'API sont DÉJÀ couverts

Constaté le 18 oct. 2026 sur le Zimaboard : la jail `caddy-auth` existante (`/etc/fail2ban/jail.d/caddy.local`,
`maxretry 5`, `findtime 600`, `bantime 3600`, `ignoreip 127.0.0.1/8 192.168.1.0/24 + l'IP fixe de Fabien`) utilise
le filtre `/etc/fail2ban/filter.d/caddy-auth.conf` :

```
failregex = ^\{.*"client_ip":"<ADDR>".*"status":401.*\}$
datepattern = "ts":{Epoch}
```

→ **tout 401 du log Caddy** (`/var/log/caddy/access.log`, JSON) compte, quel que soit le chemin : un jeton
bidon sur `/api/v1/…` ou `/mcp/…` renvoie 401 par l'app, Caddy le journalise en 401, la jail le voit. **Rien à
ajouter** : le filtre `fail2ban-dash-api.conf` de ce dossier est donc une **proposition redondante, non
appliquée** (et son regex devrait dire `client_ip`, pas `remote_ip`). Il ne servirait que si la jail
générique était un jour restreinte par chemin. Nuances : (a) les **429** (quota applicatif) ne sont pas des
401 → pas comptés par fail2ban, c'est le compteur de l'app qui freine ; (b) `/etc/fail2ban` est root : toute
modification passe par `sudo` interactif sur le Zimaboard, hors de portée de CC.

Jail telle qu'elle aurait été écrite si elle avait été nécessaire :

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

Rappel : le compteur **applicatif** (20 tentatives/min par IP sans jeton → 429) agit même sans fail2ban, y compris depuis le LAN (que fail2ban ignore).
