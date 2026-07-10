# SPEC — [COMMENT-REACTIONS] Réactions emoji + pouces sur les commentaires

**Statut : VERROUILLÉE — décisions validées par Fabien (6 juil. 2026).**
Cible : **V21.0** (après [MEMO-TABLES] V20.5). ⚠️ **BUMP EXPORT → v21**
(les commentaires sont exportés depuis v14 ; leurs réactions sont des données
utilisateur → exportées aussi). Zone invité → invariant 5 à surveiller.

---

## 1. Décisions figées

1. **Palette FIXE** (whitelist serveur, jamais de texte libre) :
   `👍 👎 ❤️ 😂 😮 🎉` — constante `REACTION_EMOJIS`, tout autre payload → 400.
2. **Qui vote** : owner + **tout invité APPROUVÉ du partage couvrant le mémo,
   même en lecture seule** — voter n'est pas éditer. C'est une exception assumée
   au « can_edit pour écrire » (l'approbation reste requise, conforme à
   l'invariant 5 : « toute écriture via /share exige un invité approuvé »).
3. **Toggle** : re-cliquer sa réaction la retire. Une réaction max par
   (commentaire, emoji, votant) — plusieurs emojis différents possibles.
4. **Identité votant** = pattern `created_by` (v19) : `''` = propriétaire
   (résolu à l'affichage via `_owner_name(db)`), sinon « Nom <email> » de
   l'invité. Jamais réécrit au renommage (historique immuable, comme [GUEST-EDIT]).
5. Les réactions ne comptent PAS dans le badge 🔔 (pas une « modification ») ;
   le refresh passe par `_data_version` (voir §5).

## 2. Modèle

Table additive :
```sql
CREATE TABLE IF NOT EXISTS comment_reactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id INTEGER NOT NULL,
  emoji TEXT NOT NULL,
  voter TEXT NOT NULL DEFAULT '',      -- '' = owner, sinon « Nom <email> »
  created_at TEXT NOT NULL,
  UNIQUE(comment_id, emoji, voter)
);
```
- **Purge en cascade** aux mêmes sites que `memo_comments`/`comment_seen` :
  suppression d'un commentaire (DELETE owner), purge définitive du mémo
  (corbeille + `_purge_trash`).
- Migration `init_db()` additive (CREATE IF NOT EXISTS), jamais destructive.

## 3. Routes

### Owner (derrière Authelia)
- `POST /api/comments/<id>/react {emoji}` → toggle (insert ou delete), 400 si
  emoji hors palette, 404 si commentaire inconnu. Voter = `''`.

### Invité (préfixe `/share/*` obligatoire — invariant 5, jamais de préfixe nouveau)
- `POST /share/<token>/comment/<id>/react {emoji}` :
  - le mémo du commentaire est **dans le scope du partage** (même contrôle que
    `share_image`/le POST commentaire existant), sinon 404 ;
  - **invité approuvé** requis (header `X-Guest-Token`), sinon 403 ;
  - **`can_edit` NON requis** (décision 2) ;
  - voter = « Nom <email> » de l'invité ; toggle idem owner.
- Le hub route vers le `/share/<share_token>` du mémo comme toutes ses écritures
  ([HUB-DASHBOARD]) — **zéro route hub nouvelle**.
- **Sonde bypass Authelia** après ajout (règle CLAUDE.md) : fetch non authentifié
  `{credentials:'omit', redirect:'manual'}` → réponse `basic`, pas `opaqueredirect`.

### Exposition (lecture)
Chaque commentaire (owner `GET /api/memos/<id>/comments`, `share_data`, hub
`/data`) gagne `reactions` agrégées :
`[{emoji, count, mine, voters: [noms affichables]}]` — `mine` calculé côté
serveur selon l'identité de l'appelant (owner ou jeton invité). Les `voters`
sont des noms affichables (owner résolu via `_owner_name`) — pas d'e-mail brut
côté invité si on peut l'éviter : exposer le nom seul (l'e-mail reste owner-only,
cohérent avec `_share_memo_dict`/`created_by`).

## 4. UI (3 pages, tokens existants — invariant 9)

- Sous chaque commentaire (fil owner = accordéon [MEMO-CONTEXT], share, hub) :
  **rangée de chips** `👍 3` par emoji présent (façon `.badge`/`.prio-btn`),
  **ma réaction = chip sélectionné** (fond `var(--accent)`, texte `#10141a`,
  comme un `.prio-btn` actif), title = liste des votants.
- Bouton **`😊+`** en fin de rangée → mini-palette des 6 emojis (markup/CSS
  façon `card-menu`, entrée CSS — invariant 8, jamais de GSAP sur le dialog).
- Clic chip ou palette = toggle → re-render du fil (optimiste ou re-fetch, au
  choix de l'implémentation).
- Invité **anonyme** (non approuvé) : chips visibles en lecture, palette/clic
  masqués (gate `canEditNow()`-like : approuvé suffit, pas can_edit).

## 5. Auto-refresh

`_data_version` : ajouter `"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM
comment_reactions"` (même pattern que memo_comments) → le poll owner 15 s et le
refresh invité voient les votes des autres.

## 6. Export / import — **v21**

- `APP_VERSION = "21"`, § Versionnage X = 21, **entrée invariant 1 ajoutée à
  `CLAUDE.md`** (obligatoire).
- Export : chaque commentaire de la liste racine `comments` gagne
  `reactions: [{emoji, voter, created_at}]` (**voter brut**, comme `created_by`
  v19 — jamais les noms résolus).
- Import :
  - commentaire résolu par (memo_uid, created_at, author) — même mécanique que
    `parent_created_at` v15 ;
  - dédup par (commentaire, emoji, voter) ; emoji hors palette → ignoré ;
  - **non destructif** : on AJOUTE les réactions manquantes, on ne supprime
    jamais (un toggle-retrait local n'est pas ré-écrasé par un vieil export —
    assumé : un ré-import peut restaurer une réaction retirée depuis, cohérent
    avec « l'import ajoute, ne supprime pas », invariant 2) ;
  - compat v1→v20 : champ absent = aucune réaction, rendu identique.
- `comment_seen` reste non exporté (précédent v15) — les réactions, si.

## 7. Tests (copie de base, jamais `data/dashboard.db`)

1. Migration sur base existante ; `py_compile` ; rendu 3 pages + `node --check`.
2. Owner : toggle on/off, 2 emojis sur le même commentaire, chip `mine` accent.
3. Invité approuvé **lecture seule** : peut réagir (share ET hub) ; invité
   anonyme → 403 (et UI sans palette) ; commentaire hors scope → 404 ;
   emoji hors palette → 400.
4. Le voter invité est « Nom <email> » en base, nom seul côté share ; owner voit
   les noms résolus.
5. Suppression du commentaire / purge corbeille → réactions purgées (compter).
6. `_data_version` change après un toggle ; « marquer vu » n'y change rien.
7. Export v21 : `reactions` brutes présentes ; **ré-import complet → 0 ajout** ;
   import v20 (sans le champ) → 0 doublon, aucune réaction fantôme ; import v21
   croisé → dédup (comment, emoji, voter) OK.
8. Sonde bypass Authelia sur la nouvelle route publique (§3).

## 8. Hors périmètre (volontaire)

- Réactions sur les mémos eux-mêmes (seulement les commentaires).
- Palette configurable, emojis libres, compteurs dans le badge 🔔/activité.
- Notifications aux votés/mentionnés.

## 9. Invariants touchés

- **1** : bump v21 (entrée à rédiger dans CLAUDE.md au moment de la livraison).
- **2** : import additif non destructif (§6).
- **5** : route publique sous `/share/*`, scope + approbation revalidés serveur,
  e-mails jamais exposés aux invités.
- **8/9** : palette en markup/CSS, tokens existants.
