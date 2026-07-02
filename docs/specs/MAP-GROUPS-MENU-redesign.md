# SPEC — [MAP-GROUPS-MENU] Menu Groupes (créer/modifier/copier/supprimer) + liste épurée

**Statut : VERROUILLÉE — maquette + décisions validées par Fabien (2 juil. 2026).**
Cible : **V20.4**. **Frontend pur** (`templates/partials/_shared.js.html` = les 3 pages
d'un coup), **zéro changement backend, zéro changement d'export** (les groupes
vivent déjà dans `memos.map_groups`, export v17, écriture via le `PUT` scopé
existant). **Parité invité IDENTIQUE** (le partial est mutualisé).

---

## 1. Problème / objectif

Aujourd'hui, chaque point de la liste de la carte porte une **case à cocher
permanente** (`renderSelbar`/checkboxes, l.303-328/401) pour sélectionner des
points et les grouper (barre « n sélectionnés → nom → ＋ Grouper »). Résultat :
liste chargée en permanence. Objectif : **liste épurée par défaut** + un **menu
Groupes** explicite pour toute la gestion (créer / modifier / copier / supprimer),
les coches n'apparaissant **que** pendant la création/modification.

## 2. Décisions figées

1. **Liste par défaut ÉPURÉE** : plus AUCUNE case à cocher permanente sur les points.
2. **Bouton « Groupes ▾ »** (près de la barre de groupes `#map-groupbar`) ouvrant
   un menu : **Créer / Modifier / Copier / Supprimer**.
3. Les **coches réapparaissent uniquement en mode Créer/Modifier** (réutilise
   l'UI de sélection actuelle : cases + champ nom + valider).
4. **Parité invité IDENTIQUE** : filtrer (chips) pour tout invité approuvé ;
   créer/modifier/copier/supprimer réservés à `can_edit` (comme aujourd'hui le
   groupage l'est déjà — variable `editable` du partial). Rien de nouveau exposé.

## 3. Comportement des actions

- **Créer** → entre en **mode sélection vierge** : coches visibles sur les points,
  champ « Nom du groupe », `Valider` (applique le groupe aux points cochés via le
  `PUT … {map_groups}` existant) / `Annuler`. = le flux `renderSelbar` actuel,
  mais déclenché par le menu au lieu d'être permanent.
- **Modifier un groupe…** → choisir un groupe existant (sous-menu ou liste) →
  mode sélection avec ses points **pré-cochés** + nom **pré-rempli** ; ajouter/
  retirer des points et/ou renommer → `Valider`. Renommer = ré-étiqueter le groupe
  sur tous ses points (retirer l'ancien nom, ajouter le nouveau via les writes
  existants) ; retirer un point = enlever le nom de groupe de ce mémo.
- **Copier un groupe…** → choisir un groupe → pré-remplir un **nouveau** nom
  (« <nom> (copie) ») avec ses points pré-cochés → `Valider` crée un 2e groupe
  sur les mêmes points (les points portent alors les deux étiquettes). Ajustable
  avant validation.
- **Supprimer un groupe…** → choisir un groupe → confirmation (`confirmPopin`) →
  retire ce nom de groupe de **tous** ses points (les points restent, juste plus
  dans ce groupe). Aucune suppression de mémo.

## 4. Contraintes techniques

- **Réutiliser l'existant** : `map_groups` (`_map_groups_json`, export v17),
  écriture via le `PUT /api/memos/<id>` owner / `PUT /share/<t>/memo/<id>` invité
  déjà câblés dans le partial (`apply` de `renderSelbar`). **Aucune route nouvelle,
  aucun champ nouveau** → export **inchangé (reste v20/… selon vague)**.
- Tout dans `_shared.js.html` (`renderGroupbar` l.278, `renderSelbar` l.303,
  checkboxes l.401) → les 3 pages (owner/share/hub) d'un coup, parité auto.
- **Invariants** : 5 (invité `can_edit` via chemins scopés existants, rien de
  neuf exposé), 6 (pas de lib, HTML autonome), 8 (menu = markup/CSS, pas de GSAP
  sur le `<dialog>`), 9 (bouton/menu façon `card-menu`/`.prio-btn` existants, pas
  de style bespoke). Le mode sélection réutilise les classes actuelles de `selbar`.
- **Mobile** : le menu et le mode sélection doivent rester utilisables dans
  l'empilement carte→frise→liste ([MAP-TIMELINE-MOBILE-ORDER]) ; coches du mode
  sélection assez grandes au doigt (règle 44px déjà gérée ailleurs — dimensions
  explicites si besoin).

## 5. Tests d'acceptation (validation Chrome par l'agent Cowork)

1. Vue par défaut : liste des points SANS coche ; chips de groupes présents ;
   bouton « Groupes ▾ » visible.
2. Créer : menu → Créer → coches apparaissent → cocher 2 points + nom → Valider →
   nouveau chip de groupe, points étiquetés (vérifiable via `/api/memos`
   `map_groups`) ; Annuler ne modifie rien ; coches disparaissent après.
3. Modifier : sélection d'un groupe → points pré-cochés + nom pré-rempli →
   ajouter 1 point + renommer → Valider → étiquettes mises à jour partout.
4. Copier : groupe → « (copie) » + mêmes points pré-cochés → Valider → 2 groupes
   distincts sur les mêmes points.
5. Supprimer : confirmation → le groupe disparaît des chips, les points restent
   (map_groups vidé de ce nom), aucun mémo supprimé.
6. Filtrage (chips) inchangé pour tous ; création/édition **masquées** pour un
   invité lecture seule, **présentes** pour un invité `can_edit` (parité owner).
7. Export inchangé (aucun bump) ; `python3 -m py_compile` (app.py intouché).
8. Mobile (≤ breakpoint) : menu + mode sélection utilisables dans l'empilement
   carte→frise→liste.

## 6. Hors périmètre (volontaire)

- Couleur de groupe (chip/points colorés) — écarté pour l'instant (pourrait être
  un lot suivant si utile ; ne pas ajouter de champ/export).
- Réordonnancement des groupes ; groupes inter-projets (un groupe reste « par
  projet » comme aujourd'hui — [MAP-SUBFILTER]/[map_groups]).
- Aucun changement au tracé/frise/vignettes (lots MAP-TIMELINE/POLISH).
