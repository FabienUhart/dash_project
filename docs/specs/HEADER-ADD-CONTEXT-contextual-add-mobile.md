# [HEADER-ADD-CONTEXT] — « + » contextuel par bloc en mobile

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Maquette variante A validée par Fabien (« + » discret dans l'en-tête de chaque bloc), décisions figées le même jour.**

## Décisions figées (Fabien, 23 juil.)

1. **Variante A** : la barre « + Ajouter un lien / + Ajouter une catégorie » disparaît en mobile, remplacée par un petit « + » rond dans l'en-tête de chaque bloc (Liens, Mémos).
2. **Pré-remplissage catégorie** : le « + Lien » pré-sélectionne la catégorie active de la barre collante. ✅ **Déjà implémenté** : `openDialog()` (index.html ~l. 7026) pose `defaultCat` depuis `state.filterCat` quand ≠ `all`/`none` — rien à coder, juste vérifier que le nouveau chemin passe par `openDialog()`.
3. **« + » du bloc Mémos = focus sur le champ « + Note rapide… »** existant (`#memo-quick`), pas de pop-in.
4. **Périmètre : mobile uniquement (≤ 900 px)** — le desktop garde la barre `#links-actions` telle quelle ([LINK-ADD-RELOCATE] V21.1.62 inchangé).

## Versionnage

- **Frontend pur, owner uniquement** (`templates/index.html` seul — `share.html`/`hub.html` non concernés, leurs barres d'ajout ont leur propre logique). **Aucun changement de schéma/API/export** → `APP_VERSION` reste **"23"**.
- Lot = **V23.3.Z** (Y bump ; Z = dernier `REALISATION.md` + 1 **au moment de journaliser** — le lot [FX-CONVERTER] V23.2.x sera passé avant, revérifier).

## Spécification

### Bloc Liens (vue Liens, ≤ 900 px)

- Masquer `#links-actions` en ≤ 900 px (media query mobile existante).
- Ajouter au-dessus de `ul#links` une **ligne d'en-tête de bloc fine**, visible **seulement ≤ 900 px ET en vue Liens** (togglée dans `renderAll` comme `#links-actions`) : label discret « 🔗 Liens » (gabarit du `<summary>` de `#memo-details` : petites capitales/muted) + **bouton rond « + » aligné à droite**.
- Tap sur ce « + » → **mini-menu 2 entrées** « + Lien » / « + Catégorie », en réutilisant le **pattern `card-menu` existant** (comme `#create-menu-btn`/`#create-menu` de la pop-in projet — pas de nouveau composant) → `openDialog()` / `addCategory()`. Ce sont les mêmes fonctions que les boutons desktop : zéro nouveau flux.

### Bloc Mémos (≤ 900 px)

- Ajouter le **« + » rond dans le `<summary>` de `#memo-details`** (à côté de `#memo-open` ⤢), visible **seulement ≤ 900 px**.
- Tap → si le `<details>` est replié, l'ouvrir ; puis scroll jusqu'à `#memo-quick` + focus. ⚠️ Un clic dans un `<summary>` toggle le `<details>` : `e.preventDefault()` + `stopPropagation()` sur le bouton (même précaution que `#memo-open`).

### Desktop (> 900 px)

- **Strictement rien ne change** : barre `#links-actions` visible, summary actuel, pas d'en-tête de bloc Liens.

## Contraintes et gotchas connus (CLAUDE.md)

- **Invariant 9** : boutons ronds au gabarit `.task .task-actions button` (rayon, `var(--panel-2)`/`var(--border)`, hover), tokens CSS uniquement. Le « + » n'est PAS en accent (action secondaire discrète — c'est tout le propos de la fiche).
- **Règle tactile** : `@media (pointer:coarse) { button { min-height:44px } }` **ovale les boutons ronds** → reprendre le fix existant (`min-height:0` + dimensions carrées explicites, cf. `.task-check`/`.thumb-del`). Zone de tap ≥ 36 px quand même (padding autour si besoin).
- **Gotcha cascade mobile** : les overrides ≤ 900 px se placent **en fin de `<style>`** (bloc « Overrides mémos mobile ») sous peine d'être silencieusement écrasés à spécificité égale.
- **Accessibilité** : `aria-label` explicites (« Ajouter un lien ou une catégorie », « Ajouter un mémo »).
- **Invariant 8** : le mini-menu n'est pas un `<dialog>` animé GSAP — pattern `card-menu` natif.
- `syncHeaderHeight()` : la barre retirée est dans `<main>`, pas dans le header — aucun impact attendu, vérifier quand même la barre collante après bascule de vue.

## Tests avant fin (DevTools mode mobile ≤ 900 px + desktop)

1. `python3 -m py_compile app.py` (aucun changement backend attendu — sanité).
2. Mobile, vue Liens : barre 2 boutons **absente**, en-tête « Liens + » présent ; « + » → menu 2 entrées ; « + Lien » avec catégorie « Médias » active → pop-in pré-remplie Médias ; sur « Tous » → sélecteur vierge ; « + Catégorie » → flux `addCategory()` habituel.
3. Mobile, autres vues (Mémos, Plan, Agenda, Partages…) : **pas** d'en-tête Liens ni de barre.
4. Mobile, bloc Mémos : « + » du summary → details ouvert + focus `#memo-quick`, le details ne se re-toggle pas ; boutons ronds **pas ovales** (mode responsive DevTools ET pointer:coarse).
5. Desktop > 900 px : identique à avant, pixel près (barre visible, pas de « + » d'en-têtes).
6. `share.html`/`hub.html` : non touchés.

## Fin de réalisation (process CLAUDE.md)

Tester → journaliser (`REALISATION.md` [V23.3.Z] + `IDEAS.md` : basculer [HEADER-ADD-CONTEXT] en « Fait », cluster NAV & MOBILE soldé) → `docker compose up -d --build` (hook → `.claude/handoff.json`) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation finale par Cowork via Chrome en mode mobile sur `http://localhost:8099/`.
