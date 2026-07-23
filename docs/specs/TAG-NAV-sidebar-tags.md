# [TAG-NAV] — Section « 🏷 Étiquettes » dans la sidebar + vue dédiée par tag

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Idée Fabien (inspirée du panneau Tags de SiYuan), décisions figées. Concrétise l'emplacement réservé par [SIDEBAR-EVERNOTE] (« Emplacement futur prévu pour une section Étiquettes [TAG-NAV] »).**

## Décisions figées

1. **Sources V1 : tags des liens (v7) + tags des projets (v8)** — les tags déjà en base, normalisés minuscules sans `#`. PAS de tags mémos en V1 (ni scan de hashtags inline, ni nouveau champ) → **aucun changement de format d'export**.
2. **Clic sur un tag = vue dédiée** (pas un simple remplissage du champ recherche) : une page « 🏷 #tag » listant tout ce qui porte l'étiquette, groupé par type. Elle **réutilise en interne les matchers de la recherche existante** (mêmes règles de normalisation) + un bouton pour basculer vers la recherche globale `#tag`.
3. **Emplacement : section sidebar repliable**, sous « Projets », au pattern exact des sections existantes ([SIDEBAR-EVERNOTE]).
4. **Owner uniquement** (`index.html`) — pages invité hors périmètre (invariant 5 intact, rien de nouveau exposé).

## Spécification

### Section sidebar

- En-tête « 🏷 ÉTIQUETTES » repliable (chevron ▸/▾, état `localStorage sbSection:tags`, déplié par défaut), **sans bouton ＋** (un tag naît en taguant un lien/projet, pas ici).
- Une ligne par tag : `#tag` + **compteur** (nb liens + nb projets qui le portent). Tri : **usage décroissant puis alphabétique**. Ellipsis + `title` sur les noms longs.
- Agrégation **côté front** depuis `state.links[].tags` et `state.projects[].tags` (déjà chargés — zéro route nouvelle). Section **masquée si aucun tag**. En mode rail 64px : masquée (comme les connecteurs d'arbre).
- Item actif surligné quand sa vue est ouverte (pattern `.cat-item` actif).

### Vue dédiée `state.view='tag'` (+ `state.tagFilter`)

- Nouveau conteneur `#tag-board` (pattern des boards existants : `hidden` + branché dans `renderAll`).
- En-tête : « 🏷 #tag » + compteur total + bouton « 🔍 Rechercher #tag » (remplit la recherche globale existante et bascule — pour retrouver le mélange complet liens/mémos/projets).
- Deux sections : **« 🔗 Liens (n) »** — cards de liens réutilisées telles quelles (mêmes favicons/statuts/actions) ; **« 📁 Projets (n) »** — lignes cliquables (emoji + nom + compteur de mémos) → ouvre le board du projet.
- Section vide masquée. Tag devenu orphelin (plus rien ne le porte) : retour à la vue Liens sans erreur.
- Clic sidebar sur un autre tag pendant la vue = re-render simple.

## Ajout rapide de tags aux liens (décision Fabien, 23 juil. 2026 — même lot)

Aujourd'hui, taguer un lien passe obligatoirement par la pop-in d'édition (champ Tags, v7). Deux raccourcis :

1. **Drag & drop lien → étiquette** : glisser une card de lien sur un tag de la nouvelle section sidebar **ajoute ce tag au lien** (réutiliser le pattern D&D lien→catégorie existant ; même mécanique de survol/highlight). Persistance via la route de mise à jour de lien EXISTANTE (le champ `tags` y passe déjà — aucune route nouvelle). Tag déjà présent sur le lien = no-op silencieux. Le compteur sidebar se met à jour au render suivant.
2. **Ajout depuis la card de lien** : à côté des chips `#tag` existantes de la card, une mini-chip **« + »** discrète ouvre un petit input inline avec **datalist des tags existants** (saisie libre autorisée, normalisation minuscules sans `#` par la fonction existante). Entrée = ajoute et sauvegarde ; Échap = annule. Pendant que l'input est ouvert, chaque chip du lien affiche un **« × »** pour retirer le tag (même sauvegarde). Input refermé = chips redeviennent passives (esprit [LESS-BUTTONS] : rien d'actif en consultation).

Contraintes propres : aucun changement de schéma ni de route (le champ `tags` des liens existe depuis v7) ; invalider ce qu'il faut si les tags interviennent dans la recherche mémoïsée ; invariant 9 (chips au gabarit existant des tags de card).

Tests additionnels : D&D lien→tag = tag ajouté + compteur à jour ; D&D avec tag déjà porté = no-op ; « + » sur card → datalist propose les tags existants → Entrée ajoute (visible sur la card et dans la section) ; « × » retire ; dernier porteur retiré → le tag disparaît de la sidebar ; la pop-in d'édition du lien reste la source complète (champ Tags inchangé).

## Contraintes

- **Frontend pur, export inchangé (v23)** — `APP_VERSION` reste "23". Lot = **V23.7.Z** (Z = dernier `REALISATION.md` + 1).
- Invariants : **6** (zéro lib), **8** (pas de GSAP sur dialog ; la section sidebar s'anime comme les autres `.cat-item` avec `clearProps`, jamais le `nav`), **9** (patterns/tokens existants : sections sidebar, `.badge` pour les compteurs, cards liens réutilisées).
- Normalisation : réutiliser la fonction existante des tags (minuscules, sans `#`) — ne pas réimplémenter.
- Mobile : la section se comporte comme les autres dans la rangée sticky (rien de spécifique).

## Tests avant fin

1. `python3 -m py_compile app.py` (sanité — aucun changement backend).
2. Sidebar : section présente avec les tags réels (`#notes`, `#pkm`…), compteurs exacts (recouper avec la recherche `#tag`), tri usage puis alpha, repli persisté après reload, masquée en rail et si zéro tag.
3. Vue tag : clic `#notes` → liens tagués en cards + projets tagués en lignes ; compteurs cohérents ; clic projet → board ; bouton 🔍 → recherche globale remplie avec `#notes`.
4. Taguer/détaguer un lien → compteurs sidebar à jour au prochain render ; dernier porteur retiré → tag disparaît de la sidebar.
5. Vues existantes (Liens/Mémos/Plan/Agenda/Partages/Corbeille/Favoris) : aucune régression de navigation.
6. Mobile : section utilisable dans la barre sticky, vue tag scrollable.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.7.Z] + `IDEAS.md` [TAG-NAV] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : parcours sidebar → vue tag → board, compteurs, persistance du repli.

## V2 possibles (hors périmètre, à re-cadrer plus tard)

Tags sur les mémos (champ en base = bump export v24, invariant 1) ; parité invité ; renommage/fusion de tags ; tag pinnable en Favoris.
