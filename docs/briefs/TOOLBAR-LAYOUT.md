# Brief CC — [TOOLBAR-LAYOUT] : UNE barre d'actions, une ligne de tri qui tient, des tuiles sans « 0 »

> **Front pur (`index.html` + `_shared.js`), `app.py` quasi intact (un seul réglage serveur de plus
> en § 5, via `/api/settings` existant), export 28 inchangé.** Doctrine TDD. Cible **V29.1.280** (était V28.12.279 ; [MEMO-URLS] a pris le bump v29).
> Lot de **polish desktop** issu de la comparaison de deux captures prod du 4 oct. 2026 (dark Chrome
> ~2000 px, light Opera 1920 px) sur le dossier 🍎 Mac. Arbitrages Fabien du 4 oct. 12:27.

## 0. Contexte — à relire quand on y revient (pourquoi ce lot existe)

Deux captures du **même dossier** à deux largeurs, et l'en-tête du board ne raconte pas la même chose :

| Capture | Barres d'actions | « Tri » | Tuiles | Horloge Tokyo |
|---|---|---|---|---|
| dark, Chrome | **empilées** (Modifier…Votes au-dessus, Mémo/Fichier/Vocal/Dossier dessous, plus étroite, calée à gauche) → ~170 px de haut avant les tuiles, bord droit en escalier | inline avec les boutons | `0` partout sauf « En cours 1 » (recherche active) | absente |
| light, Opera | côte à côte mais **écartées aux deux bords**, trou au milieu, icônes seules (pref `hdrToolbarCompact` de CET appareil) | sur sa **propre ligne** ; tri actif invisible en thème clair | `0` sur 4 tuiles, « Historique 21 » | présente |

Ce qui est en cause, dans le code :
- `renderBoard()` (~l.9860-9890) construit **deux** `hdrToolbar()` — `tb` (actions du dossier) et `td` (le « dock » Mémo/Fichier/Vocal/Dossier, `[TOOLS-DOCK]`) — posés dans une rangée `space-between; flex-wrap:wrap`. Quand la colonne du board est étroite (~880 px en dark ici, le board est centré), ça wrappe → empilement ; quand ça tient, `space-between` les éjecte aux deux bords. Chacune a **sa** bascule « ‹ › » → deux cadres, deux bascules, c'est ce que Fabien ne supporte plus : « j'en ai marre qu'il y ait deux colonnes de lots de boutons, ça prend de la place ».
- `hdrBtn({menu:true})` (`_shared.js` ~l.7760) colle une **vignette chevron « ⌄ »** en bas-droite du bouton (`.hdr-menu`, 16 px, box-shadow) : elle déborde du cadre et Fabien la trouve « vraiment pas des plus agréable ».
- `#memo-sort-bar` (~l.10180) = `cover-disp` : label « Tri » + `memoSortSeg()` + bascule Immersif/Compact, en flex **wrap** → le label se retrouve seul sur une ligne dès que ça serre. `.cover-seg button.on` = `background:var(--panel-2); color:var(--accent)` : sur thème clair, panel-2 ≈ panel → l'actif ne se voit pas.
- `#memo-date-help` (~l.10190) : texte **figé** `'Dates : d#2026-11 · d#2026-11-03..2026-11-09 · d#semaine · c#2026-09 (créés)'`, même style que la ligne de tri (`cover-disp-lbl`), collé à « SANS DATE » sans marge.
- Tuiles (`#memo-filters`, ~l.9979-10010) : `mf-count` affiche `String(counts[key])` → des `0` partout. Les `counts` sont calculés sur `allMemos` = `visibleMemos().filter(boardScopeFilter())`, donc **déjà filtrés par la recherche** : en recherche « clavier », « En cours 1 » = 1 mémo trouvé, pas 1 mémo dans le dossier. C'est le comportement voulu (les tuiles suivent la recherche) ; seul le `0` est du bruit.
- Horloge secondaire : `extraTZ` est en **localStorage** (`tz-select`, ~l.11814) → réglage **par navigateur**, d'où Tokyo sur Opera et pas sur Chrome.

**Hors lot, acté par Fabien** : les flottants ✏️ / ¥€ qui chevauchent la sidebar (« pas un problème pour moi ») ; le champ « + Titre du nouveau mémo… » n'apparaît que quand « Mémo » du dock est allumé (« me semble normal »).

## 1. Décisions

### 1.1 UNE seule barre d'actions (fusion `tb` + dock)
- `renderBoard()` ne crée plus qu'**un** `hdrToolbar()` : les actions du dossier (Modifier, Partager, Photos, Fichiers, [Télécharger], Agenda, Carte, Votes…), **puis `tb.sep()`**, puis les quatre bascules du dock (Mémo, Fichier, Vocal, Dossier — inchangées dans leur comportement : `toolsDockState`, `.on`, `aria-pressed`, focus titre). Une seule bordure, **une seule bascule « ‹ › »**, une seule pref `hdrToolbarCompact` (déjà globale).
- La barre prend **toute la largeur du board** (`width:100%` au lieu de `fit-content` quand elle contient le dock ; classe `hdr-toolbar.wide`) et **ne wrappe jamais** : `overflow-x:auto` déjà en place, + ombres de défilement latérales (`mask-image` linéaire ou pseudo-éléments) pour signaler qu'il y a des boutons cachés. Le dock reste **à droite** dans la barre (`margin-left:auto` sur le 1er bouton après le `sep`) tant que tout tient ; si ça déborde, tout défile dans le même cadre — plus jamais deux hauteurs.
- Hauteur : mode étendu 56 px de bouton (inchangé), compact 44 px. La rangée perd le `margin-bottom:0.8rem` en double.
- Mode « nu » (`< 2` boutons, `bare`) : inchangé pour les cas Tous les mémos / Inbox (pas de dock).

### 1.2 Plus de chevron « ⌄ »
- `hdrBtn({menu:true})` **n'ajoute plus** `.hdr-menu`. Indicateur de menu = le **libellé** prend un « ▾ » fin en suffixe (`Votes ▾`), rien hors du cadre du bouton ; en compact (libellé masqué), **aucun** indicateur — le `title` suffit, c'est un bouton comme les autres. CSS `.hdr-menu` supprimé (pas de code mort).
- Vérifier les deux appelants `menu:true` (Votes, et l'éventuel « Plus ») : grep `menu: true` dans `index.html`.

### 1.3 Ligne « Tri » — solution retenue : A (+ B en graine)
Trois options vues avec Fabien :
- **A — segment auto-porteur, pas de label, jamais de wrap** *(retenue)* : on retire le `<span>Tri</span>` ; `#memo-sort-seg` reçoit `aria-label="Tri des mémos"` et un `title`. `#memo-sort-bar` passe en `flex-wrap:nowrap; overflow-x:auto; gap:0.6rem` (segment à gauche, bascule Immersif/Compact à droite via `margin-left:auto`). Sous 480 px le segment défile, il ne casse pas.
- **B — un `<select>` « Tri : Plus récents ▾ »** : plus compact, mais une interaction de plus pour changer de tri, et perd la lecture d'un coup d'œil. **Graine** si A ne tient pas sur mobile.
- **C — tri dans la barre d'actions** (un bouton « Tri ▾ » à côté du dock) : rejeté, mélange affichage et actions, et c'est le bouton à menu qu'on vient de dépouiller.
- **État actif lisible en clair ET en sombre** : `.cover-seg button.on{background:var(--accent);color:var(--accent-ink,#10141a);font-weight:600}` (même encre que `.hdr-count`). Même règle pour la bascule Immersif/Compact qui partage `cover-seg`.

### 1.4 Aide des dates — discrète, espacée, **mois courant**
- Texte **calculé** à chaque rendu : `d#<YYYY-MM courant> · d#<lundi>..<dimanche> de la semaine courante · d#semaine · c#<YYYY-MM courant> (créés)` (helper pur `dateHelpLine(now)` dans `index.html`, testable ; lundi via `getDay()` avec dimanche=7, dates locales, pas UTC).
- Style propre `#memo-date-help{font-size:0.7rem;color:var(--muted);opacity:0.75;margin:0.35rem 0 0.9rem}` — plus la classe `cover-disp` (qui lui donnait le gabarit de la ligne de tri). Préfixe « Dates : » conservé. Toujours affichée (Fabien n'a pas demandé de la cacher), juste discrète.

### 1.5 Tuiles : pas de « 0 »
- `mf-count` n'est **ajouté que si `counts[key] > 0`** ; sinon la tuile n'a que son icône et son libellé (le `mf-top` garde sa hauteur : `min-height` sur `.mf-top` pour que les six tuiles restent alignées). Pas de « 1 / 21 », pas de changement du calcul : les compteurs **continuent de suivre la recherche** — on documente juste ça dans le commentaire au-dessus de `counts`.
- Même règle côté share/hub **si** les tuiles y existent avec un `0` (CC vérifie ; sinon rien).

### 1.6 Horloge secondaire sur tous les appareils
- `extraTZ` devient un **réglage serveur** : clé `extra_tz` dans `/api/settings` (GET/PUT existants, ~l.7040 `app.py`), lue au boot et appliquée ; `localStorage.extraTZ` sert de **cache** et de repli hors-ligne (PWA). Au premier chargement après déploiement : si le serveur n'a rien et que le localStorage a une valeur → on la **pousse** au serveur une fois (migration douce, pas de perte du réglage Opera).
- Le `tz-select` de Paramètres écrit les deux. Pas de nouvelle route, pas de colonne : `settings` est un sac clé/valeur (CC confirme en lisant `get_settings`/`put_settings`). Si ce n'est PAS un sac clé/valeur mais des colonnes fixes → **STOP**, on en parle (ce serait alors une graine [SETTINGS-SYNC]).

## 2. Tests (TDD — rouges d'abord)

`tests/front/test_toolbar_layout.py` (dossier avec ≥ 1 mémo à photo pour avoir la bascule Immersif, 1 scrutin pour « Votes », viewport 1280×800 puis 900×800 puis 412×900) :
1. **Une seule** `.hdr-toolbar` dans `#memo-board` quand un dossier est ouvert ; elle contient à la fois `[title^="Modifier ce projet"]` et `[title^="Afficher/masquer la barre de création"]` ; **un seul** `.hdr-toggle`. Sur Tous les mémos / Inbox : 0 ou 1 barre `bare`, pas de dock.
2. À 900 px : `getBoundingClientRect().height` de la barre ≤ 72 px (étendu) — elle ne s'est pas empilée ; `scrollWidth > clientWidth` autorisé.
3. Aucun `.hdr-menu` dans le DOM ; le bouton Votes a un libellé se terminant par « ▾ » en mode étendu, et en compact (clic sur `.hdr-toggle`) aucun caractère « ⌄ »/« ▾ » visible.
4. `#memo-sort-bar` : pas de texte « Tri » ; `#memo-sort-seg[aria-label]` ; à 412 px la barre fait **une** ligne (height ≤ 40 px). Le bouton `.on` a un `background-color` ≠ celui de ses voisins **dans les deux thèmes** (basculer `data-theme`/classe du `<html>` comme le fait le bouton 🌙).
5. `#memo-date-help` : contient `d#` + mois courant (`YYYY-MM` de la date de la page, `page.evaluate(() => new Date())`), ne contient **pas** `2026-11` (sauf si on est en novembre 2026 — comparer à la date injectée, pas à une constante) ; `getComputedStyle` → `font-size` < celui de `#memo-sort-seg button`.
6. Tuiles : dossier sans mémo en retard → `.f-overdue .mf-count` absent ; « En cours » → présent avec le bon nombre. Recherche active qui ne matche rien → aucune `.mf-count` sauf si une tuile a > 0.
7. Horloge : PUT `/api/settings {extra_tz:'Asia/Tokyo'}` via `page.request`, recharger dans un **nouveau contexte** (localStorage vierge) → `#clock-extra` (ou l'id existant) affiche « Tokyo ». Migration : contexte avec `localStorage.extraTZ='Europe/London'` et serveur vide → après boot, GET `/api/settings` renvoie `extra_tz:'Europe/London'`.
8. Zéro erreur console sur les 3 viewports.

Mutations à poser puis tuer : (a) remettre le 2ᵉ `hdrToolbar()` → 1 rougit ; (b) remettre `flex-wrap:wrap` sur `#memo-sort-bar` → 4 rougit ; (c) remettre le texte figé `2026-11` → 5 rougit ; (d) `String(counts[key])` inconditionnel → 6 rougit ; (e) ne pas pousser le localStorage au serveur → 7 rougit.

Non-régression : `test_tools_dock*`, `test_header_toolbar*`, `test_memo_sort_dates.py`, `test_card_cover*` restent verts (adapter les sélecteurs qui comptaient **deux** barres, sans affaiblir l'assertion).

## 3. Livraison

- `make test` vert (≥ 501 + nouveaux), mutations consignées dans le message de commit.
- `REALISATION.md` : `[V29.1.280] feat(board) : **[TOOLBAR-LAYOUT] une seule barre d'actions…**` avec le détail des 6 points et le tableau du § 0 en une phrase.
- IDEAS.md : retirer de la file ; graine **[SORT-SELECT]** (option B) si A gêne sur mobile.
- Rebuild local complet (BUILD_VERSION), **STOP** avant tout push : passe Cowork desktop (1280 / 900) **puis mobile** (Fabien bascule l'émulation), thème clair ET sombre, puis GO de Fabien.
