# Plan d'implémentation — [PHOTO-MAP]

> Compagnon de la spec verrouillée [PHOTO-MAP-photo-itinerary.md](PHOTO-MAP-photo-itinerary.md). Plan = comment ; spec = quoi. Ancres `file:line` au 2026-06-26.

EXIF **persisté à l'ajout** (table dérivée `image_meta`), lu en masse par la carte. **Aucune écriture mémo**, parité owner/invité **scopée**. `_build_export` `:2971` + `APP_VERSION` `:30` **non touchés** (donnée dérivée, jamais exportée). Réutilise `_image_exif` `:429`, `runMapDialog` `_shared.js.html:62`, `runImageViewer` `:507`, `_project_descendants` `:878`, `_share_scope_memos` `:1722`.

## Modèle — table `image_meta` (dérivée, non exportée)
`CREATE TABLE IF NOT EXISTS image_meta` dans `init_db()` (après `memo_comments` ~`:273`) :
- `filename TEXT PRIMARY KEY` (= clé image, `uuid.ext`, déjà unique)
- `memo_id INTEGER`, `memo_uid TEXT` (rattachement/diag)
- `lat REAL`, `lng REAL` (NULL si pas de GPS)
- `label TEXT DEFAULT ''` (reverse-geocode au moment de l'ajout)
- `taken_at TEXT DEFAULT ''` (ISO `YYYY-MM-DDTHH:MM:SS` ou date seule, depuis `_image_exif` `datetime`)
- `has_gps INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT`
Pas d'`ALTER` additif (table neuve, `IF NOT EXISTS` = migration idempotente, jamais destructive — invariant repo).

## Ancrage
- `_image_exif(name)` `:429` → `{lat,lng,label,datetime}` ou `None`. Cache `_exif_geo_cache` `:427` (un géocode par coords, mémorise `''`). `_reverse_geocode` `:372`.
- Upload owner `add_memo_image` `:1515` (après `_save_uploaded_image` `:1524`, `memo_uid` via `existing['uid']`). Upload invité `share_add_image` `:2581` (après `:2598`, scope déjà vérifié `:2592`).
- Suppr image owner `delete_memo_image` `:1541` (`os.remove` `:1557`). Invité `share_delete_image` `:2616` (`os.remove` `:2639`).
- Purge fichiers définitive `_delete_image_files` `:1076` — appelée `:1418` (suppr mémo def.) et `:3096` (`_purge_trash`, handle = `conn` pas `get_db`).
- Scope projet `_project_descendants(db, root)` `:878` (récursif). Scope invité `_share_scope_memos(db, share)` `:1722` (exclut corbeille). `_share_by_token` `:1694`, gate invité approuvé = modèle `share_data` `:2328` / `_guest_from_request`.
- Front carte : `runMapDialog(cfg)` `:62` (contrat cfg `:67-97`, `isFocused`/`subToken`/`groups` `:96-113`, `draw` `:196`, `refresh` `:294`). Markup dialog `index.html:1380` / `share.html:552` (`#map-title`,`#map-subbar`,`#map-groupbar`,`#map-list`,`#map-el`). Wrappers `openMapDialog` `index.html:2267` / `openShareMap` `share.html:1248`. `boardMapPoints` `:2280`.
- Front visionneuse : `runImageViewer(cfg)` `:507` (`images:[name],startIndex,imageUrl,downloadUrl,exifUrl`). URL image owner `/uploads/<n>`, invité `/share/<token>/image/<n>` `:2924`.

## Étapes (commits atomiques)

1. **db: table** — `image_meta` dans `init_db()` (~`:273`). Aucun bump version.

2. **server: helpers méta** — près de `_image_exif` `:429` :
   - `_record_image_meta(db, name, memo_id, memo_uid)` : `meta = _image_exif(name) or {}` ; `INSERT OR REPLACE INTO image_meta(filename,memo_id,memo_uid,lat,lng,label,taken_at,has_gps,created_at)` ; `has_gps = 1 if meta.get('lat') is not None else 0`. Idempotent (PK). Try/except silencieux → jamais bloquer l'upload.
   - `_forget_image_meta(db, names)` : `DELETE FROM image_meta WHERE filename IN (...)` (liste ou nom seul). Accepte `db` **ou** `conn` (même API `.execute`).

3. **server: câblage upload** — `add_memo_image` `:1536` (après `db.commit()`) : `_record_image_meta(db, name, memo_id, existing['uid'])`, re-commit. `share_add_image` `:2611` idem (`existing['uid']`). Le géocodage (1 appel max/coords, caché) se fait **ici, à l'ajout** — jamais à l'ouverture carte.

4. **server: câblage suppression** — `delete_memo_image` `:1555` et `share_delete_image` `:2637` : `_forget_image_meta(db, name)` à côté de l'`os.remove`. `_delete_image_files` `:1076` : ajouter `_forget_image_meta` **NON** ici (pas de db) → l'ajouter aux 2 sites appelants : suppr def. mémo `:1418` (`get_db()`) et `_purge_trash` `:3096` (`conn`), juste après `_delete_image_files(...)`.

5. **server: backfill idempotent throttlé** — `def _backfill_image_meta()` : ouvre sa propre connexion, parcourt mémos non corbeille, pour chaque `name in images` **absent de `image_meta`** → `_record_image_meta` ; `time.sleep(1.1)` **seulement** après une image qui a déclenché un géocode réseau (GPS non caché), pour ne pas marteler Nominatim. Idempotent (skip si filename déjà présent). Lancé en daemon thread à l'import, à côté de `_backup_loop` `:3588` : `threading.Thread(target=_backfill_image_meta, daemon=True).start()`. App utilisable pendant (état partiel = seules les images résolues apparaissent).

6. **server: endpoint owner** — `GET /api/projects/<int:pid>/photos` (près des routes projets `:799`) : `_valid_project_id` sinon 404 ; `ids = _project_descendants(db, pid)` ; SELECT `image_meta im JOIN memos m ON m.id = im.memo_id` où `m.project_id IN (ids)` ET `COALESCE(m.deleted_at,'')=''` ; renvoie `[{filename,memo_id,project_id,lat,lng,label,taken_at,has_gps,groups,title}]` (`groups` = `m.map_groups`, `title` = emoji+extrait pour la popup). GET seul, zéro écriture.

7. **server: endpoint invité scopé** — `GET /share/<token>/photos` (près `share_image` `:2924`) : `_share_by_token` sinon 404 ; **gate invité approuvé** (modèle `share_data`) ; `ids = [r['id'] for r in _share_scope_memos(db, share)]` (corbeille déjà exclue) ; même SELECT borné à `ids` ; renvoie même forme. **Invariant 5** : aucune image hors scope, pas de nouvelle capacité publique au-delà de la ressource partagée.

8. **front: calque photo dans `runMapDialog`** — `_shared.js.html:62`. cfg **optionnel** `loadPhotos: async()=>[...]` + `openImage(filename)`. Si présent :
   - Bouton **📷** (toggle `photoOn`) injecté près de `#map-subbar` (créé en JS, pas de markup figé → un seul partial). Off par défaut → carte identique à aujourd'hui (spec).
   - 1er allumage : `await loadPhotos()` une fois (mémoïsé). `photoLayer = L.layerGroup()`. Marqueurs **style distinct** des points-mémo : `L.circleMarker` carré-like via `divIcon` 📷 **ou** `circleMarker` couleur ambre + `weight` épais (au choix impl, doit se distinguer visuellement). Position = `lat/lng` (photos `has_gps`).
   - **Filtrage scope/sous-projet/groupe** : réutiliser `isFocused` en synthétisant `{project_id, groups}` par photo (l'endpoint les fournit) → `subToken`/`isGroupFocused`/`isSubFocused` inchangés ; hors-focus = grisé/cliquable (même rendu que les mémos). `fitBounds` peut inclure les photos en focus.
   - Clic marqueur → `cfg.openImage(filename)`.
   - **Frise « où on était »** : quand `photoOn`, `#map-list` bascule en liste **chronologique par `taken_at`** (asc) : entrée = heure (`fmtMemoTime`/`fmtExifDate` partagé) + `label` (ou « lieu inconnu » si `!has_gps`) → clic ouvre la photo. Photos **datées sans GPS** : listées, **pas** de marqueur. Sans date ni GPS : absentes. Toggle off → liste mémo (provenance) restaurée.
   - Invariant 8 : tout reste enfant du `<dialog>`, **aucun GSAP sur `#map-dialog`**.

9. **front: wire owner + invité** — `openMapDialog` `index.html:2269` : ajouter `loadPhotos:()=>fetch('/api/projects/'+state.memoProject+'/photos').then(r=>r.json())` (seulement si `memoProject` est un vrai projet, sinon ne pas passer `loadPhotos` → pas de bouton 📷 sur all/inbox) ; `openImage:(n)=>runImageViewer({images:[n],startIndex:0,imageUrl:x=>'/uploads/'+x,downloadUrl:x=>'/uploads/'+x,exifUrl:x=>'/api/image-exif/'+x})`. `openShareMap` `share.html:1250` : `loadPhotos:()=>fetch(API+'/photos',{headers:{'X-Guest-Token':guestToken()}}).then(r=>r.json())` (scopé partage), `openImage:(n)=>runImageViewer({images:[n],startIndex:0,imageUrl:x=>API.replace(/\/$/,'')+'/image/'+x,downloadUrl:...,exifUrl:x=>API+'/image-exif/'+x})`.

## Confirmations (spec → plan)
- **Aucune écriture mémo** : endpoints GET, helpers méta touchent **uniquement** `image_meta`. ✓
- **Dérivé, jamais exporté, pas de bump** : `_build_export` `:2971` + `APP_VERSION="18"` `:30` **non modifiés** ; `image_meta` ré-constructible par le backfill. ✓
- **Extract-once / pas de martèlement** : géocode à l'ajout + backfill throttlé ; carte lit `image_meta`, **zéro** appel Nominatim à l'ouverture. ✓
- **Méta suit le fichier** : `_forget_image_meta` à chaque suppression def. (per-image + purge mémo + `_purge_trash`). ✓
- **Invariant 5** : upload invité inchangé (signature `_save_uploaded_image` intacte) ; endpoint invité scopé `_share_scope_memos`, hors-scope = 404. ✓
- **Invariant 6** : pas de lib nouvelle (réutilise `exifread` d'IMAGE-EXIF) ; calque dans le partial partagé, pas de build, pas de CDN runtime. ✓
- **Invariant 8** : calque/frise/bouton enfants du dialog ; pas de GSAP sur `<dialog>`. ✓
- **Badge IMAGE-EXIF intact** : `runImageViewer.exifUrl` réutilisé tel quel, contrat inchangé. ✓

## Tests → Done-when
`python3 -m py_compile app.py` ; `cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run`. Jeu : photos JPG GPS-taguées (≥2 dates, ≥1 sous-projet), 1 photo datée sans GPS, 1 screenshot (sans EXIF).
1. **Marqueurs scopés+filtrés** : 📷 → marqueurs aux lieux, inclut descendants, respecte sous-projet/groupe (hors-focus grisés).
2. **Clic → image** : marqueur ouvre la bonne image (`runImageViewer`).
3. **Frise** : liste triée par `taken_at`, labels, photo datée sans GPS listée sans marqueur, screenshot absent.
4. **Extract-once** : ajout = 1 géocode max ; ré-ouvrir la carte = 0 appel réseau (lecture `image_meta`).
5. **Backfill idempotent+throttlé** : 2 passes → 0 doublon (PK), 2e passe skip tout, pacing ≥1 s entre géocodes.
6. **Mémo intact** : `location`/`due_date`/`due_time` inchangés via `/api/memos` avant/après.
7. **Export inchangé** : diff identique, `version` toujours 18.
8. **Cycle de vie** : suppr def. d'une image → ligne `image_meta` partie, plus de marqueur fantôme.
9. **Parité+scope invité** : invité approuvé voit calque/frise in-scope ; `GET /share/<t>/photos` hors-scope ou non-approuvé → 404/403.
10. **Pas de régression dialog** : `#map-dialog` centré, `::backdrop` OK, aucun transform GSAP.
11. **Dégradation** : géocode bloqué ou ligne absente → carte ouvre, photos sans marqueur, datées listées, aucune erreur.

## Risques / ordre
- Étape 1 (table) avant 2-9. Étape 8 sûre seule (garde `if (cfg.loadPhotos)`).
- `_purge_trash` `:3096` utilise `conn` (pas `get_db`) → `_forget_image_meta` doit accepter ce handle.
- Backfill : ne **pas** bloquer le boot (thread daemon, connexion propre, try/except par image). Nominatim ~1 req/s → sleep **uniquement** sur géocode réel (GPS non caché), pas sur les images déjà en cache/sans GPS.
- Distinguer visuellement marqueur photo ≠ point-mémo (sinon confusion) — ne pas toucher le style des points mémo existants.
- Invité : ne **pas** factoriser l'endpoint photos hors du contrôle de scope (invariant 5), copier le gate de `share_data`.
- `memos.images` peut référencer un fichier absent (corbeille/legacy) → `_image_exif` renvoie `None` sur fichier manquant (`os.path.isfile` `:433`), backfill no-op propre.

## Fichiers
`app.py` (`image_meta` init `~:273` ; helpers `_record_image_meta`/`_forget_image_meta` `~:429` ; upload `:1536`/`:2611` ; suppr `:1555`/`:1418`/`:3096`/`:2637` ; backfill + thread `~:3588` ; endpoints `~:799`/`~:2924` ; export `:2971` + `APP_VERSION` `:30` **NON touchés**) · `templates/partials/_shared.js.html` (`runMapDialog` `:62`, réutilise `runImageViewer` `:507`) · `templates/index.html` (`openMapDialog` `:2269`) · `templates/share.html` (`openShareMap` `:1250`).
