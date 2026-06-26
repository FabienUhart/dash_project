# [PHOTO-TEMPLATE-MEMO] — Vue « Photos » d'un projet (carrousel + barre d'options + frise deux niveaux)

> Status: **VALIDATED & LOCKED** (reviewer score 96/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[PHOTO-TEMPLATE-MEMO]`. Référence visuelle : `docs/specs/PHOTO-TEMPLATE-MEMO-mockup.svg` (zones numérotées 1-7). Construit sur `[PHOTO-MAP]` (table `image_meta`, endpoints photos, `runMapDialog`/calque photo) et `[IMAGE-CAROUSEL]`/`runImageViewer`.

## Target

Give each project a **project-level "Photos" view** — reached from a "📷 Photos" tile in the project's filter bar — that browses all the project's photos from the already-persisted `image_meta` (carousel of the current photo with place/date badge, thumbnails, and a two-level day→hour timeline), opens any photo full-screen in the existing viewer, jumps to that photo on the project map, and lets an authorized actor delete a photo — for the owner and approved share guests within their scope, without ever writing any memo field and without any change to the database, server, or export.

## Hard constraints

- **Project-level view, NOT a memo type/template.** This is an aggregate view of a project's photos (the timeline spans multiple days), surfaced as a project view — not a new kind of memo, not a per-memo widget. (Resolved decision; supersedes the "memo template" framing of the backlog title.)
- **Reached from a tile in the project filter bar.** A "📷 Photos" tile sits in the project's filter bar next to the existing "Carte" tile; selecting it shows the Photos view for the current project. The view's "Carte" button (mockup 4) and the map's "📷" photo toggle (`[PHOTO-MAP]`) are two doors onto the same `image_meta` data.
- **Data source is `image_meta` only.** Everything shown (image list, place `label`, capture `taken_at`, coordinates) comes from the existing scoped photo endpoints of `[PHOTO-MAP]` (owner project-scoped, guest share-scoped). No new table, column, endpoint, or server work is introduced.
- **No memo-field writes.** The view never modifies any memo field (`location`, `due_date`, `due_time`, `title`, `content`, `images` ordering, etc.) and never auto-fills a memo from a photo. Browsing, locating, and full-screen viewing are strictly read-only with respect to memos.
- **Deletion is the only mutation, and reuses the existing image-delete path.** When `can_edit`, the option bar can delete the current photo through the **existing** per-image delete route (owner and guest), which by its existing semantics removes the file, drops it from its memo's image list and from `image_meta` — exactly as deleting from the memo editor does today. No new deletion capability, no new route, gated to `can_edit`; read-only actors see no delete control. (This is the single, explicit, user-initiated mutation; it is not a memo-field edit.)
- **Carousel (mockup 1).** Shows the current photo, ‹ › navigation across the project's photos, an n/total counter, and a badge with the photo's place label and capture date/time from EXIF (degrading gracefully when a field is missing, like `[PHOTO-MAP]`).
- **Full-screen reuses the existing viewer (mockup 2).** Opening a photo full-screen uses the existing image viewer (its zoom/pan/rotation), not a new viewer.
- **Option bar reuses the viewer's actions (mockup 3).** For the current photo the view offers: full-screen, download, rotate (↺↻), zoom (−＋), **📍 locate this photo on the map**, and delete (only if `can_edit`) — reusing the existing viewer's option-bar behavior. Rotation/zoom are display-only (non-persisted), consistent with the viewer; the stored file is never re-encoded.
- **"Locate" opens the map on this photo, no write (mockup 3 / 4).** 📍 opens the project map (the `[PHOTO-MAP]` photo layer) centered/popped on this photo's coordinates; the "Carte" button opens the same project map photo layer filtered to the project. Neither writes anything; both reuse `runMapDialog`.
- **Thumbnails synced with the timeline (mockup 5).** A thumbnail strip shows the project's photos with the current one highlighted; selecting a thumbnail sets the carousel, and the highlight stays in sync with the timeline selection.
- **Day timeline with counts and filtering (mockup 6).** A timeline lists the days that have photos; each day shows the **number of photos taken that day**; clicking a day filters the carousel/thumbnails to that day's photos.
- **Hour sub-timeline on demand (mockup 7).** When a day holds several photos, a "+" expands a second, finer timeline by hour for that day; selecting an hour point focuses the corresponding photo(s). Days with a single photo need no expansion.
- **Photos without coordinates / without date.** Photos with a date but no GPS still appear in the carousel/thumbnails/timeline (placed by date; "locate" is inert for them, no error). A photo lacking a usable date appears in the carousel/thumbnails under an "undated" grouping and is **excluded from the dated day/hour timeline** (it has no day to anchor to); the view never crashes on such photos.
- **Owner/guest parity within scope (invariant 5).** The view behaves the same for the owner and an approved share guest, each limited to the photos their existing scoped endpoint returns; no photo outside scope is reachable, and no new public route or capability is added.
- **Reuse + shared partial (invariant 6, ADR-001).** Reuses `runImageViewer` and `runMapDialog`; any owner/guest-identical pure helper introduced lives in the shared partial. No new front-end build step, no runtime CDN.
- **No dialog animation regression (invariant 8).** Any pop-in/full-screen keeps its CSS entrance; no GSAP transform is applied to a `<dialog>` element.
- **Export and data unchanged.** No schema, route, server, or export change; `image_meta` already exists and is never exported. This is a front-end view over existing data.

## Non-goals

- **Not a memo type, template, or per-memo component** — it is a project view.
- **No new server work**: no table, column, endpoint, route, or export change; `[PHOTO-MAP]` endpoints stand as-is.
- **No memo-field auto-fill** from a photo (no copying place/date into `location`/`due_*`), consistent with `[PHOTO-MAP]`/`[IMAGE-EXIF]`.
- **No persisted rotation / no EXIF or image re-encoding** — rotation/zoom are display-only (as in the viewer).
- **No photo captioning, tagging, reordering, albums, or selection/bulk actions** beyond what is listed (browse, locate, full-screen, single-photo delete).
- **No soft-delete/trash for photos here** — deletion uses today's existing image-delete semantics (a separate backlog item, `[IMAGE-TRASH]`, would change that globally; out of scope here).
- **No new map behavior** — "locate"/"Carte" reuse the `[PHOTO-MAP]` photo layer unchanged.
- **No offline/empty special-casing beyond graceful display** — a project with no photos simply shows an empty Photos view (no error).

## Done-when

- **Tile opens the view:** A "📷 Photos" tile appears in a project's filter bar (next to "Carte") and opens the project's Photos view showing that project's photos. Verified by opening a project with photos and clicking the tile.
- **Carousel + badge:** The carousel shows the current photo with ‹ › navigation, an n/total counter, and a place+date badge sourced from `image_meta`. Verified by navigating across photos and reading the badge.
- **Full-screen reuses viewer:** Triggering full-screen opens the existing image viewer on the current photo. Verified by opening full-screen and confirming it is the existing viewer (zoom/pan/rotation work).
- **Option bar actions:** Download, rotate, zoom, and 📍 locate work for the current photo; delete appears only when `can_edit`. Verified by exercising each action and confirming delete is absent for a read-only actor.
- **Delete reuses existing path, no memo-field write:** Deleting the current photo (when `can_edit`) removes it via the existing image-delete route (file + memo image list + `image_meta` row) and no other memo field changes. Verified by deleting a photo and confirming the memo's `location`/`due_*`/`title`/`content` are unchanged and the photo is gone from the view, map, and memo.
- **Locate / Carte open the map on the data:** 📍 opens the project map photo layer centered/popped on the photo; "Carte" opens the same project map photo layer. Neither writes anything. Verified by clicking each and confirming the map opens on the right photo with no memo change.
- **Thumbnails sync:** Selecting a thumbnail sets the carousel and the highlight matches the current photo and timeline selection. Verified by clicking thumbnails and observing sync.
- **Day timeline counts + filter:** The day timeline shows one entry per day with a count equal to that day's photo number; clicking a day filters the carousel/thumbnails to that day. Verified by a project spanning several days and clicking a day.
- **Hour sub-timeline:** A day with several photos exposes a "+" that reveals an hour timeline for that day; selecting an hour focuses the matching photo(s); a single-photo day exposes no expansion. Verified with a day holding multiple photos and a day holding one.
- **Undated/GPS-less photos handled:** A dated GPS-less photo still appears and navigates (locate inert, no error); a photo lacking a usable date shows under an "undated" grouping in the carousel/thumbnails and is absent from the dated timeline, without breaking the view. Verified by adding such photos.
- **Guest parity + scope (invariant 5):** An approved guest sees the same Photos view limited to in-scope photos; no out-of-scope photo is reachable and no new public route is used. Verified on a share link.
- **Export unchanged + no server change (invariants):** No schema/route/endpoint/export change; exports before/after are identical. Verified by diffing exports and confirming no new server route.
- **No dialog regression (invariant 8):** Full-screen/pop-ins center with their CSS entrance; no GSAP transform on a `<dialog>`. Verified by opening full-screen.

## Stakeholders

- Decider / Owner: Fabien.
- Consumer: Fabien (owner project Photos view) and approved share guests (same view, in scope).

## Context

- Backlog source: `IDEAS.md` → `[PHOTO-TEMPLATE-MEMO]` (lines 105-113) + annotated mockup `docs/specs/PHOTO-TEMPLATE-MEMO-mockup.svg` (zones 1-7). The backlog title says "mémo photo"; the **resolved decision** narrows it to a **project-level view** (the timeline spans days → aggregate of the project, not a single memo), reached by a "📷 Photos" tile in the project filter bar.
- Builds on `[PHOTO-MAP]` (implemented): `image_meta` is filled at upload and read through scoped endpoints (`/api/projects/<id>/photos` owner, `/share/<token>/photos` guest); the photo map layer lives in `runMapDialog`. This view is a second consumer of that same data — no new server work.
- Reuses `runImageViewer` (full-screen, zoom/pan/rotation, download, delete bar from `[IMAGE-CAROUSEL]`) and `runMapDialog` (photo layer); shared owner/guest-identical helpers belong in `templates/partials/_shared.js.html` (ADR-001).
- Deletion semantics are the **existing** per-image delete (owner `DELETE /api/memos/<id>/images/<name>`, guest scoped equivalent), which already removes the file, the memo image-list entry, and the `image_meta` row — reused as-is, gated `can_edit`. Not a new memo-field edit; the standing "no memo writes" principle refers to not auto-filling memo fields from EXIF.
- Governing invariants: `CLAUDE.md` — invariant 5 (guest scope, no new public route), invariant 6 (no build/CDN, reuse + shared partial), invariant 8 (no GSAP on a `<dialog>`), export unchanged (front-end only).
- This is a behavioral contract. Exact view placement/markup, carousel/timeline mechanics, the locate-on-map wiring, and how the option bar is mounted (inline vs via full-screen) belong to the **plan**.
