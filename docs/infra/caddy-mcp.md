# Infra — Caddy : router `/mcp*` vers le serveur MCP ([DASH-MCP] lot B, V30.1.283)

> **Proposition, NON appliquée.** Le Caddyfile vit sur le Zimaboard, hors dépôt (conteneur `caddy`, monté
> `/etc/caddy/Caddyfile`). À appliquer **uniquement sur GO explicite de Fabien**, au moment du déploiement de
> V30.1.283, puis contrôle § 3. Authelia : `^/mcp/.*$` est **déjà en bypass** sur les deux domaines dash
> (appliqué le 18 oct. avec V30.0.282, voir `authelia-api-v1.md`) — rien à y changer.

## 1. Ce qui tourne dans le conteneur `dashboard` depuis V30.1.283
`bin/start.sh` lance **deux workers** : gunicorn (Flask, `:8099`, inchangé) et uvicorn (MCP, `:8100`,
`--no-access-log` : le chemin contient le jeton). Le compose publie `8100:8100`. Le MCP ne parle qu'à
`http://127.0.0.1:8099/api/v1/…` (dans le conteneur) avec le jeton reçu : il n'a aucune règle métier.

## 2. La route Caddy (sur les DEUX domaines dash)
Dans chaque bloc `dash.fabnode.dev` et `dash.homebayonne.duckdns.org`, **avant** le `reverse_proxy` général
vers 8099 (Caddy applique les `handle` dans l'ordre des matchers, le plus spécifique d'abord) :

```caddyfile
dash.fabnode.dev {
    # … forward_auth Authelia existant (il laisse passer /mcp/* : bypass) …

    # [DASH-MCP] serveur MCP (uvicorn, même conteneur que le dashboard)
    handle /mcp* {
        reverse_proxy 192.168.1.39:8100 {
            # Streamable HTTP : réponses longues / SSE → pas de mise en tampon, délais larges
            flush_interval -1
            transport http {
                read_timeout 300s
                write_timeout 300s
            }
        }
    }

    # … reverse_proxy 192.168.1.39:8099 existant (tout le reste) …
}
```

Remplacer `192.168.1.39:8100` par ce que le bloc existant utilise pour 8099 (nom de conteneur `dashboard:8100`
si Caddy et le dashboard partagent un réseau Docker ; IP de l'hôte sinon). Le `forward_auth` Authelia peut
rester devant : la règle bypass `^/mcp/.*$` répond `200` sans session.

## 3. Appliquer (le jour du GO) et contrôler
```bash
ssh -p 22 casaos@192.168.1.39
docker exec caddy sh -c 'cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date +%Y%m%d-%H%M%S)'
docker exec -it caddy vi /etc/caddy/Caddyfile            # insérer le handle ci-dessus dans les 2 blocs dash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Contrôle **depuis le Zimaboard** (jamais depuis le Mac : chaque 401 compte pour fail2ban, voir
`fail2ban-incident-20261018.md`) :

```bash
# sans jeton → 401 {} servi par le MCP (pas une page Authelia, pas un 404 Flask)
curl -s -o /dev/null -w "%{http_code}\n" -X POST --resolve dash.fabnode.dev:443:127.0.0.1 https://dash.fabnode.dev/mcp/
# avec un jeton valide (créé dans Paramètres › Appareils connectés) → la liste des 21 outils
curl -s -X POST --resolve dash.fabnode.dev:443:127.0.0.1 https://dash.fabnode.dev/mcp/<jeton>/ \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

## 4. Journalisation
Le log d'accès de Caddy (`/var/log/caddy/access.log`) **enregistre l'URI complète**, donc le jeton pour les
appels `/mcp/<jeton>/`. Ce log est root-only (600) et tourne ; c'est le même niveau d'exposition qu'un
jeton dans une URL de partage. Si on veut l'éviter : `log { … }` avec un `filter` `replace` sur `request>uri`
dans le bloc dash, ou passer les clients qui le peuvent (Claude Code, CLI) en `Authorization: Bearer`.
