# Plan d'implémentation — [IMAGE-CAROUSEL]

> Compagnon de la spec verrouillée [IMAGE-CAROUSEL-memo-image-viewer.md](IMAGE-CAROUSEL-memo-image-viewer.md). Plan = comment ; spec = quoi. Ancres `file:line` au 2026-06-26 ; reconfirmer avant édition.

**Backend inchangé.** Toutes les routes existent et suffisent — aucune route ajoutée, aucun changement d'export.

## Existant (cité)
- **Owner viewer** `index.html` : `<dialog id="lightbox"><img></dialog>` (`1302`), CSS `846-868`, `openLightbox(src)` (`3524-3529`), thumbs `thumbsEl(memo, editable)` (`3563-3586`), clic thumb → `openLightbox('/uploads/'+name)` (`3570`), suppression owner gated `editable` (`3572-3581`) → `DELETE /api/memos/<id>/images/<name>` + `loadAll()`. Pop-in CSS `@keyframes dlg-in`/`dlg-bd` (`1047-1051`).
- **Guest viewer** `share.html` : `<dialog id="lightbox">` (`508`), thumbs (`1637-1667`), clic (`1644-1648`), suppression gated `canEditNow()` (`1650-1663`) → `DELETE API+'/memo/'+id+'/images/'+name` header `X-Guest-Token` + `load()`. `API='/share/'+TOKEN` (`572`), `canEditNow()=DATA.can_edit && GUEST.status==='approved'` (`586`).
- **Routes app.py (réutilisées)** : serve owner `GET /uploads/<name>` (`1420`), upload owner (`1428`), delete owner (`1454`), serve invité `GET /share/<token>/image/<name>` (`2837`), upload invité (`2494`), **delete invité scopé `share_delete_image` (`2529-2561`)** = `can_edit` + invité approuvé + `memo_id ∈ _share_scope_memos`. Invariant 5 OK, aucune route à créer.

## Décision ADR-001
Les deux viewers ne sont **pas** byte-identiques (URL image, endpoint delete + header, fn refresh, prédicat de droit). Règle stricte → pas d'extraction copier-coller. **Choix : helper unique config-driven `runImageViewer(cfg)`** dans `_shared.js.html`, sur le modèle de `runMapDialog(cfg)`. Tout le spécifique passe par `cfg` (donc le périmètre invité ne s'élargit pas) :
```
runImageViewer({ images, startIndex, imageUrl(name), downloadUrl(name), canDelete, onDelete(name) })
```
**CSS dupliqué** byte-identique dans les deux `<style>` (invariant 6 : pas d'asset CSS partagé). `<dialog>` reste un par page ; DOM carrousel construit en JS via `el()`.

## Étapes (commits atomiques)
1. **Helper squelette** — `runImageViewer(cfg)` dans `_shared.js.html` : (re)construit le DOM dans `#lightbox`, état `idx/rot/scale`, `showModal()`/`close()`. Pas de GSAP (CSS `dlg-in`/`dlg-bd`, invariant 8). Sans état hors `cfg`.
2. **Markup carrousel + nav + indicateur** — `<img>` + prev/next + `n / total` + barre d'options. `idx` borné. Prev/next : `idx`, reset `rot=0;scale=1`, maj `src=cfg.imageUrl(images[idx])`. 1 image : prev/next masqués/inertes, `1 / 1`, viewer s'ouvre quand même. Plein écran (classe).
3. **Téléchargement** — `<a download href=cfg.downloadUrl(images[idx])>`, maj à chaque navigation. Owner `/uploads/<name>`, invité `/share/<TOKEN>/image/<name>` (routes existantes, même origine → `download` sauvegarde). Invité dans le scope. Aucune route nouvelle.
4. **Rotation ↺↻ + Zoom +/−, affichage seul** — boutons mutent `rot` (±90°) et `scale` (borné ~0.25–5), appliqués en une transform CSS sur l'`<img>` (`rotate(${rot}deg) scale(${scale})`). **Aucun fetch, aucun export.** Reset `rot/scale` à la navigation et à la fermeture.
5. **Suppression gated** — bouton rendu seulement si `cfg.canDelete`. Clic → `confirmPopin` → `cfg.onDelete(images[idx])` ; le helper splice `images`, re-clamp `idx`, re-render, ou `close()` si vide. Invité lecture : bouton jamais rendu ; serveur 403/404 en défense.
6. **Câblage owner** `index.html` — `openLightbox`/clic thumb (`3526-3529`,`3570`) → `runImageViewer` avec `images` complet du mémo, `startIndex`, `imageUrl=n=>'/uploads/'+n`, `downloadUrl` idem, `canDelete=editable`, `onDelete=async n=>{ await fetch('/api/memos/'+memo.id+'/images/'+n,{method:'DELETE'}); await loadAll(); }`.
7. **Câblage guest** `share.html` (`1637-1667`) — clic thumb → `runImageViewer` avec `imageUrl=n=>API+'/image/'+n`, `downloadUrl` idem, `canDelete=canEditNow()`, `onDelete=async n=>{ const r=await fetch(API+'/memo/'+memo.id+'/images/'+n,{method:'DELETE',headers:{'X-Guest-Token':guestToken()}}); if(r.ok) await load(); }`. Garder close-on-backdrop (`1863`).
8. **CSS (dupliqué byte-identique)** — barre d'options, flèches, indicateur, sizing plein écran (overflow rotate/zoom) dans les deux `<style>`. Overrides `@media max-width:900px` **après** les règles de base (gotcha cascade CLAUDE.md).

## Tests → Done-when (surtout manuel navigateur)
`python3 -m py_compile app.py` (par précaution, pas de change backend). Reste = JS/CSS, vérif manuelle :
- Ouvre carrousel / nav bornée (owner + `/share/<token>`), `n/total`.
- 1 image : ouvre, flèches inertes, `1/1`.
- Download owner (`/uploads/...`) + invité approuvé (`/share/.../image/...`), DevTools = route existante, pas de nouvel endpoint.
- Rotate/Zoom : **aucune requête réseau** (DevTools), reset à la navigation, orientation d'origine au ré-ouvrir ; export avant/après identique (noms seuls, pas de bump).
- Suppression permise : owner + invité editor (route scopée existante) → image partie après refresh, viewer maj/ferme.
- Suppression refusée : invité lecture → pas de bouton ; `DELETE` manuel → 403/404 (garde `2533-2540`).
- Parité owner/guest : comparer visuellement.

## Risques / ordre
- **Invariant 5** : aucune création de route ; réutiliser la delete invité scopée existante, ne pas l'élargir. Client masque le bouton, serveur reste l'autorité.
- **Invariant 8** : carrousel dans `<dialog>` → entrée CSS seulement, jamais GSAP sur `#lightbox` ; rotate/zoom sur l'`<img>` interne (OK).
- **ADR-001** : `runImageViewer(cfg)` config-driven (précédent `runMapDialog`) mais pas un copier-extract byte-identique ; repli possible = dupliquer la fn par page si lecture stricte préférée.
- **Ordre** : 1-5 (helper) avant 6-7 (câblage) ; CSS (8) avec/après. Helper = code mort tant que non câblé → aucun état cassé intermédiaire.

## Fichiers
- templates/partials/_shared.js.html · templates/index.html · templates/share.html · (app.py inchangé)
