# Brief CC — [LINK-SORT] : trier la vue Liens (plus récents d'abord)

> **Front pur, owner-only, zéro route, `app.py` intact, export 27 inchangé.** Demande Fabien du 25 sept. 2026 :
> « la page Liens pourrait avoir un système de tri, du plus récent au plus ancien, ça m'aiderait à les
> retrouver ». Doctrine TDD (CLAUDE.md § Tests & TDD). Prod actuelle : V27.44.259 → cible **V27.45.260**.
> Placé **n° 1 de la file**, devant [LINK-REFS] (petit lot, à livrer seul).

## 0. Ce qui change, en une phrase

La vue Liens gagne un sélecteur de tri — **Manuel** (l'ordre actuel, par `position`), **Plus récents**,
**Plus anciens**, **A → Z** — mémorisé sur l'appareil ; le glisser-déposer de réordonnancement ne reste
actif qu'en tri Manuel.

## 1. Décisions (fermes)

1. **Quatre modes, un seul état** : `state.linkSort ∈ {'manual','newest','oldest','name'}`, défaut `'manual'`
   (= comportement d'aujourd'hui, **aucun changement visible tant qu'on ne touche pas au sélecteur**).
2. **Clé de tri « récents »** = `created_at` DESC, **départage par `id` DESC**. ⚠ Les liens antérieurs à la
   migration uid/created_at (app.py ~l.1553) partagent la MÊME `created_at` (date de migration) — sans
   le départage par id, leur ordre serait arbitraire. Pas `updated_at` : un lien qu'on retouche ne doit pas
   « remonter » (et le refresh OG ne doit surtout pas compter comme une modification).
3. **Le tri est une VUE, jamais une écriture** : on ne touche pas à `position`, on n'appelle pas
   `/api/links/reorder`. Le D&D intra-liste (`renderLinks`, handler `dragover` ~l.4666) est **désactivé** hors
   mode Manuel (la card garde `draggable` pour le D&D vers la sidebar catégorie/étiquette — [TAG-NAV] —,
   seul le réordonnancement intra-liste est coupé). En mode trié, un `dragover` sur une card ne fait rien.
4. **Persistance locale** : `localStorage['dash:linkSort']` (même famille de clés que les autres réglages
   d'affichage du front), lu au boot, valeur inconnue → `'manual'`. Pas de réglage serveur, pas d'export.
5. **Le tri s'applique APRÈS le filtre et la recherche** : `visibleLinks()` garde son contrat (filtre
   catégorie / recherche / `#tag`) et une fonction pure `sortLinks(links, mode)` est appliquée dans
   `renderLinks()` — et dans la **vue tag** ([TAG-NAV]) si elle liste des liens, même règle. `'manual'`
   = ordre reçu de l'API (`position, id`), on ne re-trie pas.
6. **A → Z** : `name` foldé avec `searchFold` ([SEARCH-FOLD], partial) — « Éclipse » se range avec « eclipse ».
   `localeCompare` sur les valeurs foldées, départage id ASC.
7. **Placement et forme du contrôle — VALIDÉ par Fabien le 25 sept. (prototype injecté dans localhost:8099)** :
   **PAS de `<select>`** (« juste à coller au design des autres boutons »). Quatre boutons **Manuel · Plus
   récents · Plus anciens · A → Z**, **même classe et même gabarit que `#add-cat-page`** (fond `--panel-2`,
   bordure `--border`, rayon 6 px, Inter 500), placés dans `#links-actions` à droite des deux boutons d'ajout
   (desktop) ; en mobile ≤ 900 px dans `#links-blockhead`, à gauche du ＋ (libellés courts si ça déborde :
   Manuel · Récents · Anciens · A→Z). **État sélectionné = Luciole** (`docs/design/LUCIOLE-boutons.md`) :
   matière + libellé, jamais d'aplat accent — bordure et texte `--accent`, fond `--panel`, léger creux
   (`inset` ombre), exactement le rendu de « + Ajouter un lien » actif. Un seul bouton actif à la fois,
   `aria-pressed`. Invariant 9 : aucune classe nouvelle, réutiliser celle des boutons d'ajout.
8. **Hors périmètre** : pas de tri des mémos (autre lot), pas de tri côté serveur, rien sous `/share/*`
   (la table `links` n'est exposée à aucune surface invitée — verrouillé par `test_no_guest_og_surface`).

## 2. Ce qui NE bouge PAS

`GET /api/links` (`ORDER BY position, id`), `/api/links/reorder`, `visibleLinks()` (contrat inchangé),
`linkCardEl`, l'aperçu OG, le D&D vers la sidebar, la feuille mobile, share/hub.

## 3. Tests (TDD — rouges d'abord)

Fichier : `tests/front/test_link_sort.py` (e2e Playwright, décor : 4 liens créés par l'API avec des
`created_at` distincts — si l'API pose `created_at` elle-même, créer les liens **dans un ordre connu** et
poser une `position` inverse via `/api/links/reorder` pour que « manuel » ≠ « récents »).

1. **Défaut = manuel** : sans localStorage, l'ordre affiché = `position` (identique à avant le lot).
2. **Plus récents** : sélection → ordre `created_at` DESC ; le lien créé en dernier est en tête.
3. **Départage** : deux liens avec la même `created_at` (poser la même valeur via import ou fixture DB) →
   l'id le plus grand d'abord.
4. **Plus anciens** = miroir exact de 2.
5. **A → Z foldé** : « Éclipse », « eclipse », « Zèbre », « alpha » → alpha, Éclipse/eclipse (id ASC), Zèbre.
6. **Le tri survit au rechargement** (localStorage) et **une valeur corrompue** retombe sur Manuel.
7. **Le tri ne réordonne pas la base** : après avoir affiché « Plus récents », `GET /api/links` renvoie
   les `position` d'origine (aucun POST `/api/links/reorder` intercepté — `page.on('request')`).
8. **D&D coupé hors Manuel** : en mode « Plus récents », un `dragover` synthétique entre deux cards ne
   déplace pas le nœud dans `#links` ; repasser en Manuel le réactive (non-régression, verte d'emblée
   et assumée).
9. **Recherche + tri** : « eclipse » en mode « Plus récents » → seuls les résultats, dans l'ordre récent.

**Mutations à poser et tuer** (≥ 5) : départage id retiré (test 3) · `updated_at` à la place de
`created_at` (retoucher un lien ancien, il ne doit pas remonter) · tri appliqué avant le filtre / sur
`state.links` en place (test 7 : `state.links` muté ⇒ l'ordre manuel est perdu au retour) · `searchFold`
retiré du A → Z (test 5) · garde D&D retirée (test 8).

## 4. Livraison

- `templates/index.html` (+ `_shared.js.html` **seulement** si `sortLinks` doit servir à une autre page —
  aujourd'hui non : le partial ne gagne rien, ADR-001 respecté par absence).
- `REALISATION.md` : entrée `[V27.45.260]` ; `IDEAS.md` : retirer [LINK-SORT] de la file, [LINK-REFS]
  remonte n° 1. `docs/briefs/LINK-SORT.md` commité avec le lot.
- Cycle : coder → rebuild LOCAL → `make test` → journal + handoff → **STOP**. Passe Cowork puis GO Fabien
  avant tout commit/tag/push.
