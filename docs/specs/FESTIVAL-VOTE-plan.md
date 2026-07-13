# Plan de réalisation — [FESTIVAL-VOTE] (Vieilles Charrues 2026)

> Compagnon du brief verrouillé [FESTIVAL-VOTE-charrues-coup-de-coeur.md](FESTIVAL-VOTE-charrues-coup-de-coeur.md) (le brief = quoi ; ce plan = comment et dans quel ordre). Ancrages = noms de fonctions/tables (pas de `file:line`, app.py bouge vite) — re-confirmer au moment du codage.
> **⏰ Deadline dure : livré + validé + déployé + seedé en prod au plus tard mercredi 15 juillet au soir** (festival jeudi 16). Chaque phase est committable/testable seule : si le temps manque, on coupe par le bas (voir § Repli).

Cible : **V23.1.z** — `end_time` + `memo_hearts` **non exportés** → format d'export **v23 inchangé**, `APP_VERSION` inchangée.

## Contrainte d'ordre (dure)

Migration (Phase 1.1) avant toute lecture/écriture de `end_time`/`memo_hearts`. Backend (Phases 1-3) avant frontend (Phase 5). Le seed (Phase 4) peut être développé en parallèle du front mais exécuté seulement après la Phase 1 (il pose des `end_time`).

## Phase 0 — Prérequis (avant de coder)

0.1. Lire le brief + le seed JSON (`docs/specs/festival-vote-seed-vieilles-charrues-2026.json` : 83 passages, 6 `scene_locations`, convention post-minuit).
0.2. **Images du plan festival** : captures fournies par Fabien (source Google Images) directement dans `docs/specs/` (fichiers `plan-festival-2026-*.png|jpg`, ou à défaut toute image de `docs/specs/` dont le nom contient « plan »). Si absentes : avancer quand même (concerne uniquement l'étape 4.5), sauter la pièce jointe du plan illustré et le noter dans le handoff.
0.3. Base de test : `cp data/dashboard.db /tmp/test.db` — jamais `data/dashboard.db` directement (CLAUDE.md § tests).

## Phase 1 — Backend socle ❤️ (app.py)

1.1. **Migration additive** dans `init_db()` : (a) `ALTER TABLE memos ADD COLUMN end_time TEXT DEFAULT ''` (garde `PRAGMA table_info`, gabarit `due_time`) ; (b) `CREATE TABLE IF NOT EXISTS memo_hearts (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, memo_id INTEGER NOT NULL, voter TEXT DEFAULT '', created_at TEXT, UNIQUE(memo_id, voter))`. Jamais destructif (invariant 1).
1.2. **Validation** : `_clean_end_time` = réutiliser `_clean_due_time` (même regex `DUE_TIME_RE`). Règle : `end_time` sans `due_time` → `''` (une fin sans début n'existe pas) ; vider la date vide début ET fin (même site que la garde `due_time`, APRÈS la replanification récurrente — gotcha connu de [MEMO-TIME]).
1.3. **Écriture** : `end_time` dans `create_memo`, `_perform_memo_update` (payload-ou-existant), `_memo_snapshot`/révisions, duplication. `share_update_memo` : ajouter `end_time` à la whitelist (chemin scopé existant, pas de route nouvelle).
1.4. **Normalisation créneau** (helper pur) : `_slot_minutes(due_date, due_time, end_time)` → (start_abs, end_abs) en minutes absolues : minutes depuis 00:00 du `due_date` ; si début < 720 → +1440 ; si fin ≤ début → fin +1440 ; pas d'`end_time` → durée 60 min. Docstring avec les 3 exemples du brief (KATY PERRY, INTERPOL, RILÈS/TOMORA).
1.5. **Toggle ❤️** : `_toggle_heart(db, memo, voter, replace=False)` — modèle `_toggle_reaction`/`_cast_vote` : existe → retrait ; sinon contrôle chevauchement contre les ❤️ du même votant dans le **même dossier racine** (remonter via parents, gabarit `_project_descendants` inversé ou racine du mémo) ; conflit → si `replace` retirer l'ancien et poser (atomique, un seul commit), sinon lever avec le détail du mémo en conflit.
1.6. **Route owner** : `POST /api/memos/<id>/heart` `{replace?}` → 200 `{hearts, mine}` ou **409** `{error, conflict:{memo_id, artist, scene, day, start, end}}`. Voter owner = `''` (pattern `created_by`).
1.7. **Exposition** : `_memo_dict` (ou enrichissement `/api/memos`) → `end_time`, `hearts_count`, `hearts_mine`, `heart_voters` (noms résolus, e-mails owner-only comme `_vote_display_name`). Étendre `_data_version` à `memo_hearts` (+ `memos.end_time` couvert par le SELECT existant si colonnes légères listées — vérifier).
1.8. **Cascades** : purge mémo (`_purge_memo_row`) + suppression dossier + retrait invité (`_delete_votes_for_email` → miroir `_delete_hearts_for_email`) suppriment les ❤️.
✅ Test : `py_compile` ; migration sur copie de base ; curl toggle/conflit/replace/409 ; re-toggle = retrait.

## Phase 2 — Scrutin « Envies » (vérification, peu ou pas de code)

2.1. Vérifier que `_vote_scope_memo_ids(db, project_id)` d'un **vote nommé** porté par le dossier racine peut inclure les mémos des **sous-dossiers** (les options sont explicites depuis [VOTE-GROUPS] : « mémos du porteur + descendants » — normalement OK sans code).
2.2. Si OK : le seed (Phase 4) crée le scrutin « Envies » (multi, sans deadline) avec les 83 passages en options — ou instruction manuelle owner (voir 4.6). Si KO : fallback un scrutin « Envies » par sous-dossier scène (accepté par le brief).
✅ Test : voter multi owner + invité sur des passages de 2 scènes différentes, compteurs OK.

## Phase 3 — Invité + Résultats (app.py)

3.1. `POST /share/<token>/memo/<id>/heart` — **invité approuvé requis, `can_edit` NON requis** (précédent [COMMENT-REACTIONS]) ; anonyme 403, hors scope 404 ; scope revalidé ; voter = « Nom <email> ». Sous `/share/*` (invariant 5, bypass Authelia existant).
3.2. `GET /api/projects/<id>/festival-results` (owner) + `GET /share/<token>/festival-results` (tout invité du lien, lecture) → `{passages:[{memo_id, title, scene, due_date, due_time, end_time, hearts:[noms], votes}], voters:[...]}` — scene = nom du sous-dossier porteur ; agrégation sur racine + descendants (owner) / scope du partage (invité).
3.3. Vérification bypass (invariant 5) : `fetch` non authentifié sur les 2 routes `/share/...` → réponse `basic`, pas de redirect Authelia.
✅ Test : curl invité approuvé 200 / anonyme 403 / hors scope 404 ; chiffres identiques owner vs invité.

## Phase 4 — Seed (idempotent, même chemin local et prod)

4.1. **Générateur** `scripts/seed_charrues.py` (nouveau, hors app) : lit le seed JSON → écrit `charrues-import-v23.json` au **format d'import v23** : projet racine « Vieilles Charrues 2026 » + 6 sous-projets (`parent` par nom, `location` depuis `scene_locations`, emoji 🎤/🎪) + 83 mémos (title=artiste, due_date, due_time, location=scène, `end_time` si l'import le porte — sinon poser les end_time via l'API en post-seed, voir 4.3).
4.2. **Import** via le flux existant (Paramètres ou « ⬆ Importer ici » + [IMPORT-PREVIEW]) : ré-import = 0 doublon (dédup par nom/uid) — c'est le critère d'idempotence, AUCUN accès SQL direct à la prod.
4.3. **`end_time`** : n'est PAS dans l'export v23 (non exporté, choix du brief). Deux options, au choix de CC : (a) le générateur produit AUSSI `charrues-endtimes.sh` (boucle de `PUT /api/memos/<id>` par titre+date, à lancer après import) ; (b) accepter `end_time` en **entrée** d'import v23 sans jamais l'émettre à l'export (import tolérant, toujours v23 en sortie — trancher et le noter dans le handoff).
4.4. **Scrutin « Envies »** : créé par script via `POST /api/projects/<id>/votes` (owner, derrière Authelia — en local direct ; en prod : session authentifiée ou création manuelle 30 s via l'UI, instruction fournie).
4.5. **Pièces jointes** : plan illustré 2026 (fichiers Fabien) + plan d'accès (URL dans le brief, téléchargement one-shot) attachés au dossier racine — en local par script (`POST /api/projects/<id>/attachments`), en prod manuellement par Fabien via l'UI (2 min, instruction fournie).
4.6. Livrer un **README-seed** (10 lignes) : l'ordre exact des clics/commandes pour rejouer le seed en prod mercredi.
✅ Test : seed complet sur copie locale ; re-seed = 0 doublon ; échantillons horaires du brief ; carte du dossier = 6 pins scènes exactement.

## Phase 5 — Frontend (3 pages, helpers partagés — invariants 6/8/9)

5.1. **Champ « fin »** : `<input type="time">` à côté de l'heure existante (fiche mémo owner + pop-in invité can_edit), visible si date posée. Badge card : `📅 jeu 16 · 22h30 → 00h00` (étendre le site d'assemblage du badge, PAS `dueInfo()` — décision [MEMO-TIME]).
5.2. **Chip ❤️ n** sur les cards des mémos à créneau (due_date + due_time) : helper partagé `heartChip()` dans `_shared.js.html` (gabarit `reactionRow`) ; clic = POST toggle ; **409 → `confirmPopin`** « Déjà ❤️ X sur ce créneau — remplacer ? » → re-POST `{replace:true}` ; jamais d'`alert()` natif. Owner + share ; hub si trivial (routé vers le share du dossier comme le vote).
5.3. **Écran « 🏆 Résultats »** : bouton au niveau du dossier racine (board owner + share) → pop-in (markup statique, entrée CSS, pas de GSAP sur `<dialog>` — invariant 8) : onglets/chips `.prio-btn` **Podium** (tri ❤️ desc puis votes desc, compteurs + noms) / **Par ami** (les ❤️ de chacun avec jour/heure/scène) / **Par jour** (Jeu/Ven/Sam/Dim). Re-fetch à l'ouverture. Tokens CSS existants uniquement (invariant 9).
5.4. Mobile ~500 px : chips wrap, pop-in scrollable (gabarits responsive existants).
✅ Test : `node --check` sur les templates extraits si applicable + parcours Chrome complet owner/invité.

## Phase 6 — Journal + handoff

6.1. `REALISATION.md` : entrée `[V23.1.z]` (Z = dernier + 1) ; IDEAS.md : fiche [FESTIVAL-VOTE] → livré ; le brief reste la spec verrouillée.
6.2. `docker compose up -d --build` (vraie base ./data — migration additive obligatoire) puis `.claude/handoff.json` `{status:"ready", version:"V23.1.z", url}`.
6.3. **Pas de commit/tag/push sans feu vert Fabien.**

## Phase 7 — Validation & mise en prod (Cowork + Fabien, hors CC)

7.1. Cowork valide via Chrome sur `localhost:8099` (hard-refresh, cache !) : checklist d'acceptation du brief §1-7, owner ET invité (rappel : share `can_edit:1` pour pouvoir inscrire l'invité de test).
7.2. Feu vert Fabien → commit groupé + tag `V23.1.z` → push → CI « Deploy Zimaboard » (smoke `/api/version`).
7.3. **Seed prod** (mercredi) : import du fichier v23 via l'UI prod → scrutin « Envies » (UI) → pièces jointes plan (UI) → sonde bypass des 2 routes `/share/.../heart|festival-results` en prod → créer le partage du dossier (`can_edit:1`) + envoyer lien/PIN aux amis.

## Repli si le temps manque (couper par le bas)

1. Le **hub** (5.2/5.3 côté hub.html) — les amis passent par le lien de partage direct.
2. L'onglet **Par jour** des Résultats (Podium + Par ami suffisent jeudi).
3. Le **plan d'accès** en pièce jointe (le plan illustré suffit).
Jamais coupables : contrôle de chevauchement serveur, routes invité, idempotence du seed.

## Risques / points d'attention

- **Chevauchement post-minuit** : tout passe par `_slot_minutes` (un seul point de vérité, testé par les 3 exemples du brief). Ne pas dupliquer la logique côté front — le front affiche, le serveur tranche.
- **Racine du dossier** : le contrôle ❤️ se fait par dossier RACINE (remontée des parents) — un ❤️ Glenmor doit bien entrer en conflit avec un ❤️ Gwernig du même créneau (sous-dossiers différents, même festival).
- **`end_time` à l'import** (4.3) : quelle que soit l'option, l'export reste strictement v23 sans `end_time` — aucun bump, aucune entrée d'invariant 1.
- **Seed = flux d'import standard** : zéro SQL direct en prod, zéro SSH requis pour les données.
- Invariants 5 (routes sous `/share/*` + sonde), 6 (aucun CDN), 8 (pas de GSAP sur `<dialog>`), 9 (tokens/classes existants).

## Fichiers critiques

`app.py` · `templates/index.html` · `templates/share.html` · `templates/hub.html` (si parité) · `templates/partials/_shared.js.html` · `scripts/seed_charrues.py` (nouveau) · `docs/specs/festival-vote-seed-vieilles-charrues-2026.json`

---

## Prompt de lancement pour Claude Code (à coller tel quel)

> Nouveau lot **[FESTIVAL-VOTE]**, urgent (festival jeudi 16 juillet — livraison mercredi 15 au soir max). Lis dans l'ordre : `docs/specs/FESTIVAL-VOTE-charrues-coup-de-coeur.md` (brief verrouillé), `docs/specs/FESTIVAL-VOTE-plan.md` (plan de réalisation phasé), `docs/specs/festival-vote-seed-vieilles-charrues-2026.json` (données). Réalise les phases 1 → 6 dans l'ordre du plan, en committant localement par phase (sans push). Cible V23.1.z, export v23 inchangé (`end_time` et `memo_hearts` non exportés). Les images du plan festival sont attendues dans `docs/specs/` (fichiers `plan-festival-2026-*` ou toute image dont le nom contient « plan ») — si absentes, continue sans (étape 4.5 seulement) et note-le dans le handoff. Respecte CLAUDE.md (invariants 1/5/6/8/9, tests sur COPIE de la base, process de fin de réalisation : REALISATION.md + rebuild local + handoff.json, pas de push sans feu vert). Si un point du plan contredit le code réel, le plan cède — note l'écart dans le handoff.
