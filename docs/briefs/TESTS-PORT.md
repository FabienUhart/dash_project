# Brief CC — [TESTS-PORT] : rendre durables les tests de la délégation invité `/share/*`

> **Motif (chiffré)** : `make test-cov` = **32 %** de couverture back. Les plus gros blocs
> nus sont les routes de **délégation invité** (`share_set_guest_role`,
> `share_decide_role_request`, `share_admin_view`) — pourtant « testées » par ~36 tests…
> qui vivaient dans le scratchpad et **n'existent plus**. Ce sont des routes de **sécurité**
> (surface publique `/share/*`, **invariant 5**). On les met sous garde durable, d'abord.
>
> **Nature = tests de CARACTÉRISATION.** On fige le comportement **correct actuel** (le code
> est déjà en prod et éprouvé). Ce n'est donc pas du « rouge d'abord ». **Conséquence
> importante** : si un test **tombe**, ce n'est PAS un test à « ajuster » — c'est un **bug
> réel** dans une route de sécurité → **arrête-toi, signale-le** (journal `⚠` + à moi), on
> décide. Ne jamais réécrire l'assertion pour matcher un comportement faux.
>
> **Discipline** : nouveau fichier de test uniquement, **aucun changement applicatif**.
> `make test` vert → journal + handoff → **STOP**. Commit après passe Cowork + GO. Pas de
> tag ni de Deploy (test only).

---

## 1. Fichier à créer : `tests/back/test_share_delegation.py`

Marqueur `@pytest.mark.invariant` (surface `/share/*` = invariant 5 ; un rouge ici = pas de
deploy). Tourne dans la voie rapide (`-m "not e2e"`), donc aussi au hook Stop et au pre-commit.

### Contrats vérifiés dans `app.py` (pour info, ne pas les ré-explorer)

- `POST /api/shares` `{kind:"project", target_id}` → `{token, pin, ...}`.
- `POST /share/<token>/register` `{name, email, pin}` → `{guest_token, status:"approved", email}`
  (201 si nouveau, 200 si déjà là). **Ne renvoie pas l'id** → le lire en base (helper ci-dessous).
- Élever un invité en Admin (côté owner, sans auth en test) :
  `PUT /api/guests/<guest_id>/role` `{project_id, role:"admin"}`.
- `PUT /share/<token>/guests/<target_id>/role` (header `X-Guest-Token`) `{project_id, role, caps_add?, caps_remove?}`.
- `POST /share/<token>/role-request` `{role:"editor"|"commenter"}` (invité approuvé) → crée une demande *pending* sur le dossier racine du partage.
- `POST /share/<token>/role-request/<req_id>` `{decision:"grant"|"ignore"}` (header admin).
- `GET /share/<token>/admin` (header admin) → `{me, root_id, folders, guests, requests, roles}`.

### Helpers de montage (le point dur — donне-les tels quels)

```python
import sqlite3
import pytest

pytestmark = pytest.mark.invariant

H = lambda gt: {"X-Guest-Token": gt}   # header invité


def _project(c, name, parent_id=None):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    pid = r.get_json()["id"]
    if parent_id is not None:
        assert c.put("/api/projects/%d" % pid, json={"parent_id": parent_id}).status_code == 200
    return pid


def _memo(c, pid, content):
    r = c.post("/api/memos", json={"content": content, "project_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _share_project(c, pid):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()                      # {token, pin, ...}


def _register(c, token, pin, email, name="Invite"):
    r = c.post("/share/%s/register" % token, json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _guest_id(email):
    """Id share_guests par e-mail, lu dans la base TEMP du test (conftest a pointé
    app.DB_PATH dessus). Le register ne renvoie pas l'id ; on le lit ici."""
    import app
    con = sqlite3.connect(app.DB_PATH)
    try:
        row = con.execute("SELECT id FROM share_guests WHERE email = ? ORDER BY id DESC LIMIT 1",
                          (email.lower(),)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _make_admin(c, guest_id, project_id):
    """Élève un invité en Administrateur sur un dossier (route owner, sans auth en test)."""
    r = c.put("/api/guests/%d/role" % guest_id, json={"project_id": project_id, "role": "admin"})
    assert r.status_code in (200, 204), r.data
```

Note : `_project` déplace via `PUT /api/projects/<id> {parent_id}` (le POST crée à la racine).
Vérifie le nom exact du champ de déplacement si le PUT renvoie 400 (`parent_id` attendu).

---

## 2. Les tests à écrire (la liste = la spec)

### A. `share_set_guest_role` — nomination par un Admin invité

1. **`test_anonymous_cannot_nominate`** — sans `X-Guest-Token`, `PUT …/guests/<x>/role` → **403**.
2. **`test_approved_non_admin_cannot_nominate`** — invité approuvé mais **non admin** → **403** « non autorisé ».
3. **`test_nominate_out_of_scope_project_400`** — admin d'un dossier, `project_id` **hors** du sous-arbre du partage → **400** « pas dans le périmètre ».
4. **`test_invalid_project_id_400`** — `project_id` non entier → **400**.
5. **`test_cannot_nominate_self`** — `target_id == ` son propre id → **403** « on ne change pas son propre rôle ».
6. **`test_cannot_nominate_guest_of_other_link`** — cible dont le `share_id` diffère → **404**.
7. **`test_admin_nominates_moderator_ok`** — A (admin) nomme B `moderator` dans son sous-arbre →
   **200**, réponse `{guest_id, project_id, role:"moderator", source:"override"}` ; **effet visible** :
   `GET /share/<token>/admin` (en A) liste B avec `role_effective:"moderator"`.
8. **`test_nominated_act_is_journaled_revocable`** — après la nomination du 7, une ligne d'acte
   existe (lire `admin_actions` en base, ou vérifier la remontée `memo_revisions` de partage) →
   l'owner peut révoquer. *(Si `admin_actions` n'est pas la table, ajuste au vrai canal — voir
   `_apply_guest_role`.)*
9. **`test_role_capped_at_admin`** — A tente de poser un rôle **non assignable** (ex. `role:"owner"`)
   → le rôle accordé **n'excède jamais** `admin` (`_clean_role` le neutralise) : soit 400, soit
   l'effet ne pose pas « owner ». Vérifie le comportement réel et fige-le.

### B. `share_decide_role_request` — accorder / écarter une demande

Montage commun : B (approuvé) fait `POST /share/<token>/role-request {role:"editor"}` → demande
*pending* ; récupère `req_id` (lire `role_requests` en base par `guest_id`).

10. **`test_decide_requires_valid_decision`** — `decision` absente ou hors `grant|ignore` → **400**.
11. **`test_anonymous_cannot_decide`** — sans header invité → **403**.
12. **`test_decide_unknown_or_settled_request_404`** — `req_id` inexistant, **ou déjà tranché**
    (rejoue un grant sur la même demande) → **404**.
13. **`test_cannot_decide_own_request`** — le demandeur tranche sa propre demande → **403**.
14. **`test_decide_request_out_of_admin_scope_403`** — admin d'un sous-dossier, demande portant sur
    un dossier **hors** de son périmètre → **403**.
15. **`test_grant_applies_role_and_marks_granted`** — A accorde → **200** `status:"granted"`, B a
    bien le rôle demandé (via `/share/<token>/admin` ou `guest_roles`), la demande passe `granted`.
16. **`test_grant_preserves_fine_grained_caps`** — **le point délicat** : l'owner pose d'abord un
    `caps_add` sur (B, dossier) via `PUT /api/guests/<B>/role {project_id, role:"", caps_add:[...]}` ;
    A accorde ensuite la demande → le `caps_add` **est conservé** (grant ne remet pas à zéro).
17. **`test_ignore_writes_no_role`** — A `ignore` → **200** `status:"refused"`, **aucun** rôle posé
    sur B, la demande sort de la file (`/share/<token>/admin` ne la liste plus).

### C. `share_admin_view` — ce qu'un Admin invité voit (et ne voit pas)

18. **`test_admin_view_anonymous_403`** / **`test_admin_view_non_admin_403`**.
19. **`test_admin_view_scoped_to_subtree`** — A admin d'un **sous-dossier** seulement : `folders`
    ne contient que son sous-arbre ; un invité d'un dossier **voisin** n'apparaît **pas** dans
    `guests` ; **soi-même absent** de `guests` (id != me) ; **owner jamais** listé.
20. **`test_admin_view_hides_email`** — aucune entrée de `guests`/`requests` n'expose de champ
    `email` (le nom suffit).
21. **`test_admin_view_requests_scoped`** — une demande portant sur un dossier **hors** du
    périmètre de A ne remonte pas dans `requests`.

> Total ~21 tests. La plupart doivent **passer d'emblée** (le code est correct) : ce sont des
> filets. Tout **rouge** est un signalement (cf. cadrage en tête), pas un test à corriger.

---

## 3. Vague 2 (lot suivant `[TESTS-PORT-2]`, pas dans celui-ci)

À porter ensuite, par risque décroissant, d'après `htmlcov/` : `_clean_reaction_emoji`
(validation d'emoji — **pure, sans montage, très rentable**), `share_vote_memo` (vote invité),
export ZIP (`_memo_zip_files`/`_send_zip`), `_fx_rates` (cache FX). On les cadrera après celui-ci
pour garder ce lot **focalisé sur la sécurité** de la délégation.

---

## 4. Definition of Done

1. `tests/back/test_share_delegation.py` créé (~21 tests, marqueur `invariant`).
2. `make test` **vert** (ou : tout rouge **signalé** comme bug potentiel, pas masqué).
3. `make test-cov` : les trois routes de délégation ne sont plus à nu (le % remonte — le
   chiffre exact importe peu, la **surface sécurité** est ce qui compte).
4. Aucun fichier applicatif modifié (`git status` : que `tests/`).
5. Journal + handoff, **STOP**. Commit `tests/back/test_share_delegation.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT.md`) après passe Cowork + GO. Pas de tag ni de Deploy.
