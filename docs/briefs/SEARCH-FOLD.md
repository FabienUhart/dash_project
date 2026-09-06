# Brief CC — [SEARCH-FOLD] : une recherche qui trouve ce qu'on tape

> **Frontend pur, 3 pages** (`templates/partials/_shared.js.html` pour le normaliseur, `index.html`
> pour la fusion et le no-result, `share.html`/`hub.html` pour le normaliseur seul). Zéro route, zéro
> schéma, `app.py` intact, **export 27 inchangé**. Doctrine TDD (e2e rouges → verts). Clôt le mémo
> prod 256 de Fabien (« faire que la recherche fonctionne même avec le texte écrit dans les mémos »).
> Graine et mesures : IDEAS.md § [SEARCH-FOLD]. Prod actuelle : V27.43.258.

## 0. Constat (mesuré sur la prod, 244 mémos, 6 sept. 2026)

La recherche est un `.toLowerCase().includes(q)` brut, sur la requête ENTIÈRE :

1. **Accents** : « eclipse » → 4 mémos, « éclipse » → 1 ; « reservation » → 0 mémo, « réservation » → 1.
2. **Ordre des mots** : « kyoto sanjo » → 1, « sanjo kyoto » → 0 ; « lits jumeaux » → 1, « jumeaux lits » → 0.
3. **Portée « Tout » ne fusionne pas** : « japon » → ligne « PROJETS (1) Voyage Japon — 2 mémos » + **1** mémo
   listé, alors que le sous-arbre Voyage Japon en contient **51** ; le « 2 mémos » ne compte que les directs.
   « kyoto » → 5 mémos par le texte, « Activités Kyoto » en a 10.
4. **Dans un dossier, « Aucun résultat » est muet sur la portée** : depuis Voyage Japon, « eclipse » →
   « Aucun mémo ne correspond à « eclipse » » alors qu'il y en a 4 ailleurs ; le chip « dans : … ✕ »
   ([SEARCH-IN-FOLDER]) est dans le header, loin du message, qui ne propose pas d'élargir.

## 1. Où ça vit

- Parse commun : `parseSearchPrefix(raw, scope)` (`_shared.js.html` ~l.7435) — préfixes `p#`/`l#`/`m#`.
- Owner `index.html` : `matchingProjects(q)` ~l.2836, `visibleLinks()` ~l.4194, `visibleMemos()` ~l.4858,
  `boardScopeFilter()`/`searchIsScoped()` ~l.2811 ([SEARCH-IN-FOLDER]), chip « dans : » ~l.9587,
  `refreshSearch()` ~l.9700, no-result mémos ~l.9287 et liens ~l.4638 (`emptyState`), aide `/` via
  `attachSearchUI` (partial, `helpRows`).
- Share `share.html` : `shareSearch()` ~l.2433, filtre mémos ~l.2453, `shareMatchingProjects`.
- Hub `hub.html` : `hubSearch()` ~l.861, filtre mémos ~l.876.
- `projectDescendants(pid)` (owner ~l.4606), `projDescendants` (share).

## 2. Le correctif

### A. Un normaliseur partagé — `searchFold(s)` dans `_shared.js.html`

Helper **pur, sans état, identique 3 pages** (critère ADR-001) : `String(s)` → `normalize('NFD')` →
retirer les diacritiques (`/\p{M}/gu`) → minuscules → apostrophes/guillemets typographiques (’ ‘ “ ”)
en droits → espaces multiples/insécables réduits à un → `trim()`. Zéro lib (invariant 6).
`parseSearchPrefix` rend désormais `q` **foldé** ET `words` = `q.split(' ').filter(Boolean)`.

### B. Tous-les-mots, n'importe quel ordre — `searchMatch(words, ...fields)` partagé

Vrai si **chaque** mot de `words` est inclus dans la concaténation foldée des champs (` ` entre eux).
Remplace `includes(q)` partout : owner mémos (titre + `stripHTML(content)` + sous-tâches + assignés),
owner liens (name, descr, memo, tags, url_public, url_local), owner dossiers (name, tags), share/hub
mémos (titre + contenu + assignés), share/hub dossiers. **Une requête entre guillemets** `"lits jumeaux"`
= phrase exacte (un seul « mot » foldé, espaces compris) — si ça alourdit, le noter en `[SEARCH-FOLD-V2]`.
**`#tag`** garde son sens : match **exact** d'un tag (foldé des deux côtés), pas un mot parmi d'autres.

### C. Portée « Tout » fusionne (owner seulement)

Dans `visibleMemos()`, portée `all` : l'ensemble résultat = mémos trouvés par le texte **∪** mémos dont
`project_id` ∈ {dossiers trouvés par `matchingProjects` **+ leurs descendants**}, dédupliqués par `id`.
`m#` reste texte seul, `p#`/portée `projects` reste « mémos des dossiers trouvés » — mais **descendants
inclus** là aussi. Le compteur de la ligne « PROJETS (1) Voyage Japon — N mémos » dit la vérité : total
du sous-arbre (« 51 mémos », ou « 2 + 49 dans les sous-dossiers » si tu préfères, même gabarit
qu'aujourd'hui). La carte et la frise passent par `boardScopeFilter()` : vérifier qu'elles voient les
mêmes mémos que la liste (invariant du prédicat unique, cf. commentaire ~l.2808). L'étiquette de dossier
déjà présente sur les cards explique pourquoi un mémo est là — rien à ajouter.

### D. « Aucun résultat » explicite (owner)

Quand `searchIsScoped()` est vrai : hint = « Aucun mémo ne correspond à « eclipse » **dans 🗻 Voyage
Japon**. » et **deux** actions : « Chercher partout » (même bascule que le ✕ du chip : `searchWide =
true; searchWideProj = state.memoProject; refreshSearch()`) + « Effacer la recherche ». Si `emptyState`
n'accepte qu'une action, l'étendre proprement (pas de bouton bespoke — invariant 9, style Luciole
secondaire). Hors dossier : message inchangé.

### E. Aide `/`

Une ligne dans `helpRows` (3 pages) : « accents et ordre des mots indifférents — « sanjo kyoto » trouve
« Kyoto · Sanjo » ». Les préfixes ne changent pas.

## 3. Ce qui ne doit PAS bouger

`p#`/`l#`/`m#` et le sélecteur de portée ; `SEARCH_WIDE_SCOPES` ; `#tag` = match exact ; [SEARCH-IN-FOLDER]
(portée bornée au dossier + chip + `searchWide` non persisté) ; « Entrée ouvre le premier lien » ; la
feuille mobile ; `share.html`/`hub.html` ne gagnent **pas** la fusion (leur périmètre est déjà celui du
token — invariant 5, rien de nouveau côté réseau) ; aucune recherche dans les commentaires (hors lot).

## 4. Tests (TDD — rouges avant, verts après)

E2E Playwright, seed dédié (fixture : dossier « Voyage Japon » → sous-dossier « Activités Kyoto » → mémo
« 🏨 Kyoto · Sanjo » contenu « ch. lits jumeaux » ; mémo Inbox « Éclipse » ; mémo Inbox « eclipse » ;
lien tagué `#notes`). Zéro erreur console sur chaque parcours.

1. `test_search_ignores_accents` (owner + share + hub) — « eclipse » et « éclipse » rendent le **même**
   ensemble (2 mémos). **Rouge avant** (1 vs 1 mais pas les mêmes).
2. `test_search_any_word_order` (owner + share + hub) — « sanjo kyoto » = « kyoto sanjo » = 1 mémo ;
   « jumeaux lits » = 1. **Rouge avant**.
3. `test_search_all_merges_folder_subtree` (owner) — portée Tout, « japon » → les mémos du sous-arbre
   (Activités Kyoto inclus) sont listés, dédupliqués avec le mémo textuel ; la ligne PROJETS affiche le
   total du sous-arbre. **Rouge avant**. Contrôle : `m#japon` ne les ramène **pas** (non-régression).
4. `test_search_projects_scope_includes_descendants` (owner) — `p#japon` liste les mémos des descendants.
   **Rouge avant**.
5. `test_no_result_names_folder_and_widens` (owner) — dans Voyage Japon, « eclipse » → hint contient
   « dans » + « Voyage Japon » + bouton « Chercher partout » ; clic → les 2 mémos apparaissent, chip
   « dans : » disparu. **Rouge avant**.
6. Non-régressions (vertes d'emblée, assumées) : `#notes` exact (pas « #note »), `p#`/`l#` inchangés,
   [SEARCH-IN-FOLDER] toujours borné avant élargissement, « Entrée ouvre le premier lien ».
7. **Mutations** : retirer `normalize('NFD')` → #1 rougit ; remettre `includes(q)` sur la requête entière
   → #2 rougit ; retirer les descendants de la fusion → #3/#4 rougissent ; retirer l'action « Chercher
   partout » → #5 rougit.

## 5. Definition of Done

`make test` entièrement vert ; #1→#5 prouvés rouges avant ; 4 mutations tuées ; `searchFold`/`searchMatch`
vérifiés identiques 3 pages (diff) ; REALISATION.md (Z = dernier + 1, mineure → V27.44.x) ; IDEAS.md
(retirer de la file, § graine → « Fait ») ; rebuild local ; journal + handoff ; **STOP**. Pas de commit,
pas de tag, pas de push — passe Cowork puis GO explicite de Fabien. Vérif à l'œil Fabien sur la prod
après deploy : « japon », « sanjo kyoto », « éclipse », et « eclipse » depuis Voyage Japon.
