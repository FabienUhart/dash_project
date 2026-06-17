# Plan d'amélioration UX / UI

Audit du dashboard (`templates/index.html`, `templates/share.html`) réalisé avec la grille de priorités UI/UX Pro Max (1 = critique → 10 = mineur) et confronté au code réel. Chaque point cite la preuve (`fichier:ligne` ou motif), l'impact, la reco et le coût estimé.

**Contraintes projet à respecter** (rappel CLAUDE.md) : un seul fichier HTML par page, pas de build, pas de CDN au runtime (toute dépendance auto-hébergée dans `static/`, whitelist `SHARE_ASSETS` pour les invités), ne jamais animer un `<dialog>` via GSAP (invariant #8), les emojis de catégories/projets/mémos sont une **fonctionnalité utilisateur** (à conserver) — distincts des emojis utilisés comme icônes système.

Légende effort : 🟢 rapide (CSS/attrs) · 🟡 moyen (JS + CSS) · 🔴 gros (refonte partielle).

## État d'avancement (juin 2026)

- ✅ **Lot 1** : P1.1 (aria-label header), P1.4 (`--muted` éclairci #9aa7b4), P1.5 (`:focus-visible` partout + champs pop-in), P2.2 (inputs 16px mobile), P2.3 (`touch-action`), P6.1 (polices < 0.72rem remontées — plancher complet 12px restant).
- ✅ **Lot 2** : P1.2 (sidebar/tuiles/tags focusables `tabindex`+`role` et activables Entrée/Espace via `applyA11y()` + handler délégué), P1.3 (actions révélées au `:focus-within` + visibles en `pointer:coarse`), P2.1 (cibles ≥ 44px en `coarse`).
- ✅ **Finitions** : P6.4 (`tabular-nums` horloge/compteurs), P7.2 (`scale` au `:active`), P5.3 (`100dvh`), P3.3 (`will-change` au survol).
- ✅ **Lot 3 — identité** : P6.2 (police **Inter** auto-hébergée `static/Inter.woff2` + `@font-face`, fallback system-ui, whitelist partage), P4.1 (sprite SVG Lucide inline + classe `.ic` + helpers `icon()`/`shareIcon()` ; tous les emojis-**icônes système** convertis sur les deux pages — recherche, cloche, engrenage, édition, corbeille, partage, QR, duplication, image, position, carte, priorité, versions, 👤, 💬, 👁, pastilles ✎/👁). Emojis-**contenu** (catégories/projets/mémos) conservés. Restent en glyphe par nécessité : `<option>` de priorité, placeholders, 📁 projet, titres de pop-in dynamiques (🗺/🔗).
- ✅ **Lot Layout (P5)** : P5.1 (largeurs en `clamp()` — sidebar/colonne mémos/sidebar partage), P5.3 (`100dvh` sur les deux pages).
- ✅ **P8.1 — labels visibles** : labels persistants Titre / Contenu / Assigné·es / Commentaires dans les pop-ins « Éditer le mémo » (dashboard) et « Modifier le mémo » (partage), placeholder en complément (`.me-label`). Les pop-ins lien/projet utilisaient déjà des `<label>`.
- ✅ **P6.3 — tokens sémantiques** : `--danger`/`--warn`/`--guest`/`--assignee` dans `:root` (2 pages) ; toutes les couleurs d'état en dur (#ff8a80/#ffb74d/#b39ddb/#80cbc4) remplacées par ces variables. Rendu identique, centralisé/thémable.
- ✅ **P8.3 — boutons désactivés pendant async** : helper `withBusy()` + disable/opacité avec `finally` sur Sauver mémo, Créer projet/catégorie, Sauver lien, Import (dashboard) — anti double-clic. (Reste à étendre au partage si besoin.)
- ✅ **P5.2 — breakpoints unifiés** : la page partagée passe de `800px` à `900px`, alignée sur le dashboard → un seul seuil responsive (≤900px) sur les deux pages.
- ✅ **P8.2 — aria-live** : région `#sr-live` (`role=status`, `aria-live=polite`, `.sr-only`) + helper `announce()` branché sur `notify()` (couvre import/erreurs/validations) et sur le rafraîchissement manuel des statuts (dashboard). (↻ Rafraîchir converti en SVG au passage.)
- ✅ **P8.2 / P8.3 côté partage** : `withBusy` sur Enregistrer / Ajouter (mémo) / Créer (sous-projet) — anti double-clic ; région `aria-live` `#sr-live` + `announce()` (annonce « Modification enregistrée » via `put()`).
- ⏳ **Reste** : P6.1 plancher 12px complet, P3.1 (virtualisation — utile seulement si gros volume), clavier complet sur cards/tâches.

---

## P1 — Accessibilité (CRITIQUE)

### 1.1 🟢 Boutons-icônes sans `aria-label`
- **Preuve** : `#activity-btn`, `#settings-btn` n'ont qu'un `title` ; 1 seul `aria-label` dans tout `index.html`, **0** dans `share.html`.
- **Impact** : lecteurs d'écran annoncent « bouton » sans fonction. `title` n'est pas un substitut fiable.
- **Reco** : ajouter `aria-label` explicite à chaque bouton icône (🔔 → "Activité des invités", ⚙ → "Paramètres", × de fermeture, ↻, ⬇/⬆, 🗑, ⤢…).
- **Coût** : 🟢

### 1.2 🟡 Éléments cliquables non focusables au clavier
- **Preuve** : `role="button"`/`tabindex` = **0** occurrence. Cards (`.card`), items sidebar (`.cat-item`/`.sitem`), tâches (`.task`), tuiles (`.mfilter`/`.tile`), tags sont des `<div>` avec `click` handlers.
- **Impact** : navigation clavier impossible sur les actions principales (anti-pattern `keyboard-nav`). Bloquant pour a11y.
- **Reco** : sur les conteneurs interactifs non natifs, ajouter `tabindex="0"`, `role="button"` et gérer `keydown` (Enter/Espace). Mutualiser dans le helper `el()` (option `clickable: true`).
- **Coût** : 🟡

### 1.3 🟡 Actions visibles uniquement au survol
- **Preuve** : 5 règles `opacity: 0 → :hover` (`.card .actions`, `.task .task-actions`…).
- **Impact** : éditer/supprimer **impossible au tact et au clavier** (anti-patterns `hover-vs-tap`, `gesture-alternative`).
- **Reco** : révéler aussi sur `:focus-within` ; sur mobile (`pointer: coarse`), garder les actions visibles en permanence (atténuées). Au minimum un menu « ⋯ » toujours accessible.
- **Coût** : 🟡

### 1.4 🟢 Contraste du texte secondaire à vérifier
- **Preuve** : `--muted: #8a96a3` sur `--panel #161d25` ; combiné aux tailles 0.62–0.68rem (cf. P6).
- **Impact** : gris-sur-sombre proche de la limite 4.5:1, aggravé par la petite taille.
- **Reco** : viser `--muted` ≥ 4.5:1 sur `--panel` ET `--bg` (éclaircir vers ~#9aa7b4) ; vérifier avec un contrôleur de contraste. Ne jamais descendre le texte porteur d'info sous 12px (cf. P6).
- **Coût** : 🟢

### 1.5 🟢 État focus incomplet
- **Preuve** : `--ring` ajouté sur boutons/recherche, mais pas sur les cards/tâches/tuiles (qui deviendront focusables en 1.2), ni sur les `dialog input`.
- **Reco** : appliquer `:focus-visible { box-shadow: var(--ring) }` à tous les éléments interactifs, y compris les champs de formulaire des pop-ins.
- **Coût** : 🟢

---

## P2 — Tactile & Interaction (CRITIQUE)

### 2.1 🟡 Cibles tactiles sous 44px
- **Preuve** : boutons d'action `padding: 0.1–0.15rem` ; cases `.task-check` 1.15rem (~18px) ; `.thumb-del` 1.2rem.
- **Impact** : sous le minimum 44×44 (anti-pattern `touch-target-size`), mis-taps fréquents sur mobile.
- **Reco** : étendre la zone tactile via `hitSlop` CSS (pseudo-élément ou `padding` + `margin` négatif) sans grossir le visuel ; viser ≥44px sur `pointer: coarse`.
- **Coût** : 🟡

### 2.2 🟢 Champs de saisie < 16px → zoom auto iOS
- **Preuve** : `#search` `font-size: 0.9rem` (~14.4px) ; plusieurs `select`/`input[type=date]` à 0.85rem.
- **Impact** : iOS Safari zoome au focus (anti-pattern `readable-font-size`), recadrage désagréable.
- **Reco** : forcer `font-size: 16px` sur tous les `input/select/textarea` au moins en mobile (`@media (max-width:900px)`).
- **Coût** : 🟢

### 2.3 🟢 `touch-action` pour réactivité
- **Reco** : `touch-action: manipulation` sur les éléments cliquables pour supprimer le délai 300ms historique.
- **Coût** : 🟢

---

## P3 — Performance (HIGH)

### 3.1 🟡 Listes longues non virtualisées
- **Preuve** : `renderLinks`/`renderMemos` reconstruisent tout le DOM à chaque `loadAll()` (appelé après chaque mutation + `setInterval(load, 15000)` côté partage).
- **Impact** : avec beaucoup de liens/mémos, reflow complet toutes les 15 s. Recrée aussi le travail GSAP.
- **Reco** : (a) diffing minimal ou recyclage des nœuds inchangés ; (b) si le volume grandit, virtualiser au-delà de ~50 items ; (c) ne re-render que la zone visible.
- **Coût** : 🔴 (optionnel tant que le volume reste modéré).

### 3.2 🟢 Images des mémos sans dimensions réservées
- **Preuve** : `.task-thumbs img { height: 64px; max-width: 130px }` — hauteur fixe OK, mais la visionneuse et les uploads n'ont pas d'`aspect-ratio`.
- **Reco** : `loading="lazy"` + `width`/`height` ou `aspect-ratio` sur les vignettes pour éviter le CLS au chargement.
- **Coût** : 🟢

### 3.3 🟢 `will-change` ciblé sur les éléments animés
- **Reco** : poser `will-change: transform, opacity` au survol uniquement (pas en permanence) sur cards/tâches pour des transitions plus lisses sans surcoût mémoire.
- **Coût** : 🟢

---

## P4 — Choix de style (HIGH)

### 4.1 🟡 Emojis comme icônes système
- **Preuve** : 🔍 (recherche), 🔔 (activité), ⚙ (paramètres), ↻, ⬇/⬆, 🗑, 📜, ⤢, 📍, 🗺… dans header et boutons.
- **Impact** : rendu dépendant de la police OS, incohérent multi-plateforme, non thémable (anti-pattern `no-emoji-icons`).
- **Reco** : remplacer les icônes **système** par un jeu SVG cohérent (Lucide/Heroicons) **auto-hébergé** dans `static/` (sprite SVG unique `icons.svg`, ajouté à `SHARE_ASSETS`). **Conserver** les emojis de catégories/projets/mémos (contenu utilisateur, fonctionnalité existante). Distinguer clairement les deux usages.
- **Coût** : 🟡

### 4.2 🟢 Échelle d'élévation déjà cohérente — finir le travail
- **Preuve** : `--shadow`/`--shadow-lg` introduits, mais quelques pop-ins inline (`map-dialog`, `proj-dialog`) gardent des styles ad hoc.
- **Reco** : router toutes les surfaces (cards, dialogs, sheets) sur la même échelle de tokens ; supprimer les `box-shadow`/`border-radius` inline résiduels.
- **Coût** : 🟢

### 4.3 🟢 Une seule CTA primaire par écran
- **Preuve** : header avec `+ Ajouter` (primary) — OK. Vérifier les pop-ins où plusieurs boutons `.primary` peuvent coexister.
- **Reco** : un seul bouton `.primary` par dialog ; le reste en secondaire.
- **Coût** : 🟢

---

## P5 — Layout & Responsive (HIGH)

### 5.1 🟡 Sidebar/colonne mémos en largeur fixe
- **Preuve** : `nav#sidebar { width: 200px }`, `aside#memo-panel { width: 250px }`, `#snav { width: 190px }`.
- **Impact** : pas d'adaptation aux écrans très larges (perte d'espace) ni intermédiaires.
- **Reco** : `clamp()` pour les largeurs (`clamp(180px, 16vw, 240px)`) ; `main` avec `max-width` lisible et gouttières adaptatives par breakpoint (375/768/1024/1440).
- **Coût** : 🟡

### 5.2 🟢 Breakpoints unifiés
- **Preuve** : `@media (max-width:900px)` (index) vs `800px` (share).
- **Reco** : aligner sur une échelle commune (768/1024) entre les deux pages.
- **Coût** : 🟢

### 5.3 🟢 `min-h-dvh` plutôt que `100vh`
- **Preuve** : `min-height: calc(100vh - 57px)`.
- **Reco** : utiliser `100dvh`/`calc(100dvh - …)` pour éviter le saut lié à la barre d'URL mobile.
- **Coût** : 🟢

---

## P6 — Typographie & Couleur (MEDIUM)

### 6.1 🟡 Trop de polices minuscules
- **Preuve** : **11×** `0.72rem` (~11.5px), + `0.68`, `0.65`, **`0.62rem`** (~10px) — labels, badges, méta, compteurs.
- **Impact** : sous le plancher lisible 12px (anti-pattern `readable-font-size`), surtout pour du texte porteur d'info.
- **Reco** : plancher à 12px (0.75rem) pour tout texte signifiant ; réserver < 12px aux pastilles purement décoratives. Définir une échelle type explicite (12/14/16/18/24/32).
- **Coût** : 🟡

### 6.2 🟡 Pas de police de marque
- **Preuve** : `font-family: -apple-system, …, system-ui` uniquement.
- **Reco** : adopter **Inter** (recommandé par le design system pour outils/dashboards) **auto-hébergé** dans `static/` (`woff2`, `font-display: swap`, ajouté à `SHARE_ASSETS`) — pas de Google Fonts CDN (invariant #6). Garder system-ui en fallback.
- **Coût** : 🟡

### 6.3 🟢 Tokens de couleur sémantiques
- **Preuve** : couleurs d'état dispersées (`#ff8a80`, `#b39ddb`, `#15232e`…) en dur dans les règles.
- **Reco** : promouvoir en tokens sémantiques (`--danger`, `--scheduled`, `--today`, `--surface-active`) pour cohérence et thématisation.
- **Coût** : 🟢

### 6.4 🟢 Chiffres tabulaires pour compteurs/dates
- **Reco** : `font-variant-numeric: tabular-nums` sur l'horloge, les compteurs (`.count`, `.mf-count`, `.tn`) et les dates pour éviter le micro-jitter (cohérent avec le count-up GSAP).
- **Coût** : 🟢

---

## P7 — Animation (MEDIUM) — déjà solide, finitions

### 7.1 🟢 Sortie plus courte que l'entrée
- **Reco** : quand on ajoute des transitions de sortie (suppression d'une card/tâche), durée ~60–70 % de l'entrée (`exit-faster-than-enter`).
- **Coût** : 🟢

### 7.2 🟢 Feedback d'appui (scale)
- **Reco** : léger `scale(0.97)` au `:active` sur cards/tuiles cliquables (`scale-feedback`) ; déjà présent sur les boutons.
- **Coût** : 🟢

### 7.3 ✅ Conformité acquise
- `prefers-reduced-motion` géré, `transform/opacity` uniquement, entrée pop-ins en CSS (invariant #8), stagger au changement de vue seulement. **Rien à corriger.**

---

## P8 — Formulaires & Feedback (MEDIUM)

### 8.1 🟡 Labels visibles dans les pop-ins
- **Preuve** : plusieurs champs s'appuient sur `placeholder` (ex. `me-title` « 🏷 Titre (optionnel) », inputs de localisation).
- **Reco** : label visible persistant par champ (anti-pattern `input-labels`/placeholder-only) ; le placeholder en complément, pas en remplacement.
- **Coût** : 🟡

### 8.2 🟢 Toasts / aria-live pour les retours
- **Preuve** : retours via pop-in `notify` (bien) ; pas de région `aria-live` pour les états async (statuts, sauvegarde).
- **Reco** : `role="status"`/`aria-live="polite"` sur une zone de feedback légère (sauvegarde auto, statut en ligne) ; ne pas voler le focus.
- **Coût** : 🟢

### 8.3 🟢 États désactivés explicites
- **Reco** : pendant un appel async (import, sauvegarde, ajout), désactiver le bouton + opacité 0.5 + curseur (`disabled-states`, `loading-buttons`). Vérifier `uiBusy()` couvre bien tous les cas.
- **Coût** : 🟢

---

## P9 — Navigation (HIGH)

### 9.1 🟡 État actif et hiérarchie de la sidebar
- **Preuve** : `.cat-item.active` + liseré ajouté (bien). Projets imbriqués indentés.
- **Reco** : renforcer le repère d'emplacement courant (poids + couleur + liseré déjà là) ; sur l'arbre profond, envisager un fil d'Ariane léger en tête de board (`breadcrumb-web`) pour 3+ niveaux.
- **Coût** : 🟡

### 9.2 🟢 Préserver scroll/état au changement de vue
- **Reco** : restaurer la position de scroll en revenant sur une vue (`state-preservation`), surtout sur les longues listes de mémos.
- **Coût** : 🟢

### 9.3 🟢 Séparer les actions destructrices
- **Preuve** : boutons « Supprimer » dans les pop-ins d'édition (déjà en `.danger`, placés à gauche via `margin-right:auto`).
- **Reco** : conserver la séparation spatiale + couleur danger (`destructive-nav-separation`) — déjà conforme, à maintenir.
- **Coût** : ✅

---

## P10 — Données (LOW)

- Pas de graphiques actuellement. **Si** un jour des stats (mémos par projet, complétions/semaine) : barres pour comparaison, état vide explicite, `tabular-nums`, labels directs, accessibilité couleur (jamais la couleur seule). Hors périmètre immédiat.

---

## Ordre d'exécution recommandé

**Lot 1 — Accessibilité & tactile (impact max, coût faible)** 🟢🟡
P1.1 (aria-label) · P1.5 (focus-visible partout) · P2.2 (inputs 16px) · P2.3 (touch-action) · P1.4 (contraste --muted) · P6.1 (plancher 12px). Surtout du CSS/attributs, zéro risque logique.

**Lot 2 — Interaction clavier/tactile** 🟡
P1.2 (tabindex/role + keydown via `el()`) · P1.3 (actions sur focus-within + visibles en coarse) · P2.1 (hitSlop 44px).

**Lot 3 — Identité visuelle** 🟡
P6.2 (Inter auto-hébergé) · P4.1 (sprite SVG système, garder emojis contenu) · P6.3/6.4 (tokens sémantiques + tabular-nums) · P4.2 (finir l'échelle d'élévation).

**Lot 4 — Layout & finitions** 🟢🟡
P5.1 (largeurs `clamp`) · P5.2/5.3 (breakpoints, dvh) · P8.1 (labels visibles) · P8.2/8.3 (aria-live, disabled) · P7.1/7.2 (micro-anim).

**Lot 5 — Performance (si volume croît)** 🔴
P3.1 (diffing/virtualisation) · P3.2/3.3 (lazy img, will-change).

Chaque lot reste compatible « un seul fichier, pas de build, pas de CDN » : Inter et le sprite SVG s'ajoutent dans `static/` + `SHARE_ASSETS`, comme GSAP/Quill/Leaflet.
