# Plan d'implémentation — [IMAGE-EXIF]

> Compagnon de la spec verrouillée [IMAGE-EXIF-photo-metadata-badge.md](IMAGE-EXIF-photo-metadata-badge.md). Plan = comment ; spec = quoi. Ancres `file:line` au 2026-06-26.

EXIF lu à la volée, **jamais stocké/exporté**, **affichage seul** (badge par image), **aucune écriture mémo**, parité owner/invité scopée. `_build_export` et `APP_VERSION` **non touchés**.

## Lib
`exifread==3.0.0` (pur Python, lecture seule, pas Pillow) → `requirements.txt`. Dockerfile inchangé (`pip install -r requirements.txt`). Même pattern self-hosté que `qrcode`.

## Ancrage
- Upload signature `_save_uploaded_image` `app.py:51` (intact) ; routes upload `:1428` owner / `:2494` invité (intactes).
- Serve owner `/uploads/<filename>` `:1420` (`SAFE_IMG_NAME` `:35`, `UPLOAD_DIR` `:31`).
- Serve invité `/share/<token>/image/<name>` `:2837` — **contrôle de scope à recopier** : `_share_by_token` `:1607` → `SAFE_IMG_NAME` → boucle `_share_scope_memos` `:1635` → `name in row.images` sinon 404.
- `_reverse_geocode(lat,lng)` `:371` → string « place, city » ≤80c ou `""` (try/except silencieux). `_clean_location` `:341` (garde lat/lng bornées).
- Cache mémoire modèle `_favicon_cache` `:1542`.
- Front : `runImageViewer(cfg)` `_shared.js.html:505` (contrat cfg :501, render :548) ; `thumbsEl` `index.html:3591` (cfg viewer :3600) ; miniatures invité `share.html:1706` (cfg :1714, `API` :618).

## Étapes (commits atomiques)
1. **dep** — `exifread==3.0.0` dans `requirements.txt`.
2. **server: _image_exif** — près de `:371`, cache module `_exif_geo_cache = {}` (modèle `_favicon_cache`). `import exifread`. `_exif_dms_to_deg(value, ref)` (DMS Ratio→décimal, négatif si S/W, try/except→None). `_image_exif(name)` : path dans `UPLOAD_DIR` ; `exifread.process_file(f, details=False)` dans try/except→None ; GPS (`GPS GPSLatitude/Ref/Longitude/Ref`) borné comme `_clean_location` ; date `EXIF DateTimeOriginal` (`YYYY:MM:DD HH:MM:SS`→ISO) ; **si ni GPS ni date → None** ; label via cache `key=(round(lat,4),round(lng,4))` sinon `_reverse_geocode` (mémoriser aussi `""` → anti-abus) ; retourne `{lat,lng,label,datetime}`.
3. **server: routes** — owner `GET /api/image-exif/<name>` (près `:1420`) : basename + `SAFE_IMG_NAME` sinon 404, `jsonify(_image_exif(name) or {})`. Invité `GET /share/<token>/image-exif/<name>` (après `:2837`) : **copier verbatim** le contrôle de scope de `share_image`, sur match → `jsonify(_image_exif(name) or {})`, sinon 404 (invariant 5).
4. **front: badge dans le viewer** — `runImageViewer` : étendre cfg `exifUrl(name)` (optionnel). `el('div',{class:'iv-exif'})` ajouté à `stage`, masqué par défaut. Dans `render()` : reset badge, garde `if(cfg.exifUrl)`, `fetch(cfg.exifUrl(name))` + jeton de course (index inchangé) → si `label||datetime` : `📷 ` + `[label, fmtExifDate(datetime)].filter(Boolean).join(' · ')`, sinon masqué (repli coords si label vide). Helper format date local (style `fmtMemoTime`). Sûr seul (sans exifUrl → no-op).
5. **front: wire** — `index.html` thumbsEl cfg `:3600` : `exifUrl:(n)=>'/api/image-exif/'+n`. `share.html` `:1714` : `exifUrl:(n)=>API+'/image-exif/'+n`. (Optionnel non retenu v1 : badge sur la miniature — multiplie les fetch.)

## Confirmations
Aucune écriture mémo (routes GET seules). Aucun stockage (zéro migration ; seul dict mémoire non persistant). Export inchangé (`_build_export` `:2863` + `APP_VERSION` `:30` intacts). Upload accept path intact. Invariant 5 (scope invité recopié), invariant 8 (badge enfant de stage, pas de GSAP sur dialog).

## Tests → Done-when
`python3 -m py_compile app.py` ; `pip install -r requirements.txt` ; `cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run`. Photo JPG GPS-taguée + screenshot (EXIF strippé).
1. Badge si EXIF (owner). 2. Pas d'EXIF → pas de badge, pas d'erreur. 3. Mémo intact (location/due_date/due_time inchangés via `/api/memos`). 4. Rien persisté (restart → même badge depuis fichier). 5. Export inchangé (diff identique, version 18). 6. Parité+scope invité (in-scope badge ; hors-scope `/share/<t>/image-exif/<x>` → 404). 7. Dégradation géocodeur (bloquer nominatim → image OK, badge dégradé). 8. Géocodeur non abusé (ré-ouvrir → 1 seul appel par coords, cache). 9. Dep self-hostée.

## Risques/ordre
Étape 1 avant 2-3 (sinon `import exifread` casse le boot). Étape 4 sûre seule (garde cfg.exifUrl). Perf Nominatim : cache `(round4)→label` (mémorise `""`), option Lock+1s. Tags EXIF tolérants (try/except→no-op). Invariant 5 : ne pas factoriser la route invité hors scope.

## Fichiers
requirements.txt · app.py (`_image_exif`+cache ~:371, routes ~:1420/~:2837 ; export :2863 / APP_VERSION :30 NON touchés) · templates/partials/_shared.js.html (`runImageViewer` :505) · templates/index.html (`thumbsEl` :3591) · templates/share.html (:1706/:1714)
