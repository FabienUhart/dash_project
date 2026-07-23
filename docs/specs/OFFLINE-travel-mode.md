# [OFFLINE] — Mode hors ligne pour le voyage (SW versionné : lecture + notes rapides synchronisées)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Contexte : voyage Japon de Fabien début novembre, réseau intermittent. Décisions : lecture offline complète + création de notes Inbox hors ligne (pas d'édition offline) ; owner d'abord ; lot dédié APRÈS [PWA]. Prérequis : [UPDATE-PROMPT] (livré avec [PWA]) = le garde-fou qui rend le SW gérable.**

## Périmètre (et non-périmètre)

- ✅ Ouvrir l'app sans réseau : app-shell + **dernière synchro des données en lecture** (mémos, projets, liens, priorités — tout ce que `loadAll` charge), bandeau « 📴 Hors ligne — données du {date heure} ».
- ✅ **Noter hors ligne** : le champ note rapide (et lui seul) fonctionne sans réseau → file locale, synchronisation automatique au retour du réseau (création de mémos **Inbox uniquement**).
- ✅ Photos (dérivées t/s) et tuiles de carte **déjà vues** : re-affichables (cache). Pas de pré-téléchargement massif.
- ❌ PAS d'édition/suppression/vote/commentaire hors ligne (conflits invités — hors périmètre assumé). Les boutons concernés sont désactivés hors ligne avec un title explicite.
- ❌ Pages invité : phase ultérieure. Owner (`index.html`) seulement.

## Service worker — discipline stricte (le point qui fait peur, traité de front)

- **`static/sw.js` versionné par `APP_VERSION`+build** (la version REALISATION, injectée — cache name `dash-v<version>`) : un déploiement = un nouveau cache, l'ancien est **purgé à l'activation**. `skipWaiting` déclenché par le clic sur l'invite **[UPDATE-PROMPT]** (jamais silencieusement).
- **Stratégie network-first PARTOUT** : en ligne, comportement identique à aujourd'hui (le réseau fait foi, le cache n'est qu'un filet) → pas de cache fantôme en usage normal. Offline seulement → réponse cache.
- Périmètre du SW : app-shell (`/`, `/static/*` whitelistés), **GET de données** (`/api/links|memos|projects|priorities|settings|version…` : dernière réponse OK mise en cache), dérivées images `?size=t|s` et tuiles OSM **en cache LRU borné** (~50 Mo, purge FIFO). **JAMAIS de cache des POST/PUT/DELETE**, jamais des routes `/share/*` (invariant 5 : rien de nouveau côté public), jamais des réponses non-200 ni des redirects (piège Authelia : ne JAMAIS mettre en cache une redirection de login).
- Session Authelia expirée hors ligne : non-problème (pas de réseau = pas de redirect) ; en ligne, redirect → passe au réseau, jamais caché.

## Détection + bandeau

- `navigator.onLine` + échec des fetchs → état `offline` : bandeau discret fixe (tokens, invariant 9) « 📴 Hors ligne — données du {horodatage de la dernière synchro réussie} ». Retour réseau → bandeau vert bref « ✓ Reconnecté — synchronisation… » puis disparition + reload des données.

## File de notes hors ligne

- Note rapide hors ligne → entrée `{texte, created_at}` dans une file **localStorage** (`offlineQueue`, borné ~100), affichée immédiatement dans l'UI comme mémo « ⏳ en attente de synchro » (visuellement distinct, non éditable).
- Reconnexion → rejeu séquentiel des `POST /api/memos` (Inbox) ; succès = retrait de la file + refresh ; échec réseau = la file reste, retry au prochain retour en ligne. **Idempotence** : générer l'`uid` côté client au moment de la note (l'API l'accepte-t-elle à la création ? sinon dédup par contenu+created_at au rejeu — vérifier, choisir la plus sûre, la documenter).
- La file survit au reboot du téléphone (localStorage). Vider la file = uniquement par synchro réussie.

## Contraintes

- **Export inchangé (v23)** — rien de nouveau en base côté serveur (la file est locale). Lot = **V23.11.Z** (après [PWA] ; Z = dernier `REALISATION.md` + 1).
- Invariants 5 (SW jamais sur `/share/*`), 6 (SW maison, zéro lib), 8, 9. `py_compile` + `node --check sw.js`.
- Le site reste 100 % fonctionnel navigateur classique / SW non supporté (dégradation propre).

## Tests avant fin (DevTools → Network → Offline, puis mode avion réel)

1. En ligne : comportement strictement identique (network-first) ; déploiement simulé → [UPDATE-PROMPT] apparaît, clic → nouveau cache actif, ancien purgé (vérifier Application → Cache Storage).
2. Passage offline : app s'ouvre, données de dernière synchro affichées, bandeau avec le bon horodatage ; boutons d'édition désactivés ; photos/tuiles déjà vues re-affichées.
3. Note rapide offline ×3 → « ⏳ en attente » ; retour en ligne → les 3 arrivent dans Inbox, une seule fois chacune (rejouer le scénario 2× pour vérifier l'idempotence) ; file vide.
4. Coupure en PLEIN rejeu → pas de doublon au retour suivant.
5. Redirect Authelia jamais en cache (simuler session expirée en ligne → login normal, puis vérifier le cache).
6. Quota : après navigation carte intensive, cache borné (~50 Mo), rien ne casse quand la purge LRU joue.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.11.Z] + `IDEAS.md` [OFFLINE] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : scénarios 1-6 en DevTools ; le test mode avion réel sur téléphone = Fabien, idéalement des semaines avant le départ.
