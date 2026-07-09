# MEMORY BANK — dash_project

**Dernière mise à jour :** 9 juillet 2026 (V20.6.39 — UX carte : ✕ sticky + sync marqueur↔jour)
**Nature :** index de mémoire. La **source canonique** reste `CLAUDE.md` (racine). Ce fichier pointe vers elle, il ne la recopie pas (anti-duplication — cf. ADR-001).

## Résumé global

Dashboard personnel auto-hébergé sur un **Zimaboard**, utilisé comme page d'accueil du navigateur : liens vers services self-hosted (catégories, statuts online/offline, favicons), mémos/tâches façon Planify (projets imbriqués, priorités, échéances, sous-tâches, récurrence), carte Leaflet des mémos géolocalisés, et partage externe par lien à jeton + PIN (invités identifiés, droits, commentaires). Recherche instantanée, horloge multi-fuseaux, météo, thème clair/sombre.

## Stack technique (réelle — PAS Django/Dash)

- **Backend :** Flask + SQLite **sans ORM, sans blueprint** — tout dans `app.py`. Migration de schéma additive dans `init_db()`.
- **Frontend :** **JS vanilla**, pas de framework, **pas de build**. Un fichier par page : `templates/index.html` (propriétaire) et `templates/share.html` (invité). Helpers purs mutualisés dans `templates/partials/_shared.js.html` (inclus au rendu Jinja — ADR-001).
- **Données :** SQLite (`data/dashboard.db`), uploads (`data/uploads/`), en volume Docker. Export/import JSON versionné (v1->v20), rétro-compatible et non destructif.
- **Déploiement :** `docker compose up -d --build` (gunicorn, port 8099), derrière **Caddy + Authelia** en prod. Pas d'auth dans l'app.
- **Dépendances front auto-hébergées** dans `static/` (Quill, GSAP, Leaflet) — pas de CDN au runtime.

## Sources canoniques (à lire avant toute modif importante)

- **`CLAUDE.md`** (racine) — architecture, **8 invariants**, format d'export, historique détaillé, procédure de test. **Référence.**
- **`docs/adr/`** — décisions d'archi. ADR-001 = mutualisation des helpers front owner/invité (Option C, partial Jinja).
- **`IDEAS.md`** — backlog (quick wins, confort/UX, dette technique, ambitieux), tags `[NOM]` repris par Claude Code.
- **`patterns.md`** (ici) — conventions transverses + pointeurs.
- **`dash-cicd-setup.md`** (ici, reference) — infra CI/CD : runner self-hébergé `zimaboard` (systemd, user `casaos`, `~/actions-runner`), dossier de déploiement `/mnt/StorageNaN/home_casaos/Documents/projects/dash_project`, workflows `ci.yml`/`deploy.yml`, process release (tag `VX.Y.Z` = tête de `REALISATION.md`) + rollback + gotcha « tag sur commit sans workflows ».

## État actuel (mise à jour 9 juillet 2026)

- **Version courante : V20.6.39** — format d'export toujours **v20**. Derniers lots UX carte (partial `_shared.js.html` → parité owner/share/hub) : `[MAP-MARKER-DAY-SYNC]` V20.6.39 (clic marqueur Leaflet = sélectionne le jour du point via le MÊME chemin que le chip « Jour N » — `marker.on('click', () => applyDay(p.due_date || null))` ; sans date/pin projet → « Tous » ; popup conservée) et `[MAP-CLOSE-UX]` V20.6.37 (en-tête `.map-head` sticky top:0 + bouton ✕ `.map-x` aria Fermer, visible desktop aussi ; footer carte non-flottant en mobile `position:static` — les AUTRES pop-ins gardent leur pied sticky [DIALOG-STICKY-ACTIONS]) **puis** V20.6.38 (revert : retrait du bouton flottant « ↑ » `#map-totop` ajouté en .37 — le ✕ suffit). Avant : `[VERSION-VISIBLE]` V20.6.36 (version de build visible — `_build_version()` parse `REALISATION.md` → `BUILD_VERSION`, footer owner version complète, route `GET /api/version` ; share/hub gardent `v20`) et `[MAP-DAYCHIP-ALL]` V20.6.35 (chip « 🌍 Tous » en tête de la frise ; `applyDay(d)` = chemin unique de (dé)sélection de jour). Encore avant : hotfixes mobile carte V20.6.32→34. `origin/main` avant ce push = `ae007ca`. Détail : `REALISATION.md` § V20. Déploiement Zimaboard manuel par Fabien (hard refresh après — HTML autonome caché).
- **Avant ces hotfixes (7 juillet, commités/poussés)** : `[MEMO-TABLES]` V20.5.30 (tableaux dans l'éditeur Quill des mémos, module `quill-table-better` 1.2.3 vendorisé, helper `applyTableBetter()` du partial, 3 pages, dégradation propre) et `[DIALOG-STICKY-ACTIONS]` V20.6.31 (pied des pop-ins en `position:sticky`, 3 pages, + fix du sélecteur `order:4` mort de la carte share/hub). `origin/main` avant ce push = `b1c56a8`.
- **Série carte v20 poussée** (détail normatif : `REALISATION.md` § V20 + `CLAUDE.md` invariant 1) :
  - `[MAP-TIMELINE]` `2089bc8` — **bump export v20**, `projects.is_trip` héritable (NULL/1/0, résolution au plus proche ancêtre, `_resolve_trip` serveur / `resolveTripLocal` partial, invités = `trip` résolu lecture seule) ; frise chronologique des mémos datés + curseur « aujourd'hui » + tracé itinéraire pointillé **réservé aux voyages**. Spec `docs/specs/MAP-TIMELINE-trip-timeline-and-route.md`.
  - `[MAP-TRIP-POLISH]` `3219a66` — marqueurs-vignettes photo numérotés ①② chronologiques (voyages), chips « Jour N », miniatures dans la frise ; **+ fix bloquant « carte noire »** (tuiles + `setView` AVANT tout vecteur, `drawRoute` idempotent, démontage try/catch — voir gotcha `patterns.md`).
  - `[MAP-DAYCHIP-ACTIVE]` + `[MAP-TIMELINE-MOBILE-ORDER]` `e5e7158` — chip « Jour N » actif (un seul, re-clic désélectionne) ; mobile : ordre carte→frise→liste (row aplatie `display:contents !important`, liste protégée `flex:0 0 auto` + min-height du collapse flex du dialog).
  - `[MAP-GROUPS-MENU]` `8e8709f` — liste de points épurée (plus de coches permanentes) + menu « Groupes ▾ » créer/modifier/copier/supprimer ; **gate share resserré à `canEditNow()`** (lien can_edit ET invité approuvé — un anonyme ne voit plus les outils d'édition).
- **Avant la carte (même journée)** : `[AGENDA]`/`[AGENDA-PROJECT]`/`[AGENDA-SMART-MONTH]` (vue calendrier 3 pages, D&D, filtre projet, mois d'atterrissage utile), `[GUEST-RESEND-LINK]`, `[GUEST-SUBPROJECT]`, et la vague V19.8→V19.13 (hub `/share/hub/`, cookie session HttpOnly, `[GUEST-EDIT]`, `[SETTINGS-TABS]`, `[SIDEBAR-TREE]`, `[AUTO-REFRESH]`). Tout est sur `origin/main`, tout validé Cowork/Chrome.
- **Hub invité** (inchangé) : routes sous `/share/hub/<hub_token>`, cookie HttpOnly `dashhubsession` 180 j (lecture `/data` seulement), écritures par jetons de dossier revalidées serveur ; `_data_version` exclut les volatils (`last_seen_at`/`session_token`/`activity_seen_at`).
- **Backlog** : prochains lots planifiés `[BOARD-SUBHIDE]` (V20.7) et `[COMMENT-REACTIONS]` (V21.0, ⚠️ bump export v21) — specs verrouillées dans `docs/specs/`. Aussi : `[NOTIFY-EMAIL]` (plomberie SMTP prête), `[TAG-NAV]`, `[IMAGE-TRASH]`, `[IMAGE-LAZY-LOAD]`, couleur de groupe (écartée de [MAP-GROUPS-MENU]), confort/UX — voir `IDEAS.md`.


## Instructions pour Claude

- Avant une modif importante : lire **`CLAUDE.md`** (surtout les 8 invariants + le format d'export), puis `docs/adr/`, puis ce fichier et `patterns.md` si pertinent.
- Ne jamais casser la **compat ascendante de l'export/import** ni les **invariants** de `CLAUDE.md`.
- Après une grosse feature ou décision d'archi : proposer une mise à jour de cette Memory Bank **et** de `CLAUDE.md`, sans dupliquer le contenu entre les deux.
