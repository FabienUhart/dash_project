# SPEC — [AGENDA] Vue calendrier mensuelle (owner + invités, D&D inclus)

**Statut : VERROUILLÉE — décisions validées par Fabien (2 juil. 2026, maquette approuvée).**
Cible : **V19.14**. Frontend (3 pages), **zéro route nouvelle, export inchangé** (v19).
Écritures = endpoints existants uniquement → pas de zone sécurité nouvelle, mais
la parité invité reste soumise à l'invariant 5 (scope + can_edit revalidés serveur).

---

## 1. Décisions figées

1. **D&D dès la v1** : glisser un mémo d'un jour à l'autre change son `due_date`.
2. **Parité invité directe** : la vue arrive en même temps dans `index.html`,
   `share.html` et `hub.html` (scopée à leurs mémos).
3. **Mobile (≤900 px) : liste par jour** (pas de grille écrasée), sans D&D.

## 2. La vue (desktop)

- **Accès** : owner = item sidebar « 📆 Agenda » (sous Plan) → `state.view='agenda'` ;
  share/hub = même logique que la vue Plan existante (tuile/toggle « 📆 Agenda »).
- **Grille mensuelle CSS grid maison** (invariant 6 : AUCUNE lib calendrier) :
  7 colonnes lun→dim, semaines du mois courant, jours hors-mois grisés,
  **aujourd'hui surligné** (bordure accent). Navigation « ‹ / › / Aujourd'hui »,
  mois courant à l'ouverture (mois affiché non persisté — simple).
- **Cases jour** : jusqu'à 2-3 chips de mémo (pastille couleur + titre/extrait
  ellipsé) + « +N » si débordement. Couleur de pastille = priorité sinon
  `usableProjColor(projet)` sinon défaut — même résolution que la carte.
  **Mémos terminés masqués** ; mémos sans `due_date` absents (logique : l'agenda
  montre l'échéancier). Corbeille exclue (comme partout).
- **Panneau du jour** sous la grille : clic sur un jour → « jeudi 2 juillet —
  N mémos », liste triée **sans heure d'abord puis heure croissante** (règle
  [MEMO-TIME]), heure affichée « 14h30 » quand présente. Clic mémo → pop-in
  d'édition existante (owner : `openMemoEditor` ; share/hub : leur éditeur,
  gaté `can_edit` comme aujourd'hui). Jour du jour sélectionné par défaut.

## 3. D&D (v1)

- Glisser un chip de mémo sur une autre case = **changer `due_date`** vers ce jour.
  `due_time` **conservé tel quel** (on déplace le jour, pas l'heure) ; récurrence :
  aucun traitement spécial (même effet que modifier le champ date dans la pop-in).
- **Écritures** : owner → `PUT /api/memos/<id> {due_date}` ; invité →
  `PUT /share/<token>/memo/<id>` (share) / via `api(share_token,…)` (hub) —
  chemins existants, **revalidés serveur** (scope + can_edit + invité approuvé,
  invariant 5). Invité lecture seule : chips **non draggables**.
- Feedback : case survolée en surbrillance pendant le drag ; après drop, re-render
  (le mémo change de case) — pas de GSAP sur un dialog (invariant 8).
- **Pas de D&D en mobile** (liste) ni sur les jours hors-mois.

## 4. Mobile (≤900 px)

Liste agenda groupée par jour du mois affiché : uniquement les jours **ayant des
mémos**, en-têtes « jeu 2 juil — N mémos » + lignes mémo (pastille, heure, titre).
Même navigation mois (‹ › Aujourd'hui). Clic mémo → pop-in. Pas de grille, pas de D&D.

## 5. Mutualisation (ADR-001)

Helpers **purs et identiques** (construction de la matrice du mois, regroupement
par jour, tri intra-jour, format des libellés de jour FR) → `templates/partials/
_shared.js.html`, après **diff strict** owner/invité (règle existante : n'extraire
que des corps identiques, sans dépendance à `state`/`DATA`). Le rendu de la vue
(branché sur `state.memos` vs `DATA.memos`) reste par page, comme les sidebars.

## 6. Invariants

- **5** : zéro route nouvelle ; invités = données déjà dans `share_data`/`hub /data`,
  écritures scopées existantes ; rien de nouveau exposé.
- **6** : pas de lib externe, CSS grid maison, tout inliné au rendu Jinja.
- **8** : entrée de vue sans GSAP sur dialog ; GSAP éventuel sur les cases
  uniquement (comme les cards), avec `clearProps`.
- **9** : tokens/classes existants (chips façon `.badge`/`.prio-btn`, boutons
  `.task-actions`-like, couleurs via variables CSS).
- **1/2** : export/import strictement inchangés (aucun changement backend attendu).

## 7. Tests d'acceptation (validation Chrome par l'agent Cowork)

1. Grille juillet 2026 correcte (lun→dim, offsets, aujourd'hui surligné),
   navigation ‹ › / Aujourd'hui.
2. Chips aux bons jours, +N si >3, terminés/corbeille absents, couleurs
   priorité/projet correctes.
3. Panneau du jour : tri sans-heure-d'abord puis heures croissantes,
   « 14h30 » affiché, clic mémo → pop-in existante.
4. D&D owner : drop sur un autre jour → `due_date` changé, `due_time` conservé,
   case mise à jour ; drop sur jour hors-mois = no-op.
5. Invité `can_edit` (share ET hub) : D&D fonctionne (200, revalidé serveur) ;
   invité **lecture seule** : chips non draggables.
6. Mobile ≤900 px : liste par jour, pas de grille ; navigation mois OK.
7. Thèmes clair/sombre ; auto-refresh 15 s ne casse pas la vue (mois affiché
   conservé au re-render).
8. `python3 -m py_compile` (app.py ne devrait pas bouger) + export inchangé.

## 8. Hors périmètre (volontaire)

- Vue semaine, drag pour changer l'heure, création de mémo depuis une case
  (raffinements possibles en V19.15+).
- Persistance du mois affiché entre sessions.
- Notifications d'échéance (recoupe [NOTIFY-EMAIL]).
