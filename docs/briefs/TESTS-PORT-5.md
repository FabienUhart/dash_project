# Brief CC — [TESTS-PORT-5] : les entrailles de l'import

> **La douleur d'origine.** `import_links` (157 lignes) + `_import_dry_run` (46, **0 %**) sont
> le plus gros bloc nu, et c'est là que [IMPORT-CONTENT-DEDUP-FIX] avait perdu **12 mémos sur 51
> en silence** (V27.36.228). La batterie d'invariants tient déjà la **crête** (round-trip sans
> perte, v1 importable, non-destruction, uid stable, 2 mémos même contenu/uid distinct). Ce lot
> descend dans les **branches** que la crête ne touche pas : dry-run, « Importer ici », résolution
> des projets, remap des priorités, dédup fine. Invariants **1/2/3**.
>
> **Nature = caractérisation + mutation** (même moule). Un test qui tombe = bug réel → arrête-toi,
> signale. Chaque garde éprouvée par mutation. **Zéro réseau.**
>
> **Discipline** : fichier de test only, aucun changement applicatif. `make test` vert → journal +
> handoff → **STOP**. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 1. Fichier : `tests/back/test_import_internals.py` (marqueur `invariant`)

Contrats relevés dans `app.py` (ne pas ré-explorer) :

- `POST /api/import` corps `{links?, memos?, categories?, projects?, priorities?, resolutions?}`.
- `POST /api/import?dry_run=1` → **rapport LECTURE PURE, aucune écriture** :
  `{projects:[{name,status,children}], memos:[{uid,title,project_name,status,conflict_kind?,updated_local?,updated_fichier?}], bilan:{projects_new,projects_merge,memos_new,memos_skip,conflicts_active,conflicts_trashed}}`.
  Statut projet : `merge` si uid connu **ou** nom connu, sinon `new`. Statut mémo : `new` (uid
  inconnu) · `skip` (uid connu + **même signature** `_memo_import_sig` = contenu/titre/done/date/heure)
  · `conflict`+`active` (uid connu, signature différente, pas en corbeille) · `conflict`+`trashed`
  (uid connu, local en corbeille).
- `POST /api/import?target_parent_id=<id>` (« Importer ici ») : `<id>` non entier → **400**
  « target_parent_id invalide » · dossier inconnu → **400** « dossier cible introuvable » · si le
  dossier cible porte un **nom présent dans le fichier** → **400** cycle. Sinon rattache **au dossier
  cible** les **racines NOUVELLES** du fichier (jamais un projet existant — invariant 2 ; jamais un
  sous-dossier qui a son parent dans le fichier) ; collision de nom au dossier cible → **laissé à la
  racine**, jamais de 409.
- `resolutions` : `{ "<uid>": "overwrite" | "duplicate" | "skip" }`, absent = `skip` (newer-wins par
  uid). **Sémantique exacte à vérifier** contre le bloc d'insertion mémo (autour de la garde
  `if res != "duplicate" and not uid:`) avant de figer les assertions.

Helpers : réutilise `_project`, `_memo` (via API) pour poser l'état EXISTANT, puis `POST /api/import`
avec des payloads forgés ; vérifie par `GET /api/export` (mémos non supprimés) ou lecture directe de
la base temp.

---

## 2. Les tests (la liste = la spec)

### A. `_import_dry_run` — lecture pure, 0 % aujourd'hui (gros gain, sûr)

1. **`test_dry_run_writes_nothing`** — base peuplée, `POST …?dry_run=1` avec des mémos neufs →
   200 + rapport ; puis `GET /api/export` **inchangé** (aucun mémo ajouté, rien de commité).
2. **`test_dry_run_project_new_vs_merge`** — un projet d'uid **connu mais renommé** → `merge` ;
   un projet inconnu → `new` ; `bilan.projects_new/merge` cohérents.
3. **`test_dry_run_memo_new_skip_conflict`** — quatre mémos montés exprès : uid inconnu → `new` ;
   uid connu **identique** (même signature) → `skip` ; uid connu **modifié** → `conflict/active` ;
   uid connu dont le local est **en corbeille** → `conflict/trashed`. `bilan` correspondant.
4. **`test_dry_run_arbre_projets`** — un parent + son enfant dans le fichier → l'arbre `projects`
   du rapport imbrique l'enfant sous le parent.

### B. `target_parent_id` — « Importer ici » (sûreté des données, invariant 2)

5. **`test_import_here_invalid_id_400`** — `target_parent_id=abc` → 400.
6. **`test_import_here_unknown_folder_400`** — id inexistant → 400 « introuvable ».
7. **`test_import_here_cycle_400`** — le dossier cible porte un **nom du fichier** → 400 cycle.
8. **`test_import_here_attaches_new_root`** — une **racine nouvelle** du fichier atterrit **sous**
   le dossier cible ; un projet **existant** n'est **jamais** déplacé ; un **sous-dossier** (parent
   dans le fichier) reste sous son parent, pas sous la cible.
9. **`test_import_here_collision_stays_at_root`** — nom déjà pris sous la cible → le nouveau reste
   **à la racine** (tolérant, aucun 409).

### C. Résolution projets / catégories / priorités

10. **`test_project_resolved_by_uid_even_if_renamed`** — projet local d'uid U ; import d'un projet
    uid U mais **nom différent** → **merge** dans l'existant (pas de doublon), uid local inchangé.
11. **`test_projects_created_topologically`** — le fichier liste l'**enfant avant le parent** →
    les deux créés, enfant **sous** le parent (jamais « tout à la racine »).
12. **`test_memo_project_resolved_by_uid_then_name`** — mémo avec `project_uid` connu → rattaché ;
    `project` (nom) inconnu → **dossier créé à la racine**.
13. **`test_category_enriches_but_never_overwrites`** — catégorie existante sans couleur : l'import
    avec couleur la **remplit** ; catégorie déjà colorée : l'import **ne l'écrase pas**.
14. **`test_priority_remapped_by_name_not_raw_id`** — invariant 1 (v10) : un mémo importé dont la
    priorité pointe un **id fichier** est remappé sur la priorité **de même nom** en local (jamais
    l'id brut). Monte deux bases où « P2 » n'a pas le même id pour le prouver.

### D. Dédup mémo & résolutions (le cœur données)

15. **`test_content_dedup_only_without_uid`** — deux mémos **sans uid** au **même contenu** dans le
    fichier → **un seul** créé (anti-doublon legacy) ; MAIS deux mémos **même contenu / uid
    distinct** → **les deux** survivent (le bug corrigé — complète le flagship côté « sans uid »).
16. **`test_resolutions_overwrite_duplicate_skip`** *(sémantique à vérifier d'abord)* — sur un mémo
    d'uid en conflit : `resolutions={uid:"overwrite"}` → mis à jour ; `"duplicate"` → **nouvelle**
    ligne (nouvel uid) ; `"skip"`/absent → **inchangé**. Si la sémantique réelle diffère du brief,
    **fige le réel et signale** (comme toujours).

> Lot conséquent (~16 tests). **Point de découpe si besoin** : livre **A + B + D** (dry-run,
> Importer ici, dédup — le plus chargé en risque « données ») et note **C** (résolution
> projets/priorités) en `[TESTS-PORT-5b]` plutôt que de bloquer. Ne te force pas à tout caser
> dans un lot indigeste.

---

## 3. Definition of Done

1. `tests/back/test_import_internals.py` créé (marqueur `invariant`), gardes éprouvées par mutation
   (au minimum le dry-run non-écrivant #1, « Importer ici » n'affecte pas l'existant #8, et la dédup #15).
2. `make test` **vert** (ou rouge **signalé**, jamais masqué).
3. `make test-cov` : `import_links` et `_import_dry_run` remontent nettement (c'est le plus gros bloc nu).
4. `git status` : seul `tests/` bouge.
5. Journal + handoff, **STOP**. Commit `tests/back/test_import_internals.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT-5.md`) après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 4. Après ce lot

`[TESTS-PORT-6]` (utilitaires owner, **sans réseau** : ZIP, `_fx_rates`/`hub_fx`, `hub_send_link`,
branches vocales de `_soft_delete_comment`), puis on quitte le chantier [TESTS-PORT] — la couverture
sera passée bien au-delà des 50 %, avec les zones à risque (surface publique + données) sous garde.
