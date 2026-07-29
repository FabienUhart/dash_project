# [AGENDA-DAY-POPIN] — Pop-in « jour » de l'Agenda (remplace le panneau sous la grille)

**Brief pour Claude Code — lot V25.2.Z (frontend pur, EXPORT v25 INCHANGÉ, zéro route/schéma,
`app.py` intact).** Lire `CLAUDE.md` avant. Z = compteur continu de `REALISATION.md`.

## 1. Contexte

Constat Fabien (iPad, pire sur portable) : plusieurs mémos le même jour = pas de vue « jour »
cliquable. Dans `renderAgendaView()` : chips 0.7rem, « +N » = span non cliquable, panneau du
jour rendu SOUS la grille (hors champ), interactions pensées souris/D&D ; en ≤ 900 px, liste
de tout le mois sans navigation par jour. **Maquette interactive validée par Fabien le
29 juil.** (pop-in jour : grosses lignes, heure en badge, ‹ › jour, « + Mémo ce jour »).

## 2. Décisions (tranchées avec Fabien — implémenter, ne pas rediscuter)

- **D1 — Pop-in PARTOUT** : souris comme tactile, desktop comme mobile. Elle **REMPLACE** le
  panneau du jour sous la grille, qui disparaît, ainsi que l'état `agendaSelDay` (plus de
  cellule « sélectionnée ») — la pop-in EST la vue jour. Un seul comportement à maintenir.
- **D2 — `<dialog>` natif** avec l'entrée CSS habituelle `dlg-in` — **JAMAIS de GSAP sur un
  dialog** (invariant 8, [[gsap-dialog-toplayer-gotcha]]). Le `uiBusy()` existant (dialog
  ouvert) couvre le différé du poll 15 s — vérifier, ne rien réinventer.
- **D3 — Contenu** : titre = `agendaDayLabel(iso)` + compteur « n mémos » ; lignes en
  **tap-targets ≥ 44 px** : pastille couleur (`agendaChipColor`), titre (`agendaMemoTitle`),
  heure en badge à droite si `due_time` (`fmtMemoTime`), chevron ; tap → `openMemoEditor(m)`
  owner / l'équivalent existant côté share/hub (la pop-in jour se ferme d'abord — pas deux
  dialogs empilés, règle « un seul top-layer »). **AMENDEMENT 29 juil. (retour de test Fabien) :
  comportement drill-down — à la FERMETURE de l'éditeur ouvert depuis la pop-in jour (enregistrer,
  annuler ou Échap), la pop-in jour se ROUVRE automatiquement sur le même jour, contenu re-rendu
  depuis les données fraîches (mémo re-daté ou supprimé → il disparaît de la liste ; jour devenu
  vide → état vide navigable). Même retour pour le flux « + Mémo ce jour ». Un éditeur ouvert
  AUTREMENT que depuis la pop-in jour ne doit évidemment PAS la faire apparaître.** Jour vide → état vide propre (« Rien ce
  jour-là. ») mais navigable.
- **D4 — Navigation ‹ jour précédent / jour suivant ›** dans l'en-tête : change le contenu
  SANS fermer, y compris vers les jours vides ; franchit les bornes de mois (le mois affiché
  derrière suit si on sort du mois courant, au plus simple : mettre à jour `agendaYM` au
  passage). Échap / ✕ / clic hors = fermer.
- **D5 — « + Mémo ce jour »** : bouton en bas de la pop-in → ouvre le flux de création de
  mémo EXISTANT avec `due_date` préremplie au jour affiché (owner ; côté share/hub seulement
  si le rôle permet la création — mêmes gardes que les « + » existants). La pop-in jour se
  ferme à l'ouverture du flux.
- **D6 — Déclencheurs** : clic/tap sur une cellule de la grille → pop-in du jour ; « +N »
  devient un **vrai bouton** (même action) ; clic direct sur une chip → `openMemoEditor` du
  mémo comme aujourd'hui (comportement conservé) ; en ≤ 900 px, l'en-tête de chaque jour de
  la liste mensuelle devient tappable → même pop-in.
- **D7 — Le D&D souris de replanification reste intact** (drag chip → cellule). Attention au
  clic fantôme post-drop : un drop ne doit PAS ouvrir la pop-in (garde sur `agendaDragId`).

## 3. Implémentation

- **Parité 3 pages** : l'agenda existe dans `index.html`, `share.html`, `hub.html` → helper
  partagé dans `_shared.js.html` (cfg : source des jours/mémos, labels, openMemo, création
  autorisée + callback, couleurs), même patron que les autres helpers (invariant 9).
- Plages [MEMO-DATE-RANGE] : réutiliser `agendaGroupByDay` tel quel (un mémo à plage couvre
  chaque jour — l'hôtel du 3→6 apparaît dans la pop-in du 4). Tri existant conservé
  (sans-heure d'abord).
- Dialog créé une fois par page (à la volée au premier usage, comme `attachQuickView`),
  contenu re-rendu à chaque ouverture/navigation. Styles : tokens existants, `.prio-btn`,
  pas de nouvelle dépendance (invariant 6).
- Supprimer proprement : rendu du `ag-day-panel` desktop, état `agendaSelDay`, classe `sel`
  des cellules (et son CSS mort).

## 4. Acceptation (validation Cowork ensuite)

1. Desktop souris ET iPad : clic cellule (ou « +N ») → pop-in ; 2 gestes max pour ouvrir
   n'importe quel mémo d'un jour chargé ; plus AUCUN panneau sous la grille.
2. ‹ › feuillette les jours sans fermer, jours vides inclus, franchit les mois ; Échap/✕
   ferment ; le poll 15 s ne casse rien pop-in ouverte (uiBusy).
3. « + Mémo ce jour » préremplit la date (owner + invité autorisé ; absent sinon).
4. Chip → éditeur du mémo ; D&D chip → cellule replanifie SANS ouvrir la pop-in.
5. Mobile ≤ 900 px : en-têtes de jour tappables → pop-in.
6. Plage 3→6 nov visible dans la pop-in du 4 ; parité share (invité approuvé) et hub.
7. `node --check` 3 templates + partial ; `python3 -m py_compile app.py` (intact) ;
   export toujours 25 ; zéro route nouvelle.

## 5. Fin de réalisation

Journal IDEAS→REALISATION [V25.2.Z], rebuild local, `.claude/handoff.json` "ready".
**Ni commit ni push** sans feu vert Fabien (validation Cowork d'abord).
