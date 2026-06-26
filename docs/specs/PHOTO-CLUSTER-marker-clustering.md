# [PHOTO-CLUSTER] — Regroupement (clustering) des marqueurs photo de la carte

> Status: **VALIDATED & LOCKED** (reviewer score 96/100, 2026-06-26). Immutable contract — changes require a new spec revision. Tag: `[PHOTO-CLUSTER]`. Raffinement de `[PHOTO-MAP]` (calque photo de la carte projet, owner + invité).

## Target

When the photo layer of a project's map dialog shows overlapping or nearby photo markers, group them into a single cluster marker bearing a count badge that splits into its constituent markers as the user zooms in, and fans out (spiderfies) the photos sharing the exact same point on demand — for the owner and approved share guests alike, degrading to today's plain photo markers if the clustering capability is unavailable.

## Hard constraints

- **Photo layer only.** Clustering applies exclusively to the photo markers introduced by `[PHOTO-MAP]`. The memo/project points layer keeps its current behavior unchanged; no clustering is added to it.
- **Self-hosted, no runtime CDN (invariant 6).** The clustering capability ships as files served from the app's own static assets (script + styles), installed into the build like the other self-hosted front-end libraries. No CDN fetch, no runtime external dependency is introduced.
- **Count badge on overlap.** When several photo markers occupy the same or close-enough screen positions at the current zoom, they collapse into one cluster marker showing the number of photos it contains.
- **Split on zoom.** Zooming in progressively separates a cluster into smaller clusters and, eventually, individual photo markers, so the user can reach any single photo by zooming.
- **Spiderfy on exact-same point.** Photos pinned at the exact same coordinates (e.g. several photos of one place) cannot be separated by zoom; activating their cluster fans them out (a "spider" of individual markers) so each photo is individually reachable and clickable.
- **Individual photo behavior preserved.** A single (unclustered or spiderfied) photo marker keeps the `[PHOTO-MAP]` behavior: it is visually the photo marker and clicking it opens that image in the existing image viewer.
- **Graceful degradation.** If the clustering capability is absent or fails to load, the photo layer still works exactly as in `[PHOTO-MAP]` — plain individual photo markers, each clickable — with no error, no blank map, and no blocked dialog.
- **Owner/guest parity within scope (invariant 5).** Clustering looks and behaves the same on the owner dashboard and on the shared page. The guest page can load the clustering files through the existing public static-asset allowlist (the same mechanism already used for the map/editor assets); the allowlist gains only these specific clustering files and nothing else. No new public route or capability beyond serving these whitelisted static files; the guest photo data itself stays scoped exactly as `[PHOTO-MAP]` defined.
- **Respects existing photo-layer filtering.** Clustering composes with the photo layer's current scope and sub-project/group focus: only the photos that the photo layer would display are clustered, and the focus/greyed-out distinction from `[PHOTO-MAP]` is preserved (a cluster reflects the photos currently shown).
- **No dialog animation regression (invariant 8).** The map dialog keeps its CSS-based entrance; no GSAP transform is applied to the `<dialog>` element. Clustering/spiderfy animations are confined to map markers, never the dialog.
- **Export and data unchanged.** No change to the export format, to `image_meta`, to any schema, route shape, or server behavior. This is a front-end rendering refinement of the photo layer.

## Non-goals

- **No clustering of memo/project points** — photo layer only, this run.
- **No new server work**: no endpoint, no schema, no export change, no change to how photo metadata is produced or scoped (`[PHOTO-MAP]` stands as-is).
- **No change to the chronological side panel ("frise")** of `[PHOTO-MAP]`; it keeps listing photos as today. (Clustering is a map-marker concern.)
- **No custom cluster theming beyond a legible count badge** — no heatmap, no cluster-coloring by date/place, no per-cluster thumbnails.
- **No CDN fallback** when the local files are missing — missing capability means plain markers (degradation), never an external fetch.
- **No new external library for the memo points** or anywhere outside the photo layer.

## Done-when

- **Cluster with count appears:** On a project whose photo layer has several nearby photos, opening the map and enabling the photo layer shows a cluster marker with a count instead of overlapping pins. Verified by adding N nearby GPS photos and confirming, at low zoom, exactly one cluster marker whose badge count equals N (no individual overlapping pins shown).
- **Splits on zoom:** Zooming in breaks the cluster into smaller clusters/individual markers until each photo is individually visible. Verified by zooming in and reaching a single photo marker.
- **Spiderfy on identical point:** Several photos at the exact same coordinates fan out when their cluster is activated, and each fanned marker opens its own image. Verified by adding ≥2 photos with identical coordinates and activating the cluster.
- **Single photo opens viewer:** A non-clustered (or spiderfied) photo marker opens the correct image in the existing viewer. Verified by clicking an individual marker.
- **Degrades with no plugin:** With the clustering files absent/unloadable, the photo layer renders plain individual markers, all clickable, with no console error and a working map dialog. Verified by removing/blocking the clustering files and re-opening the map.
- **Guest parity + allowlist (invariant 5):** On a share link, an approved guest sees the same clustering, the clustering files load via the static-asset allowlist, and no asset outside that explicit allowlist is exposed. Verified by opening a shared project map as a guest and confirming clustering works and only the whitelisted files are served.
- **Filtering preserved:** With a sub-project/group focus active, the cluster reflects only the photos the photo layer currently shows (focused vs greyed), matching `[PHOTO-MAP]`. Verified by toggling a focus filter and confirming the clustered count changes to match exactly the number of currently-shown photos.
- **No CDN (invariant 6):** No runtime request to an external host is introduced by clustering; the capability resolves from local static files only. Verified by building/serving offline and confirming clustering works with no outbound asset request.
- **No dialog regression (invariant 8):** The map dialog still centers with its CSS entrance and `::backdrop`; no GSAP transform on the dialog. Verified by opening the map dialog.
- **Memo points unchanged:** The memo/project points layer renders exactly as before (no clustering, no behavior change). Verified by opening a map with located memos and confirming identical behavior to before this feature.

## Stakeholders

- Decider / Owner: Fabien.
- Consumer: Fabien (owner map dialog) and approved share guests (clustered photo layer, in scope).

## Context

- Backlog source: `IDEAS.md` → `[PHOTO-CLUSTER]` (line 103, under `[PHOTO-MAP]`). The backlog names **Leaflet.markercluster** as the intended self-hosted plugin and "spiderfy" as the same-point behavior; the concrete library, file names, allowlist entries, and wiring belong to the **plan**, not here.
- Builds on `[PHOTO-MAP]` (implemented): the photo layer lives in the shared `runMapDialog` (one partial used by both the owner and the share page), renders photo markers, applies scope + sub-project/group focus, and opens an image in the existing viewer on click. This spec only changes how those photo markers are grouped on the map.
- Existing infra reused: the self-hosted front-end asset convention (owner via the app's static path, guest via the public static-asset allowlist already used for the map/editor libraries), and the existing map dialog and image viewer.
- Governing invariants: `CLAUDE.md` — invariant 5 (guest scope + public asset allowlist), invariant 6 (no build-time CDN, self-hosted deps), invariant 8 (no GSAP on a `<dialog>`), and the standing export-unchanged rule (here: strictly unchanged — front-end only).
- This is a behavioral contract. The plugin choice, exact static file names, allowlist additions, cluster styling, and degradation check belong to the **plan**.
