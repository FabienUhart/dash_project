# Brief CC — [MEMO-SORT-DATES] : trier les mémos (board + colonne) et chercher par date

> **Front pur, owner-only, zéro route, `app.py` intact, export 27 inchangé.** Demande Fabien du 25 sept. 2026,
> prototype validé dans localhost:8099 (« clairement j'aime la page mémos avec les boutons »). Doctrine TDD.
> Cible **V27.46.261**. Placé **n° 2 de la file**, derrière [LINK-SORT] (V27.45.260) — le livrer APRÈS,
> il en réutilise la doctrine (tri = vue, jamais d'écriture de `position`, D&D coupé hors Manuel).

## 0. Ce qui change, en deux phrases

Les mémos gagnent un tri — **Manuel · Plus récents · Modifiés · Échéance** — visible sur le **board** (rangée
« Tri » sur la ligne d'« Affichage ») et dans la **colonne MÉMOS** (bouton ⇅ dans l'en-tête → mini-menu), un
seul réglage pour les deux, mémorisé sur l'appareil. La barre de recherche comprend deux préfixes de date,
**`d#` (échéance)** et **`c#` (création)**, affichés en chip dans le champ et combinables avec du texte.

## 1. Décisions (fermes)

### Tri
1. **Un seul état** `state.memoSort ∈ {'manual','newest','updated','due'}`, défaut `'manual'` (= aujourd'hui,
   **rien ne bouge tant qu'on ne clique pas**). Persisté `localStorage['dash:memoSort']`, valeur inconnue →
   `'manual'`. **Board et colonne lisent le MÊME état** : cliquer sur le board change la colonne, et inversement.
2. **Clés** : `newest` = `created_at` DESC ; `updated` = `updated_at` DESC ; `due` = échéance ASC (date la plus
   proche d'abord — clé = `due_date`, puis `due_time` si présente, **mémos sans date EN BAS**, entre eux en ordre
   manuel) ; **départage systématique par `id`** (DESC pour newest/updated, ASC pour due). Le tri s'applique
   **après** les filtres (tuiles En cours / Aujourd'hui / … , dossier courant, recherche) et **dans chaque
   section** du board (À venir, En retard, …) : la fonction pure `sortMemos(memos, mode)` est appelée là où
   chaque liste est rendue (`renderMemos()` ~l.9558 pour la colonne, sections de `renderBoard()` ~l.8734),
   jamais sur `state.memos` en place. `manual` = ordre reçu de l'API (`position, id`), on ne re-trie pas.
3. **Le tri est une VUE, jamais une écriture** : pas d'appel à `/api/memos/reorder` (~l.9491), `position`
   intacte. Le **D&D de réordonnancement** (colonne ET board) est **coupé hors Manuel** ; le D&D vers la
   sidebar (déplacer dans un dossier, `dragMemoId` ~l.4973 / handler ~l.3453) **reste actif** dans tous les
   modes — changer de dossier n'est pas réordonner.
4. **Board** : rangée « Tri » **sur la ligne existante `.cover-disp`** (« Affichage : Immersif / Compact »),
   à gauche, `margin-right:auto` ; libellé `.cover-disp-lbl` « Tri » + un `.cover-seg` de 4 `.cover-seg-btn`
   (actif = classe `on`, `aria-pressed`) — **le composant existant, aucune classe nouvelle** (invariant 9).
   Mobile ≤ 900 px : la rangée passe à la ligne, libellés courts si ça déborde (Manuel · Récents · Modifiés ·
   Échéance tiennent ; sinon icônes trait + `title`).
5. **Colonne MÉMOS** : bouton `⇅` de classe `mini-add-btn` dans le `<summary>` (~l.2250), **entre ⤓ et ＋**,
   `title="Trier"`, `aria-haspopup`. Clic → mini-menu **du même gabarit que `#links-add-menu`** (`.card-menu`,
   4 entrées, coche ✓ devant l'entrée active). Quand le tri n'est pas Manuel, le bouton passe en état
   « matière » Luciole (bordure/texte accent) pour dire qu'un tri est actif — jamais d'aplat.
6. **Vues non touchées** : Plan, Agenda, Carte, frise voyage, vue tag, share/hub (invités : rien dans ce lot,
   parité en V2 si Fabien la demande). Ces vues ont leur propre ordre (dates, géographie).

### Recherche par date
7. **Deux préfixes**, dans la grammaire existante de `parseSearchPrefix` (partial, ~l.7471) :
   - **`d#`** = **échéance** : un mémo matche si sa plage `[due_date, due_end ou due_date]` **intersecte**
     l'intervalle demandé (un séjour 6→8 nov. sort pour `d#2026-11-07`).
   - **`c#`** = **création** : `created_at` (jour local Europe/Paris — comparer sur la date locale, pas l'ISO
     UTC brut) dans l'intervalle.
   - **Formes acceptées**, toutes → un intervalle `[from, to]` inclusif en `YYYY-MM-DD` :
     `2026-11-07` (jour) · `2026-11` (mois) · `2026` (année) · `2026-11-03..2026-11-09` (plage, `..`) ·
     `aujourd'hui`/`aujourdhui` · `demain` · `hier` · `semaine` (lundi→dimanche courants) · `mois` ·
     et le **format FR** `07/11/2026`, `11/2026`. Foldé via `searchFold` avant analyse (accents/majuscules
     indifférents). Forme non reconnue → **le préfixe est ignoré et le texte est cherché tel quel** (jamais
     de résultat vide silencieux : le chip n'apparaît pas, c'est le signal).
   - **Combinable** : `d#2026-11 kyoto` = intervalle **ET** mots (`searchMatch`) ; un seul préfixe de date
     par requête (le premier gagne). `d#`/`c#` **restent scopés** au dossier courant ([SEARCH-IN-FOLDER]) —
     pas dans `SEARCH_WIDE_SCOPES`. Ils s'appliquent aux **mémos seulement** : en scope Liens/Projets ils
     sont ignorés comme texte.
   - **Chip** : le préfixe reconnu devient un chip **dans le champ**, gabarit de `#search-chip` (~l.2184 /
     CSS l.176) : « 📅 échéance : nov. 2026 ✕ » ou « 🕓 créés : sept. 2026 ✕ » ; ✕ retire le préfixe du champ
     et garde le texte libre. Ligne d'aide sous les tuiles du board (même style que la ligne [SEARCH-FOLD]),
     non cliquable : « Dates : d#2026-11 · d#2026-11-03..2026-11-09 · d#semaine · c#2026-09 (créés) ».
     Le panneau d'aide `/` existant gagne ces deux lignes.
8. **Partial vs page (ADR-001)** : **l'analyse** (`parseDatePrefix(raw) → {kind:'due'|'created', from, to,
   rest, label}`, pure, et la reconnaissance dans `parseSearchPrefix`) vit dans **`_shared.js.html`** —
   définie une fois ; **l'application** aux mémos (`visibleMemos()` ~l.4879) et le chip restent dans
   `index.html` : share/hub ne câblent rien (ils reçoivent un `dateRange` qu'ils ignorent — une future
   parité ne redéfinira pas le parseur). Aucune fonction du partial ne touche `state`.

## 2. Ce qui NE bouge PAS

`GET /api/memos`, `/api/memos/reorder`, `p#`/`l#`/`m#`/`#tag`, `SEARCH_WIDE_SCOPES`, [SEARCH-IN-FOLDER],
[SEARCH-FOLD], « Entrée ouvre le premier lien », la feuille mobile, les tuiles de filtre, [SPLIT-SCROLL],
⤓/⤒, Plan/Agenda/Carte, share/hub, export 27.

## 3. Tests (TDD — rouges d'abord)

`tests/front/test_memo_sort.py` + `tests/front/test_search_dates.py` (e2e Playwright, décor : 6 mémos créés
par l'API dans un ordre connu, `due_date` variées dont une plage 6→8 nov. et deux sans date, `position`
inversée via `/api/memos/reorder` pour que Manuel ≠ Récents ; `updated_at` distinct par un PUT sur un ancien).

**Tri**
1. Défaut = manuel, identique à avant le lot (colonne ET board), sans localStorage.
2. Board « Plus récents » : ordre `created_at` DESC dans **chaque section** ; départage id.
3. « Modifiés » : le mémo ancien qu'on vient de PUT passe en tête.
4. « Échéance » : plus proche d'abord, plage classée par son **début**, **sans date en bas** (en ordre manuel
   entre eux).
5. **Synchronisation** : choisir « Échéance » sur le board → le mini-menu de la colonne montre ✓ Échéance et
   la colonne est triée ; l'inverse aussi. Une seule clé localStorage.
6. Survit au rechargement ; valeur corrompue → Manuel.
7. **Aucune écriture** : après tri, `GET /api/memos` renvoie les `position` d'origine, aucun POST
   `/api/memos/reorder` intercepté.
8. D&D de réordonnancement coupé hors Manuel (dragover synthétique ne déplace pas le nœud) ; **D&D vers un
   dossier de la sidebar toujours actif** en mode trié (le mémo change de dossier) — non-régression.
9. Filtre puis tri : tuile « En retard » + « Échéance » → seuls les en-retard, la plus ancienne échéance d'abord.

**Dates**
10. `d#2026-11` → tous les mémos dont la plage touche novembre, dont la plage 6→8 nov. ; `d#2026-11-07` →
    la plage 6→8 nov. sort (intersection), un mémo du 5 nov. ne sort pas.
11. `d#2026-11-03..2026-11-09`, `d#11/2026`, `d#07/11/2026`, `d#semaine`, `d#aujourd'hui` → intervalles
    attendus (figer la date via `page.clock` ou une horloge injectée — le test ne dépend pas du jour réel).
12. `c#2026-09` → seuls les mémos créés en sept. (créer un mémo avec `created_at` d'août par import v27).
13. `d#2026-11 kyoto` → intersection ET texte ; `d#nimporte` → chip absent, recherche texte « nimporte ».
14. Chip : présent avec le bon libellé, ✕ retire le préfixe et **garde** « kyoto » dans le champ.
15. **Scopé** : depuis Voyage Japon, `d#2026-11` ne sort que le sous-arbre, chip « dans : … » toujours là,
    « Chercher partout » élargit.
16. Zéro erreur console sur chaque parcours (fixture `console_errors`).

**Mutations à poser et tuer** (≥ 7) : départage id retiré (2) · sans-date en tête (4) · état non partagé
board/colonne (5) · tri sur `state.memos` en place (7 : l'ordre manuel est perdu au retour) · garde D&D retirée
(8) · intersection remplacée par « `due_date` dans l'intervalle » (10 : la plage 6→8 n'apparaît plus pour
`d#…-07`) · `created_at` comparé en UTC (12 : un mémo créé le 30 sept. 23h30 Paris bascule) · `d#` ajouté
à `SEARCH_WIDE_SCOPES` (15).

## 4. Livraison

- `templates/partials/_shared.js.html` (parseur pur), `templates/index.html`, 2 fichiers de tests.
- `REALISATION.md` : `[V27.46.261]` ; `IDEAS.md` : retirer [MEMO-SORT-DATES]. `docs/briefs/MEMO-SORT-DATES.md`
  commité avec le lot.
- Cycle : tests rouges → code → rebuild LOCAL → `make test` → journal + handoff → **STOP**. Passe Cowork
  (board, colonne, chip, D&D) puis GO Fabien avant tout commit/tag/push.
