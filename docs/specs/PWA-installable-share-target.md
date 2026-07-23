# [PWA] — Dashboard installable (manifest + icônes + Share Target Android)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Décisions : périmètre owner + pages invité ; PAS de service worker en phase 1 (choix assumé anti-cache-fantôme). Suite logique de [WEB-CAPTURE] : le Share Target est le pendant mobile des bookmarklets.**

## Objectif

Installer le dashboard sur l'écran d'accueil (mobile et desktop) comme une vraie app (plein écran, icône, couleurs), et sur Android brancher le menu « Partager » natif → arrivée dans le flux `?capture=` existant.

## Spécification

### Manifest + icônes

- **`/manifest.webmanifest`** servi par Flask (route simple, derrière Authelia pour l'owner — l'installation se fait connecté, c'est le comportement attendu) : `name` « Dashboard », `short_name`, `start_url: '/'`, `display: 'standalone'`, `background_color`/`theme_color` = tokens du thème sombre (`#0e1217`), `lang: 'fr'`, icônes ci-dessous, et **`share_target`** :
  ```json
  "share_target": { "action": "/", "method": "GET",
    "params": { "title": "title", "text": "text", "url": "url" } }
  ```
  → au partage Android, l'app s'ouvre sur `/?title=…&text=…&url=…` : **adapter le lecteur de params [WEB-CAPTURE]** pour reconnaître AUSSI cette forme (sans `capture=`) : `url` présente → flux « lien » ; `text` seul → flux « note » ; nettoyage `replaceState` et anti-XSS identiques.
- **Icônes PNG** générées depuis `static/favicon.svg` : 192×192, 512×512 + variantes **maskable** (padding safe-zone), committées dans `static/` (pas de génération au build — invariant 6, pas d'étape de build).
- Balises dans les templates : `<link rel="manifest">` + `<meta name="theme-color">` (2 thèmes via `media`) + `apple-touch-icon` (PNG 180×180) pour iOS.

### Pages invité (share.html + hub.html)

- Même `<link rel="manifest">`… mais servi par une **route publique sous `/share/`** (invariant 5) : **`/share/assets/manifest-guest.webmanifest`** (whitelist `SHARE_ASSETS` ou route dédiée sous `/share/`), avec `start_url` **relatif à la page du jeton** — subtilité : un manifest statique ne peut pas connaître le token. Solution : générer le manifest invité **dynamiquement** via `GET /share/<token>/manifest.webmanifest` (token revalidé, `start_url: '/share/<token>'` ou l'URL hub) — l'invité installe SON accès. Icônes via `/share/assets/` (déjà whitelistées ou à ajouter).
- Le manifest invité n'expose RIEN d'autre que l'URL que l'invité connaît déjà (invariant 5). **Pas de `share_target` côté invité** (le flux capture est owner-only derrière Authelia).
- Sonde bypass obligatoire sur la nouvelle route `/share/<token>/manifest.webmanifest` (fetch `credentials:'omit'` → `basic`, pas de redirect Authelia).

### Pas de service worker (phase 1)

- **Aucun SW** : installabilité assurée par manifest + HTTPS (Chrome/Safari modernes n'exigent plus de SW). L'app nécessite le réseau, comme aujourd'hui. → zéro couche de cache à invalider à chaque lot. (Phase 2 possible plus tard : SW network-first versionné `APP_VERSION` + skipWaiting, à re-cadrer.)

### iOS — limites connues (à documenter dans REALISATION, pas à contourner)

- Installation « Sur l'écran d'accueil » : OK (manifest + apple-touch-icon). **Share Target : non supporté par iOS** — le partage natif restera Android ; sur iPhone, le raccourci = l'app installée + saisie normale.

## Invite de mise à jour ([UPDATE-PROMPT] — idée Fabien, 23 juil. 2026, même lot)

Le vrai risque sans SW n'est pas le cache mais la **page/app ouverte longtemps** (le dashboard tourne des jours ; en PWA standalone il n'y a pas de bouton recharger) : le JS en mémoire reste l'ancien après un déploiement.

- **Version embarquée au rendu** : chaque page (owner, share, hub) reçoit la version courante via Jinja (la même source que `/api/version` — vérité unique, pas de constante dupliquée).
- **Détection** : réutiliser les polls EXISTANTS (owner : `/api/activity` 15 s — y exposer la version pour éviter une requête en plus ; share/hub : leur refresh périodique existant, la version passe par `share_data`/`/data` ou un champ du payload déjà rafraîchi). Comparaison stricte embarquée ≠ serveur.
- **Invite** : toast/badge discret persistant « ⬆ Nouvelle version (VX.Y.Z) — Recharger » (pattern `undoToast`/`notify` existant, tokens invariant 9, PAS de reload automatique sauvage). Clic → `location.reload()`. Respecter `uiBusy()` : pop-in ouverte ou saisie en cours → l'invite attend la fin (même mécanique différée qu'[AUTO-REFRESH]).
- Mismatch de version d'EXPORT (X) : même mécanique, rien de spécial — l'invite couvre tout changement.
- Préparation phase 2 : si un service worker arrive un jour, cette invite devient le déclencheur standard `skipWaiting` — l'UX est déjà en place.

Tests additionnels : simuler un écart de version (modifier la valeur embarquée au devtools ou bumper REALISATION sur copie) → l'invite apparaît sur les 3 pages au tick suivant ; en pleine édition → différée à la fermeture de la pop-in ; clic Recharger → page à jour, invite disparue ; versions égales → jamais d'invite.

## Contraintes

- **Export inchangé (v23)**. Lot = **V23.10.Z** (après [VOICE-MESSAGES] ; Z = dernier `REALISATION.md` + 1).
- Invariants : **5** (routes invité sous `/share/` uniquement + sonde bypass), **6** (icônes committées, zéro build, zéro CDN), **8**, **9**. `py_compile` + `node --check`.
- Ne PAS casser le comportement navigateur classique (le site reste 100 % utilisable non installé).

## Tests avant fin

1. `python3 -m py_compile app.py` ; `GET /manifest.webmanifest` → JSON valide (owner connecté) ; icônes 200.
2. Chrome desktop : icône « Installer » dans l'omnibox → app standalone, thème correct.
3. `/?title=T&url=https://example.com` (forme share target) → pop-in lien pré-remplie, URL nettoyée ; `/?text=Note` → note pré-remplie ; XSS titre = texte brut (mêmes tests que [WEB-CAPTURE]).
4. Invité : `GET /share/<token>/manifest.webmanifest` sans auth → `basic` 200, `start_url` correct ; token invalide → 404 ; page share installable.
5. Lighthouse (ou audit Chrome) : installabilité verte owner ET share.
6. Tests réels par Fabien : installation Android + partage natif vers l'app ; installation iPhone (sans partage).

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.10.Z] + `IDEAS.md` [PWA] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : manifests, formes d'URL, sonde bypass, installabilité desktop ; l'installation mobile réelle = Fabien.
