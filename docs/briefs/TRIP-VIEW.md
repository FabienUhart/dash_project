# Brief CC — [TRIP-VIEW] : la vue Voyage façon Polarsteps (étapes + carte + trajets)

> _Renuméroté le 29 oct. 2026 : V30.4.286 est parti avec [MEMO-PRINT], V30.5.287 avec [MEMO-PDF] v2 ; lot 1 → **V30.6.x**, lot 2 → **V31.0.x** (Z fixé à la livraison, cf. REALISATION.md)._

> **Deux lots.** Lot 1 **V30.6.x** = front + 1 route batch de dates, **export 30 inchangé** (la
> préférence d'affichage vit en `localStorage` par dossier, V1). Lot 2 **V31.0.x** = table
> additive `trip_legs` → **bump export v31**. Doctrine TDD, STOP avant push, GO Fabien. Demande
> Fabien du 20 oct. 2026 (mémo prod 513) devant Polarsteps : « l'affichage de Polarsteps est mieux
> pour le suivi du voyage » ; « va pour coder ça aujourd'hui ». **Pas de maquette** (arbitrage
> Fabien) : les trois captures `docs/briefs/assets/trip-view-polarsteps-*.png` SONT la maquette.
> Cas de test réel : **Voyage Japon**, 1er → 19 nov. 2026 (prod dossier 3, local dossier 124),
> invités Manon et Thomy. Fenêtre : lot 1 en prod cette semaine, lot 2 avant le 1er nov.
> [TRIP-VIEW] et la Frise de [FOLDER-VIEWS] coexistent (deux entrées du futur sélecteur).

## 0. Contexte — à relire

- Ce qui existe : `projects.is_trip` (flag voyage hérité, `_clean_is_trip`), `memos.location`
  (`{lat,lng,label}`, `parseLoc`), `memos.due_date`/`due_end` ([MEMO-DATE-RANGE]), la carte
  `runMap` du partial avec sa frise [MAP-TIMELINE] (`datedPoints()`, `renderFrieze`,
  `switchDayThenLocate`, [FRISE-STEP-NOGPS]), [CARD-COVER] (1re photo), le géocodage, le drag
  tactile des listes, `.cover-seg` pour les segments, Luciole pour les boutons (invariant 9).
- Ce que Polarsteps apporte et qu'on n'a pas : **une colonne d'ÉTAPES ordonnées** (pas une liste
  de mémos datés), le compte des **nuits** avec − / +, le **tracé numéroté** qui relie les étapes
  dans l'ordre, et le **trajet** entre deux étapes. Capture 1 = l'écran cible, capture 2 = le
  choix du trajet, capture 3 = la carte seule.
- **Constat sur le vrai dossier** (Voyage Japon LOCAL = dossier **124**, sous-dossiers Activités
  Kyoto 128 / Tokyo 129, Activités Osaka 115 hors arbre ; prod = dossier 3) : les mémos datés
  existants sont des **activités d'un jour** (« 🏯 Château d'Osaka » 4 nov., « 🗼 Akihabara + Sky
  Tree » 12 nov.), 10 avec GPS. Polarsteps, lui, compte des **séjours** (Osaka 3 → 6 nov.). Donc :
  - **Étape = mémo à PLAGE de dates** (`due_end` > `due_date`) : un séjour, une ville, un hôtel.
    C'est elle qui porte le numéro, le marqueur, les nuits et le tracé.
  - **Activité = mémo d'un seul jour** : elle se range **sous l'étape qui couvre sa date**, dans
    une liste repliée « 8 activités » (chevron), chaque ligne = emoji + titre + jour, clic =
    ouvre le mémo ; ses marqueurs restent sur la carte en petit (sans numéro), reliés à rien.
  - Activités dont la date ne tombe dans aucune étape → section « Hors étapes · n » en bas de la
    colonne (clic = ouvre) ; ce sont elles qui invitent à créer l'étape manquante.
  - Avec `location` → marqueur ; sans → gris « sans position » ([FRISE-STEP-NOGPS], clic = inviter
    à géolocaliser). Mémos non datés : absents de la vue (ils restent dans la liste).
  - Sous-arbre inclus (les activités vivent dans les sous-dossiers). **Rien à changer aux
    activités existantes : le seed de démo (§ 1.6) ne pose que les 6 séjours.**

## 1. Lot 1 — V30.6.x : étapes + carte + nuits

### 1.1 Accès
- **Un sélecteur d'affichage** (Fabien, 14h22 : « faudrait que ce soit un choix possible, comme
  la Frise ») : segment `.cover-seg` en tête du board — **Liste · Voyage · Carte** — « Voyage »
  n'apparaissant que sur un dossier voyage (`is_trip` résolu vrai). C'est le même sélecteur que
  [FOLDER-VIEWS] remplira ensuite (Frise, Grille, Kanban, Bulles) : le composant est écrit pour
  accueillir d'autres entrées, chaque vue = une fonction `renderBoardView(mode)`. La frise
  actuelle de la carte ([MAP-TIMELINE]) reste un bouton DANS la vue Carte, inchangée.
- Préférence mémorisée par dossier en `localStorage['dash:tripView:<project_id>']` (V1, pas de
  colonne). Retour « Liste » = board actuel strictement inchangé.

### 1.2 Écran (desktop ≥ 901 px) — capture 1
- **Colonne gauche (≈ 40 %)** : en-tête « 1 → 19 nov. · 17/18 nuits » (nuits = somme des
  `(fin − début)` par étape ; le dénominateur = `(dernier jour − premier jour)` ; en rouge si
  trou ou chevauchement). Puis les **étapes** dans l'ordre des dates : pastille numérotée
  (couleur = `marker_color` sinon accent), **couverture** (1re photo du mémo, sinon emoji du
  mémo, sinon rien), **titre**, « dim. 01 nov. → lun. 02 nov. », bloc **« − n nuits + »**,
  poignée ⋮⋮ de réordonnancement, bouton ⋯ (ouvrir le mémo, retirer la date = sortir de la vue).
  Entre deux étapes : un rond « + » (crée un mémo daté au jour suivant la fin de l'étape, dans
  le dossier courant, titre vide focus) — le trajet (lot 2) viendra à côté.
- **Carte droite (≈ 60 %)** : `runMap` existant en mode voyage : marqueurs **numérotés** (même
  numéro que la colonne, `L.divIcon`), **polyline pointillée** reliant les étapes avec position
  dans l'ordre des dates (`dashArray`), fit bounds sur les étapes. **Synchro** : clic sur une
  étape → `setView` sur son marqueur + popup ; clic sur un marqueur → l'étape se surligne et
  défile dans la colonne. La frise [MAP-TIMELINE] est masquée en vue Voyage (la colonne la
  remplace), le bouton frise aussi.
- **Mobile ≤ 900 px** : colonne seule, plein écran ; la carte = onglet « Carte » existant ;
  dans la colonne, le « + » et les − / + restent au doigt (≥ 44 px).

### 1.2 bis Sous-dossiers et groupes : on GARDE ce qui existe (Fabien, 14h20 : « j'aimais bien les
sous-dossiers et les groupes qu'on pouvait trier sur la map »)
- La barre de filtres actuelle de la carte (**SOUS-DOSSIERS** avec Tous / Aucun / Inverser, et les
  **groupes** `map_groups`) reste affichée en vue Voyage, au même endroit, même composant. Un
  filtre agit sur les **activités** (points sur la carte ET lignes sous les étapes, avec le
  compteur « n activités » recalculé) ; les **étapes** (séjours) restent toujours visibles, numéros
  et tracé compris, pour ne jamais perdre le fil du voyage.
- Chaque ligne d'activité porte un petit badge de son sous-dossier (emoji/couleur du dossier,
  gabarit des chips existants) ; clic sur le badge = filtre sur ce sous-dossier.
- Un séjour peut aussi venir d'un **sous-dossier** : si un sous-dossier porte lui-même une plage
  de dates (le dossier a `location` et on lui ajoute des dates via son mémo « porteur » existant,
  cf. [FESTIVAL-FRISE-FOCUS] `passageInfo` / porteur), il compte comme une étape — V1 : on se
  limite aux mémos à plage ; noter la piste en REALISATION si elle s'avère simple.

### 1.3 Gestes et règles de dates (le cœur du lot)
- **− / + nuits** sur l'étape k : `due_end_k ± 1 j`, puis **décalage en chaîne** de toutes les
  étapes suivantes du même delta (début ET fin). Minimum 0 nuit (début = fin). Un seul appel :
  `POST /api/memos/batch-dates` `{changes:[{id, due_date, due_end}, …]}` owner (transaction,
  200 → liste des mémos mis à jour, `_log_revision` par mémo, auto-refresh). Invités : même
  logique via `POST /share/<token>/memos/batch-dates`, scopée au partage, gatée par la capacité
  d'édition existante (invariant 5), uniquement sur les mémos du partage.
- **Réordonner** (poignée, drag souris + tactile existant) : l'étape déplacée **prend les dates
  de sa nouvelle place** (recalcul : on garde la durée de chaque étape, on ré-enchaîne depuis le
  premier jour). Même route batch. Aucune écriture de `position`.
- **« + » entre deux étapes** : nouveau mémo `due_date = due_end(k)+1`, `due_end = idem`, les
  suivantes décalées d'un jour (batch). Annuler = corbeille (invariant 7).
- Tout ce qui est écrit est réversible (dates seulement, jamais de suppression).

### 1.4 Parité invités
- `share.html` / `hub.html` : même bouton « Voyage » si le partage porte un dossier voyage, même
  colonne, même carte (helpers dans `_shared.js.html`, ADR-001 : `tripSteps(memos)`,
  `tripNights(steps)`, `renderTripColumn(cfg)`). − / + et poignée visibles seulement avec la
  capacité d'édition ; « + » idem. Un invité ne voit que les mémos de son partage (déjà le cas).

### 1.5 Tests (rouges d'abord)
Back : (1) `batch-dates` décale 3 étapes d'un coup, transactionnel (une erreur → rien d'écrit) ;
(2) refuse un id hors partage côté share (404, rien modifié) ; (3) refuse sans capacité d'édition
(403) ; (4) `_log_revision` écrit une révision par mémo touché ; (5) export v30 inchangé
(fixture d'export → identique avant/après). E2E owner : (6) dossier voyage → bouton Voyage,
colonne avec les étapes dans l'ordre des dates et numéros = marqueurs ; (7) « + 1 nuit » sur
l'étape 2 → étape 3 et 4 décalées d'un jour, en-tête mis à jour ; (8) drag de l'étape 3 avant
la 2 → dates ré-enchaînées, durées conservées ; (9) clic étape → carte centrée, clic marqueur →
étape surlignée ; (10) dossier non voyage → pas de bouton ; (11) retour Liste = board inchangé.
E2E invité : (12) lecteur : colonne visible, aucun − / + ni poignée ; éditeur : − / + fonctionne
et n'écrit que dans son partage. Mobile 390 : (13) colonne plein écran, cibles ≥ 44 px.
Mutations : retirer la transaction (test 1), retirer le filtre share (test 2), inverser le sens
du décalage (test 7).

### 1.6 Seed de démonstration (LOCAL seulement)
`scripts/seed_trip_demo.py` : refuse de tourner hors localhost / si `APP_ENV=prod` ; idempotent
(tag `#demo-trip`) ; pose dans **Voyage Japon LOCAL (124)** les 6 **séjours** à plage de dates :
1 🛫 Toulouse 1 → 2 nov. (43.60, 1.44) · 2 🏯 Osaka 3 → 6 (34.69, 135.50) · 3 ⛩️ Kyoto 6 → 8
(35.01, 135.77) · 4 🏙️ Nagoya 8 → 10 (35.18, 136.91) · 5 ♨️ Hakone 10 → 12 (35.23, 139.11) ·
6 🗼 Tokyo 12 → 19 (35.68, 139.69), avec `location{lat,lng,label}`. Les 10 activités existantes
(3 → 6 nov. Osaka, 12 nov. Tokyo) doivent alors se ranger d'elles-mêmes sous Osaka et Tokyo :
c'est le test de la règle étape/activité. Lancer avant la capture du STOP.

## 2. Lot 2 — V31.0.x : trajets entre étapes (capture 2)

- Table additive `trip_legs (id, from_memo_id, to_memo_id, from_uid, to_uid, mode TEXT, km REAL,
  minutes INTEGER, note TEXT, created_at)`, UNIQUE(from, to). **Exportée** (v31) par uid, import
  tolérant, purge en cascade avec le mémo.
- Entre deux étapes de la colonne : bloc « 🚄 105 km · 1 h 45 » (icônes trait, une par mode :
  train, voiture, avion, bus, bateau, vélo, marche, moto). Clic → pop-in « Trajet de A à B » :
  liste des modes (radio, gabarit capture 2), **distance à vol d'oiseau pré-remplie** (haversine
  entre les deux `location`, arrondie), durée saisie (h / min), note. Pas de service d'itinéraire
  externe, pas de clé Mapbox : V1 manuelle, point.
- Sur la carte : le segment du tracé prend le style du mode (train = trait plein, avion = arc
  pointillé long, bateau = tirets), popup = le bloc trajet.
- Routes owner + share scopées, API v1 (`GET/PUT /api/v1/memos/<id>/legs`) + outil MCP
  `set_trip_leg`. Tests : haversine Toulouse → Osaka ≈ 9 9xx km (tolérance 1 %), cascade,
  export/import v31 + v30 toujours importable, invariant 5.

## 3. Livraison
Lot 1 : `REALISATION.md` [V30.6.x], brief ↔ IDEAS.md ([TRIP-VIEW] retiré de la file après le
lot 2 seulement), handoff pour la passe Cowork (owner desktop sur Voyage Japon local 124, mobile
390, invité Demo invité 142 / share 87 si le dossier est voyage, sinon créer un partage lecteur sur
Voyage Japon LOCAL). STOP avant commit avec la ligne pytest.
**Hors périmètre** : sélecteur général d'affichage ([FOLDER-VIEWS]), Frise générique, Travel Book
(MEMO-PDF), calcul automatique d'itinéraire.
