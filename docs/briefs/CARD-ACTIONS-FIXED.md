# Brief CC — [CARD-ACTIONS-FIXED] : barre d'action fixe en pied de card (owner + invité + hub)

> **Lot 1 de la maquette v3 des cards.** Front only, doctrine **TDD**. Objectif validé par Fabien
> sur maquette : les actions d'une card (👁 voir · ✎ éditer · 💬 · ⋯) vivent dans une **barre en
> pied**, au **même endroit** quel que soit le type de card (lien, photo, texte, checklist) — plus
> jamais sur la ligne du titre. **Périmètre : les trois pages** — propriétaire, invité, hub.
>
> Maquettes de référence (déjà dans le repo) : `docs/maquettes/maquette-card-actions.html`
> (avant/après monochrome) et `docs/maquettes/maquette-cards-v3.html` (anatomie par média).
>
> **Portée stricte de CE lot** : uniquement l'**ancrage des actions en pied**. PAS l'aperçu de lien
> OG, PAS le polish audio/photo, PAS le chip lieu — ce sont des lots suivants de la v3.

---

## 1. Le constat (mesuré dans le code)

- **Propriétaire (`index.html`)** : a **déjà** un pied de card `.task-foot` (projet à gauche, actions
  à droite, séparées par un trait, l.~1207). C'est la cible — il sert de **référence**.
- **Invité (`share.html`)** : les actions vivent dans `.task-acts` (l.308, `margin-left:auto`) et
  sont ajoutées **à la ligne du titre** (`row.appendChild(acts)`, l.~3578). Selon le contenu (lien
  vs photo+vignette), l'œil 👁 se cale à un endroit différent → il « se balade ».
- **Hub (`hub.html`)** : même schéma (`.task-acts` sur la ligne, l.~1296).

Il y a eu un correctif [MEMO-VIEW correctif 3] qui **groupe** les actions pour qu'elles wrappent
ensemble — il règle le wrap, pas l'**ancrage**. Le pied de card règle l'ancrage.

## 2. Le correctif

Amener **invité et hub** à la **parité** avec le pied de card du propriétaire : sortir `.task-acts`
de la ligne du titre et le poser dans une **barre en pied** de la card — **catégorie/projet à
gauche, actions à droite**, séparée par un filet, hauteur/position constantes. Réutiliser le gabarit
`.task-foot` existant (invariant 9), pas un nouveau langage visuel.

- **Invité (`share.html`)** : construire un pied de card (comme `.task-foot`) contenant à gauche la
  provenance déjà affichée (dossier/catégorie) et à droite le groupe `.task-acts` (👁, puis ✎/⋯ si
  `canEditMemo`). Retirer le `row.appendChild(acts)` de la ligne du titre. Garder l'ordre œil-en-tête
  et le groupement (le wrap reste bon).
- **Hub (`hub.html`)** : idem.
- **Propriétaire (`index.html`)** : **vérifier la parité** avec la maquette (icônes trait
  monochromes, catégorie à gauche / actions à droite, trait de séparation). S'il est déjà conforme,
  n'y touche pas — sinon aligne au minimum. Ne pas régresser le comportement existant.

Contraintes :
- **Icônes Tabler trait, `currentColor`, monochrome** (déjà le style de l'app) — muted au repos,
  accent au survol. Aucun aplat coloré ajouté.
- **Compact** est le mode où le défaut se voit → c'est la cible première. En **Immersif**, le
  propriétaire descend déjà les actions dans un pied sur la couverture (`CARD-COVER`) : **garder ce
  comportement**, ne pas le casser ; l'invité doit être cohérent avec lui.
- Le pied ne s'affiche que s'il y a quelque chose à montrer (catégorie et/ou actions), comme
  aujourd'hui. Une card sans action ne gagne pas une barre vide.

## 3. Tests (TDD)

**e2e par une vraie porte** (la leçon des lots précédents — pas de rendu simulé) :

1. **`test_guest_card_actions_are_anchored`** — page invité, affichage Compact, deux cards de
   **types différents** (une card-lien, une card-photo) → l'ancre du bouton 👁 (sa position
   horizontale/verticale, ou son conteneur `.task-foot`) est **la même** sur les deux. Aujourd'hui
   elle diffère → le test doit être **rouge avant**, vert après.
2. **`test_guest_actions_not_on_title_row`** — les actions ne sont plus enfant de la ligne de titre
   mais du **pied** de la card (structure DOM).
3. **Propriétaire** : un test léger que le pied de card owner **n'a pas régressé** (actions toujours
   présentes et cliquables).
4. Éprouver par **mutation** l'ancre (remettre `.task-acts` sur la ligne du titre → le test #1 rougit
   sur le bon message).

## 4. Definition of Done

1. Invité + hub : actions en **pied de card** (parité avec owner), plus sur la ligne du titre ;
   œil/actions au **même endroit** quel que soit le média. Owner vérifié conforme (ou aligné a
   minima), non régressé.
2. Icônes trait monochromes, classes existantes réutilisées (invariant 9), Immersif préservé.
3. `make test` **entièrement vert** ; tests §3 rouges avant / verts après, ancre éprouvée par mutation.
4. `git status` : `templates/share.html`, `templates/hub.html`, éventuellement `templates/index.html`,
   `tests/…`, `REALISATION.md`. Pas de `.idea`. Rebuild local.
5. **Vérif à l'œil Fabien** : côté invité **et** owner, en Compact, parcourir une colonne de cards de
   types variés → le bouton 👁 tombe toujours au même endroit (le test de la maquette).
6. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**, puis **tag + Deploy**
   (prod actuelle : V27.40.248).

## 5. Après ce lot (la suite de la v3, pour mémoire — NE PAS faire ici)

`[LINK-OG]` aperçu de lien enrichi (miniature + titre + domaine, **backend** OpenGraph + cache) —
le plus gros gain visuel ; puis le **polish** photo/audio/checklist ; puis le **chip lieu** sur la
card. Un lot à la fois.
