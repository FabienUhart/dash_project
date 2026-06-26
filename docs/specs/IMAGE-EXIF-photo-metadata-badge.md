# [IMAGE-EXIF] — Badge de métadonnées photo (lieu + date de prise de vue)

> Status: **VALIDATED & LOCKED** (reviewer score 100/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[IMAGE-EXIF]`.

## Target

When a memo image is displayed, the app reads that image file's EXIF on the server on the fly and shows, alongside the image, a non-editable badge with the photo's capture place and capture date/time when present — without storing anything, without changing the memo, and without changing the export, for both the owner and approved share guests within their scope.

## Hard constraints

- **Per-image, read-only, display-only.** The metadata belongs to the image, not the memo. It is shown next to the image (thumbnail and/or viewer); it never writes any memo field (location, due_date, due_time, or anything else) and never opens a "copy to memo" prompt.
- **Read on the fly, never stored.** EXIF is parsed from the stored image file each time it is needed. No database row, no table, no new column, no cache that survives a restart is required by the contract. Re-reading after a server restart yields the same badge from the same file.
- **Export strictly unchanged.** The export keeps storing image file names only (v6+). No version bump, no new field, nothing EXIF-related ever enters the export.
- **Server-side extraction via a lightweight pure-Python dependency.** EXIF is read with a lightweight pure-Python library added to `requirements.txt` that only *reads* metadata (it must not manipulate or re-encode the image). The library is installed via pip and self-hosted in the image build (no CDN at runtime), consistent with invariant 6.
- **Upload validation unchanged.** Image upload still passes the existing binary-signature check (invariant 5); this feature only reads already-accepted files, it does not change the accept path.
- **Guest scope (invariant 5).** Any guest-facing way to obtain an image's EXIF is gated exactly like the existing public image route: the requested file must belong to a memo within the share's scope; a file outside the scope returns not-found. No new public capability beyond the shared resource, and EXIF of out-of-scope images is never exposed.
- **Place label is best-effort and reuses the existing reverse geocoder.** GPS coordinates from EXIF are turned into a short "place, city" label with the existing reverse-geocoding helper. If that lookup fails or is unavailable, the badge degrades gracefully (shows the date alone, or coordinates, never an error) and the image still displays normally.
- **No abuse of the external geocoder.** Repeated display of the same image must not hammer the external geocoding service; resolution of identical coordinates is throttled/deduplicated (an in-memory, non-persistent mechanism is acceptable). The only external calls are the already-used geocoding endpoint.
- **Non-intrusive on missing data.** An image without usable EXIF (screenshots, re-encoded/stripped photos from messaging apps) produces no badge and no error — a silent no-op.
- **Owner/guest parity.** The badge appears the same way on the owner dashboard and on the shared page, each limited to images the actor may already see.

## Non-goals

- **No write to the memo.** No auto-fill or prompt to copy place/date into the memo's `location`, `due_date`, or `due_time`. (This supersedes the original backlog wording.)
- **No persisted "photo date" field** and no new memo/image schema, table, or column.
- **No storage or export of EXIF** in any form.
- **No EXIF editing, stripping, rotation, or re-encoding** of the stored file (read-only metadata access).
- **No automatic map pin or location dot** derived from the photo.
- **No aggregation across a memo's images** — each image carries its own badge independently; there is no "first image wins" memo-level behavior, because nothing is written to the memo.
- **No new external runtime service** beyond the geocoding endpoint already in use.

## Done-when

- **Badge shown when EXIF present:** Uploading then viewing a photo that carries GPS + capture date/time shows a badge with the place label and the capture date/time next to that image. Verified by uploading a known GPS-tagged photo and observing the badge (owner).
- **No EXIF → no badge:** Viewing an image with no usable EXIF (e.g. a screenshot) shows the image with no badge and logs no error. Verified by uploading a stripped/screenshot image.
- **Memo untouched:** After uploading and viewing EXIF-tagged images, the memo's `location`, `due_date`, and `due_time` are unchanged from before. Verified by comparing the memo fields before/after.
- **Nothing persisted:** No new table/column/row is created; the badge is reproduced purely from the file after a server restart (no DB state). Verified by restarting the app and re-viewing the same image.
- **Export unchanged:** An export taken before and after using the feature is identical regarding images (file names only) and the version number is not bumped. Verified by diffing exports.
- **Guest parity + scope:** An approved guest sees the badge for in-scope images; requesting EXIF for a file not in the share's scope returns not-found. Verified on a share link (in-scope image shows badge; out-of-scope file name is rejected).
- **Geocoder degradation:** With the geocoding lookup failing/unavailable, an EXIF-tagged image still displays and the badge degrades (date alone or coordinates), never an error or a blocked image. Verified by simulating a geocoder failure.
- **Geocoder not abused:** Repeatedly displaying the same EXIF-tagged image does not issue one external geocoding call per display for identical coordinates. Verified by observing outbound calls are deduplicated/throttled.
- **Dependency self-hosted:** The EXIF library is declared in `requirements.txt` and present in the built image; no runtime CDN fetch is introduced. Verified by building and checking the dependency resolves offline.

## Resolved decisions

- Storage: **read on the fly, not stored, not exported** (export stays v6/unchanged).
- Action on add/display: **display only** — a badge on the image; **no write to the memo**, no copy prompt. (Reverses the original backlog idea of pre-filling `location`/`due_time`.)
- The metadata is **per-image**, independent of the memo and of other images.

## Stakeholders

- Decider / Owner: Fabien.
- Consumer: Fabien (owner viewer) and approved share guests (read-only badge, in scope).

## Context

- Backlog source: `IDEAS.md` → `[IMAGE-EXIF]`. Note: the original entry proposed pre-filling the memo's `location`/`due_time`; this spec deliberately narrows to **display-only, per-image, not stored** per the decider's choices.
- Existing infra reused: server-side image files in `data/uploads/`, served by the owner image route and the public scoped share image route; the existing reverse-geocoding helper for GPS→label; the existing binary-signature upload validation.
- Governing invariants: `CLAUDE.md` — invariant 5 (guest scope + signature-validated uploads), invariant 6 (no build / self-contained, self-hosted deps), and the standing "export backward-compatible / unchanged" rule (invariant 1/2 — here: unchanged).
- This is a behavioral contract. The exact library name, route shapes, EXIF tag parsing, cache mechanism, and badge markup belong to the **plan**, not here.
