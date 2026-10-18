# Incident — 18 oct. 2026 : `dash.fabnode.dev` refuse la connexion depuis le Mac (fail2ban)

## Symptôme
Depuis le Mac (LAN 192.168.1.x, sortie Internet par la box) : `ERR_CONNECTION_REFUSED` sur
`https://dash.fabnode.dev` et `https://dash.homebayonne.duckdns.org` (curl → code 000, immédiat).
Depuis l'extérieur : le serveur répond. Depuis le Zimaboard lui-même, Caddy répond (`302` vers Authelia
en 443, `405` en 80) et le conteneur `caddy` est « Up 4 weeks » : **Caddy n'est pas en cause**.

## Cause (établie en lecture seule, sans accès root)
- Les deux domaines pointent sur **90.30.38.24** (IPv4 publique ACTUELLE de la box, dynamique :
  `cloudflare-ddns` + `duckdns` tournent justement pour la suivre).
- La jail `caddy-auth` (`/etc/fail2ban/jail.d/caddy.local`) ignore `127.0.0.1/8 192.168.1.0/24
  83.193.173.231` : **83.193.173.231 est une ancienne IP publique**, périmée. L'IP courante n'est pas
  ignorée.
- Quand le Mac appelle `https://dash.fabnode.dev`, le trafic sort par la box et revient par son IP
  publique (pas de hairpin NAT en LAN) : Caddy voit `client_ip = 90.30.38.24`.
- Le test d'intrusion prod de V30.0.282 (13:40) a envoyé **6 requêtes → 401 par domaine, 12 au total**
  (sans jeton, cookie seul, jeton bidon, plus les en-têtes) ; le filtre `caddy-auth` matche **tout 401**
  (`maxretry 5`, `findtime 600`) → **ban de 90.30.38.24 pour 1 h** (`bantime 3600`). Un ban fail2ban =
  règle iptables REJECT → « connection refused », exactement le symptôme. `/var/log/fail2ban.log` a été
  modifié à 14:00 (contenu non lisible : root:adm).
- Le ban expire seul **une heure après** (≈ 14:40–15:00 Paris) si rien n'est fait.

## Résolution (18 oct. 2026, ~14:15 Paris)
`sudo fail2ban-client status caddy-auth` (Fabien, Terminal.app) : **Banned IP list : 90.30.38.24** — 13 bans
au total depuis la création de la jail, 829 échecs cumulés (la jail travaille vraiment). `unbanip
90.30.38.24` → 0 banni. Vérifié depuis le Mac : les deux domaines répondent `302` vers Authelia, TCP 443
ouvert. **Correctif `ignoreip` appliqué dans la foulée** (Fabien, sudo) : `reload caddy-auth` → OK, `get caddy-auth ignoreip` liste `127.0.0.0/8, 192.168.1.0/24, homebayonne.duckdns.org, ::1, 90.30.38.24`. Incident clos.

## Ce que CC ne peut pas faire
`fail2ban-client` parle à `/var/run/fail2ban/fail2ban.sock` (root only), `sudo` exige un mot de passe
interactif, le log est illisible : **aucune lecture ni levée de ban possible depuis une session CC.**
C'est à Fabien, dans un terminal :

```bash
ssh -t -p 22 casaos@192.168.1.39
sudo fail2ban-client status caddy-auth                 # liste "Banned IP list"
sudo fail2ban-client set caddy-auth unbanip 90.30.38.24
sudo grep -E "Ban|Unban" /var/log/fail2ban.log | tail -20
```

## Correctif durable (APPLIQUÉ le 18 oct. 2026, Fabien, root)
Dans `/etc/fail2ban/jail.d/caddy.local`, remplacer la ligne `ignoreip` :

```ini
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24 90.30.38.24 homebayonne.duckdns.org
```

- `192.168.1.0/24` : déjà présent (LAN direct, ex. `http://192.168.1.39:8099`).
- `90.30.38.24` : l'IP publique **du jour** — elle changera. D'où le **nom DNS** : fail2ban résout
  les hostnames d'`ignoreip` au (re)démarrage, donc `homebayonne.duckdns.org` suit l'IP dynamique à
  chaque `reload` (`fabnode.dev` volontairement exclu : l'apex peut passer par le proxy Cloudflare). Limite : résolus au démarrage seulement → après un changement d'IP,
  un `sudo fail2ban-client reload caddy-auth` (ou un cron quotidien) remet la liste à jour. Si l'apex
  `fabnode.dev` ne pointe pas sur la box (Cloudflare proxy), garder seulement `homebayonne.duckdns.org`.
- Puis : `sudo fail2ban-client reload caddy-auth` et vérifier `sudo fail2ban-client get caddy-auth ignoreip`.

## Leçon pour les prochains tests d'intrusion
Un test d'intrusion depuis le Mac **compte comme une attaque** pour la jail (tout 401). Avant d'en
refaire un : (1) vérifier que l'IP publique courante est ignorée (`fail2ban-client get caddy-auth
ignoreip` vs `curl ifconfig.me`), ou (2) le faire depuis le Zimaboard (`127.0.0.1` ignorée) avec
`--resolve dash.fabnode.dev:443:127.0.0.1`, ou (3) se limiter à 4 requêtes → 401 par fenêtre de 10 min.
Les 429 de l'app ne comptent pas (statut ≠ 401). À ajouter au § 3 de `authelia-api-v1.md`.
