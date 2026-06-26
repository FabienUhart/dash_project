# Plan d'implémentation — [PHOTO-CLUSTER]

> Compagnon de la spec verrouillée [PHOTO-CLUSTER-marker-clustering.md](PHOTO-CLUSTER-marker-clustering.md). Plan = comment ; spec = quoi. Ancres `file:line` au 2026-06-26 (après [PHOTO-MAP]).

**Front pur.** Aucun changement serveur/schéma/export/`image_meta`. Clusterise **uniquement** le calque photo de `[PHOTO-MAP]` (dans `runMapDialog`, partial partagé). Plugin **Leaflet.markercluster auto-hébergé** dans `static/`, whitelisté `/share/assets`, **dégrade** en marqueurs simples si absent. Points-mémo (`markerLayer`) **non touchés**.

## Lib
**Leaflet.markercluster 1.5.3** (dist), 3 fichiers dans `static/` :
- `leaflet.markercluster.js` (≈ 33 ko)
- `MarkerCluster.css` (styles de base : positionnement spiderfy)
- `MarkerCluster.Default.css` (thème compteur : pastilles `.marker-cluster-*`)
Récupérés **au build** (comme `leaflet.js`/`gsap.min.js`), depuis le paquet npm `leaflet.markercluster@1.5.3` (`dist/`). **Aucun CDN au runtime** (invariant 6). Dockerfile inchangé (fichiers servis depuis `static/`).

## Ancrage
- Calque photo : `runMapDialog` partial. `drawPhotos()` `_shared.js.html:310` (markers `L.marker`+divIcon `:316-320`, `.addTo(photoLayer)` `:318`), `togglePhotos()` `:345` (`photoLayer = L.layerGroup().addTo(activeMap)` `:353`, remove `:356`), `photoFocus(ph)` `:308`, `refresh()` `:381`. Points-mémo : `markerLayer` `:80` (intact).
- Whitelist invité : `SHARE_ASSETS` `app.py:2423`. Route `/share/assets/<name>` (liste blanche).
- Includes owner : `index.html:10-11` (`/static/leaflet.css` + `leaflet.js`). Invité : `share.html:11-12` (`/share/assets/...`).

## Étapes (commits atomiques)

1. **assets** — déposer `leaflet.markercluster.js`, `MarkerCluster.css`, `MarkerCluster.Default.css` dans `static/` (build-time, pas de fetch runtime).

2. **whitelist invité** — `SHARE_ASSETS` `:2423` : ajouter les 3 noms exacts (`"leaflet.markercluster.js","MarkerCluster.css","MarkerCluster.Default.css"`). Rien d'autre (invariant 5 : seuls ces fichiers exposés).

3. **includes templates** — `index.html` après `:11` : 2 `<link rel=stylesheet href="/static/MarkerCluster.css">` + `.../MarkerCluster.Default.css`, puis `<script src="/static/leaflet.markercluster.js" defer></script>` **après** `leaflet.js` (le plugin étend `L`, `defer` garde l'ordre). `share.html` après `:12` : idem en `/share/assets/...`. Plugin absent → `<script>` 404 silencieux, `L.markerClusterGroup` reste `undefined` → dégradation (étape 5).

4. **calque grisé séparé** — `_shared.js.html` : nouvelle variable `photoGreyLayer` à côté de `photoLayer` `:298`. Raison : un cluster ne peut pas « griser » un membre individuellement. Décision (spec → compteur = photos **affichées**) : les photos **en focus** vont dans le cluster (`photoLayer`), les photos **hors focus** (grisées) vont dans un `L.layerGroup` plain non clusterisé (`photoGreyLayer`), gardant l'opacité 0.35. Sans filtre actif, `photoFocus` est vrai partout → tout dans le cluster, calque gris vide.

5. **cluster group + dégradation** — `togglePhotos()` `:353` : remplacer
   `photoLayer = L.layerGroup().addTo(activeMap)` par
   `photoLayer = (typeof L.markerClusterGroup === 'function' ? L.markerClusterGroup({ showCoverageOnHover:false, maxClusterRadius:40, spiderfyOnMaxZoom:true, zoomToBoundsOnClick:true }) : L.layerGroup()).addTo(activeMap)` ;
   `photoGreyLayer = L.layerGroup().addTo(activeMap)`. À l'extinction `:356` : `remove()` les deux. `spiderfyOnMaxZoom`/`zoomToBoundsOnClick` (défauts) couvrent l'éventail au **même point exact** (cas Bayonne) ET la séparation au zoom. Plugin absent = `L.layerGroup` → comportement [PHOTO-MAP] inchangé (marqueurs simples, tous cliquables, 0 erreur).

6. **drawPhotos split focus/grisé** — `drawPhotos()` `:310-322` : `photoLayer.clearLayers()` **et** `photoGreyLayer.clearLayers()` ; pour chaque photo, `marker.addTo(focused ? photoLayer : photoGreyLayer)`. Le clic `cfg.openImage` et la popup restent identiques sur chaque marqueur (donc spiderfié = ouvrable). `refresh()` `:381` rappelle `drawPhotos()` à chaque changement de filtre → compteur du cluster recalculé sur les photos en focus.

## Confirmations (spec → plan)
- **Calque photo only** : seules `photoLayer`/`photoGreyLayer` changent ; `markerLayer` (mémo) intact. ✓
- **Auto-hébergé, pas de CDN** : 3 fichiers `static/`, includes locaux, whitelist invité. ✓
- **Badge compteur + split zoom + spiderfy** : `markerClusterGroup` défauts (`spiderfyOnMaxZoom`, `zoomToBoundsOnClick`, thème `.Default.css`). ✓
- **Clic photo → visionneuse** : `cfg.openImage` inchangé sur chaque marqueur. ✓
- **Dégradation** : ternaire `typeof L.markerClusterGroup === 'function'` → repli `L.layerGroup` (= [PHOTO-MAP]). ✓
- **Parité invité (inv. 5)** : mêmes includes via `/share/assets`, whitelist limitée aux 3 fichiers ; données photo toujours scopées (endpoint [PHOTO-MAP] inchangé). ✓
- **Focus préservé (inv. lié)** : focus → cluster, grisé → calque plain ; compteur = photos affichées. ✓
- **Pas de GSAP sur `<dialog>` (inv. 8)** : animations cluster/spiderfy = marqueurs Leaflet, jamais le dialog. ✓
- **Export/données inchangés** : zéro ligne serveur. `APP_VERSION`/`_build_export`/`image_meta` non touchés. ✓

## Tests → Done-when
`cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run`. Jeu : ≥3 photos GPS proches, ≥2 au **même** point exact, 1 sous-projet, photos grisables par filtre.
1. **Cluster + compteur** : 📷 → 1 pastille « N » au lieu de N pins superposés (bas zoom).
2. **Split zoom** : zoomer → clusters plus petits → marqueurs isolés.
3. **Spiderfy point identique** : 2 photos mêmes coords → clic cluster = éventail, chaque marqueur ouvre **sa** photo.
4. **Marqueur isolé → visionneuse** : clic = bonne image (`runImageViewer`).
5. **Dégradation** : renommer/bloquer les 3 fichiers → marqueurs simples, tous cliquables, 0 erreur console, dialog OK.
6. **Parité invité + whitelist** : carte partagée invité → mêmes clusters, fichiers servis par `/share/assets`, aucun autre asset exposé.
7. **Filtrage préservé** : activer un focus sous-projet/groupe → compteur cluster = nb de photos en focus (grisées hors cluster, visibles).
8. **Pas de CDN** : offline → clustering OK (aucune requête sortante d'asset).
9. **Pas de régression dialog** : `#map-dialog` centré, `::backdrop` OK, 0 transform GSAP.
10. **Points-mémo inchangés** : carte avec mémos localisés = comportement identique à avant.

## Risques / ordre
- Étape 3 (includes) après 1 (fichiers présents) sinon 404 — mais 404 = dégradation propre, pas de casse.
- Ordre script : `leaflet.markercluster.js` **après** `leaflet.js` (sinon `L` undefined au chargement du plugin). `defer` préserve l'ordre du DOM.
- CSS seul absent (JS présent) : clusters fonctionnels mais non stylés — dégradation acceptable, whitelister les 2 CSS pour l'éviter.
- `.addTo(group)` marche pour `MarkerClusterGroup` ET `LayerGroup` (`marker.addTo` → `group.addLayer`), donc un seul chemin de code focus/grisé.
- Ne **pas** clusteriser `markerLayer` (mémo) — périmètre strict.
- Récupération build-time des fichiers : si pas de réseau au moment de l'impl, déposer manuellement les 3 fichiers du paquet `leaflet.markercluster@1.5.3`.

## Fichiers
`static/` (+3 : `leaflet.markercluster.js`, `MarkerCluster.css`, `MarkerCluster.Default.css`) · `app.py` (`SHARE_ASSETS` `:2423`) · `templates/index.html` (includes `~:11`) · `templates/share.html` (includes `~:12`) · `templates/partials/_shared.js.html` (`photoGreyLayer` `~:298`, `togglePhotos` `:353/356`, `drawPhotos` `:310-322`). Serveur/export **non touchés**.
