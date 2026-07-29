# [PROJECT-NAME-PER-FOLDER] — Noms de dossiers dupliqués (unicité par dossier parent)

**Brief pour Claude Code — lot V25.0.Z (⚠️ BUMP EXPORT v24 → v25, voir §6).**
Lire `CLAUDE.md` + `.claude/memory/MEMORY.md` avant de commencer. Z = dernier Z de `REALISATION.md` + 1.

## 1. Contexte / bug constaté en prod

Créer un dossier (projet) dont le nom existe déjà **n'importe où** dans l'arbre renvoie
409 « project already exists ». C'est un héritage d'avant `parent_id` (projets à plat) :

- schéma : `projects.name TEXT NOT NULL UNIQUE` (contrainte **globale**, `init_db()`) ;
- garde explicite dans `create_project` (`POST /api/projects`, ~l. 1536) ;
- même garde côté invité `share_add_project` (`POST /share/<t>/projects`, ~l. 7104) et
  `share_update_project` (rename, ~l. 7199) ;
- ⚠️ le PUT owner `update_project` (~l. 1561) ne fait **aucune** garde applicative sur le nom
  → un rename en doublon lève l'IntegrityError SQLite (500 brut). Bug latent à corriger au passage.

Depuis la hiérarchie ([v12] projets imbriqués), c'est illégitime : « restaurants » sous
« Voyage Japon » ET sous « Voyage Corée » doit être possible.

## 2. Décisions (tranchées avec Fabien — ne pas rediscuter, implémenter)

- **D1 — Unicité PAR DOSSIER PARENT, pas d'unicité globale.** Deux dossiers de même nom ne
  peuvent pas être **frères** (même `parent_id`, racine incluse). Sémantique système de
  fichiers. Comparaison **inchangée** par rapport à aujourd'hui (`WHERE name = ?`,
  sensible à la casse — ne pas introduire de normalisation).
- **D2 — Identifiant stable `uid` sur les projets** (pattern `memos.uid`, invariant 3) :
  UUID généré à la création, **backfillé par `init_db()`**, jamais régénéré. C'est LUI qui
  porte le match export/import désormais — le nom ne peut plus être une clef fiable.
- **D3 — Bump du format d'export : v25** (le format v24 identifie les projets par NOM —
  `memos[].project`, `projects[].parent`, ambigu dès qu'un doublon existe). Voir §6.
- **D4 — La collision s'applique aussi au DÉPLACEMENT** : déplacer un dossier (D&D ou PUT
  `parent_id`) vers un parent qui contient déjà un frère du même nom → 409 explicite
  (« un dossier de ce nom existe déjà à cet endroit »), owner comme invité. Jamais de 500.
- **D5 — Pas de renommage automatique** (pas de suffixe « (2) ») côté owner/invité sur les
  routes normales. Seule EXCEPTION : le provisioning des espaces invités et l'import
  gardent leur logique de suffixe/dédup existante, **re-scopée au parent** (§4, §5).

## 3. Migration de schéma (additive, non destructive — invariant 1)

SQLite ne sait pas retirer une contrainte UNIQUE → **rebuild de la table `projects`**
(pattern [FAVORITES V1.1] : rename → create → port → drop) :

1. `ALTER TABLE projects RENAME TO projects_v1` ; recréer `projects` **sans** UNIQUE sur
   `name`, avec **toutes** les colonnes actuelles (lister dynamiquement via
   `PRAGMA table_info` pour ne rien perdre : color, position, tags, emoji, parent_id,
   location, description, marker_color, is_trip, vote_*, created_by, role_floor, etc.) ;
2. port intégral **en préservant les `id`** (référencés par `memos.project_id`, `shares`,
   `attachments.project_id`, `favorites`, `votes`, `memo_votes`… — aucune FK déclarée mais
   les ids doivent rester identiques) ; `DROP TABLE projects_v1` ;
3. nouvel index : `CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_name_parent ON
   projects(COALESCE(parent_id, 0), name)` — ⚠️ un simple `UNIQUE(parent_id, name)` ne
   marche PAS (NULL distincts en SQLite → doublons à la racine possibles), d'où le
   `COALESCE` (les ids commencent à 1, 0 est libre) ;
4. colonne additive `projects.uid TEXT DEFAULT ''` + **backfill** `uuid4` pour toute ligne
   sans uid (même mécanique que le backfill des `memos.uid`) ;
5. migration **idempotente** (guard : ne rebuild que si le UNIQUE global est encore là —
   détectable via `PRAGMA index_list` / `sqlite_master`) et sûre multi-workers gunicorn.

## 4. Backend — routes et gardes (sweep complet)

Recenser TOUS les `FROM projects WHERE name` (grep) et les re-scoper au parent :

- `create_project` (owner) : garde `(name, parent…)` — ⚠️ aujourd'hui `POST /api/projects`
  ignore `parent_id` (le front fait un PUT après création, cf. memory Cowork) : la garde à
  la création se fait donc **à la racine** (parent NULL), et c'est le PUT qui revalide au
  déplacement (D4). Si tu préfères accepter `parent_id` au POST au passage, OK mais sans
  casser le front existant.
- `update_project` (owner, PUT) : ajouter la garde applicative rename **ET** déplacement
  (D4) — combinaison (nouveau nom, nouveau parent) testée en une fois. Fin du 500 latent.
- `share_add_project` + `share_update_project` (invité) : mêmes gardes, scopées au parent
  visé (déjà revalidé dans le périmètre du share — invariant 5, rien d'autre ne change).
- Provisioning des espaces invités (~l. 4390, « suffixe discret si déjà pris ») : la
  recherche de collision passe de globale à **scopée au dossier parent** (`sp["id"]`).
- Messages d'erreur en français, cohérents : « un dossier de ce nom existe déjà à cet
  endroit ».

## 5. Export / import v25 (cœur du lot)

**Export** (`_build_export`, global ET [EXPORT-SUBTREE]) :

- chaque projet émet **`uid`** et **`parent_uid`** (uid du parent, `''` si racine) — les
  clefs `name`/`parent` (nom) **restent** émises (lisibilité + compat) ;
- chaque mémo émet **`project_uid`** en plus de `project` (nom) ;
- [EXPORT-SUBTREE] : `proj_names` doublé d'un `proj_uids` ; le parent hors sous-arbre est
  émis en `parent_uid` + `parent` (nom) comme aujourd'hui ;
- `APP_VERSION = "25"`, `version: 25` dans l'export.

**Import** (`/api/import`, dry-run [IMPORT-PREVIEW] inclus — même logique de résolution) :

- résolution d'un projet : **1) par `uid`** s'il est présent et connu ; **2) sinon par
  (nom, parent résolu)** — c'est-à-dire par chemin, plus jamais par nom à plat ; **3) sinon
  création** (uid importé conservé, ou généré si absent). Les deux passes de résolution du
  `parent` ([v12]) passent à la même logique uid-d'abord ;
- compat v1→v24 (invariant 1) : pas d'uid projet dans le fichier → résolution (nom, parent)
  ; dans ces anciens exports les noms étaient globalement uniques à l'émission, donc le
  chemin est toujours résolvable. Si malgré tout une ambiguïté résiduelle survient (même
  (nom, parent) impossible — ne devrait pas arriver), prendre le match de plus petit `id`
  (déterministe), jamais d'erreur ;
- **upsert par uid** : uid connu + nom différent = **le projet a été renommé** → mise à
  jour du nom (newer-wins, invariant 2), pas de doublon ;
- `target_parent_id` ([V20.12.53]) : « racine nouvelle » s'évalue désormais par
  uid-puis-chemin, comportement sinon inchangé (D1 de [IMPORT-PREVIEW] : l'import global
  des Paramètres et le POST sans `dry_run`/`resolutions` restent compatibles scripts) ;
- ré-import d'un export v25 complet → **0 ajout, 0 doublon** (scénario critique n° 2) ;
- [IMPORT-PREVIEW] : l'arbre new/merge s'affiche inchangé (les doublons de nom sont
  désambiguïsés par leur position dans l'arbre indenté).

## 6. Versionnage & journal

- **X : 24 → 25** (changement de format = seul motif de bump, cf. CLAUDE.md §Versionnage).
- Ajouter l'entrée **v25** à l'invariant 1 de `CLAUDE.md` (uid/parent_uid/project_uid,
  résolution uid-d'abord puis (nom, parent), unicité par dossier, upsert non destructif,
  compat v1→v24 garantie) + section Historique.
- `REALISATION.md` : entrée `[V25.0.Z]` ; `IDEAS.md` : basculer l'item en « Fait ».
- Spec : ce fichier fait foi (`docs/specs/PROJECT-NAME-PER-FOLDER-duplicate-names.md`).

## 7. Frontend (3 pages, léger)

- Pop-ins création/édition : afficher le 409 via `notify()` avec le nouveau message
  (jamais d'`alert`). D&D projet→projet : un 409 au déplacement → `notify()` + retour à
  l'état d'avant (pas de déplacement fantôme à l'écran).
- Aucun autre chantier : sidebar, « Déplacer vers… », vue Plan et pop-in carte montrent
  déjà la hiérarchie (les homonymes sont désambiguïsés par leur position dans l'arbre) ;
  les sélecteurs de dossier travaillent par `id`.

## 8. Tests avant commit (copie de base, jamais `data/dashboard.db`)

`python3 -m py_compile app.py` + scénarios critiques du CLAUDE.md, plus :

1. migration sur base existante : app démarre, ids projets **inchangés**, uid posés,
   `GET /api/projects` OK, partages/favoris/votes intacts ;
2. créer « restaurants » sous deux parents différents → 201 ; deux fois sous le même → 409 ;
   deux fois à la racine → 409 ;
3. rename owner vers un nom de frère → 409 propre (plus de 500) ; déplacement (PUT
   `parent_id` et D&D) vers un parent contenant un homonyme → 409 + UI intacte ;
4. invité : mêmes cas via `/share/<t>/projects` et PUT projet (scope inchangé, invariant 5) ;
5. export v25 → ré-import → 0 ajout / tout « skipped » ; import d'un **export v24 réel**
   (backup de Fabien) → 0 doublon, arbre identique ; renommer un dossier puis ré-importer
   son export v25 antérieur → le nom N'est PAS écrasé si le local est plus récent
   (invariant 2) ;
6. [EXPORT-SUBTREE] d'un sous-arbre contenant un homonyme d'un dossier externe → « ⬆
   Importer ici » le raccroche au bon endroit (uid), pas au faux jumeau ;
7. provisioning espace invité avec prénom en collision **dans le même dossier** → suffixe ;
   même prénom dans un autre dossier → pas de suffixe.

## 9. Hors périmètre (ne pas faire)

- Pas d'unicité insensible à la casse, pas de normalisation des noms existants.
- Pas de fusion/dédoublonnage de projets existants.
- Catégories et priorités : unicité globale **conservée** (pas de hiérarchie, hors sujet).
- Pas de refonte de l'import au-delà de la résolution décrite en §5.

## 10. Fin de réalisation

Process habituel : tests → journal → `docker compose up -d --build` (localhost:8099) →
`.claude/handoff.json` pour la validation Cowork. **Ni commit ni push** sans feu vert Fabien.
