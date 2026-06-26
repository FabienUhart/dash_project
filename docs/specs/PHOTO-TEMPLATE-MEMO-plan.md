# Plan d'implémentation — [PHOTO-TEMPLATE-MEMO]

> Compagnon de la spec verrouillée [PHOTO-TEMPLATE-MEMO-photos-view.md](PHOTO-TEMPLATE-MEMO-photos-view.md). Plan = comment ; spec = quoi. Ancres `file:line` au 2026-06-26 (après [PHOTO-MAP]/[PHOTO-CLUSTER]). Maquette : `PHOTO-TEMPLATE-MEMO-mockup.svg` (repères 1-7).

**Front pur.** Zéro serveur/schéma/route/export. Données = endpoints photos **existants** de [PHOTO-MAP] (`/api/projects/<id>/photos` owner, `/share/<token>/photos` invité). Réutilise `runImageViewer` (plein écran + barre) et `runMapDialog` (calque photo). Nouveau composant partagé `runPhotoView(cfg)` dans le partial (ADR-001). Aucune écriture de **champ mémo** ; la **suppression** réutilise la route image existante (gated `can_edit`).

## Décisions de montage (spec → plan)
- **Vue = pop-in `#photo-dialog`** (comme `#map-dialog`), pas une vue board plein écran : parité owner/invité simple, un seul `runPhotoView` partagé, ouvert par une tuile.
- **Accès** : bouton/tuile **« 📷 Photos »** à côté de « Carte » — owner dans l'en-tête du board (`renderBoard`), invité dans `renderTiles`. Visible pour un **vrai projet** uniquement (pas all/inbox owner ; share projet), cohérent avec le calque photo [PHOTO-MAP]. Pas de compteur (évite un fetch à chaque render) : la vue charge à l'ouverture, état vide si aucune photo.
- **Barre d'options (repère 3)** : montée **en deux endroits**. Sur la card : plein écran ⤢ · télécharger ⬇ · 📍 localiser · supprimer 🗑 (si `can_edit`). **Rotation/zoom** vivent dans `runImageViewer` (plein écran) où ils existent déjà — pas de réimplémentation sur la card (la spec laisse le montage au plan).
- **Plein écran** = `runImageViewer` avec la **liste filtrée courante** + `startIndex` → carrousel plein écran navigable, badge EXIF (`exifUrl`) et suppression (`onDelete`) déjà câblés.

## Ancrage
- Données photo (forme déjà servie par [PHOTO-MAP]) : `{filename, memo_id, project_id, lat, lng, label, taken_at, has_gps, groups, title}` — `taken_at` (frise), `label` (badge), `lat/lng/has_gps` (localiser), `memo_id` (suppression).
- Owner en-tête board : `renderBoard` `index.html:4133`, bloc boutons projet `:4161-4180` (bouton « Carte » `:4175`). `openMapDialog` `:2272`. Suppression image owner : `DELETE /api/memos/<id>/images/<name>` route `delete_memo_image` `app.py:1678`.
- Invité tuiles : `renderTiles` `share.html:1275`, tuile « Carte » `:1299-1307`. `openShareMap` `:1252`. Suppression invité : `DELETE /share/<token>/memo/<id>/images/<name>` route `share_delete_image` `app.py:2758`. `API='/share/'+TOKEN` `share.html:627`, `guestToken()`.
- Partial : `runMapDialog` `_shared.js.html:62` (à étendre : `autoPhoto`/`focusFilename`), `runImageViewer` `:507` (cfg `images/startIndex/imageUrl/downloadUrl/canDelete/onDelete/exifUrl`), `fmtMemoTime`/`fmtTaken` (frise) — `fmtTaken` est **local** à `runMapDialog`, à **promouvoir** en helper partial pour le réutiliser.
- Markup dialogs : owner `index.html:1385` (`#map-dialog`), invité `share.html:556`. Ajouter `#photo-dialog` à côté, sur les deux pages.

## Étapes (commits atomiques)

1. **helper date partagé** — promouvoir `fmtTaken(iso)` (actuellement local à `runMapDialog`) en fonction **top-level du partial** (mois FR → « 6 nov · 14h30 »), réutilisée par `runMapDialog` ET `runPhotoView`. Pas de changement de comportement.

2. **markup `#photo-dialog`** — ajouter un `<dialog id="photo-dialog">` (titre `#photo-title`, conteneur `#photo-body`, bouton fermer) sur `index.html` (~`:1385`) et `share.html` (~`:556`), même squelette que `#map-dialog` (largeur `min(560px,96vw)`, padding). Internes construits en JS (un seul `runPhotoView`, pas de markup dupliqué).

3. **`runPhotoView(cfg)` dans le partial** — nouveau composant après `runMapDialog`. `cfg = { title, loadPhotos:async()=>[...], canEdit, deletePhoto:async(ph)=>{}, openMap:(focusFilename)=>{}, imageUrl(n), downloadUrl(n), exifUrl(n) }`. Logique :
   - charge `photos = await loadPhotos()` (une fois), tri par `taken_at` ; bucket **« sans date »** (taken_at vide) séparé.
   - état : `dayFilter` (null|`YYYY-MM-DD`), `expandedDay`, `cur` (index dans la liste visible). `visible = dayFilter ? photos du jour : tous` (+ bucket sans date listé hors frise datée).
   - **carrousel (1)** : image courante (`imageUrl`), ‹ › (wrap), compteur `cur+1/visible.length`, **badge** `📷 label · fmtTaken(taken_at)` (dégrade si vide).
   - **barre (3)** : ⤢ plein écran → `runImageViewer({images:visible.map(filename), startIndex:cur, imageUrl, downloadUrl, exifUrl, canDelete:canEdit, onDelete:async(name)=>{ await deletePhoto(byName(name)); await reload(); }})` ; ⬇ `<a download href=downloadUrl>` ; 📍 `openMap(visible[cur].filename)` (inerte/masqué si `!has_gps`) ; 🗑 si `canEdit` → `confirmPopin` puis `deletePhoto` + reload.
   - **vignettes (5)** : `visible`, courante surlignée, clic = set `cur` ; sync avec la frise.
   - **frise jours (6)** : jours distincts de `visible`/tous, **compteur = nb photos du jour**, clic = `dayFilter` ; un point par jour (style maquette), jour actif mis en avant.
   - **frise heures (7)** : sur un jour à ≥2 photos, bouton « + » → `expandedDay`, 2ᵉ frise par heure (points `HH`hMM), clic = focalise la/les photo(s) de cette heure (set `cur`). Jour à 1 photo → pas de « + ».
   - `reload()` = re-`loadPhotos()` + re-render (après suppression). Invariant 8 : tout enfant de `#photo-dialog`, aucun GSAP sur le dialog.

4. **étendre `runMapDialog` (localiser/Carte)** — cfg optionnels `autoPhoto` (bool) et `focusFilename` (string). Si `autoPhoto` : après `refresh(true)`, déclencher `togglePhotos()` (calque ON d'emblée). Si `focusFilename` : après `drawPhotos()`, retrouver la photo, `activeMap.setView([lat,lng], 16)` + ouvrir sa popup. N'altère pas le comportement existant (cfg absents = identique).

5. **wire owner** — `renderBoard` `index.html:~4173` : pour un **vrai projet**, ajouter un bouton « 📷 Photos » à côté de « Carte » → `openPhotoView()`. Nouveau wrapper `openPhotoView()` (près de `openMapDialog` `:2272`) :
   `runPhotoView({ title: nomProjet, loadPhotos:()=>fetch('/api/projects/'+state.memoProject+'/photos').then(r=>r.json()), canEdit:true, deletePhoto:ph=>fetch('/api/memos/'+ph.memo_id+'/images/'+ph.filename,{method:'DELETE'}).then(r=>r.json()), openMap:fn=>openMapDialog(nomProjet, boardMapPoints(), boardMapPoints, {autoPhoto:true, focusFilename:fn}), imageUrl:x=>'/uploads/'+x, downloadUrl:x=>'/uploads/'+x, exifUrl:x=>'/api/image-exif/'+x })`.
   Étendre la signature `openMapDialog(title, points, recompute, extra)` pour passer `autoPhoto`/`focusFilename` à `runMapDialog` (les wrappers actuels passent `extra` absent = inchangé).

6. **wire invité** — `renderTiles` `share.html:~1299` : pour un **share projet**, ajouter une tuile « 📷 Photos » à côté de « Carte » → `openSharePhotos()` :
   `runPhotoView({ title: DATA.title, loadPhotos:()=>fetch(API+'/photos',{headers:{'X-Guest-Token':guestToken()}}).then(r=>r.json()), canEdit:!!DATA.can_edit, deletePhoto:ph=>fetch(API+'/memo/'+ph.memo_id+'/images/'+ph.filename,{method:'DELETE',headers:{'X-Guest-Token':guestToken()}}).then(r=>r.json()), openMap:fn=>openShareMapFocus(fn), imageUrl:x=>API+'/image/'+x, downloadUrl:x=>API+'/image/'+x, exifUrl:x=>API+'/image-exif/'+x })`.
   `openShareMap` étendu (ou `openShareMapFocus(fn)`) pour passer `autoPhoto:true, focusFilename:fn` à `runMapDialog`.

## Confirmations (spec → plan)
- **Vue projet, pas type de mémo** : pop-in `#photo-dialog` ouvert par tuile « 📷 Photos » du projet. ✓
- **Données image_meta only** : `loadPhotos` = endpoints [PHOTO-MAP] existants, zéro nouvelle route/colonne. ✓
- **Aucune écriture champ mémo** : seule mutation = suppression via route image existante (fichier + `memos.images` + `image_meta`), gated `can_edit`. Localiser/plein écran/navigation = lecture. ✓
- **Réutilisation** : `runImageViewer` (plein écran + barre rotation/zoom/download/delete/exif), `runMapDialog` (calque photo + autoPhoto/focus). Helpers (`fmtTaken`) dans le partial. ✓
- **Parité owner/invité scopée (inv. 5)** : mêmes endpoints scopés, suppression via chemins scopés existants, aucune nouvelle route publique. ✓
- **Inv. 6** : pas de build, pas de CDN, composant dans le partial. **Inv. 8** : pas de GSAP sur `#photo-dialog`. ✓
- **Export/données inchangés** : zéro ligne serveur ; `image_meta`/`APP_VERSION`/`_build_export` non touchés. ✓

## Tests → Done-when
`cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run`. Jeu : projet ≥5 photos sur ≥3 jours, 1 jour à ≥2 photos (frise heures), 1 photo datée sans GPS, 1 sans date.
1. Tuile « 📷 Photos » dans la barre projet (owner board + share) → ouvre la vue.
2. Carrousel : ‹ › + compteur + badge lieu/date (`image_meta`).
3. Plein écran → `runImageViewer` (zoom/pan/rotation).
4. Barre : télécharger/rotation/zoom/📍 localiser OK ; 🗑 visible seulement si `can_edit`.
5. Suppression → route image existante (fichier + `memos.images` + `image_meta`) ; `location`/`due_*`/`title`/`content` du mémo **inchangés** ; photo disparue de la vue, carte, mémo.
6. 📍/Carte → carte projet, calque photo ON, centrée sur la photo ; aucune écriture.
7. Vignettes sync (courante surlignée ↔ frise).
8. Frise jours : compteur = nb photos/jour ; clic = filtre le jour.
9. Frise heures : « + » sur un jour à ≥2 photos → frise horaire ; jour à 1 photo = pas de « + ».
10. Photo datée sans GPS : présente, 📍 inerte ; photo sans date : groupe « sans date », hors frise datée ; pas de crash.
11. Parité invité scopée : invité voit la vue (photos in-scope), aucune hors scope.
12. Export inchangé ; `#photo-dialog`/plein écran centrés, `::backdrop` OK, 0 GSAP sur dialog.

## Risques / ordre
- Étape 1 (promouvoir `fmtTaken`) avant 3/4. Étape 4 (extension `runMapDialog`) avant 5/6 (localiser).
- `openMapDialog`/`openShareMap` gagnent un 4e arg optionnel `extra` → vérifier que les appels existants (sans `extra`) restent identiques.
- Suppression : mapper `filename → memo_id` via `photos[]` (la route image a besoin du `memo_id`). Après suppression, **recharger** `loadPhotos` (sinon vignettes/frise désync).
- `runImageViewer.onDelete` reçoit `name` → retrouver `ph` par filename dans `runPhotoView` puis `deletePhoto`.
- Tuile « 📷 Photos » sans compteur (pas de fetch au render) : vue vide propre si 0 photo.
- Ne **pas** réimplémenter rotation/zoom sur la card (déjà dans `runImageViewer`) — éviter la divergence.
- Invité non `can_edit` : pas de 🗑 (card ni viewer `canDelete:false`).

## Fichiers
`templates/partials/_shared.js.html` (`fmtTaken` promu, `runPhotoView` nouveau, `runMapDialog` +`autoPhoto`/`focusFilename`) · `templates/index.html` (`#photo-dialog` markup, bouton board `renderBoard`, `openPhotoView` + `openMapDialog` 4e arg) · `templates/share.html` (`#photo-dialog` markup, tuile `renderTiles`, `openSharePhotos` + `openShareMap` focus). **`app.py` non touché** (endpoints/suppression déjà là). Export/schéma inchangés.
