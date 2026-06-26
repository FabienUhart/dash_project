# [IMAGE-CAROUSEL] — Memo image carousel + viewer options

> Status: **VALIDATED & LOCKED** (reviewer score 100/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[IMAGE-CAROUSEL]`.

## Target

When a memo's image is opened, the viewer presents all of that memo's images as a navigable full-screen carousel with an options bar (download, rotate for viewing only, zoom, and delete when permitted), behaving identically for the owner and for approved share guests within their scope.

## Hard constraints

- **Scope = the current memo's images only.** The carousel navigates the set of images attached to the memo being viewed, in their stored order; it never exposes images from another memo.
- **Navigation is complete and bounded.** Previous/next controls, a position indicator (current / total), and a full-screen presentation. With a single image, navigation controls are inert or hidden but the viewer still opens.
- **Download uses the existing file routes only.** Owner downloads via the existing owner image route; an approved guest downloads via the existing public share image route. No new file-serving route is added; the guest can only download images within the shared resource's scope (invariant 5).
- **Rotation is view-only and not persisted.** Rotating (↺ ↻) changes only the on-screen orientation; it never rewrites the stored file, never calls the server, and never changes the export. Reopening the image shows it in its original orientation.
- **Zoom is view-only and not persisted.** Zooming in/out changes only the on-screen scale; it never modifies the file, the server, or the export. Rotation and zoom reset when navigating to another image or closing the viewer.
- **Delete is gated by existing permissions.** A delete control is available only to an actor allowed to delete a memo image today: the owner, or an approved guest with edit rights acting within the share scope. A read-only guest never sees or can trigger delete. Deleting removes the image from the memo via the existing deletion behavior.
- **No export/format change.** The export keeps storing image file names only (v6+); no version bump, no new field. Nothing about persisted data changes.
- **Upload validation unchanged.** Image upload still goes through the existing binary-signature check (invariant 5); this feature touches viewing/deleting, not the accept path.
- **Owner/guest parity.** The carousel and its options behave the same on the owner dashboard and on the shared page, each limited to what that actor is allowed to do (read-only guest: view + download; editor guest/owner: also delete).
- **No build, self-contained output (invariant 6).** No external runtime dependency and no build step are introduced. If the viewer component is identical for owner and guest, it lives as a shared pure helper per ADR-001; otherwise it is duplicated per page without widening guest scope.
- **No animation on a `<dialog>` element via GSAP (invariant 8).** Any motion follows the existing CSS pop-in convention; GSAP, if used, animates only non-top-layer children.

## Non-goals

- **No persisted rotation.** Server-side re-encoding (e.g. rewriting the file) is explicitly out of scope; only view-only rotation ships.
- **No persisted zoom or crop, no image editing** (filters, annotations, cropping, reordering images).
- **No new upload capability or new accepted file types.** Viewing/deleting only.
- **No cross-memo gallery, no album, no slideshow autoplay.**
- **No change to where files are stored or how they are named** (`data/uploads/`, existing naming and routes).
- **No new public route** and no widening of the guest scope beyond the already-shared resource.
- **No reordering of a memo's images** from the viewer.

## Done-when

- **Opens as carousel:** Clicking a memo image opens a full-screen viewer showing that image with previous/next controls and a "current / total" indicator. Verified by opening a memo that has ≥2 images and observing navigation + indicator.
- **Navigation bounded:** Previous/next cycle through exactly the current memo's images in stored order and do not leak other memos' images. Verified by navigating past both ends with a known set.
- **Single image:** Opening a memo with exactly one image still opens the viewer; navigation controls are hidden or inert and the indicator reflects 1 / 1. Verified by opening a single-image memo.
- **Download:** The download control saves the currently shown image file; for the owner via the owner route, for an approved guest via the share route, both within scope. Verified by downloading as owner and as an approved guest.
- **Rotate view-only:** Rotating changes only on-screen orientation; no network request is made and, after closing and reopening, the image is back to its original orientation. Verified by rotating, reopening, and confirming orientation reset; and by confirming no server call fires on rotate.
- **Zoom view-only:** Zooming changes only on-screen scale; no persistence; resets on navigate/close. Verified by zooming, navigating to another image, and confirming reset.
- **Delete permitted:** As owner and as an approved editor guest, deleting the shown image removes it from the memo (reflected after refresh) and the viewer updates or closes appropriately. Verified in both roles.
- **Delete denied:** As a read-only guest, no delete control is present and no client path can delete an image. Verified by inspecting the read-only guest viewer.
- **Owner/guest parity:** The viewer's look and controls match between the owner dashboard and the shared page, each constrained to that actor's rights. Verified by comparing both.
- **Export unchanged:** Exporting before and after using the feature (rotate/zoom/navigate) yields an identical image-related payload (file names only, no version bump). Verified by diffing an export taken before vs. after view-only actions.

## Resolved decisions

- Rotation: **view-only** (CSS transform, not persisted, no server call).
- Zoom: **included**, also view-only (not persisted).
- Delete visibility: **owner + approved editor guest** (follows existing image-delete permissions); read-only guest never sees it.
- Component placement: prefer a **shared pure helper** (ADR-001) if owner/guest code is identical; otherwise duplicate per page.

## Stakeholders

- Decider / Owner: Fabien.
- Consumer: Fabien (owner viewer) and approved share guests (read + download always; delete only with edit rights).

## Context

- Backlog source: `IDEAS.md` → `[IMAGE-CAROUSEL]`. Current state = thumbnails + a simple viewer.
- Existing infra reused: images served by the owner route and the public share image route; upload via the binary-signature check; export stores file names only since v6.
- Governing invariants: `CLAUDE.md` — invariant 5 (guest scope + signature-validated uploads), invariant 6 (no build / self-contained, shared helpers in `templates/partials/_shared.js.html` per ADR-001), invariant 8 (no GSAP on a `<dialog>`).
- This is a behavioral contract. Exact viewer markup, helper names, CSS, and which existing functions/routes are reused belong to the **plan**, not here.
