# Brief CC — [MAP-NO-AUTOPAN] : la carte ne bouge plus toute seule au survol

> **Front pur (`_shared.js`), zéro route, `app.py` intact, export 28 inchangé.** Constat Fabien du
> 30 sept. 2026 sur la carte Voyage Japon : « je regarde mes points et la carte change toute seule
> pour aller sur ce point, c'est gênant ». Doctrine TDD. Cible **V28.9.276** ([GUEST-SEARCH-GRAMMAR]
> passe en V28.10.277).

## 1. Cause

`wireMarkerPopup` (~l.1461) ouvre la bulle **au survol** (150 ms). Les marqueurs mémo sont liés par
`marker.bindPopup(buildMarkerPopup(p))` (~l.1864) **sans option** → Leaflet applique `autoPan: true`
par défaut et **déplace la carte** pour faire tenir la bulle dès qu'un point est près d'un bord. Sur
une grappe de points (Tokyo : 29), promener la souris fait dériver la carte. Les bulles de passage
(`showPassagePopup`, l.2110) ont déjà un `autoPan` explicite ; les bulles photo (l.2382) ont le même
défaut.

## 2. Décision

1. `bindPopup(…, { autoPan: false })` pour les marqueurs mémo/projet (l.1864) **et** photo (l.2382).
   Le survol n'a plus aucun effet sur la vue ; la bulle peut être partiellement hors cadre, c'est
   accepté (le point est sous la souris).
2. Le **clic** garde un recadrage volontaire : ligne de liste → `setView(ll, 16)` (existant) ;
   marqueur → épingle + bulle, **sans** déplacer (le point est déjà visible). Frise et chip de jour :
   inchangés (`setView` explicite existant).
3. Rien d'autre ne change : clusters, `fitBounds` initial, filtres, épingle, `restorePin`.

## 3. Tests (TDD — rouges d'abord)

`tests/front/test_map_no_autopan.py` (dossier avec ~6 mémos géolocalisés dont un placé pour tomber
près du bord droit après `fitBounds` ; carte ouverte via la tuile Carte) :
1. Relever `map.getCenter()` (via `window.__activeMap` de test ou l'instance exposée par la page),
   survoler le marqueur du bord (`page.hover` sur `.leaflet-marker-icon` / circle path), attendre
   400 ms → bulle ouverte **et** centre identique (tolérance 1e-6).
2. Cliquer la ligne de liste du même mémo → centre = son `lat/lng`, zoom 16.
3. Survoler une vignette photo géolocalisée (calque Photos activé) → centre identique.
4. Zéro erreur console.
Mutations : `autoPan: false` retiré sur les mémos (1 rougit) ; retiré sur les photos (3 rougit).

## 4. Livraison

`templates/partials/_shared.js.html`, `tests/front/test_map_no_autopan.py`, `REALISATION.md`,
`IDEAS.md`, ce brief. Cycle habituel, **STOP** au rebuild local, passe Cowork (carte locale Voyage
Japon), GO.
