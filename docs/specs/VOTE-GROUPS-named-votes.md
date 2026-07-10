# [VOTE-GROUPS] — Votes nommés multiples par dossier (V20.9)

**Statut : spec VERROUILLÉE (10 juil. 2026, décisions Fabien figées). Implémenter telle quelle ; tout écart = retour de cadrage avant code.**

## 1. Objectif

Aujourd'hui le dossier EST le vote (un scrutin unique, options = enfants directs non exclus). Ce lot ajoute des **votes nommés multiples** dans un même dossier, chacun sur son propre sous-ensemble de mémos, avec son nom, son mode (un seul / plusieurs), sa deadline, sa clôture, son gagnant. Exemple : dans « Voyage Japon », un vote « restaurant 1er jour midi » sur 3 mémos restos, un vote « hôtel Kyoto » sur 2 hôtels. Le geste UI = celui des **groupes de la carte** : cocher des mémos → « Créer un vote » → nommer.

## 2. Décisions figées (ne pas rediscuter)

- **D1** — Un mémo peut appartenir à **plusieurs votes** simultanément.
- **D2** — Le **vote-dossier V1 reste le défaut et ne bouge pas** : colonnes `projects.vote_*` et comportements V20.7/V20.8 inchangés. C'est le « vote du dossier » (sans nom). Les votes nommés s'ajoutent À CÔTÉ, sans migration des données existantes.
- **D3** — **Les invités peuvent créer des votes**, gouvernés par une **permission par dossier/sous-dossier, héritable** (modèle `is_trip` : valeur locale ou héritée, résolution au plus proche ancêtre, revalidée serveur).
- **D4** — Export **inchangé (v20)** : votes nommés, options et voix = donnée d'atelier NON exportée (cohérent avec l'étape 0 du vote V1). Ré-import d'une vieille sauvegarde → zéro impact sur les votes.

## 3. Modèle de données (migrations additives dans `init_db()`, invariant 1)

```
CREATE TABLE IF NOT EXISTS votes (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL,          -- dossier porteur
  name        TEXT NOT NULL,             -- « restaurant 1er jour midi » (≤80 c., non vide)
  vote_mode   TEXT DEFAULT '',           -- '' → single résolu ; 'multi'
  vote_deadline TEXT DEFAULT '',         -- ISO local Europe/Paris, '' = sans deadline (mêmes règles que V1)
  vote_closed INTEGER DEFAULT 0,
  vote_winner_ids TEXT DEFAULT '',       -- snapshot figé à la clôture (ex æquo inclus)
  created_by  TEXT DEFAULT '',           -- '' = owner, sinon « Nom <email> » (pattern created_by existant)
  created_at  TEXT
);
CREATE TABLE IF NOT EXISTS vote_options (
  vote_id INTEGER NOT NULL,
  memo_id INTEGER NOT NULL,
  UNIQUE(vote_id, memo_id)
);
ALTER TABLE memo_votes ADD COLUMN vote_id INTEGER;   -- NULL = voix du vote du dossier (V1) → zéro migration
CREATE UNIQUE INDEX IF NOT EXISTS ux_memo_votes_named
  ON memo_votes(vote_id, voter, memo_id) WHERE vote_id IS NOT NULL;
ALTER TABLE projects ADD COLUMN vote_create TEXT DEFAULT '';  -- permission §4 : '' hérité / 'owner' / 'guests'
```

- ⚠️ **Index (amendé après question CC, 10 juil.)** : l'ancien `ux_memo_votes_multi` non partiel entrerait en collision avec D1 (même mémo voté par la même personne dans 2 votes nommés = même triplet project_id/voter/memo_id). Migration : **DROP `ux_memo_votes_multi` + CREATE partiel `WHERE vote_id IS NULL`** (couverture identique pour le vote-dossier — toutes ses lignes ont vote_id NULL — aucune perte) ; `ux_memo_votes_named` couvre `WHERE vote_id IS NOT NULL`. Les deux index PARTITIONNENT `memo_votes` par vote_id. Même geste d'échange d'index qu'en V20.8, données intactes. Unicité « single » = applicative dans `_cast_vote`, par (vote, voter).
- **Options d'un vote nommé** : mémos du dossier porteur **et de ses descendants** (même périmètre que carte/agenda — un resto peut vivre dans un sous-dossier). Adhésion EXPLICITE via `vote_options` (pas d'« enfants directs » implicites). `vote_excluded` ne concerne QUE le vote du dossier — sans effet sur les votes nommés (l'adhésion explicite fait office de filtre).

## 4. Permission de création (héritable, D3)

- `projects.vote_create` : `''` = hérité ; `'owner'` = owner seul ; `'guests'` = owner + invités. **Résolution au plus proche ancêtre ; défaut racine = `'guests'`** (décision Fabien : les invités peuvent, la restriction est l'exception).
- **Invité autorisé** = invité **approuvé** sur un lien **can_edit** couvrant le dossier ET permission résolue `'guests'` (même triple gate que le menu Groupes carte : `canEditNow()` + revalidation serveur systématique).
- UI owner : chips « Création de votes : Hérité (résolu affiché) / Owner seul / Invités aussi » dans la pop-in projet, sous la zone vote (gabarit chips `is_trip`). Jamais exposé brut aux invités : `/share/.../data` expose un booléen résolu `can_create_vote` (lecture seule, façon `trip`).
- **Gestion d'un vote** : l'owner gère tout ; un invité ne gère que **les votes qu'il a créés** (match sur la partie e-mail de `created_by`, pas la chaîne complète — même règle que la cascade [GUEST-EDIT]) : renommer, modifier les options, mode, deadline, clore/rouvrir, reset, supprimer. Voter reste ouvert à tout invité approuvé (can_edit non requis — §2.3 de la spec V1).

## 5. Routes (préfixes existants, AUCUNE route hors `/api/*` ou `/share/*` — invariant 5)

Owner (derrière Authelia) :
- `POST /api/projects/<id>/votes` — body `{name, vote_mode?, vote_deadline?, memo_ids[]}` → crée vote + options (memo_ids revalidés dans le périmètre §3, ≥1 option, 409 si nom dupliqué dans le dossier).
- `PUT /api/votes/<vid>` — nom / mode (bascule multi→single = purge « plus récente gagne » par votant, même règle que V20.8) / deadline / `memo_ids[]` (retirer une option d'un vote → supprime les voix de cette option DANS CE VOTE, confirm UI si voix > 0).
- `POST /api/votes/<vid>/close` · `/reopen` (mêmes gardes deadline que V1) · `/reset` (purge voix du vote, rouvre, config conservée — sémantique [VOTE-RESET]).
- `DELETE /api/votes/<vid>` — supprime vote + options + voix. **Aucun mémo supprimé.**
- Voter : `POST /api/memos/<id>/vote` gagne un body optionnel `{vote_id}` — absent/null = vote du dossier (compat totale V1/V2).

Invité (sous `/share/<token>/…`, bypass Authelia existant, scope + permission revalidés serveur à CHAQUE écriture) :
- `POST /share/<t>/votes`, `PUT /share/<t>/votes/<vid>`, `POST /share/<t>/votes/<vid>/close|reopen|reset`, `DELETE /share/<t>/votes/<vid>` — gate §4 (créateur seulement pour la gestion), 403 générique indiscernable sinon.
- `POST /share/<t>/memo/<id>/vote` — body `{vote_id?}`, invité approuvé requis, memo dans le scope ET option du vote, 409 si vote clos, 400 sinon (« pas une option de vote »).
- Lecture : `/data` (share + hub) et `GET /api/…` existants exposent `votes[]` par projet (id, name, état résolu, mode, deadline, compteurs, `vote_mine` par option, gagnants si clos, `mine` = je l'ai créé) + `can_create_vote` résolu.

## 6. UI (3 pages owner/share/hub, helpers dans `_shared.js.html` — ADR-001)

- **Chips de scrutin** au-dessus des sections du board quand le dossier a ≥1 vote actif : `🗳 (dossier)` (si `vote_enabled`) + un chip par vote nommé — libellé « 🗳 restaurant 1er jour midi » + mini-état (ouvert/clos/deadline), gabarit `.prio-btn`, actif = `.sel`. **Le chip sélectionné détermine ce que montrent les cards** : bouton Voter/☑ Ma voix + compteur DU scrutin sélectionné, uniquement sur ses options. Aucun chip sélectionné = comportement actuel (vote du dossier). Sélection non persistée (remise à zéro au changement de vue).
- **Menu « 🗳 Votes ▾ »** dans l'en-tête du board (à côté du badge vote existant), calqué sur le menu Groupes de la carte (2 niveaux, tokens seuls) : **Créer** (mode sélection : coches sur les cards du board — pattern `groupMode` —, nom pré-focus, mode ☝️/☑️, deadline optionnelle, Valider/Annuler) / **Modifier ▸** / **Clore ▸** / **Rouvrir ▸** / **Remettre à zéro ▸** (confirm danger) / **Supprimer ▸** (confirm danger « les voix seront supprimées, pas les mémos »). Entrées de gestion filtrées : owner = tous, invité = ses votes.
- Badges d'état par vote au même gabarit pilule que le badge vote-dossier (V20.7.45). Clôture : gagnant(s) « 🏆 » sur les cards du scrutin sélectionné, ex æquo inclus (règle V1 §9.a).
- Mobile : chips en rangée défilable (pattern [SETTINGS-TABS]). Thème clair : tokens uniquement (invariant 9). Animations : jamais de GSAP sur un `<dialog>` (invariant 8).

## 7. Cascades & cas limites

- Mémo supprimé/purgé → retiré de `vote_options` + ses voix supprimées (tous votes), mêmes sites que `memo_comments` (règle V1 §3.1).
- Dossier supprimé → ses votes, options et voix supprimés.
- Invité retiré → ses voix supprimées dans TOUS les votes du scope (étendre la cascade existante, match partie e-mail) ; **les votes qu'il a créés SURVIVENT** (l'owner en hérite la gestion).
- Mémo déplacé HORS du périmètre du dossier porteur → retiré des options des votes de ce dossier (voix de cette option purgées) — cohérent avec la revalidation serveur.
- `vote_enabled=0` sur le dossier : ne touche PAS les votes nommés (indépendants du vote-dossier). Chip « (dossier) » disparaît, les nommés restent.
- Deadline atteinte = clôture au premier accès (même mécanique `_ensure_vote_snapshot`, généralisée par vote).
- `_data_version` étendu : `votes`, `vote_options`, `memo_votes.vote_id` (hors champs déjà exclus).

## 8. Export / import (D4)

Export **v20 inchangé**. `votes`, `vote_options`, `memo_votes` non exportés. Ré-import non destructif → 0 ajout, 0 suppression de votes/voix. Test obligatoire : export → ré-import sur copie de base avec 2 votes nommés actifs → tout identique.

## 9. Tests d'acceptation (copie de base, puis validation Chrome par l'agent Cowork)

1. Migration : base V20.8 existante → `init_db()` → colonnes/tables créées, voix V1 intactes (`vote_id` NULL), vote-dossier inchangé.
2. Owner crée « resto J1 » (3 options dont 1 mémo de sous-dossier, mode multi) → chip visible, coches OK, 409 sur nom dupliqué.
3. Un même mémo dans 2 votes → compteurs indépendants, voter dans l'un ne touche pas l'autre (D1).
4. Vote du dossier toujours fonctionnel en parallèle (chip « (dossier) »), `vote_excluded` sans effet sur les nommés.
5. Single nommé : revoter déplace la voix ; multi nommé : toggle par option.
6. Clôture « resto J1 » → 🏆 sur le gagnant du scrutin sélectionné seulement ; reopen exige deadline redéfinie/effacée ; reset purge et rouvre.
7. Permission : dossier hérité `guests` → invité approuvé can_edit crée un vote via le hub ; owner passe le sous-dossier en `owner` → 403 générique côté invité (création), voter reste possible ; invité lecture seule = jamais de création.
8. Gestion créateur : l'invité modifie/clôt SON vote, 403 sur celui de l'owner ; l'owner gère tout.
9. Cascades : suppression d'une option à voix (confirm + purge), retrait de l'invité → ses voix disparaissent partout, son vote survit ; suppression du vote → mémos intacts.
10. Export→ré-import (§8). 11. Sondes bypass Authelia sur les nouvelles routes `/share/.../votes*` (réponse app sans cookies, jamais opaqueredirect). 12. `python3 -m py_compile app.py` + `node --check` sur les 3 pages rendues. 13. Console propre.

## 10. Invariants & hors périmètre

Invariants 1 (migrations additives), 2 (upsert non destructif), 5 (invité = routes scopées revalidées, pas de master token, 403 indiscernables), 6 (zéro CDN runtime), 8 (GSAP jamais sur dialog), 9 (tokens/gabarits existants). Versionnage : `[V20.9.Z]` (Z = dernier + 1), tag → deploy CI.

**Hors périmètre** (lots suivants, ne pas implémenter) : [VOTE-MAP] V20.10 (le vote sur la carte, par vote), [VOTE-V1.1] V20.11 (event agenda du gagnant), notifications de clôture, vote depuis le popup carte.
