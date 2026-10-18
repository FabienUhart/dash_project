# Brief CC — [EDITOR-SLASH] + [EDITOR-AUTOLIST] : l'éditeur avale les « / » et « 1. » transforme tout en liste

> **Front pur, 3 pages (`index.html`, `share.html`, `hub.html`, helper dans `_shared.js`), zéro route,
> export 29 inchangé.** Cible **V29.2.281**. Doctrine TDD. Source : mémo prod 409 (dossier Dash, 18 oct.
> 2026, constaté en saisissant le mémo [DASH-MCP] au clavier sur v29.1.280). Deux bugs P1 qui touchent
> **tout mémo saisi au clavier** contenant une date, un chemin, une URL ou des sections numérotées.
> À corriger **avant** le chantier API/MCP.

## 0. Contexte — à relire

- **Bug 1 · [EDITOR-SLASH]** — `index.html` ~l.11140 :
  ```js
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault(); searchInput.focus();
  ```
  Le raccourci « / » (focus recherche) teste le `tagName` mais pas `isContentEditable` : dans le
  `.ql-editor` de Quill (un `div contenteditable`), chaque « / » est **avalé** et le focus saute dans la
  recherche. « 18/10/2026 » → « 18102026 », `/api/v1/openapi.json` → `apiv1openapi.json`. Le titre
  (`<input>`) n'est pas touché. Il existe déjà le bon prédicat dans `uiBusy()` (~l.5943 : INPUT,
  TEXTAREA, `isContentEditable`) — il n'est pas utilisé ici. Share/hub n'ont pas ce raccourci
  (vérifié au grep), mais le prédicat doit vivre dans le partial pour les futurs raccourcis à une touche
  ([KEYS-1-9], « ? » de [SHORTCUT-HELP]).
- **Bug 2 · [EDITOR-AUTOLIST]** — Quill 2 a un binding clavier par défaut **`list autofill`** : en
  début de ligne, « 1. » / « 1) » / « - » / « * » / « [ ] » suivi d'un **espace** convertit la ligne en
  liste ; Entrée **continue** la liste. Un mémo rédigé en sections « 1. LE PRINCIPE », « 2. … » devient
  une seule liste ordonnée où chaque paragraphe est un item. `applyTableBetter` pose
  `modules.keyboard = { bindings: QuillTableBetter.keyboardBindings }` sur les 3 pages : c'est là qu'on
  règle les bindings, en un seul endroit.
- Contournement constaté : `Quill.find(container).setText(texte, 'user')` depuis la console → le
  stockage est sain, le problème est **uniquement à la saisie**.

## 1. Décisions

### 1.1 Raccourcis à une touche : un seul prédicat partagé
- Helper pur dans `_shared.js.html` : `function inTextEntry(el = document.activeElement)` → vrai si
  `el` est INPUT / TEXTAREA / SELECT, `el.isContentEditable`, ou descendant de `.ql-editor`, ou si un
  `dialog[open]` est présent (un raccourci ne doit jamais tirer sous une pop-in — c'est aussi le cas
  « éditeur ouvert mais focus sur un bouton »).
- Le handler « / » de `index.html` devient `if (e.key === '/' && !inTextEntry()) {…}` ; `uiBusy()`
  réutilise `inTextEntry()` pour sa partie focus. Aucun autre comportement ne change : « / » hors
  zone de saisie ouvre toujours la recherche.

### 1.2 Autofill de liste : garder les puces, retirer les numéros
Option retenue (entre « tout couper » et « tout garder ») : l'autofill reste pour `- `, `* ` et
`[ ] ` / `[x] ` (puces et cases à cocher, voulues quand on les tape), et **ne se déclenche plus pour
`1. ` / `1) `** — une section numérotée est un paragraphe, les listes ordonnées se créent par la
barre d'outils. Implémentation dans `applyTableBetter` (3 pages d'un coup) : surcharger le binding
`'list autofill'` de Quill par une copie dont la regex **exclut** le motif numérique
(`/^\s*?(\[\s?\]|\[x\]|-|\*|•)$/`), `format: { 'code-block': false, blockquote: false, table: false }`
conservé. Pas de nouvelle lib (invariant 6). Les listes ordonnées existantes se rendent et s'éditent
comme avant (Entrée continue, Entrée sur item vide sort — comportement Quill inchangé).

## 2. Tests (TDD — rouges d'abord)

`tests/front/test_editor_slash.py` (owner + share éditeur + hub, saisie **clavier réelle**
`page.keyboard.type`, jamais `setText`) :
1. Owner, éditeur ouvert, taper `a/b 18/10/2026 http://x.y/z` dans le contenu → les **4** « / » sont
   dans `quill.getText()` et dans le mémo sauvegardé ; le champ recherche est **vide** et n'a pas le focus.
2. Owner, éditeur fermé, focus sur le body → « / » donne le focus à la recherche (non-régression).
3. Owner, éditeur ouvert, focus sur un bouton de la pop-in (Tab) → « / » ne touche pas la recherche.
4. Share (invité `can_edit`) et hub : même saisie que 1 → 4 « / » conservés (il n'y a pas de raccourci,
   le test fige qu'il n'en apparaîtra pas sans garde).
5. Taper `1. Titre` Entrée `texte` Entrée `2. Suite` → 3 paragraphes `<p>`, **aucun** `<ol>` ; même
   chose avec `1) `.
6. Taper `- un` Entrée `deux` → `<ul>` de 2 items (puces conservées) ; `[ ] tâche` → liste `check`.
7. Bouton « liste ordonnée » de la barre → `<ol>` fonctionne toujours.
8. Zéro erreur console, 3 pages.
Mutations : (a) `isContentEditable` retiré du prédicat → 1 rougit ; (b) `dialog[open]` retiré → 3 ;
(c) binding autofill d'origine remis → 5 ; (d) regex sans `-` → 6.
Non-régression : `test_editor_autolink*`, `test_mentions*`, `test_table_better*` (si existants) verts.

## 3. Livraison
`make test` vert, `REALISATION.md` `[V29.2.281] fix(éditeur) : **[EDITOR-SLASH] + [EDITOR-AUTOLIST]…**`,
IDEAS.md (graine [SHORTCUT-HELP]/[KEYS-1-9] : « passer par `inTextEntry()` »), rebuild local complet,
smoke clavier réel dans Chrome, handoff + ligne [CC] (TZ Paris), **STOP avant push** → passe Cowork
(owner + invité, desktop + mobile) → GO.
