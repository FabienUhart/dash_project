# Brief CC — [SPLIT-SCROLL] : la colonne MÉMOS défile toute seule (desktop)

> **Frontend pur, `templates/index.html` seul** (l'aside `#memo-panel` n'existe qu'owner, vue Liens).
> Zéro route, zéro schéma, **export 27 inchangé**, `app.py` intact. Doctrine TDD (un e2e rouge → vert).
> Demande Fabien (6 sept. 2026) : « quand on scroll les Mémos à droite, ça fait scroller le milieu
> aussi ; je veux découper ces scrolls. »

## 0. Constat

- `nav#sidebar` (gauche) a déjà son propre défileur en desktop ≥ 901 px — lot [SIDEBAR-TREE] :
  `position:sticky; top:var(--header-h); height:calc(100dvh - var(--header-h)); overflow-y:auto;
  overscroll-behavior:contain; scrollbar-width:thin` (index.html ~l.747).
- `aside#memo-panel` (droite, ~l.1463) est un **bloc de page** sans hauteur ni overflow : c'est la
  **fenêtre** qui défile → la molette sur les mémos entraîne le board du milieu, et le board fait
  défiler les mémos. Le `<summary>` MÉMOS (sticky `top:var(--header-h)`, [MEMO-JUMP-BOTTOM]) et
  `#memo-quick-wrap` (sticky `bottom:0`) sont collants **par rapport à la fenêtre**.
- Le bouton ⤓/⤒ ([MEMO-JUMP-BOTTOM], ~l.9813) fait `window.scrollTo(scroller.scrollHeight)` en
  desktop et teste `window.innerHeight + scrollY ≥ scrollHeight` : il suppose que la page défile.

## 1. Le correctif

1. **CSS, dans le même `@media (min-width: 901px)` que la sidebar** : `aside#memo-panel` reçoit le
   **même gabarit** — `position:sticky; top:var(--header-h,57px); height:calc(100dvh - var(--header-h,57px));
   overflow-y:auto; overscroll-behavior:contain; scrollbar-width:thin; scrollbar-color` + les 3 règles
   `::-webkit-scrollbar` (copier celles de la sidebar, ou **factoriser** un sélecteur groupé
   `nav#sidebar, aside#memo-panel` — au choix, mais une seule source de vérité). Le `main` du milieu
   continue de défiler avec la fenêtre : c'est le découpage voulu. `overscroll-behavior:contain` est
   ce qui empêche la molette, arrivée en bout de colonne, de « déborder » sur la page.
2. **Les deux collants deviennent relatifs au nouveau défileur** : `#memo-details summary` passe à
   `top:0` (il est déjà sous le header puisque l'aside l'est) ; `#memo-quick-wrap` `bottom:0` reste
   valable (sticky par rapport à l'ancêtre défilant le plus proche = l'aside). Vérifier que le fond
   opaque `var(--panel)` couvre bien (padding de l'aside à compenser si un liseré transparaît, cf.
   leçon [DIALOG-STICKY-ACTIONS-DESKTOP]).
3. **[MEMO-JUMP-BOTTOM] desktop** : le défileur de référence devient **`#memo-panel`**, plus la
   fenêtre — `atBottom()` = `panel.scrollTop + panel.clientHeight ≥ panel.scrollHeight - 4`, le clic
   fait `panel.scrollTo({top: atBottom() ? 0 : panel.scrollHeight, behavior:'smooth'})`, et le
   listener de re-sync écoute le **`scroll` du panel** (en plus/à la place de `window`). La branche
   **mobile ≤ 900 px ([MEMO-JUMP-MOBILE]) ne bouge pas** : en empilé, l'aside redevient un bloc de page
   (le `@media` desktop ne s'applique pas), tout reste comme avant.
4. **Mobile ≤ 900 px : strictement inchangé** (aside pleine largeur, `<details>` repliable, summary
   remis en statique par la règle existante).

## 2. Ce qu'il ne faut PAS faire

- Pas de `height` sur `main` ni de scroll interne au board : le milieu garde le défilement de page
  (les en-têtes sticky du board, le dock, la vue Plan/Carte s'y appuient).
- Pas de JS pour « bloquer » la propagation de la molette : `overscroll-behavior:contain` suffit.
- Ne pas toucher `share.html`/`hub.html` (pas d'aside mémos).

## 3. Tests (TDD, e2e Playwright desktop ≥ 901 px)

1. `test_memo_panel_scrolls_independently` — **rouge avant** : owner, vue Liens, viewport 1400×800,
   assez de mémos pour dépasser la hauteur (fixture ou seed) ; `page.mouse.wheel(0, 2000)` la souris
   **au-dessus de `#memo-panel`** → `#memo-panel.scrollTop > 0` **ET** `window.scrollY == 0`.
   Aujourd'hui : `scrollTop` reste 0 et `scrollY` bouge → rouge. (⚠ `behavior:'smooth'` est un no-op
   dans le navigateur piloté — attendre un `scrollTop` stable, pas une animation.)
2. `test_board_scroll_does_not_move_memos` — molette au-dessus de `main` → `window.scrollY > 0` et
   `#memo-panel.scrollTop == 0`.
3. `test_memo_jump_targets_panel` — clic `#memo-jump-btn` → `#memo-panel.scrollTop` proche de
   `scrollHeight - clientHeight`, `window.scrollY == 0`, libellé bascule en ⤒ ; second clic → `scrollTop == 0`.
   (Le test existant de `test_smoke_front.py` l.160 sur `#memo-panel` reste vert.)
4. Non-régression **mobile** : viewport 420 px, `#memo-panel` n'a **pas** d'`overflow-y:auto` calculé
   (`getComputedStyle` → `visible`) et le ⤓ garde le comportement [MEMO-JUMP-MOBILE].
5. **Mutation** : retirer `overscroll-behavior:contain` → #1 doit rougir (la molette en bout de course
   fait bouger `scrollY`) ; si ce n'est pas mesurable en headless, le noter honnêtement plutôt qu'un
   test vert pour la mauvaise raison.
6. Zéro erreur console sur chaque parcours.

## 4. Definition of Done

`make test` vert ; tests #1-3 prouvés rouges avant ; REALISATION.md (`Z` = dernier + 1) ; IDEAS.md ;
rebuild local ; journal + handoff ; **STOP** (pas de commit/tag/push — passe Cowork puis GO Fabien).
Vérif à l'œil Fabien : molette sur les mémos → seuls les mémos bougent ; molette sur le board → seul
le board bouge ; sidebar inchangée ; ⤓/⤒ ; note rapide toujours collée en bas de la colonne.
