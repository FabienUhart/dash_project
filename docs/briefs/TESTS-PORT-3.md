# Brief CC — [TESTS-PORT-3] : surface de VOTE invitée `/share/*`

> **Suite de [TESTS-PORT] vagues 1 & 2.** Dernier gros bloc de la surface publique invitée
> (invariant 5) : voter. `share_vote_memo` (≈39 lignes nues) est le cœur ; les routes de
> **scrutins nommés** (`/share/<token>/votes…`) ajoutent création / modif / clôture / reset /
> suppression, toutes gardées par `_share_vote_guest_or_403` + `_share_managed_vote`.
>
> **Nature = caractérisation** (comme les vagues précédentes). On fige le comportement correct.
> **Un test qui tombe = bug réel** → arrête-toi, signale, ne réécris jamais l'assertion. Éprouve
> chaque garde par **mutation** (casse-la, vois tomber exactement un test, restaure `app.py`).
>
> **⚠ Interdiction réseau** : aucun test ne doit toucher le réseau. (Sans objet ici — le vote est
> local — mais règle générale de la suite, cf. ZIP/FX plus tard.)
>
> **Discipline** : fichier de test only, aucun changement applicatif. `make test` vert → journal
> + handoff → **STOP**. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 1. Fichier : `tests/back/test_share_votes.py` (marqueur `invariant`)

### Contrats relevés dans `app.py`

- `POST /share/<token>/memo/<memo_id>/vote` `{vote_id?}` → cast. Gardes : token 404 · non approuvé
  403 (`_approved_or_403`) · mémo hors scope 404 · mémo pas une option de vote 400
  (« pas une option de vote ») · capacité `vote` (= commenter) refusée 403 (`_role_gate`) ·
  **dossier clos → 409** (`_vote_is_closed`). Deux modes : dossier (projet `vote_enabled`) ou
  scrutin nommé (`vote_id`, dont le porteur doit être dans le scope, sinon 400).
- `POST /share/<token>/votes` → créer un scrutin nommé (`share_create_vote`). Exige
  `_share_vote_guest_or_403` **et** projet dans le scope **et** `vote_create == "guests"` sur le
  dossier **et** capacité `create_vote` → sinon **403**.
- `PUT /share/<token>/votes/<vid>` (modif), `POST …/votes/<vid>/close|reopen|reset`, `DELETE
  …/votes/<vid>` → tous passent par `_share_managed_vote` (il faut gérer CE scrutin) → **403/404** sinon.

### Activer le vote (levier de montage)

`PUT /api/projects/<id>` accepte `vote_enabled`, `vote_mode` (`"single"`/`"multi"`),
`vote_deadline`, `vote_create` (`"owner"`/`"guests"`). Donc :

```python
def _enable_vote(c, pid, mode="single", deadline=None, vote_create=None):
    body = {"vote_enabled": 1, "vote_mode": mode}
    if deadline is not None:     body["vote_deadline"] = deadline
    if vote_create is not None:  body["vote_create"] = vote_create
    r = c.put("/api/projects/%d" % pid, json=body); assert r.status_code == 200, r.data
```

> **Deux points à VÉRIFIER en montant** (et à figer sur le réel) : (a) le levier exact pour
> mettre un vote de dossier en état **clos** — a priori une `vote_deadline` **passée** (ex.
> `"2000-01-01T00:00:00+00:00"`) suffit à `_vote_is_closed` ; confirme, sinon trouve le vrai
> levier. (b) quel **rôle/cap** porte `create_vote` côté invité (probablement `editor` via
> `PUT /api/guests/<id>/role`) — établis-le, puis fige.

Réutilise les helpers des vagues 1/2 (`_project`, `_memo`, `_share`, `_register`, `_guest_id`,
`H`). `_share(..., role=...)` fixe le rôle du lien (`"viewer"` vs `"commenter"`).

---

## 2. Les tests (la liste = la spec)

### A. `share_vote_memo` — le cœur

1. **`test_vote_anonymous_403`** — sans header → 403.
2. **`test_vote_memo_out_of_scope_404`** — mémo d'un dossier non partagé → 404.
3. **`test_vote_not_an_option_400`** — mémo d'un dossier **non** `vote_enabled` → 400 « pas une option de vote ».
4. **`test_viewer_cannot_vote_403`** — lien `role="viewer"`, dossier `vote_enabled` → 403 (capacité `vote` refusée).
5. **`test_commenter_can_vote_single`** — lien `role="commenter"`, dossier `vote_enabled` single → **succès** (200), la voix est enregistrée (le refetch du board/mémo montre le votant).
6. **`test_vote_closed_returns_409`** — dossier `vote_enabled` avec **deadline passée** → 409 « vote clos ».
7. **`test_named_vote_id_out_of_scope_400`** — `{vote_id}` d'un scrutin dont le porteur est hors scope → 400.
8. **`test_vote_excluded_memo_400`** *(si applicable)* — mémo marqué `vote_excluded` → 400.

### B. Scrutins nommés — **gardes d'autorisation** (le plus important : qui peut toucher)

9. **`test_create_vote_denied_without_guests_permission`** — projet `vote_create` ≠ `"guests"` (défaut) → **403**, même pour un invité approuvé.
10. **`test_create_vote_denied_without_capability`** — `vote_create="guests"` mais invité sans `create_vote` (ex. `commenter`) → **403**.
11. **`test_manage_vote_denied_for_non_manager`** — un invité qui ne gère pas le scrutin : `PUT`,
    `close`, `reopen`, `reset`, `DELETE` sur `<vid>` → **403/404** (via `_share_managed_vote`).
    *(Un scrutin peut être créé côté owner pour le montage ; l'important est le refus.)*
12. **`test_vote_routes_anonymous_403`** — `POST /votes`, `POST /votes/<vid>/close` sans header → 403.

### C. Scrutin nommé — happy-path (OPTIONNEL, si le montage est propre)

13. **`test_guest_creates_named_vote`** — `vote_create="guests"` + invité porteur de `create_vote`
    (rôle à établir) → `POST /share/<token>/votes {title, memo_ids}` → **201**, scrutin visible.
14. **`test_creator_can_close_then_cast_409`** — le créateur `close` son scrutin (200), puis un cast
    dessus → **409**. *(Boucle la boucle : clôture ⇒ plus de voix.)*

> Si le montage du happy-path (C) s'avère fragile (cap `create_vote`, forme de `memo_ids`),
> **livre A + B et note C en reste** — ne bloque pas le lot sur le point le plus touffu.

---

## 3. Definition of Done

1. `tests/back/test_share_votes.py` créé (marqueur `invariant`), gardes éprouvées par mutation.
2. `make test` **vert** (ou rouge **signalé**, jamais masqué).
3. `make test-cov` : `share_vote_memo` (au minimum) ne sont plus à nu ; idéalement aussi les
   routes de scrutins nommés côté gardes.
4. `git status` : seul `tests/` bouge.
5. Journal + handoff, **STOP**. Commit `tests/back/test_share_votes.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT-3.md`) après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 4. Hors lot (rappel)

Micro-fix docstring `share_admin_view` (vague 1) : toujours à faire **à part** (1 ligne `app.py`).
