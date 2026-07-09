# SPEC — [VOTE-DECISION] Dossier en mode vote (V1 « choisir un »)

**Statut : VERROUILLÉE — décisions validées par Fabien (9 juil. 2026).**
Cible : **V1 = mode `single`** (« choisir un »). Schéma pensé **extensible au mode
`multi`** (intérêts multiples, cas festival) en **V2** via un simple échange
d'index unique (colonnes inchangées, cf. §3.1), **sans refonte**.
Zone invité → **invariant 5** (route publique sous `/share/*`, scope + approbation).

⚠️ **Export** : **numéro NON figé ici**. Décision au build (§7) — d'abord trancher
si les voix/flags entrent dans le payload : **si non → aucun bump de X** ; **si oui
→ bump découplé de [COMMENT-REACTIONS]**, numéro assigné à la livraison selon
l'ordre réel de ship. **Aucune pré-réservation.**

---

## 1. Concept

Un **dossier** (projet ou sous-projet) peut être basculé en **mode vote**. Ses
**mémos directs deviennent les options** du vote. Le **modèle de voix = (personne,
mémo)**, avec un **mode porté par le dossier** :

- **V1 — `single`** : chaque personne choisit **un** mémo du dossier. Une voix par
  (personne, dossier) ; revoter **déplace** la voix vers un autre mémo.
- **V2 — `multi`** (hors V1, cf. §8) : plusieurs mémos par personne (cas festival).

**Portée = mémos DIRECTS du dossier uniquement.** Un **sous-dossier lui-même en
mode vote** est un **vote indépendant** : il n'alimente PAS le vote du parent, et
ses mémos ne sont pas des options du parent. (Un mémo n'est option que du dossier
au vote dont il est enfant **direct**.)

**Cycle de vie** : **ouvert** → **clos** (deadline atteinte OU clôture manuelle
owner) = **résultats en lecture seule, gagnant figé et badgé**. Réouverture owner
possible (§2.7).

## 2. Décisions figées

1. **Le vote vit sur le dossier** (réutilise la hiérarchie projets/mémos), options =
   **mémos directs** du dossier (décision §1). Pas de mémo « sondage » dédié.
2. **Mode `single` en V1** ; `vote_mode` stocké sur le dossier pour l'extension.
3. **Qui vote** : **owner + tout invité APPROUVÉ** du partage couvrant le dossier,
   **même en lecture seule** (`can_edit` NON requis) — voter n'est pas éditer.
   Exception assumée au gating `can_edit`, identique à [COMMENT-REACTIONS] décision 2
   (l'approbation reste requise, invariant 5).
4. **Une voix modifiable** jusqu'à la deadline / clôture. Re-cliquer le mémo déjà
   choisi = **retirer sa voix** (toggle). Voter un autre mémo (single) = **déplacer**
   sa voix (UPDATE de la ligne unique, cf. §3.1).
5. **Identité votant** = pattern `created_by` (v19) : `''` = propriétaire (résolu à
   l'affichage via `_owner_name(db)`), sinon « Nom <email> » de l'invité. Jamais
   réécrit au renommage (historique immuable, comme [GUEST-EDIT]).
6. **Configuration + clôture = owner-only.** Un invité ne configure, ne clôt ni ne
   rouvre un vote (même `can_edit`).
7. **Clôture / réouverture** :
   - **Clos = état DÉRIVÉ**, évalué **à chaque lecture pour tout le monde** :
     `vote_closed=1` (clôture manuelle owner) **OU** (`vote_deadline` non vide **ET**
     maintenant > deadline). Pas de cron.
   - **Gel du gagnant paresseux** : le **snapshot** de `vote_winner_id` (+ ex æquo,
     §9.a) est écrit **à la 1re lecture par n'importe qui** (owner OU invité) qui
     constate le passage `ouvert→clos` par deadline, si pas déjà figé. Idempotent.
   - **Réouverture owner** : autorisée, **à condition de redéfinir OU d'effacer la
     deadline** dans la même action (sinon re-clôture immédiate). Efface le gel
     (`vote_winner_id=NULL`), **conserve les voix** qui **redeviennent modifiables**,
     état exposé « vote rouvert ».
8. **Une voix modifiable** ≠ badge 🔔 : le vote **ne compte PAS** dans l'activité
   (pas une « modification ») ; le refresh passe par `_data_version` (§5).

## 3. Modèle

### 3.1 Table additive `memo_votes`
```sql
CREATE TABLE IF NOT EXISTS memo_votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,     -- dossier au vote (portée), dénormalisé
  memo_id INTEGER NOT NULL,        -- option choisie (enfant DIRECT du dossier)
  voter TEXT NOT NULL DEFAULT '',  -- '' = owner, sinon « Nom <email> »
  created_at TEXT NOT NULL
);
-- V1 single : unicité (personne, dossier) en BASE → empêche la double voix normale.
CREATE UNIQUE INDEX IF NOT EXISTS ux_memo_votes_single
  ON memo_votes(project_id, voter);
```
- **Fonctionnement normal single** : la contrainte `UNIQUE(project_id, voter)`
  garantit **une seule voix par (personne, dossier)** au niveau base (pas seulement
  applicatif). **Revoter = UPDATE `memo_id`** de la ligne existante ; **retirer =
  DELETE** la ligne. La règle « plus récente gagne » (§7) n'intervient **que** comme
  **réconciliation d'import**, jamais en fonctionnement normal.
- **Extension V2 `multi` — sans refonte** : on **remplace le seul index unique** par
  `UNIQUE(project_id, voter, memo_id)` (autorise N mémos par personne) — migration
  additive (DROP INDEX + CREATE INDEX, **colonnes et lignes inchangées**), pas de
  refonte de table ni de route.
- **Portée dénormalisée** (`project_id`) : unicité single, comptage et scoping sans
  re-remonter l'arbre. **Revalidée serveur** : le mémo voté est un **enfant direct**
  du dossier au vote, sinon 400/404.
- **Cascades explicites** :
  - **Supprimer un mémo** (option) → **supprime ses voix** (`DELETE FROM memo_votes
    WHERE memo_id = ?`), aux mêmes sites que `memo_comments` : suppression, purge
    définitive (corbeille + `_purge_trash`).
  - **Supprimer le dossier** → supprime toutes ses voix.
  - **Désactiver le vote** (`vote_enabled=0`) → voix **masquées mais CONSERVÉES** ;
    **réactiver les restaure** telles quelles (jamais de DELETE à la désactivation).
  - **Invité retiré** (retrait/refus d'un accès, DELETE guest) → **ses voix sont
    supprimées avec son accès** (`DELETE FROM memo_votes` du `voter` retiré, dans le
    scope concerné). **Match sur la partie e-mail du `voter`** (identifiant stable),
    **pas** sur la chaîne complète « Nom <email> » : un invité **renommé** après avoir
    voté ([GUEST-EDIT] ne réécrit jamais le `voter` déjà posé) puis retiré serait raté
    par un match par chaîne. Cohérent : plus d'accès → plus de voix.

### 3.2 Colonnes additives sur `projects` (le dossier)
```
vote_enabled   INTEGER DEFAULT 0     -- 0/1
vote_mode      TEXT    DEFAULT ''     -- '' → 'single' résolu ; 'multi' (V2)
vote_deadline  TEXT    DEFAULT ''     -- ISO 'YYYY-MM-DDTHH:mm' local ou '' = pas de deadline
                                      -- l'ISO SANS fuseau s'interprète en Europe/Paris
                                      -- (fuseau de l'app) → « clôt à 13h » non ambigu
vote_closed    INTEGER DEFAULT 0     -- 0/1, clôture manuelle owner
vote_winner_id INTEGER               -- NULL tant qu'ouvert ; figé (snapshot) à la clôture
```
- Migration `init_db()` **additive** (ALTER ADD COLUMN, `CREATE TABLE/INDEX IF NOT
  EXISTS`), jamais destructive (invariant 1). Absent = `vote_enabled=0` → dossier
  normal, rendu identique (compat ascendante).
- **`vote_state` résolu** (runtime, jamais stocké brut) : `closed` si `vote_closed=1`
  **OU** deadline dépassée ; sinon `open`. Évalué **à chaque lecture, pour tous**.
- **Snapshot du gagnant** posé paresseusement (§2.7) : à la 1re lecture constatant
  `open→closed` par deadline, on calcule et écrit `vote_winner_id` (voir §9.a pour
  l'ex æquo). Écriture idempotente (skip si déjà figé). La clôture manuelle owner
  écrit le snapshot immédiatement.

## 4. Routes

### Owner (derrière Authelia)
- **Configurer / activer** : `PUT /api/projects/<id>` accepte `vote_enabled`,
  `vote_mode` (V1 : `'single'`), `vote_deadline` (ISO ou `''`). Réutilise l'update
  projet existant (aucune route nouvelle pour la config).
- **Clore** : `POST /api/projects/<id>/vote/close` → `vote_closed=1`, calcule et fige
  `vote_winner_id` (+ ex æquo §9.a). Idempotent. Owner-only.
- **Rouvrir** : `POST /api/projects/<id>/vote/reopen` **avec deadline redéfinie ou
  effacée** (corps `{vote_deadline}` — vide = plus de deadline) → `vote_closed=0`,
  `vote_winner_id=NULL`. **Refusé (400)** si la nouvelle deadline est déjà dépassée
  (éviterait la re-clôture immédiate). Voix conservées, redevenues modifiables.
- **Voter** : `POST /api/memos/<id>/vote` → voter = `''`. Le mémo = la cible.
  Toggle/retarget (§2.4). **400** si le mémo n'est pas enfant direct d'un dossier au
  vote ; **409** si le dossier est **clos** (revote bloqué **serveur**, §9.c).

### Invité (préfixe `/share/*` obligatoire — invariant 5, jamais de préfixe nouveau)
- **Voter** : `POST /share/<token>/memo/<id>/vote` :
  - mémo **dans le scope du partage** (même contrôle que `share_image` / le POST
    commentaire existant), sinon 404 ;
  - **invité approuvé** requis (header `X-Guest-Token`), sinon 403 ;
  - **`can_edit` NON requis** (décision 2.3) ;
  - **vote refusé si le dossier est clos** → **409 serveur** (§9.c), pas seulement
    masqué en UI ;
  - voter = « Nom <email> » ; toggle/retarget idem owner.
- **Config / clôture / réouverture = owner-only** : aucune route invité.
- Le **hub** route vers le `/share/<share_token>` du mémo comme toutes ses écritures
  ([HUB-DASHBOARD]) — **zéro route hub nouvelle**.
- **Sonde bypass Authelia** après ajout (règle CLAUDE.md nouvelle route publique) :
  fetch non authentifié `{credentials:'omit', redirect:'manual'}` → réponse `basic`,
  pas `opaqueredirect`.

### Exposition (lecture)
- **Payload dossier** (owner `/api/projects`, `share_data`, hub `/data`) :
  `vote_enabled`, `vote_mode`, `vote_deadline`, **`vote_state`** (`open`/`closed`
  résolu), `vote_winner_id` (quand clos), **`vote_winner_ids`** (ex æquo figé, §9.a).
  Owner voit `vote_closed` brut ; invités ne voient que l'état résolu (lecture seule).
- **Chaque mémo d'un dossier au vote** : `vote_count`, `vote_mine` (bool, calculé
  serveur selon l'appelant), `vote_voters: [noms affichables]`, `is_winner` (quand
  clos). Les `voters` = **noms affichables** (owner résolu via `_owner_name`) —
  **jamais l'e-mail brut côté invité** (e-mail owner-only, cohérent avec
  `_share_memo_dict`/`created_by`).

## 5. Auto-refresh

`_data_version` : ajouter `"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM memo_votes"`
(pattern `memo_comments`) **et** couvrir les **flags de vote des projets** dans
l'empreinte (ouverture/clôture/deadline/winner visibles) → le poll owner 15 s et le
refresh invité voient les votes et les changements d'état des autres.

## 6. UI (3 pages, tokens existants — invariants 8/9)

### Niveau dossier
- **Indicateur « 🗳 Vote »** sur l'en-tête du dossier (board owner + board invité
  share/hub) : `.badge` avec **deadline affichée** (« clôt le … » / « clos le … » /
  « vote rouvert ») et **état** (ouvert/clos).
- **Owner** : action **« Clore le vote »** (façon `.task-actions button`, action
  principale en accent) ; config (activer, mode, deadline) + **réouverture** dans la
  **pop-in projet** existante (`openCreateDialog('project', …)`), tokens existants.
- **Carte du dossier** : **point gagnant mis en avant** (halo/anneau accent,
  réutilise le focus de `runMapDialog`) ; ouvert, l'option en tête ressort
  discrètement. **Cf. §9.d** : un dossier au vote **sans mémo géolocalisé** vote
  normalement, seule cette mise en avant carte est absente (pas de carte).

### Niveau mémo (option)
- **Bouton « Voter »** (façon `.prio-btn` ; **ma voix = chip sélectionné**, fond
  `var(--accent)`, texte `#10141a`), **compteur** de voix, **qui a voté**
  (avatars-initiales `@Nom` comme les assignés ; title = liste complète).
- **Option en tête** (plus de voix) mise en avant dans la liste des mémos.
- **Clos** : boutons Voter **désactivés**, **résultats en lecture seule**, **gagnant
  badgé** « 🏆 Gagnant » (ou « 🏆 Ex æquo » si égalité, §9.a).
- **Invité anonyme** (non approuvé) : compteurs/résultats **visibles en lecture**,
  bouton Voter masqué (gate `canEditNow()`-like : **approuvé suffit, pas can_edit**).

Rappel invariant 8 : indicateurs/pop-ins en markup + CSS/`@keyframes`, **jamais de
GSAP sur un `<dialog>`**.

## 7. Export / import — **numéro NON figé (décision au build)**

**Étape 0 (à trancher au build, avant d'écrire l'export)** : les voix et/ou les
flags de vote entrent-ils dans le payload d'export ?
- **Si NON** (voix = donnée d'atelier transitoire, non exportée — précédent
  `comment_seen`) → **aucun bump de X**, aucune entrée d'invariant 1, compat inchangée.
  ⚠️ conséquence : un ré-import ne restaure pas un vote clos (le résultat vit dans la
  base seulement). Acceptable si le vote est vu comme éphémère.
- **Si OUI** → **bump export découplé de [COMMENT-REACTIONS]** ; le numéro (`v21`,
  `v22`, …) est **assigné à la livraison selon l'ordre réel de ship**, **jamais
  pré-réservé ici**. Alors :
  - `APP_VERSION` bumpé, § Versionnage X mis à jour, **entrée invariant 1 ajoutée à
    `CLAUDE.md`** (obligatoire) ;
  - Export : sur chaque **projet**, `vote_enabled/mode/deadline/closed/winner_id`
    (**brut**, jamais l'état résolu) ; liste racine **`votes`** :
    `[{project_uid?, memo_uid, voter, created_at}]` (**voter brut** comme
    `created_by` v19 ; rattachement par `memo_uid`) ;
  - Import : **additif, non destructif** (invariant 2) — on **ajoute** les voix
    manquantes, jamais de suppression ; compat ascendante (champ absent = pas de
    vote) ; **réconciliation single** : si l'import crée une 2e voix pour une même
    (personne, dossier), **la plus récente par `created_at` gagne** (l'autre est
    écartée) — cohérent « single = une voix », sans supprimer d'autres votants ;
    `vote_winner_id` figé importé tel quel.

## 8. Hors V1 — « suite »

- **[VOTE V2] mode multi-intérêts** (festival) : `vote_mode='multi'` — **échange
  d'index unique** (§3.1), UI en sélection multiple. Aucune refonte. **✅ LIVRÉ
  [V20.8.47]** — voir §12.3.
- **[VOTE V1.1] création auto de l'événement d'agenda** pour le gagnant à la clôture
  (réutilise `due_date`/`due_time` + [AGENDA]).
- **[COMMENT-REACTIONS] réactions emoji** sur les commentaires : **spec séparée
  verrouillée** (V21), indépendante de ce lot.

## 9. Cas limites (traités)

**a. Égalité de voix à la clôture** — **on affiche l'ex æquo**, pas de gagnant unique
forcé : tous les mémos à égalité de tête sont badgés « 🏆 Ex æquo » et exposés dans
`vote_winner_ids` (figé au snapshot ; `vote_winner_id` = NULL tant que l'égalité
tient). L'**owner peut trancher manuellement** (choisir un gagnant parmi les ex æquo,
via `POST /api/projects/<id>/vote/close` avec `{winner_id}` optionnel, ou une action
dédiée) → fige alors `vote_winner_id` sur ce mémo. **Zéro voix** → pas de gagnant
(aucun badge).

**b. Invité retiré après avoir voté** — **sa voix est supprimée avec son accès**
(cascade §3.1 : DELETE des `memo_votes` du `voter` retiré). Les compteurs et le
gagnant se recalculent (si le vote est encore ouvert) ; si déjà clos et figé, le
snapshot `vote_winner_id`/`vote_winner_ids` **ne bouge pas** (résultat historique
préservé).

**c. Revote après clôture** — **bloqué côté SERVEUR** (409 owner et invité, §4), pas
seulement masqué en UI : une requête de vote sur un dossier à `vote_state=closed` est
rejetée, quels que soient l'appelant et l'état de son UI.

**d. Dossier au vote sans mémo géolocalisé** — le **vote fonctionne normalement**
(options, voix, compteurs, clôture, gagnant) ; **seule la mise en avant du point
gagnant sur la carte est absente** (il n'y a pas de carte pour ce dossier). Aucun
blocage, aucune erreur.

## 10. Décisions verrouillées (récap des 6 arbitrages)

1. Options = **mémos directs** ; un sous-dossier au vote est **indépendant** du parent.
2. État clos **dérivé, évalué à chaque lecture pour tous** ; **snapshot du gagnant
   paresseux à la 1re lecture par n'importe qui** après la deadline. Pas de cron.
3. **Réouverture owner** autorisée **si deadline redéfinie/effacée** ; voix
   conservées et re-modifiables ; état « vote rouvert ».
4. **Voix conservées** à la désactivation (masquées, restaurées à la réactivation) ;
   cascades : mémo supprimé → voix supprimées ; **invité retiré → voix supprimées**.
5. Single : **unicité `(personne, dossier)` en BASE** (empêche la double voix en
   fonctionnement normal) ; « plus récente gagne » **uniquement** en réconciliation
   d'import.
6. **Export : numéro non figé** ; d'abord trancher au build si les voix/flags sont
   exportés (si non → aucun bump ; si oui → numéro assigné au ship, découplé de
   [COMMENT-REACTIONS], pas de pré-réservation).

## 12. Extensions livrées après V1 (amendements, [V20.7.46])

Validées par Fabien, dans l'esprit de la V1 (export inchangé — voix/config/exclusion =
donnée d'atelier, **toujours v20**, pas d'entrée d'invariant 1).

### 12.1 [VOTE-RESET] — remise à zéro (owner-only)
- Route **`POST /api/projects/<id>/vote/reset`** (derrière Authelia) : **supprime toutes
  les voix** `memo_votes` du dossier, **efface le gel** (`vote_winner_ids=''`,
  `vote_winner_id=NULL`), **remet `vote_closed=0`** → vote rouvert. **Même garde que
  reopen** : exige une deadline redéfinie ou effacée (**400** si la deadline fournie est
  déjà dépassée). Ne touche **ni les mémos ni la config** (`vote_enabled`/`vote_mode`
  conservés). `_data_version` déjà couvert (`memo_votes` + flags projets).
- **UI** : bouton **« ↺ Remettre à zéro »** dans la zone config vote de la pop-in projet.
  Action destructive → **`confirmPopin` en style danger** (`var(--red)`, convention
  Supprimer), libellé explicite « Toutes les voix seront supprimées ».

### 12.2 [VOTE-EXCLUDE] — mémo « hors vote »
- Colonne additive **`memos.vote_excluded`** (`INTEGER DEFAULT 0`, migration `init_db()`
  non destructive). **Non exportée** — trade-off assumé (comme les voix : un ré-import
  ne restaure pas l'exclusion).
- **Sémantique** : le mémo reste **visible/éditable** dans le dossier mais **n'est pas une
  option** — pas de bouton Voter, pas de `vote_count`/`vote_mine`/`vote_voters`, **jamais
  gagnant** (`_compute_winners`/`_ensure_vote_snapshot` l'ignorent via
  `COALESCE(vote_excluded,0)=0`).
- **Serveur** : `POST /api/memos/<id>/vote` **ET** `POST /share/<token>/memo/<id>/vote`
  → **400** sur un mémo exclu (revalidé serveur, invariant 5). **Exclure un mémo qui a
  des voix → ses voix sont supprimées** (`DELETE FROM memo_votes WHERE memo_id=?` dans la
  route owner ; `confirmPopin` front avec le compte si > 0).
- **Config owner-only** (comme enabled/mode/deadline) : case **« Hors vote »** dans le
  détail du mémo, **affichée seulement si le dossier direct est en mode vote** ;
  `PUT /api/memos/<id>` accepte `vote_excluded` **hors** `_perform_memo_update` (donc
  `share_update_memo` — whitelist — **ne l'accepte pas**). **Invité = lecture seule** :
  `vote_excluded` exposé dans `_share_memo_dict` (badge « 🗳 hors vote » sur la card),
  aucun contrôle.
- **UI 3 pages** : card d'un mémo exclu → ni Voter ni compteur, **badge `.badge`** discret
  (invariant 9).

### 12.3 [VOTE-MULTI] — mode « plusieurs choix » (V2, [V20.8.47])
- **Migration additive (§3.1)** : index `UNIQUE(project_id, voter)` **remplacé** par
  `UNIQUE(project_id, voter, memo_id)` (`init_db()` : DROP `ux_memo_votes_single` +
  CREATE `ux_memo_votes_multi`, colonnes/lignes intactes, voix existantes préservées). En
  **single**, unicité une-voix-par-personne **applicative** (`_cast_vote` UPDATE la ligne).
- **`_cast_vote(…, mode)`** : en **multi**, toggle par **(voter, mémo)** — voter un 2ᵉ
  mémo n'écrase pas le 1ᵉʳ, re-cliquer retire cette voix-là seulement. Mode résolu depuis
  `proj.vote_mode`. Gardes inchangées (exclu 400, clos 409, invité approuvé, scope).
  Gagnant/ex æquo/snapshot : têtes = max voix. Reset/deadline/reopen/exclude compatibles.
- **Bascule owner** (pop-in projet) : chips « ☝️ Un seul / ☑️ Plusieurs ». single→multi
  libre ; **multi→single** → `confirmPopin` danger + **purge serveur** `_collapse_votes_to_single`
  (garde la voix la plus récente par votant, règle « plus récente gagne » §7).
- **UI 3 pages** : boutons = cases à cocher en multi (« ☑️ Ma voix » / « ☐ Voter »,
  plusieurs actives), badge d'en-tête inchangé (title « · plusieurs choix »). Parité invité.
- **Export inchangé (v20)**, zéro route nouvelle. Invariants 1/2/5/8/9.

## 11. Invariants touchés

- **1** : migration additive (ALTER ADD + CREATE IF NOT EXISTS), jamais destructive.
  Bump export **conditionnel** (§7) — entrée invariant 1 **seulement si** les voix
  sont exportées.
- **2** : import additif non destructif (§7).
- **5** : route publique de vote sous `/share/*`, **scope + approbation revalidés
  serveur**, config/clôture/réouverture owner-only, **e-mails jamais exposés aux
  invités** ; sonde bypass Authelia obligatoire.
- **8/9** : indicateurs/pop-ins en markup + CSS, tokens existants, pas de GSAP sur
  les dialogs, réutilisation de `.prio-btn`/`.badge`/`.task-actions`/focus carte.
