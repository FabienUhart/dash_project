# MEMORY BANK — dash_project

**Dernière mise à jour :** 2 juillet 2026 (soir — vague carte v20)
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

## État actuel (mise à jour 2 juillet 2026, soir)

- **Version courante : V20.4.29** — ⚠️ **format d'export = v20** (première évolution depuis v19 : `projects.is_trip`, cf. invariant 1 de `CLAUDE.md`). `origin/main` = `8e8709f` [MAP-GROUPS-MENU]. Déploiement Zimaboard manuel par Fabien (hard refresh après — HTML autonome caché).
- **Série carte v20 poussée** (détail normatif : `REALISATION.md` § V20 + `CLAUDE.md` invariant 1) :
  - `[MAP-TIMELINE]` `2089bc8` — **bump export v20**, `projects.is_trip` héritable (NULL/1/0, résolution au plus proche ancêtre, `_resolve_trip` serveur / `resolveTripLocal` partial, invités = `trip` résolu lecture seule) ; frise chronologique des mémos datés + curseur « aujourd'hui » + tracé itinéraire pointillé **réservé aux voyages**. Spec `docs/specs/MAP-TIMELINE-trip-timeline-and-route.md`.
  - `[MAP-TRIP-POLISH]` `3219a66` — marqueurs-vignettes photo numérotés ①② chronologiques (voyages), chips « Jour N », miniatures dans la frise ; **+ fix bloquant « carte noire »** (tuiles + `setView` AVANT tout vecteur, `drawRoute` idempotent, démontage try/catch — voir gotcha `patterns.md`).
  - `[MAP-DAYCHIP-ACTIVE]` + `[MAP-TIMELINE-MOBILE-ORDER]` `e5e7158` — chip « Jour N » actif (un seul, re-clic désélectionne) ; mobile : ordre carte→frise→liste (row aplatie `display:contents !important`, liste protégée `flex:0 0 auto` + min-height du collapse flex du dialog).
  - `[MAP-GROUPS-MENU]` `8e8709f` — liste de points épurée (plus de coches permanentes) + menu « Groupes ▾ » créer/modifier/copier/supprimer ; **gate share resserré à `canEditNow()`** (lien can_edit ET invité approuvé — un anonyme ne voit plus les outils d'édition).
- **Avant la carte (même journée)** : `[AGENDA]`/`[AGENDA-PROJECT]`/`[AGENDA-SMART-MONTH]` (vue calendrier 3 pages, D&D, filtre projet, mois d'atterrissage utile), `[GUEST-RESEND-LINK]`, `[GUEST-SUBPROJECT]`, et la vague V19.8→V19.13 (hub `/share/hub/`, cookie session HttpOnly, `[GUEST-EDIT]`, `[SETTINGS-TABS]`, `[SIDEBAR-TREE]`, `[AUTO-REFRESH]`). Tout est sur `origin/main`, tout validé Cowork/Chrome.
- **Hub invité** (inchangé) : routes sous `/share/hub/<hub_token>`, cookie HttpOnly `dashhubsession` 180 j (lecture `/data` seulement), écritures par jetons de dossier revalidées serveur ; `_data_version` exclut les volatils (`last_seen_at`/`session_token`/`activity_seen_at`).
- **Backlog** : `[NOTIFY-EMAIL]` (plomberie SMTP prête), `[VOTES]`, `[TABLES]`, `[TAG-NAV]`, `[IMAGE-TRASH]`, `[IMAGE-LAZY-LOAD]` (si perf vignettes carte), couleur de groupe (écartée de [MAP-GROUPS-MENU]), confort/UX — voir `IDEAS.md` (section « En cours » vide).


## Instructions pour Claude

- Avant une modif importante : lire **`CLAUDE.md`** (surtout les 8 invariants + le format d'export), puis `docs/adr/`, puis ce fichier et `patterns.md` si pertinent.
- Ne jamais casser la **compat ascendante de l'export/import** ni les **invariants** de `CLAUDE.md`.
- Après une grosse feature ou décision d'archi : proposer une mise à jour de cette Memory Bank **et** de `CLAUDE.md`, sans dupliquer le contenu entre les deux.
