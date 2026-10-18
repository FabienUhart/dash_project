# Infra — Caddy : router `/mcp*` vers le serveur MCP ([DASH-MCP] lot B, V30.1.283)

> **APPLIQUÉE le 18 oct. 2026 à 15:05 (Paris), sur GO explicite de Fabien**, après le déploiement de V30.1.283
> (Caddy v2.11.3). Le Caddyfile vit sur l'HÔTE : **`/home/casaos/Documents/projects/caddy/Caddyfile`**
> (casaos, 600), monté **en lecture seule** dans le conteneur `caddy` (`/etc/caddy/Caddyfile`) — on l'édite donc
> côté hôte, puis `docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.
> Sauvegardes : `Caddyfile.bak-20261018-150553` (hôte, à côté) et `/data/Caddyfile.bak-20261018-150520` (volume
> du conteneur). `caddy validate` : « Valid configuration », reload OK. Contrôle § 3 : voir `REALISATION.md`
> [V30.1.283] et le journal du 18 oct. Authelia : `^/mcp/.*$` **déjà en bypass** depuis V30.0.282
> (`authelia-api-v1.md`), rien n'y a changé.
>
> Ce qui a été inséré (les deux blocs dash : `handle @dash { … }` du bloc `*.homebayonne.duckdns.org`, et le
> bloc `dash.fabnode.dev`) : après `import authelia`, un `handle /mcp*` → `192.168.1.39:8100` et un `handle`
> de repli → `192.168.1.39:8099` (le `reverse_proxy` nu d'avant), schéma « switch » déjà utilisé plus bas dans
> le fichier. Le `handle` est terminal : `/mcp*` ne tombe jamais dans le repli.

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

Le bloc existant utilise `192.168.1.39:8099` (IP de l'hôte, ports publiés) : même forme pour 8100. Le
`forward_auth` Authelia (`import authelia`) reste devant : la règle bypass `^/mcp/.*$` répond `200` sans session.

## 3. Appliquer (le jour du GO) et contrôler
```bash
ssh -p 22 casaos@192.168.1.39
F=/home/casaos/Documents/projects/caddy/Caddyfile          # SOURCE du bind mount (ro dans le conteneur)
cp "$F" "$F.bak-$(date +%Y%m%d-%H%M%S)"
vi "$F"                                                     # insérer le handle ci-dessus dans les 2 blocs dash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec caddy caddy reload   --config /etc/caddy/Caddyfile --adapter caddyfile
```

⚠ Piège vécu : `docker exec caddy sh -c 'cat > /etc/caddy/Caddyfile'` échoue (« Read-only file system ») —
le fichier est monté `:ro`. Écrire sur l'hôte, recharger depuis le conteneur. Un `caddy validate` sur une copie
dans `/tmp` du conteneur permet de tester AVANT de toucher l'hôte.

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
