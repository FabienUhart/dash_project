# PATTERNS & CONVENTIONS — dash_project

Conventions transverses. Le détail normatif vit dans `CLAUDE.md` (8 invariants) ; ici = rappels + pointeurs.

## Architecture

- `app.py` : monolithe Flask + SQLite, **sans ORM ni blueprint**. Petits helpers privés `_xxx()` réutilisés par les routes owner ET invité (ex. `_perform_memo_update` partagé par `/api/memos` et `/share/<t>/memo`). Backend déjà DRY.
- `templates/index.html` (owner) et `templates/share.html` (invité) : **un fichier par page, JS vanilla, pas de build**. Sortie HTML auto-contenue (CSS + JS inlinés).
- `templates/partials/_shared.js.html` : **helpers purs et identiques** owner/invité, inclus par `{% include %}` (ADR-001). Y vivent : `el` (double forme), `treeConnector`, `runMapDialog(cfg)`, `usableProjColor`, `provenanceColor`, `setTheme`, `stagger`, `announce`, `syncHeaderHeight`, mentions x4. **N'y mettre que du sans-état, identique aux deux pages.**

## Base de données & migrations

- Migrations **uniquement additives** dans `init_db()` (`ALTER TABLE` + backfill). **Jamais** dropper une colonne ou des données.
- `uid` (UUID) stable par lien/mémo, suit l'élément à travers export/import. Ne jamais le régénérer.
- **Suppression douce** : `deleted_at` (corbeille), jamais de `DELETE` SQL direct depuis l'UI. Purge auto après `BACKUP_KEEP_DAYS`.

## Export / import (critique)

- **Compat ascendante obligatoire** : `/api/import` accepte tous les exports v1->v19. Toute évolution **incrémente `version`** et reste importable.
- Import **non destructif** : ajoute / met à jour (uid + `updated_at` plus récent) / enrichit les champs vides. N'écrase jamais un champ rempli par une donnée plus ancienne.
- Champs additifs : absent à l'import = valeur par défaut (compat).

## Sécurité & partage

- **Pas d'auth dans l'app** (assurée par le reverse proxy). Exception : routes publiques `/share/<token>/...` (bypass Authelia), protégées par le jeton + PIN, **strictement scopées** à la ressource partagée (invariant 5). Écriture invité = invité approuvé (`X-Guest-Token`).
- Uploads d'images validés par **signature binaire** (`_save_uploaded_image`). Jamais d'upload sans cette vérif.

## Frontend

- **Réutiliser les classes existantes des cards, pas de styles bespoke** ([PHOTO-UI-CONSISTENCY]). Tout nouveau composant (boutons d'action, chips, pastilles) doit pointer sur les classes établies — boutons ronds = `.task-actions button` / `.iv-btn` (token `--border`, rayon 9px, hover `--text`/`--panel`/`--muted`), action principale en accent (`.iv-accent`/`.texp`/`.tedit` = `--accent`), danger = `.iv-del`/`.thumb-del` (`--red`) ; petits chips = `.prio-btn` (sélectionné = `--accent`/`#10141a`) ; pastilles texte = `.badge`. Une seule source de vérité du look, jamais de couleur/rayon/hover en dur inline. ⚠️ `share.html` n'a **pas** de `button {}` de base : toute classe utilisée côté invité (`.prio-btn`…) doit y être **autonome** (border/bg/color/hover explicites), sinon chips bruts.
- Dépendances **auto-hébergées dans `static/`** (Quill, GSAP, Leaflet, Leaflet.markercluster, favicon). Servies aux invités via `/share/assets/<nom>` (liste blanche). Pas de CDN runtime.
- **GSAP** : ne jamais animer un `<dialog>` lui-même (casse le top-layer Chromium). Entrée des pop-ins en CSS (`@keyframes`). GSAP n'anime que des éléments hors top-layer (invariant 8).
- Couches **non mutualisées** (encore dupliquées, par nature) : les deux `renderSidebar`, l'assemblage des vues/board, l'accès données (`state` owner vs `DATA` invité scopé), les endpoints d'écriture (`/api/...` vs `/share/...`).
- **Cohérence visuelle** (invariant 9 de `CLAUDE.md`) : réutiliser les classes des cards (`.task .task-actions button`, `.prio-btn`, `.mfilter`, `.badge`) + variables CSS, jamais de styles bespoke ni de couleurs en dur. Une seule source de vérité du look, owner et invité (composants du partial).
- ⚠️ **Leaflet dans un `<dialog>`** (gotcha « carte noire », vague v20) : ne JAMAIS ajouter de couches **vectorielles** (`circleMarker`, `polyline`, divIcon-markers) avant que la carte ait une **vue** (tuiles + `setView` d'abord, TOUJOURS — sans vue, le renderer SVG n'a pas ses `_pxBounds` → `reading 'intersects'`, setup interrompu, carte noire, instance orpheline « container is being reused »). Tout `.remove()`/`removeLayer()` de couche **gardé par `hasLayer`** (le remove d'une polyline jamais rendue jette `reading 'parentNode'`). Démontage en try/catch + purge du `_leaflet_id` du conteneur.
- ⚠️ **Cache après rebuild** : la page livrée est un HTML autonome inliné — après un `docker compose up -d --build`, un refresh normal peut resservir l'ANCIEN HTML depuis le cache navigateur. **Hard refresh (Cmd+Shift+R) obligatoire avant de juger un bug de rendu** (a produit un faux rapport ❌ complet sur la vague v20). Astuce : vérifier en console qu'un marqueur du nouveau code est présent dans `document.documentElement.innerHTML`.
- ⚠️ **Style inline vs média query** : un `style="display:flex"` inline bat toute règle de media query sans `!important` (cas `#map-row` → `display:contents !important`). Et dans un `<dialog>` en flex column, le `max-height` UA compresse le seul enfant compressible à 0×0 — protéger chaque enfant qui doit rester visible (`flex:0 0 auto` + `min-height`) et faire scroller le dialog.
- **Liste à cocher (`li[data-list]`)** : la case doit être dans le **même flux** que son texte (item flex : `display:flex` sur le `li`, case = `::before` `flex:0 0 auto`), **jamais** en `position:absolute` ni calée par une marge négative dépendant de l'indentation Quill — sinon le texte décroche au wrap et une ligne vide laisse une case orpheline (`:empty::before { display:none }`). CSS **dupliqué à l'identique** dans `index.html` ET `share.html` (parité owner/invité).

## Tester avant de committer (voir CLAUDE.md)

- `python3 -m py_compile app.py`.
- Lancer sur une **copie** de la base : `cp data/dashboard.db /tmp/test.db` puis `DB_PATH=/tmp/test.db flask --app app run -p 8099`. Jamais sur `data/dashboard.db`.
- Scénarios : migration sur base existante OK ; ré-import d'un export complet -> 0 ajout ; import v1 sans uid -> pas de doublon.
- `backup*.json` et `data/` sont gitignorés (données perso) — ne jamais committer.
- ⚠️ **Gotcha RTK** (proxy CLI token-optimisé du poste de Fabien) : `curl … > fichier` capture la sortie **filtrée/tronquée** par RTK, pas le corps HTTP brut → pour les fetches de test (pages rendues, JSON exact), utiliser **python `urllib`** (ou un script python) au lieu de curl redirigé.
