# Brief CC — [SEARCH-ALL] : scope « Tout » = une vraie page de résultats au milieu

> **Front pur, owner desktop + mobile, zéro route, `app.py` intact, export 28 inchangé.** Demande
> Fabien du 29 sept. 2026 (« quand on cherche en Tout, je veux tous les liens et tous les mémos,
> dossiers, sous-dossiers, et le texte qui matche dans un mémo, au milieu »), maquette injectée
> dans localhost:8099 validée (« bien mieux »). Doctrine TDD. Cible **V28.8.275**.

## 0. Ce qui change, en une phrase

Quand la recherche est active avec le scope **Tout**, le milieu affiche une **vue Résultats** unique
(Liens · Dossiers · Mémos, avec pour chaque mémo l'endroit où le mot a matché), quelle que soit la
vue de départ ; effacer la recherche ramène à la vue précédente. Les scopes Liens / Mémos / Dossiers
gardent leur comportement (filtre de la vue en cours).

## 1. Constats (29 sept., V28.5.272)

- En desktop, « Tout » **filtre la vue courante** : depuis la vue Liens, « newss » (nom d'un dossier)
  donne « Aucun lien ne correspond » alors que 3 dossiers et 5 mémos matchent ; depuis « Tous les
  mémos », le board affiche déjà PROJETS (3) + mémos mais **pas les liens**.
- Un mémo trouvé via une sous-tâche (« New sous tache ») ou via son dossier ([SEARCH-FOLD]) ressemble
  à un faux positif : rien n'indique **où** ça a matché.
- Le moteur existe déjà : `ownerSearchResults(q, scope, date)` (~l.10640) sert la feuille mobile via
  `cfg.results` (`_shared.js` ~l.8070) et repasse par `matchingProjects`, `visibleMemos()`,
  `boardScopeFilter()`, `visibleLinks()` — donc **mêmes résultats que le board** (garantie à garder).

## 2. Décisions (fermes — maquette validée)

1. **Déclencheur** : `searchActiveNow()` **et** scope `all` (pas de préfixe l#/m#/p#/#tag) → `state.view =
   'search'` en mémorisant la vue précédente (`state.searchReturn = {view, memoProject}`), en desktop
   comme en mobile (en mobile la feuille reste ; à la fermeture de la feuille avec une recherche
   active, le milieu montre la vue Résultats). Effacer (✕, Échap, champ vidé) → restaure
   `searchReturn`. Un préfixe de scope pendant la saisie (`m#…`) → on quitte la vue Résultats vers la
   vue précédente filtrée, comme aujourd'hui. Le chip « dans : dossier » borne la vue Résultats au
   sous-arbre, comme le board.
2. **Contenu**, dans cet ordre, sections toujours présentes avec compteur (`.sec` + `<b>n</b>`) :
   - en-tête « 🔍 Résultats pour « q » » + résumé « n liens · n dossiers · n mémos » + bouton
     « Effacer la recherche · Échap » (Luciole, `prio-btn`) ;
   - **🔗 Liens** : ligne compacte (favicon `/api/favicon/<id>`, nom surligné, URL, catégorie),
     clic = ouvrir l'URL (comme la feuille). Vide → « Aucun lien ne contient « q ». » ;
   - **📁 Dossiers** : ligne (emoji/pastille, nom surligné, **chemin complet** « IDEE › newproject »
     avec le dernier segment en gras, « n mémos · ouvrir → »), clic = ouvrir le dossier
     (`state.memoProject = id`, vue memos). Inclut sous-dossiers à toute profondeur ;
   - **📝 Mémos** : la card compacte existante (`renderMemoCard` / factory du board, invariant 9) +
     sous la card une **ligne d'indice** `.sr-hit` quand le match n'est **pas** dans le titre :
     `☑ SOUS-TÂCHE …`, `¶ CONTENU …extrait…`, `💬 COMMENTAIRE …`, `📎 FICHIER nom`, `📁 DOSSIER dans le
     dossier X`. Extrait : 40 caractères avant, 70 après, `<mark>` sur le terme (accents ignorés
     comme le moteur). Titre qui matche → `<mark>` dans le titre, pas de ligne d'indice. Un seul
     indice par mémo, priorité titre > contenu > sous-tâche > commentaire > fichier > dossier.
3. **Moteur** : une fonction pure `searchHits(q)` dans `index.html` qui renvoie `{links, folders,
   memos:[{memo, where, snippet}]}` en réutilisant `matchingProjects`, `visibleMemos()+boardScopeFilter()`,
   `visibleLinks()`. `ownerSearchResults` (feuille mobile) **la consomme** pour que feuille et vue
   Résultats ne divergent jamais (même ordre, mêmes comptes). Le calcul de `where/snippet` vit dans
   `_shared.js` (`searchWhere(memo, q)`, ADR-001) pour être réutilisable côté share plus tard.
4. **Surlignage** : `<mark>` avec fond `rgba(accent, .22)`, jamais de HTML non échappé (le contenu
   est strippé puis échappé avant l'insertion du `<mark>`).
5. **Sidebar et colonne MÉMOS** : inchangées (elles continuent de filtrer).
6. **Hors périmètre** : share/hub, tri des résultats (ordre du moteur), pagination (si > 200 mémos,
   « n autres… » qui déplie), recherche dans les votes.

## 3. Ce qui NE bouge PAS

Grammaire (`p#/l#/m#/#tag/d#/c#`), `parseSearchPrefix`, `searchActiveNow`, `matchingProjects`,
[SEARCH-FOLD], board « Tous les mémos » et son bloc PROJETS quand le scope n'est pas Tout, feuille
mobile (même résultats), `app.py`, export 28.

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_search_all.py` (décor : dossier « newss » avec 2 mémos, sous-dossier
« IDEE/newproject » avec 1 mémo, mémo « Idées » avec sous-tâche « New sous tache », mémo dont seul le
contenu contient « new », 1 lien « Newsletter », 1 lien sans rapport).

1. Depuis la vue Liens, taper `new` → `state.view === 'search'`, en-tête « Résultats pour « new » »,
   sections Liens 1 / Dossiers 2 / Mémos 5 ; chemin « IDEE › newproject » affiché.
2. Le mémo « Idées » porte l'indice « SOUS-TÂCHE » avec `<mark>New</mark>` ; le mémo « contenu » porte
   « CONTENU » avec extrait ; les mémos de « newss » portent « DOSSIER dans le dossier newss » ; un
   mémo au titre matché n'a **pas** de ligne d'indice mais un `<mark>` dans le titre.
3. Échap → retour à la vue Liens (view + memoProject restaurés) ; idem via ✕.
4. Depuis « Tous les mémos » avec chip « dans : newss » → vue Résultats bornée (0 lien hors dossier,
   2 mémos, 0 dossier autre que newss).
5. `m#new` → pas de vue Résultats, board filtré (comportement actuel) ; `l#new` → vue Liens filtrée.
6. Clic sur « newproject » → vue memos du dossier ; clic sur une card mémo → éditeur ouvert.
7. Mobile 412 px : feuille ouverte, `new`, fermer la feuille → vue Résultats au milieu ; les comptes de
   la feuille et de la vue sont **identiques** (moteur partagé).
8. Zéro erreur console sur chaque test ; aucun `<script>`/HTML brut d'un contenu de mémo n'est rendu
   (mémo contenant `<b>new</b><img onerror>` → texte échappé).

Mutations à poser puis tuer : (a) `searchReturn` non restauré (3) ; (b) indice toujours « titre » (2) ;
(c) `ownerSearchResults` ne passant plus par `searchHits` (7 : comptes divergents) ; (d) extrait non
échappé (8) ; (e) chip dossier ignoré (4).

## 5. Livraison

`templates/index.html`, `templates/partials/_shared.js.html`, `tests/front/test_search_all.py`,
`REALISATION.md` `[V28.8.275]`, `IDEAS.md` (retirer [SEARCH-ALL] de la file), ce brief commité.
Cycle : tests rouges → code → rebuild LOCAL → `make test` → journal + handoff → **STOP**. Passe
Cowork desktop + mobile, puis GO.
