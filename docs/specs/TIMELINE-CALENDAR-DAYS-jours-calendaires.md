# [TIMELINE-CALENDAR-DAYS] — Frise voyage : des « Jours » qui collent au calendrier

**Brief pour Claude Code — lot V26.4.Z (frontend pur, EXPORT v26 INCHANGÉ, zéro route,
`app.py` intact).** Lire `CLAUDE.md` avant. Z = compteur continu de `REALISATION.md`.
À lancer APRÈS [MEMO-CARD-CLICK] (V26.3) — son helper `scrollToMemo` est réutilisé ici.

## 1. Contexte (demande Fabien, nuit du 23 juil., après édition des dates d'hôtels)

Dans la frise d'un dossier voyage (`is_trip`), « Jour N » = la N-ième DATE DISTINCTE
portant un mémo. Exemple réel : arrivée le 3 nov, mémos le 3 et le 6, rien les 4-5 →
le 6 nov s'affiche « Jour 2 » alors que c'est le 4ᵉ jour du séjour ; et déplacer la date
d'un hôtel fait glisser TOUTE la numérotation. La frise raconte « les mémos dans l'ordre »
au lieu de « le voyage jour par jour ».

## 2. Décisions (validées Fabien — implémenter, ne pas rediscuter)

- **D1 — Jour N = date de DÉBUT du voyage + (N−1) jours CALENDAIRES.** Numérotation
  continue sur toute la plage du voyage : du **min(due_date)** au **max(due_end, due_date)**
  des mémos du périmètre de la frise (dossier `is_trip` résolu + descendants — MÊME
  périmètre que la frise/carte actuelle, ne pas l'élargir). S'appuyer sur les helpers
  existants de plages (`memoDays`/`memoCoversDay`, [MEMO-DATE-RANGE]) — un mémo à plage
  couvre chacun de ses jours (l'hôtel 3→6 est présent aux Jours 1,2,3,4).
- **D2 — Les jours SANS mémo existent** : chip/tuile présente mais DISCRÈTE (grisée,
  gabarit réduit, style tokens muted) — c'est l'outil de repérage des trous du planning.
  Cliquable comme un jour normal (applyDay → état vide propre du jour).
- **D3 — Condensation des grands trous** : à partir de **3 jours vides consécutifs**, une
  seule chip condensée « Jours 8–12 · rien » (au lieu de 5 chips) — garde la frise lisible
  si un mémo isolé étire la plage (ex. un « vol retour » lointain). Clic sur la chip
  condensée → non-action V1 (ou déplie les jours, si trivial — sinon hors périmètre).
- **D4 — Recalcul IMMÉDIAT** au changement d'une date/plage (pas de cache, pas d'état
  résiduel) : éditer l'hôtel re-numérote la frise à la volée, comme le reste du re-render.
- **D5 — Cohérence totale** : les tuiles de la frise, `applyDay` (filtre d'un jour sur la
  carte), et tout libellé « Jour N » affiché (badges, pop-ins) suivent LA MÊME règle —
  une seule fonction de correspondance jour↔date, mutualisée dans le partial.
- **D6 — Parité 3 pages** : carte/frise voyage owner ET pages invité (share/hub) — Marie
  voit les mêmes « Jours » que Fabien. Invariant 5 : aucun élargissement de périmètre.
- **D7 — Zéro nouveau réglage** : la date de début n'est PAS une donnée à saisir — c'est
  le min des dates du dossier. (Si un jour Fabien veut une date de début explicite par
  voyage, ce sera un lot séparé avec bump d'export — hors périmètre ici.)

## 3. Implémentation — points d'attention

- Fonction unique `tripDayIndex(iso, tripRange)` / `tripDayDate(n, tripRange)` dans
  `_shared.js.html`, consommée par les 3 pages (invariant 9). Timezone : rester en dates
  ISO « YYYY-MM-DD » calendaires (pas d'objets Date à minuit local pour compter — piège
  DST : compter en UTC ou par différence de chaînes via un util existant).
- Mémos SANS date dans le dossier voyage : hors frise (comportement actuel conservé).
- Un seul mémo daté → plage d'un jour, « Jour 1 » ; zéro mémo daté → frise absente
  (comportement actuel).
- Réutiliser `scrollToMemo`/flash ([MEMO-CARD-CLICK]) si la frise navigue vers des mémos.
- Ne PAS toucher à l'agenda général ni à la pop-in jour ([AGENDA-DAY-POPIN]) — seul le
  monde « voyage » (frise/carte des dossiers is_trip) est concerné.

## 4. Acceptation (validation Cowork ensuite — données réelles Voyage Japon)

1. Hôtel Osaka 3→6 nov + mémos réels : le 6 nov = « Jour 4 » (plus « Jour 2 ») ; l'hôtel
   apparaît aux Jours 1-4 ; les jours réellement vides sont visibles en chips grisées.
2. ≥ 3 jours vides consécutifs → chip condensée « Jours X–Y · rien ».
3. Déplacer la date d'un hôtel → renumérotation immédiate, aucune valeur en cache.
4. applyDay depuis un jour vide → état vide propre ; depuis un jour plein → mémos du jour.
5. Parité invité (share du dossier voyage + hub) : mêmes numéros de Jours.
6. `node --check` 3 pages + partial ; `py_compile` (app.py intact) ; export toujours 26.

## 5. Fin de réalisation

Journal IDEAS→REALISATION [V26.4.Z], rebuild local, handoff ready.
**Ni commit ni push** sans feu vert Fabien (validation Cowork d'abord).
