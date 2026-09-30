# Brief CC — [GUEST-SEARCH-GRAMMAR] : la recherche invitée parle la même grammaire que l'owner

> **Front pur (share + hub + partial), zéro route, `app.py` intact, export 28 inchangé.** Détaché
> de [SEARCH-ALL] le 30 sept. 2026 (ne tenait pas dans le lot). Constat Cowork
> (`docs/tests/test-page-invite.md` § 3) : côté invité, `d#2026-09` répond « Aucun » alors qu'un
> mémo est daté du jour, la recherche ignore les sous-tâches, et l'aide ne liste que `p#`/`m#`.
> Doctrine TDD. Cible **V28.11.278**. Brief écrit par CC le 30 sept., § 2.4 tranché par Fabien le
> même jour. **Code : pas avant le GO explicite de Fabien.**

## 0. Ce qui change, en une phrase

Sur la page de partage et le hub, `d#…` (échéance), `c#…` (création), les sous-tâches et `#mot`
filtrent les mémos comme chez le propriétaire. La question « une recherche est-elle en cours ? »
se pose partout par un seul prédicat (texte **ou** date), jamais par le texte seul.

## 1. État des lieux (mesuré dans le code, V28.8.275)

**Déjà là** : `parseSearchPrefix` (partial) reconnaît `p#`/`m#`/`l#` sur les 3 pages ;
`parseDatePrefix` (partial) sait lire `d#`/`c#`, mais l'analyse est **opt-in** (`opts.dates`) et
seul l'owner la demande. Sans ce drapeau, `d#2026-09` reste le **texte** « d#2026-09 » → aucun mémo.

**Ce qui manque, page par page :**

| Où | Aujourd'hui | À faire |
|---|---|---|
| `share.html` `shareSearch()` (~l.2431) | `parseSearchPrefix(raw, scope)` | ajouter `{ dates: true }` |
| `hub.html` `hubSearch()` (~l.861) | idem | idem |
| `share.html` `scopedMemos()` (~l.2441) | filtre texte = titre + contenu + assignés | + filtre de date, + sous-tâches, + `#mot` |
| `hub.html` `hubMemoFilter()` (~l.871) | idem | idem |
| `memoInDateRange` | vit dans `index.html` (~l.5523), dépend de `dateStr` (owner) | **monter dans le partial** (voir § 2.2) |
| Aide + feuille (`attachSearchUI`, 2 pages) | lignes `p#`, `m#`, `éÉ` ; pas de `dates` | lignes `d#`, `c#`, `#…` ; `dates: true` |
| Chip de date | owner seulement (`#search-date-chip`, `renderSearchDateChip`) | même chip sur share + hub |

**Les tests « texte seul » à remplacer** — chacun dirait « pas de recherche » devant un `d#2026-11`
sans mot, exactement le piège déjà payé trois fois (share, board owner, feuille mobile).
Inventaire **complet**, re-grepé sur V28.8.275 (`f685d83`) le 30 sept. : **10 points de décision**.

| # | Fichier:ligne | Code | Rôle |
|---|---|---|---|
| S1 | `share.html:2440` | `!!shareSearch().q` | `shareSearchScoped()` — chip « dans : » |
| S2 | `share.html:2445` | `!(q && shareSearchWide)` | `scopedMemos()` — borne au dossier |
| S3 | `share.html:2449` | `if (!q) return ms` | `scopedMemos()` — « pas de recherche » |
| S4 | `share.html:4041` | `if (!shareSearch().q) shareSearchWide = false` | `shareRefreshSearch()` |
| S5 | `share.html:4073` | `if (!q) return []` | feuille mobile `results` |
| H1 | `hub.html:873` | `if (!q) return ms` | `hubMemoFilter()` |
| H2 | `hub.html:884` | `!!hubSearch().q` | `hubSearchScoped()` |
| H3 | `hub.html:888` | `!!hubSearch().q && hubSearchWide` | `focusedMemos()` |
| H4 | `hub.html:2646` | `if (!hubSearch().q) hubSearchWide = false` | `hubRefreshSearch()` |
| H5 | `hub.html:2685` | `if (!q) return []` | feuille mobile `results` |

**Écartés, à juste titre** (le grep les attrape aussi) : `share.html:2433` et `hub.html:863`
(`share/hubMatchingProjects` : trouver un DOSSIER exige un nom, le texte seul y est la bonne
question) ; `share.html:2098` et `hub.html:2241` (le `q` y est l'instance Quill de l'éditeur).
`shareSearchRaw()` / `hubSearchRaw()` ne servent qu'aux définitions et à `getQuery`.

La carte (`shareMapPoints`), la frise/agenda (`shareDatedPoints`), les tuiles (`renderTiles`) et
`visibleShareMemos` passent déjà **tous** par `scopedMemos()` ; côté hub, board et agenda passent
par `focusedMemos()`. Filtrer à ces deux endroits suffit donc : jamais un point de carte sans sa
card (même exigence que [SEARCH-IN-FOLDER]).

## 2. Décisions proposées

1. **Un prédicat partagé** dans le partial : `searchIsActive(parsed)` →
   `!!(parsed && (parsed.q || parsed.date))`. Chaque page s'en sert : `shareSearchActive()`,
   `hubSearchActive()` ; l'owner garde `searchActiveNow()`, dont le corps devient
   `searchIsActive(parseSearch())` (comportement identique, un seul endroit décide). **Tous** les
   tests de la liste § 1 passent par lui. Règle pour la suite : aucun `.q` seul ne décide si l'on
   cherche.
2. **`memoInDateRange(m, date)` monte dans le partial** (ADR-001 : pur, sans état). Le corps actuel
   dépend de `dateStr` (propre à `index.html`) : on le remplace par un jour local calculé dans la
   fonction (`getFullYear/getMonth/getDate` + `padStart`), strictement équivalent. L'owner supprime
   sa copie et appelle celle du partial : une seule définition, déjà couverte par
   `test_search_dates.py` (non-régression owner). ⚠ Grep le nom avant (piège [SEARCH-ALL] : une
   2e déclaration `function` écrase la 1re sans erreur).
3. **Filtre des mémos invités** (même ordre que `visibleMemos` owner) : date d'abord (si `date`,
   `memoInDateRange`), puis texte s'il reste des mots. Champs du texte : titre, contenu (sans HTML),
   assignés, **sous-tâches** (`m.subtasks[].content`, déjà exposé par `_share_memo_dict`).
   `p#` garde son sens (mémos des dossiers trouvés) ; les dates n'existent pas pour `p#`/`l#`
   (déjà garanti par `parseSearchPrefix`).
4. **`#mot`** = le `#mot` **écrit dans le contenu d'un mémo** (comme l'owner : le titre n'est pas lu), match exact avec borne de fin,
   plié des deux côtés, **même règle que l'owner** : `#note` ne trouve pas `#notes`. Le test de
   l'owner est une regex en ligne dans `visibleMemos` ; on l'extrait dans le partial
   (`memoHasHashtag(m, tag)`) et l'owner l'appelle aussi.
   **Tranché par Fabien le 30 sept. : V1 SANS étiquettes de dossier.** Côté invité, `#mot` =
   uniquement le `#mot` écrit dans un mémo. Chez l'owner, `#japon` ramène aussi les mémos des
   dossiers **étiquetés** `japon` ; côté invité c'est impossible en front pur, car ni `share_data` ni
   `hub_data` n'exposent `tags` sur les dossiers (mesuré). Exposer ou non les étiquettes aux invités
   est une décision de consentement : elle relève de **[SHARE-SCOPE-SHEET]** (IDEAS.md, écran « Ce
   que je partage » au moment du partage, interrupteurs par facette et par partage, lus côté
   serveur), **pas** de ce lot ni d'une graine séparée.
5. **Chip de date** : `renderSearchDateChip` passe dans le partial en helper **sans état**,
   `renderDateChip(chipEl, date, onClear)` (libellé « 📅 échéance : » / « 🕓 créés : », ✕ qui
   retire le préfixe). L'owner l'adopte, avec un rendu identique et vérifié par
   `test_search_dates.py`. Share et hub ajoutent un `<span id="search-date-chip" hidden>` à côté
   de leur champ, stylé par les **mêmes règles CSS que l'owner**, recopiées (le CSS reste par page,
   ADR-001).
6. **Aide et feuille** : lignes `d#` (« Par **échéance** — *d#2026-11*, *d#semaine* »), `c#`
   (« Par date de **création** — *c#2026-09* »), `#…` (« Un **#mot** écrit dans un mémo — *#resa* »),
   `dates: true` dans les deux `attachSearchUI`. Placeholder : « Rechercher… (p# dossiers, d# dates) ».
7. **Noms : état au 30 sept. (grep des 4 templates, piège de la double déclaration)** —
   `memoInDateRange` existe **une fois**, `index.html:5552` (appelée l.5567) : on la **déplace**, on
   ne la redéclare pas. `renderSearchDateChip` existe dans `index.html:10685` (appelée l.9663 et
   l.11026) : elle **devient** un appel à `renderDateChip`. `searchActiveNow` existe dans
   `index.html:3210` (5 appelants) : elle garde son nom et appelle `searchIsActive`. **Aucune**
   occurrence de `memoHasHashtag`, `renderDateChip`, `searchIsActive`, `shareSearchActive`,
   `hubSearchActive` dans les 4 templates. ⚠ `dateStr` est un nom **owner** (`index.html`) : le
   jour local du partial doit s'appeler autrement (ex. `localIsoDay`), sinon la déclaration du
   partial écraserait l'owner. La regex `#tag` à extraire est `index.html:5585`.
8. **Invariant 5** : aucune donnée nouvelle ; on filtre ce que `share_data` / `hub/data` renvoient
   déjà (bornés au jeton). Zéro route. Le fuseau est celui du navigateur de l'invité (c'est « son »
   aujourd'hui).

## 3. Ce qui NE bouge PAS

Grammaire et comportement owner (hors factorisation à l'identique), `parseSearchPrefix`,
`parseDatePrefix`, le chip « dans : dossier » et `shareSearchWide`/`hubSearchWide` (sauf leur
remise à zéro, qui passe par le nouveau prédicat), la vue Résultats owner [SEARCH-ALL] (owner
seulement), `app.py`, export 28.

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_guest_search_grammar.py`. Contexte `timezone_id: "Europe/Paris"` (comme
`test_search_dates.py`). Décor dans un dossier partagé : « GSG kyoto » dû du 3 au 6 nov. 2026
(`due_end`), « GSG août » dû le 10 août, « GSG tardif » **créé** le 30/09 à 22 h 30 Z (posé en
base comme `test_search_dates`), « GSG courses » avec la sous-tâche « acheter du wasabi », « GSG
resa » dont le contenu porte `#resa` et « GSG resas » qui porte `#resas`. **Le décor est supprimé
en sortie** (fixture, cf. `test_search_all.py`).

Share (invité approuvé) **et** hub (même décor, via une session hub) :

1. `d#2026-11` → uniquement « GSG kyoto » ; `d#2026-11-05` → kyoto (jour **à l'intérieur** de la
   plage) ; le chip « 📅 échéance : » est visible, son ✕ retire le filtre.
2. `c#2026-10` → « GSG tardif » y est (jour local = 1er oct.), « GSG août » n'y est pas.
3. `d#2026-11 kyoto` → kyoto ; `d#2026-11 août` → rien ; `d#nimporte` → pas de chip, recherche
   texte (0 résultat).
4. `wasabi` → « GSG courses » (sous-tâche) ; `m#wasabi` → idem.
5. `#resa` → « GSG resa » seul (pas « GSG resas »).
6. **Le prédicat, pas le texte** : dans un sous-dossier, `d#2026-11` est **borné** au dossier (chip
   « dans : » allumé) ; ✕ du chip → élargi ; la **carte et l'agenda** montrent les mêmes mémos que
   la liste ; la **feuille mobile** (412 px) donne les mêmes résultats que le board.
7. Aide desktop : lignes `d#`, `c#`, `#…` présentes (share et hub).
8. Owner, non-régression : `test_search_dates.py` et `test_search_fold.py` restent verts sans
   modification (factorisation de `memoInDateRange`, `memoHasHashtag`, `renderDateChip`,
   `searchIsActive`).
9. Zéro erreur console partout.
10. **Le bug d'origine, rouge-avant** (`docs/tests/test-page-invite.md` § 3) : sur share **et** sur
    hub, un mémo dû le 15 sept. 2026 ; `d#2026-09` → ce mémo est listé (aujourd'hui : « Aucun »,
    parce que `d#2026-09` est cherché comme TEXTE). Doit être rouge sur V28.8.275, vert après.
11. **L'aide invitée reste invitée** : sur share et hub, ni le panneau d'aide desktop ni la feuille
    mobile ne mentionnent `l#` (les liens sont owner-only) ni la vue « Résultats » ([SEARCH-ALL],
    owner-only). Garde-fou : vert avant comme après, il interdit de recopier l'aide owner telle quelle.

Mutations à poser puis tuer : (a) `dates: true` retiré côté share (1 rougit) ; (b) un des tests
`.q` remis à la place du prédicat — `shareSearchScoped` (6) et `hubRefreshSearch` (6, chip jamais
remis à zéro) ; (c) sous-tâches retirées du texte (4) ; (d) borne de fin du `#mot` retirée (5) ;
(e) jour UTC au lieu du jour local dans `memoInDateRange` (2) ; (f) feuille qui garde
`if (!q) return []` (6, feuille vide sur `d#`) ; (g) ligne d'aide `l#` ajoutée côté invité (11).

## 5. Livraison

`templates/share.html`, `templates/hub.html`, `templates/partials/_shared.js.html`,
`templates/index.html` (factorisation seulement), `tests/front/test_guest_search_grammar.py`,
`REALISATION.md` `[V28.11.278]`, `IDEAS.md` (retirer [GUEST-SEARCH-GRAMMAR] de la file ; **pas** de
nouvelle graine : les étiquettes de dossier côté invité relèvent de [SHARE-SCOPE-SHEET], § 2.4), ce
brief. **Squelette de tests déjà posé** (30 sept.) : `tests/front/test_guest_search_grammar.py`,
décor + 11 scénarios **marqués skip** (« GSG — code à venir ») ; la séance commence par retirer les
skips et les voir rouges. Cycle : tests rouges → code → rebuild LOCAL → `make test` → journal + handoff → **STOP**.
Passe Cowork (share + hub, desktop + mobile), puis GO.
