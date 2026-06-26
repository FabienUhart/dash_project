# [PHOTO-MAP] — Itinéraire photo : lieux des photos sur la carte du projet + frise « où on était »

> Status: **VALIDATED & LOCKED** (reviewer score 96/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[PHOTO-MAP]`. Builds on `[IMAGE-EXIF]` (capture-place/date extraction already exists).

## Target

On a project's map dialog, let the owner and approved share guests see and browse where that project's photos were taken — scoped to the project hierarchy and the map's current filters — without ever writing to any memo and without changing the export. (The photo-place data is derived from each image's EXIF; *how* it is obtained and kept fast is fixed in Hard constraints below.)

## Hard constraints

- **No write to memos, ever.** Showing photo places and the chronological list never modifies a memo's `location`, `due_date`, `due_time`, `marker_color`, `map_groups`, or any other field. The photo layer is purely derived from images. (Decision already taken in the backlog.)
- **Extract once at add-time, persist as derived data.** Each image's capture place (coordinates + short place label) and capture date/time are extracted when the image is added — on the owner add-image path **and** the approved-guest add-image path — and stored as derived data keyed by image, so the map dialog reads them directly without re-parsing every file or re-calling the external geocoder on each open. The external geocoder is called at most once per image (at add-time), reusing the existing reverse-geocoding helper, with the existing throttle/dedupe so it is never hammered.
- **Derived, re-buildable, never exported.** This stored metadata is derived from the image files (themselves never exported — file names only, v6+). It is **not** part of the export, introduces **no** export version bump, and is fully re-buildable from the existing image files. An export taken before and after using the feature is identical.
- **Backfill of pre-existing images.** Images added before this feature get their metadata populated by a backfill pass that is **idempotent** (re-running never duplicates or corrupts rows, and skips already-populated images) and **throttled** for the external geocoder so the backfill cannot hammer it. The app stays usable while the backfill runs; a partially-backfilled state degrades gracefully (only resolved images appear on the layer).
- **Stored metadata stays consistent with the files.** When an image file is permanently removed, its derived metadata row is removed too, so the photo layer never points at a non-existent file. (Soft-deleted / trashed memos and images follow the same exclusion as everywhere else — out of scope of the layer while trashed.)
- **Photo layer is opt-in on the existing project map dialog.** The map dialog gains a toggle that overlays photo markers, visually distinct from the existing memo points, without altering the memo points, the board, or the existing sub-project/group filters. With the toggle off, the map behaves exactly as today.
- **Photo markers obey the map's current scope and filters.** The photo layer is scoped to the current project and, recursively, its descendant sub-projects, and respects the map's currently active sub-project and group filters the same way memo points do (in-focus vs greyed/out-of-focus follows the same model). Photos of memos outside the current scope never appear.
- **Selecting a photo marker opens that image** in the app's existing image viewer (owner and guest each within what they may already see).
- **Chronological side panel (« où on était »).** When the photo layer is active, a side panel lists the project's photos ordered by capture date/time, each entry showing its capture time and place label with quick access to open the photo. Photos that have a capture date but no usable coordinates appear in the list (date + "unknown place"/no-place) but get no map marker. Photos with neither date nor coordinates are absent from both.
- **Guest scope (invariant 5).** Guest access to the photo layer and the chronological list goes through the existing share scope only: a guest sees photo metadata strictly for images belonging to memos within their share's scope (the shared project/memo and its in-scope descendants). No new public capability beyond the shared resource; out-of-scope image metadata is never exposed, and the add-image extraction on the guest path stays inside the existing scoped upload path (no new public route shape that widens guest reach).
- **Reuse, no build, self-contained (invariant 6).** Reuses the existing map dialog and image viewer and the existing front-end shared helpers; no new front-end build step, no runtime CDN beyond the calls already in use. Any owner/guest-identical pure helper introduced lives in the shared partial per ADR-001.
- **No dialog animation regression (invariant 8).** The map dialog and any pop-in keep their CSS-based entrance; GSAP is never applied to the `<dialog>` element itself.
- **Upload validation unchanged (invariant 5).** Adding an image still passes the existing binary-signature validation; this feature only reads metadata from already-accepted files.
- **Graceful degradation.** A failed/empty extraction, a failed geocode, or a missing metadata row produces no error and no broken layer — affected photos simply have no marker (and, if dated, still appear in the list); the map and images keep working.

## Non-goals

- **No memo auto-fill or copy prompt** of place/date into any memo field (superseded backlog idea; consistent with `[IMAGE-EXIF]`).
- **No export of the derived metadata** in any form, and no export version bump.
- **No drawn route line / polyline** connecting the photo points; the "itinerary" is the set of markers plus the chronological list, not a drawn path. (Possible later.)
- **No EXIF editing, stripping, rotation, or re-encoding** of stored files (read-only metadata access, as in `[IMAGE-EXIF]`).
- **No general photo gallery, clustering, heatmap, or per-photo captioning** beyond the marker + chronological list described here.
- **No new external runtime service** beyond the geocoding endpoint already in use.
- **No change to the existing per-image EXIF badge** (`[IMAGE-EXIF]`); this feature is additive and independent of that badge.
- **No re-geocoding on map open** and no live re-extraction loop; resolution happens at add-time and during the one-off backfill only.

## Done-when

- **Photo markers appear, scoped & filtered:** On a project that has GPS-tagged photos, toggling the photo layer in its map dialog shows markers at the photos' capture places, including photos from descendant sub-projects, and honoring the active sub-project/group filters (out-of-focus photos greyed like memo points). Verified by adding GPS-tagged photos across a project + sub-project and observing the layer with/without filters.
- **Marker opens the image:** Selecting a photo marker opens that exact image in the existing viewer. Verified by clicking a marker and confirming the opened image matches.
- **Chronological panel:** With the layer active, the side panel lists the project's photos in capture-time order with place labels and opens the photo on selection; a dated photo without coordinates is listed without a marker. Verified by adding photos with varied dates and a date-only photo.
- **Extract-once / no geocoder hammering:** Adding an image resolves its place at most once; opening the same project map repeatedly issues no per-photo external geocoding calls. Verified by observing outbound calls on add vs. on repeated map opens.
- **Backfill idempotent & throttled:** Running the backfill on a store of pre-existing images populates their metadata without duplicates, skips already-populated images on a second run, and does not burst the external geocoder. Verified by running the backfill twice and inspecting row counts and outbound call pacing.
- **Memos untouched:** After adding and viewing EXIF-tagged photos, every targeted memo's `location`, `due_date`, `due_time` and other fields are unchanged. Verified by comparing memo fields before/after.
- **Export unchanged:** Exports taken before and after using the feature are identical regarding images (file names only) with no version bump. Verified by diffing exports.
- **Metadata follows file lifecycle:** Permanently deleting an image removes its derived metadata so no marker points at a missing file. Verified by permanently deleting an image and confirming its marker/list entry is gone.
- **Guest parity + scope (invariant 5):** An approved guest sees the photo layer and chronological list only for in-scope images; requesting photo data for a project/image outside the share's scope returns not-found and exposes nothing. Verified on a share link with in-scope and out-of-scope images.
- **No dialog regression (invariant 8):** The map dialog still centers correctly with its CSS entrance and `::backdrop`; no GSAP transform is applied to the dialog. Verified by opening the map dialog and confirming centering/backdrop.
- **Degradation:** With the geocoder failing or a metadata row missing, the map dialog still opens, EXIF-less photos simply lack markers, dated ones still list, and no error surfaces. Verified by simulating a geocoder failure and a missing row.

## Stakeholders

- Decider / Owner: Fabien.
- Consumer: Fabien (owner map dialog) and approved share guests (read-only photo layer + chronological list, in scope).

## Context

- Backlog source: `IDEAS.md` → `[PHOTO-MAP]` (lines 97–102). Decision already locked there: **no writes to memos**.
- Builds on `[IMAGE-EXIF]` (VALIDATED & LOCKED, 2026-06-26): server-side capture-place/date extraction from an image's EXIF and the reverse-geocoding helper already exist; `[IMAGE-EXIF]` reads on the fly for a per-image badge, whereas `[PHOTO-MAP]` adds an at-add-time **persisted derived cache** so the map can read many photos at once without re-parsing/re-geocoding. The two are complementary: this spec does not alter the `[IMAGE-EXIF]` badge contract.
- Existing infra reused: the project map dialog and its sub-project/group filter model, the image viewer, the public scoped share image access (invariant 5), the export's "file names only" image rule (v6+), and the shared front-end helper partial (ADR-001).
- Governing invariants: `CLAUDE.md` — invariant 5 (guest scope + signature-validated uploads), invariant 6 (no build / self-contained, self-hosted deps), invariant 8 (no GSAP on a `<dialog>`), and the standing export-unchanged rule (here: strictly unchanged; the derived metadata is never exported).
- This is a behavioral contract. The exact table/columns, route shapes, marker rendering, backfill trigger, and panel markup belong to the **plan**, not here.
