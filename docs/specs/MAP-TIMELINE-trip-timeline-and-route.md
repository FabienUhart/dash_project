# SPEC — [MAP-TIMELINE] Frise chronologique + itinéraire « voyage » sur la carte

**Statut : VERROUILLÉE — décisions validées par Fabien (2 juil. 2026, maquette approuvée).**
Cible : **V20.1** — ⚠️ **BUMP DU FORMAT D'EXPORT → v20** (invariant 1 : nouvelle
entrée de compat, `APP_VERSION` → "20"). Zone sensible : format de données.
[MAP-ROUTES] du backlog est absorbé par ce lot.

---

## 1. Décisions figées

1. **Frise + curseur « aujourd'hui »** : pour **tout projet daté** (pas seulement
   les voyages) — jalons/échéanciers en profitent.
2. **Tracé itinéraire** : **réservé aux « voyages »**, via un flag **héritable au
   plus proche** porté par les projets/sous-projets.
3. Mémos **datés sans GPS** : présents dans la frise (non centrables).
4. **Parité invité directe** (la carte est mutualisée dans `runMapDialog`).

## 2. Le flag « voyage » (héritable)

### Modèle (additif, non destructif)
```
projects.is_trip INTEGER DEFAULT NULL   -- NULL = hérite, 1 = voyage, 0 = pas voyage
```
Migration `PRAGMA table_info` + `ALTER TABLE` (jamais de DROP).

### Résolution « au plus proche » (helper unique, ex. `_resolve_trip(db, project_id)`
côté serveur si besoin, et helper front partagé)
Pour un projet P : remonter P puis ses ancêtres ; le **premier `is_trip` non NULL
rencontré** tranche (1 = voyage, 0 = non). Aucun ancêtre tranché → **pas voyage**
(défaut). Un point-mémo hérite du statut de SON projet. La carte d'un parent
non-voyage contenant un sous-arbre voyage trace donc l'itinéraire **de ce
sous-arbre seulement**.

### UI owner
Pop-in projet : ligne « ✈️ Voyage » avec **3 chips** (`.prio-btn`) :
**Hérité (défaut) / Oui / Non** → PUT `/api/projects/<id> {is_trip: null|1|0}`.
Afficher entre parenthèses la valeur héritée résolue quand « Hérité » est
sélectionné (ex. « Hérité (voyage, via 🗻 Japon) »).

### Invités
`share_data` / hub `/data` : les projets exposent `is_trip` **résolu par le
serveur** (booléen `trip` déjà calculé, pour ne pas exiger l'arbre complet côté
invité — l'arbre du partage peut être tronqué au scope). **Lecture seule** pour
les invités (pas d'édition du flag via `/share`, même `can_edit` — c'est un
réglage de structure owner, comme la couleur par défaut de la carte).

## 3. Export / import v20 (invariant 1)

- Export : `version: 20` ; chaque projet gagne `is_trip` (null/0/1, valeur BRUTE
  non résolue).
- Import : compat **v1→v19** (champ absent = NULL = hérite → rendu identique,
  compat ascendante garantie) ; **upsert non destructif** (newer-wins n'écrase
  jamais un `is_trip` tranché (0/1) par un absent/NULL plus ancien).
- Scénario de test rituel : ré-import d'un export complet → 0 ajout ;
  import v19 → pas de doublon, `is_trip` reste NULL partout.
- `APP_VERSION` → "20", footer « v20 », entrée v20 ajoutée à l'invariant 1 de
  CLAUDE.md au moment du lot.

## 4. Frise chronologique (tout projet daté) — dans `runMapDialog`

- **Bande horizontale sous la carte** : les mémos **datés** du périmètre courant
  (projet + descendants, mêmes filtres focus sous-projet/groupes), triés
  `due_date` + `due_time` (réutiliser `agendaDayCompare`). Étape = date courte
  + emoji/titre ellipsé **+ miniature de la 1re image du mémo s'il en a une**
  (réf. Roamy/Polarsteps — URL d'image via le résolveur DE LA PAGE : `/uploads/`
  owner, `/share/<t>/image/` invité, invariant 5) ; clic = centrer + popup ;
  **sans GPS** = affichée, non centrable, style discret distinct. Défilement
  horizontal si longue.
- **Groupement par jour** (réf. Roamy) : séparateurs de jour dans la frise +
  **chips « Jour 1 · 5 nov », « Jour 2 »…** cliquables (clic = faire défiler la
  frise à ce jour ET mettre en avant ses étapes ; re-clic = tout). Chips
  visibles quand le périmètre couvre ≥2 jours ; style `.prio-btn`.
- **Curseur « aujourd'hui »** : barre de progression remplie jusqu'à aujourd'hui
  + repère vertical étiqueté ; passées **estompées + ✓**, étape du jour
  **halo accent**, futures normales.
- **Reflet marqueurs** : point daté passé = opacité ~0.45, point du jour = halo —
  **couleurs existantes intactes** (priorité/projet/`marker_color`, système v16).
  Mémos sans date : marqueurs strictement inchangés.
- **Masquable** (bouton, persisté localStorage par projet, comme le calque 📷) ;
  visible seulement si ≥1 mémo daté dans le périmètre.

## 5. Tracé itinéraire (voyages seulement)

- Polyline **pointillée** Leaflet (`dashArray`, Leaflet core — invariant 6),
  reliant dans l'ordre chronologique les points **GPS + datés** dont le projet
  **résout à « voyage »** (§2), restreinte aux points « en avant » (même focus),
  recalculée à chaque changement de focus. Jamais de segment vers un point sans
  GPS, sans date, ou non-voyage.
- Aucun tracé nulle part si aucun point du périmètre ne résout à voyage
  (le cas « Maison » : frise oui, trajets non — la problématique d'origine).
- **Marqueurs-vignettes des étapes du voyage** (réf. Polarsteps) : pour les
  points GPS+datés qui résolvent à « voyage », le marqueur devient un
  **cercle-vignette** (1re image du mémo, `divIcon` rond, liseré = la couleur
  résolue du point — système v16 préservé) surmonté d'un **badge numéroté**
  ①②③ dans l'ordre chronologique ; **sans image** = cercle numéroté simple
  (même liseré couleur). Les points non-voyage, sans date, et le calque 📷
  gardent leurs marqueurs actuels. ⚠️ Perf : les images sont servies pleine
  taille (pas de thumbnails serveur) — vignettes en `background-size:cover`,
  chargement au moment de l'affichage du calque ; si ça pèse sur le Zimaboard,
  le lot compagnon sera [IMAGE-LAZY-LOAD] (backlog), PAS de génération de
  miniatures dans ce lot.

## 6. Invariants

- **1/2** : bump v20 discipliné (§3), migration additive idempotente.
- **5** : aucune route publique nouvelle ; invités = `trip` résolu en lecture
  seule dans les payloads existants ; flag éditable owner-only.
- **6** : aucune lib nouvelle (polyline = Leaflet core) ; helpers purs communs
  → `_shared.js.html` (ADR-001, diff strict).
- **8** : rien n'anime le `<dialog>`. **9** : tokens/classes existants.
- Le calque photos 📷 et sa frise « Où on était » restent **inchangés**.

## 7. Tests d'acceptation (validation Chrome par l'agent Cowork)

1. Migration sur copie + `py_compile` ; export → `version: 20`, `is_trip` présent ;
   ré-import complet → 0 ajout ; import d'un export v19 → 0 doublon, NULL partout.
2. Pop-in projet : chips Hérité/Oui/Non, héritage résolu affiché, PUT OK.
3. Projet « voyage » : frise triée, curseur entre passé et futur, sans-GPS non
   centrable, tracé pointillé dans l'ordre chronologique, marqueurs estompés/halo
   avec couleurs préservées ; **marqueurs-vignettes** : mémo avec image = cercle
   photo + badge n° (image chargée via la route DE LA PAGE — vérifier côté invité
   `/share/<t>/image/`), sans image = cercle numéroté ; ordre des numéros =
   chronologie ; **chips de jour** cliquables quand ≥2 jours, vignettes dans la
   frise.
4. Projet daté NON voyage : frise + curseur SANS tracé.
5. Héritage : parent non tranché + sous-projet « Oui » → carte du parent = tracé
   sur le sous-arbre seulement ; parent « Oui » → tout le périmètre tracé ;
   sous-projet « Non » sous un parent « Oui » → exclu du tracé.
6. Focus sous-projet/groupes : tracé et frise suivent les points « en avant ».
7. Invités (share + hub) : frise/tracé identiques, `trip` résolu reçu, flag
   non éditable ; invité lecture seule = interactions de consultation seulement.
8. Masquage de la frise persisté ; mobile utilisable (bande défilable).

## 8. Hors périmètre (volontaire)

- Édition du flag par les invités ; notion de « dates du voyage » distinctes des
  échéances ; réordonnancement manuel des étapes (l'ordre = chronologie) ;
  habillage spécifique « mode voyage » au-delà du tracé et des marqueurs-vignettes.
- **Distances entre étapes, durées de trajet, liens « Directions »** (écartés par
  Fabien le 2 juil. — pas de calcul à vol d'oiseau ni de lien externe dans ce lot).
- Génération de miniatures côté serveur (→ [IMAGE-LAZY-LOAD] si besoin perf).
