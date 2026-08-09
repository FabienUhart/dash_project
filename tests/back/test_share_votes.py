"""[TESTS-PORT vague 3] Surface de VOTE invitée sous /share/* — invariant 5.

Dernier gros bloc de la surface publique invitée : voter. `share_vote_memo` porte les deux
modes (vote de DOSSIER et scrutin NOMMÉ) ; les routes `/share/<token>/votes…` ajoutent la
création et la gestion, gardées par `_share_vote_guest_or_403` + `_share_managed_vote`.

Même nature qu'aux vagues 1 et 2 : **CARACTÉRISATION** du comportement correct actuel.
**Un rouge ici est un bug dans une route de sécurité**, jamais une assertion à réaligner.
Aucun test ne touche le réseau (le vote est entièrement local).

Trois contrats du brief se sont révélés faux à la lecture d'`app.py` ; ce sont les vrais qui
sont figés ici, et ils changent le sens des tests :
  · `_resolve_vote_create` vaut **« guests » par DÉFAUT** (« les invités peuvent », D3) — le
    refus de création se teste donc en posant `vote_create="owner"` EXPLICITEMENT, pas en
    s'appuyant sur un défaut restrictif qui n'existe pas ;
  · créer un scrutin nommé se paie `creer-vote`, capacité que porte **`editor`** (et au-dessus),
    pas `commenter` — un commentateur vote mais n'ouvre pas de scrutin ;
  · le corps de création attend **`name`**, pas `title`.
"""
import sqlite3

import pytest

pytestmark = pytest.mark.invariant


H = lambda gt: {"X-Guest-Token": gt}

PASSE = "2000-01-01T00:00"          # deadline franchement dépassée → vote clos


# ─────────────────────────────────────────────────────────────── montage ────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _memo(c, pid, content):
    r = c.post("/api/memos", json={"content": content, "project_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _share(c, pid, role="commenter"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token,
               json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _guest_id(email, share_id):
    con = _db()
    try:
        row = con.execute("SELECT id FROM share_guests WHERE email = ? AND share_id = ?",
                          (email.lower(), share_id)).fetchone()
        return row["id"] if row else None
    finally:
        con.close()


def _enable_vote(c, pid, mode="single", deadline=None, vote_create=None):
    body = {"vote_enabled": 1, "vote_mode": mode}
    if deadline is not None:
        body["vote_deadline"] = deadline
    if vote_create is not None:
        body["vote_create"] = vote_create
    r = c.put("/api/projects/%d" % pid, json=body)
    assert r.status_code == 200, r.data
    return r.get_json()


def _set_role(c, guest_id, pid, role):
    """Élève (ou rétrograde) un invité sur un dossier — route owner, derrière Authelia en prod."""
    r = c.put("/api/guests/%d/role" % guest_id, json={"project_id": pid, "role": role})
    assert r.status_code in (200, 204), r.data


def _cast(a, gt, memo_id, token=None, **payload):
    return a["c"].post("/share/%s/memo/%d/vote" % (token or a["token"], memo_id),
                       headers=(H(gt) if gt else {}), json=payload)


def _owner_named_vote(c, pid, name, memo_ids):
    r = c.post("/api/projects/%d/votes" % pid, json={"name": name, "memo_ids": memo_ids})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _voters_of(memo_id, project_id=None, vote_id=None):
    """Qui a voté pour ce mémo, lu en base (le payload agrège, la base tranche)."""
    con = _db()
    try:
        if vote_id is not None:
            rows = con.execute(
                "SELECT voter FROM memo_votes WHERE memo_id = ? AND vote_id = ?",
                (memo_id, vote_id)).fetchall()
        else:
            rows = con.execute(
                "SELECT voter FROM memo_votes WHERE memo_id = ? AND project_id = ? "
                "AND COALESCE(vote_id, 0) = 0", (memo_id, project_id)).fetchall()
        return sorted(r["voter"] for r in rows)
    finally:
        con.close()


@pytest.fixture
def arena(client):
    """Un dossier partagé « commentateur » avec deux mémos-options, plus un dossier HORS
    partage — pour que le périmètre ait quelque chose à refuser."""
    c = client
    pid = _project(c, "Dossier vote")
    m1 = _memo(c, pid, "Option A")
    m2 = _memo(c, pid, "Option B")
    out_pid = _project(c, "Dossier prive")
    out_mid = _memo(c, out_pid, "Hors perimetre")

    sh = _share(c, pid, role="commenter")
    gtA = _register(c, sh["token"], sh["pin"], "a@ex.com", "Alice")
    gtB = _register(c, sh["token"], sh["pin"], "b@ex.com", "Bob")
    return {
        "c": c, "pid": pid, "m1": m1, "m2": m2,
        "out_pid": out_pid, "out_mid": out_mid,
        "share_id": sh["id"], "token": sh["token"], "pin": sh["pin"],
        "gtA": gtA, "gtB": gtB,
        "idA": _guest_id("a@ex.com", sh["id"]), "idB": _guest_id("b@ex.com", sh["id"]),
    }


# ══════════════════════ A. share_vote_memo — le cœur ══════════════════════

def test_vote_unknown_token_404(arena):
    _enable_vote(arena["c"], arena["pid"])
    assert _cast(arena, arena["gtA"], arena["m1"], token="jeton-invente").status_code == 404


def test_vote_anonymous_403(arena):
    """Voter n'exige pas `can_edit` (§2.3 : voter n'est pas éditer) mais exige d'être approuvé."""
    _enable_vote(arena["c"], arena["pid"])
    r = _cast(arena, None, arena["m1"])
    assert r.status_code == 403, r.data
    assert r.get_json()["status"] == "anonymous"
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []


def test_vote_memo_out_of_scope_404(arena):
    """Un mémo hors partage n'existe pas pour ce jeton — 404, on ne confirme rien."""
    _enable_vote(arena["c"], arena["out_pid"])
    r = _cast(arena, arena["gtA"], arena["out_mid"])
    assert r.status_code == 404, r.data


def test_vote_not_an_option_400(arena):
    """Dossier sans vote ouvert : le mémo existe et l'invité a le droit de voter — il n'y a
    simplement rien à voter. 400 explicite, pas un 404 trompeur."""
    r = _cast(arena, arena["gtA"], arena["m1"])
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "pas une option de vote"


def test_viewer_cannot_vote_403(arena):
    """Lien LECTURE : le vote est ouvert, la personne est approuvée, et pourtant non."""
    c = arena["c"]
    _enable_vote(c, arena["pid"])
    sh = _share(c, arena["pid"], role="viewer")
    gt = _register(c, sh["token"], sh["pin"], "v@ex.com", "Vera")

    r = _cast(arena, gt, arena["m1"], token=sh["token"])
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []


def test_commenter_can_vote_single(arena):
    """Le cas nominal : commentateur = votant. Vérifié en base, pas seulement dans la réponse."""
    _enable_vote(arena["c"], arena["pid"], mode="single")
    r = _cast(arena, arena["gtA"], arena["m1"])
    assert r.status_code == 200, r.data
    assert r.get_json()["project_id"] == arena["pid"]

    voix = _voters_of(arena["m1"], project_id=arena["pid"])
    assert len(voix) == 1 and "a@ex.com" in voix[0]


def test_single_mode_replaces_the_previous_vote(arena):
    """Mode `single` : une seule voix par personne — le second choix REMPLACE le premier,
    il ne s'ajoute pas."""
    _enable_vote(arena["c"], arena["pid"], mode="single")
    assert _cast(arena, arena["gtA"], arena["m1"]).status_code == 200
    assert _cast(arena, arena["gtA"], arena["m2"]).status_code == 200

    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []
    assert len(_voters_of(arena["m2"], project_id=arena["pid"])) == 1


def test_multi_mode_keeps_both_and_toggles(arena):
    """Mode `multi` : on cumule les options, et re-voter la même la retire (interrupteur)."""
    _enable_vote(arena["c"], arena["pid"], mode="multi")
    assert _cast(arena, arena["gtA"], arena["m1"]).status_code == 200
    assert _cast(arena, arena["gtA"], arena["m2"]).status_code == 200
    assert len(_voters_of(arena["m1"], project_id=arena["pid"])) == 1
    assert len(_voters_of(arena["m2"], project_id=arena["pid"])) == 1

    assert _cast(arena, arena["gtA"], arena["m1"]).status_code == 200
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []
    assert len(_voters_of(arena["m2"], project_id=arena["pid"])) == 1


def test_two_guests_vote_independently(arena):
    """Deux personnes, deux voix : le `single` borne UNE personne, pas le scrutin."""
    _enable_vote(arena["c"], arena["pid"], mode="single")
    assert _cast(arena, arena["gtA"], arena["m1"]).status_code == 200
    assert _cast(arena, arena["gtB"], arena["m1"]).status_code == 200
    assert len(_voters_of(arena["m1"], project_id=arena["pid"])) == 2


def test_vote_closed_by_deadline_returns_409(arena):
    """Deadline dépassée = scrutin clos : 409, et surtout AUCUNE voix enregistrée."""
    _enable_vote(arena["c"], arena["pid"], deadline=PASSE)
    r = _cast(arena, arena["gtA"], arena["m1"])
    assert r.status_code == 409, r.data
    assert r.get_json()["error"] == "vote clos"
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []


def test_closing_by_deadline_freezes_the_result(arena):
    """Gel PARESSEUX : le vainqueur est figé au premier accès après l'échéance — sinon un
    mémo ajouté après coup pourrait changer un résultat déjà annoncé."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], mode="single")
    assert _cast(arena, arena["gtA"], arena["m1"]).status_code == 200
    assert c.put("/api/projects/%d" % arena["pid"],
                 json={"vote_deadline": PASSE}).status_code == 200

    assert _cast(arena, arena["gtB"], arena["m1"]).status_code == 409
    con = _db()
    try:
        row = con.execute("SELECT vote_winner_ids FROM projects WHERE id = ?",
                          (arena["pid"],)).fetchone()
    finally:
        con.close()
    assert str(arena["m1"]) in (row["vote_winner_ids"] or "")


def test_excluded_memo_is_not_an_option_400(arena):
    """[VOTE-EXCLUDE] Un mémo retiré du scrutin n'est pas votable, même dans un dossier ouvert.
    Aucune route n'écrit ce drapeau aujourd'hui — on le pose en base pour éprouver la garde."""
    _enable_vote(arena["c"], arena["pid"])
    con = _db()
    try:
        con.execute("UPDATE memos SET vote_excluded = 1 WHERE id = ?", (arena["m1"],))
        con.commit()
    finally:
        con.close()

    r = _cast(arena, arena["gtA"], arena["m1"])
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "pas une option de vote"
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []
    # …et l'option voisine reste votable : l'exclusion est par MÉMO, pas par dossier.
    assert _cast(arena, arena["gtA"], arena["m2"]).status_code == 200


# ───────────────── A bis. mode « scrutin nommé » de la même route ─────────────────

def test_named_vote_out_of_scope_400(arena):
    """`vote_id` dont le dossier porteur est hors du partage → 400. Le scrutin d'un autre
    dossier n'est pas un scrutin qu'on peut atteindre par ce jeton."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["out_pid"], "Ailleurs", [arena["out_mid"]])
    r = _cast(arena, arena["gtA"], arena["m1"], vote_id=vid)
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "pas une option de vote"


def test_named_vote_on_an_ancestor_folder_is_out_of_reach(arena):
    """Le cas que la garde de périmètre existe VRAIMENT pour couvrir — et il a fallu une
    mutation survivante pour le voir.

    Le test précédent passe même sans la garde : son scrutin étranger n'a pas mon mémo pour
    option, donc c'est le contrôle d'à côté qui refuse. Il prouvait la bonne réponse pour la
    mauvaise raison. Ici le scrutin vit sur le dossier PARENT du dossier partagé : ses options
    éligibles incluent légitimement les mémos des descendants, donc le mien. Toutes les autres
    gardes passent — seule celle du périmètre du partage peut encore dire non.
    """
    c = arena["c"]
    parent = _project(c, "Dossier parent, non partage")
    assert c.put("/api/projects/%d" % arena["pid"],
                 json={"parent_id": parent}).status_code == 200
    vid = _owner_named_vote(c, parent, "Scrutin du parent", [arena["m1"]])

    r = _cast(arena, arena["gtA"], arena["m1"], vote_id=vid)
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "pas une option de vote"
    assert _voters_of(arena["m1"], vote_id=vid) == [], \
        "un invité ne vote pas dans un scrutin porté par un dossier hors de son partage"


def test_named_vote_unknown_or_garbage_400(arena):
    for bad in (999999, "pas-un-entier"):
        r = _cast(arena, arena["gtA"], arena["m1"], vote_id=bad)
        assert r.status_code == 400, (bad, r.data)


def test_named_vote_memo_not_an_option_400(arena):
    """Le mémo doit être une OPTION de ce scrutin — être dans le même dossier ne suffit pas."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Restaurant", [arena["m1"]])
    r = _cast(arena, arena["gtA"], arena["m2"], vote_id=vid)
    assert r.status_code == 400, r.data


def test_named_vote_cast_ok(arena):
    """Voter dans un scrutin nommé ne demande PAS que le dossier soit `vote_enabled` : le
    scrutin porte son propre périmètre."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Restaurant", [arena["m1"], arena["m2"]])
    r = _cast(arena, arena["gtA"], arena["m1"], vote_id=vid)
    assert r.status_code == 200, r.data
    assert r.get_json()["vote_id"] == vid

    voix = _voters_of(arena["m1"], vote_id=vid)
    assert len(voix) == 1 and "a@ex.com" in voix[0]
    # la voix vit dans le scrutin, pas dans le vote de dossier
    assert _voters_of(arena["m1"], project_id=arena["pid"]) == []


def test_named_vote_closed_returns_409(arena):
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Restaurant", [arena["m1"]])
    assert c.post("/api/votes/%d/close" % vid).status_code == 200

    r = _cast(arena, arena["gtA"], arena["m1"], vote_id=vid)
    assert r.status_code == 409, r.data
    assert r.get_json()["error"] == "vote clos"
    assert _voters_of(arena["m1"], vote_id=vid) == []


# ═══════════ B. Scrutins nommés — qui peut créer, qui peut gérer ═══════════

def _create(arena, gt, token=None, **payload):
    return arena["c"].post("/share/%s/votes" % (token or arena["token"]),
                           headers=(H(gt) if gt else {}), json=payload)


def test_create_vote_anonymous_403(arena):
    r = _create(arena, None, name="Resto", memo_ids=[arena["m1"]])
    assert r.status_code == 403, r.data


def test_vote_actions_anonymous_403(arena):
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Resto", [arena["m1"]])
    t = arena["token"]
    assert c.post("/share/%s/votes/%d/close" % (t, vid)).status_code == 403
    assert c.post("/share/%s/votes/%d/reopen" % (t, vid)).status_code == 403
    assert c.post("/share/%s/votes/%d/reset" % (t, vid)).status_code == 403
    assert c.put("/share/%s/votes/%d" % (t, vid), json={"name": "X"}).status_code == 403
    assert c.delete("/share/%s/votes/%d" % (t, vid)).status_code == 403


def test_create_vote_denied_when_reserved_to_owner(arena):
    """`vote_create` vaut « guests » PAR DÉFAUT (D3) : le refus se prouve en le posant à
    « owner », pas en comptant sur un défaut restrictif — qui n'existe pas."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="owner")
    _set_role(c, arena["idA"], arena["pid"], "editor")   # capacité présente, permission absente

    r = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]])
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"


def test_create_vote_denied_without_capability(arena):
    """Permission ouverte aux invités, mais `creer-vote` appartient à `editor` : un
    commentateur vote et n'ouvre pas de scrutin. Les deux conditions sont cumulatives."""
    _enable_vote(arena["c"], arena["pid"], vote_create="guests")
    r = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]])
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"


def test_editor_guest_creates_named_vote(arena):
    """Les deux conditions réunies → création. Le corps attend `name` (pas `title`)."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")

    r = _create(arena, arena["gtA"], name="Restaurant", memo_ids=[arena["m1"], arena["m2"]])
    assert r.status_code == 201, r.data
    vid = r.get_json()["id"]

    con = _db()
    try:
        row = con.execute("SELECT created_by, project_id FROM votes WHERE id = ?", (vid,)).fetchone()
    finally:
        con.close()
    assert "a@ex.com" in row["created_by"]      # la paternité est tracée (elle fonde la gestion)
    assert row["project_id"] == arena["pid"]


def test_create_vote_options_are_restricted_to_the_share_scope(arena):
    """Les options proposées sont filtrées au périmètre du partage : un mémo étranger est
    écarté SILENCIEUSEMENT, et s'il ne reste rien → 400. Pas de fuite par la liste d'options."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")

    r = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["out_mid"]])
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "au moins une option requise"

    mixte = _create(arena, arena["gtA"], name="Resto2",
                    memo_ids=[arena["out_mid"], arena["m1"]])
    assert mixte.status_code == 201, mixte.data
    con = _db()
    try:
        opts = [x["memo_id"] for x in con.execute(
            "SELECT memo_id FROM vote_options WHERE vote_id = ?",
            (mixte.get_json()["id"],)).fetchall()]
    finally:
        con.close()
    assert opts == [arena["m1"]], "le mémo hors partage ne doit pas devenir une option"


def test_non_manager_cannot_touch_a_vote(arena):
    """Gérer un scrutin, c'est l'avoir créé : celui de l'owner reste hors d'atteinte, même
    d'un invité Éditeur qui a pourtant la capacité `creer-vote`."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _owner_named_vote(c, arena["pid"], "Resto du proprio", [arena["m1"]])
    t, gt = arena["token"], arena["gtA"]

    assert c.put("/share/%s/votes/%d" % (t, vid), headers=H(gt),
                 json={"name": "Détourné"}).status_code == 403
    assert c.post("/share/%s/votes/%d/close" % (t, vid), headers=H(gt)).status_code == 403
    assert c.post("/share/%s/votes/%d/reopen" % (t, vid), headers=H(gt)).status_code == 403
    assert c.post("/share/%s/votes/%d/reset" % (t, vid), headers=H(gt)).status_code == 403
    assert c.delete("/share/%s/votes/%d" % (t, vid), headers=H(gt)).status_code == 403

    con = _db()
    try:
        row = con.execute("SELECT name, vote_closed FROM votes WHERE id = ?", (vid,)).fetchone()
    finally:
        con.close()
    assert row["name"] == "Resto du proprio" and not row["vote_closed"]


def test_manage_vote_out_of_scope_403(arena):
    """Un scrutin d'un dossier hors partage : 403 générique, jamais 404 — on ne dit pas s'il
    existe (403 indiscernable, comme le veut la doctrine des routes de gestion)."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["out_pid"], "Ailleurs", [arena["out_mid"]])
    r = c.post("/share/%s/votes/%d/close" % (arena["token"], vid), headers=H(arena["gtA"]))
    assert r.status_code == 403, r.data


def test_a_guest_cannot_manage_his_own_vote_through_another_token(arena):
    """Le cas que la garde de périmètre à la GESTION couvre vraiment — révélé, là encore, par
    une mutation survivante.

    Le test précédent passe même sans la garde : le scrutin étranger est celui de l'owner,
    donc la garde de paternité refuse de toute façon. Ici la MÊME personne a deux liens et a
    créé le scrutin elle-même sur l'autre : la paternité passe, la capacité aussi (les deux
    liens sont Éditeur). Un jeton ne doit pas servir de passe-partout vers le périmètre d'un
    autre — c'est la garde de périmètre, et elle seule, qui peut encore refuser.
    """
    c = arena["c"]
    sh1 = _share(c, arena["pid"], role="editor")
    sh2 = _share(c, arena["out_pid"], role="editor")
    gt1 = _register(c, sh1["token"], sh1["pin"], "z@ex.com", "Zoe")
    gt2 = _register(c, sh2["token"], sh2["pin"], "z@ex.com", "Zoe")
    _enable_vote(c, arena["out_pid"], vote_create="guests")

    cree = c.post("/share/%s/votes" % sh2["token"], headers=H(gt2),
                  json={"name": "Chez moi", "memo_ids": [arena["out_mid"]]})
    assert cree.status_code == 201, cree.data
    vid = cree.get_json()["id"]

    # …et le même scrutin, atteint par l'AUTRE jeton, reste hors de portée.
    for appel in (
        lambda: c.post("/share/%s/votes/%d/close" % (sh1["token"], vid), headers=H(gt1)),
        lambda: c.post("/share/%s/votes/%d/reset" % (sh1["token"], vid), headers=H(gt1)),
        lambda: c.delete("/share/%s/votes/%d" % (sh1["token"], vid), headers=H(gt1)),
    ):
        r = appel()
        assert r.status_code == 403, r.data

    con = _db()
    try:
        row = con.execute("SELECT name, vote_closed FROM votes WHERE id = ?", (vid,)).fetchone()
    finally:
        con.close()
    assert row and row["name"] == "Chez moi" and not row["vote_closed"]


def test_memo_share_vote_options_cannot_reach_the_whole_folder(arena):
    """L'autre garde que rien ne distinguait : `_share_restrict_memo_ids`.

    Sur un partage de DOSSIER, le périmètre du partage et celui du scrutin coïncident — le
    filtre est donc inobservable, et mon premier test passait grâce au filtre d'à côté
    (`_create_named_vote` borne déjà les options au sous-arbre du dossier). Sur un partage de
    MÉMO, les deux divergent : le scrutin vit sur le dossier porteur, dont l'invité ne voit
    qu'UN mémo. Sans ce filtre, il ferait entrer comme option un mémo qu'il n'a pas le droit
    de voir — et son titre remonterait dans le payload du scrutin.
    """
    c = arena["c"]
    sh = c.post("/api/shares", json={"kind": "memo", "target_id": arena["m1"],
                                     "role": "editor"})
    assert sh.status_code in (200, 201), sh.data
    sh = sh.get_json()
    gt = _register(c, sh["token"], sh["pin"], "m@ex.com", "Mona")
    _enable_vote(c, arena["pid"], vote_create="guests")

    # m2 est dans le même dossier, mais HORS du partage (qui ne porte que m1).
    r = c.post("/share/%s/votes" % sh["token"], headers=H(gt),
               json={"name": "Resto", "project_id": arena["pid"], "memo_ids": [arena["m2"]]})
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "au moins une option requise"

    # …et le mémo réellement partagé, lui, fait une option valide.
    ok = c.post("/share/%s/votes" % sh["token"], headers=H(gt),
                json={"name": "Resto", "project_id": arena["pid"], "memo_ids": [arena["m1"]]})
    assert ok.status_code == 201, ok.data
    con = _db()
    try:
        opts = [x["memo_id"] for x in con.execute(
            "SELECT memo_id FROM vote_options WHERE vote_id = ?",
            (ok.get_json()["id"],)).fetchall()]
    finally:
        con.close()
    assert opts == [arena["m1"]]


def test_creator_can_manage_then_closing_blocks_the_cast(arena):
    """Boucle la boucle : le créateur clôt son scrutin (200), et plus personne n'y vote (409)."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto",
                  memo_ids=[arena["m1"], arena["m2"]]).get_json()["id"]
    assert _cast(arena, arena["gtB"], arena["m1"], vote_id=vid).status_code == 200

    fermeture = c.post("/share/%s/votes/%d/close" % (arena["token"], vid), headers=H(arena["gtA"]))
    assert fermeture.status_code == 200, fermeture.data
    assert _cast(arena, arena["gtB"], arena["m2"], vote_id=vid).status_code == 409


def test_creator_reset_wipes_every_voice(arena):
    """Réinitialiser efface les voix de TOUT LE MONDE — c'est bien pour ça que la capacité est
    revérifiée à l'usage (E8), et pas seulement au moment de la création."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]
    assert _cast(arena, arena["gtB"], arena["m1"], vote_id=vid).status_code == 200
    assert len(_voters_of(arena["m1"], vote_id=vid)) == 1

    r = c.post("/share/%s/votes/%d/reset" % (arena["token"], vid), headers=H(arena["gtA"]))
    assert r.status_code == 200, r.data
    assert _voters_of(arena["m1"], vote_id=vid) == []


def test_creator_can_rename_and_reoption_his_vote(arena):
    """Le chemin nominal de la gestion : le créateur modifie son scrutin — et ses nouvelles
    options restent bornées à son périmètre."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]

    r = c.put("/share/%s/votes/%d" % (arena["token"], vid), headers=H(arena["gtA"]),
              json={"name": "Restaurant du soir",
                    "memo_ids": [arena["m1"], arena["m2"], arena["out_mid"]]})
    assert r.status_code == 200, r.data
    assert r.get_json()["name"] == "Restaurant du soir"

    con = _db()
    try:
        opts = sorted(x["memo_id"] for x in con.execute(
            "SELECT memo_id FROM vote_options WHERE vote_id = ?", (vid,)).fetchall())
    finally:
        con.close()
    assert opts == sorted([arena["m1"], arena["m2"]]), \
        "le mémo hors partage ne doit pas entrer par la porte du PUT non plus"


def test_put_vote_rejects_an_empty_name_and_an_unknown_token(arena):
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]

    vide = c.put("/share/%s/votes/%d" % (arena["token"], vid), headers=H(arena["gtA"]),
                 json={"name": "   "})
    assert vide.status_code == 400, vide.data
    assert vide.get_json()["error"] == "nom requis"

    assert c.put("/share/jeton-invente/votes/%d" % vid, headers=H(arena["gtA"]),
                 json={"name": "X"}).status_code == 404

    con = _db()
    try:
        assert con.execute("SELECT name FROM votes WHERE id = ?", (vid,)).fetchone()["name"] == "Resto"
    finally:
        con.close()


def test_creator_can_delete_his_vote(arena):
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]
    assert _cast(arena, arena["gtB"], arena["m1"], vote_id=vid).status_code == 200

    r = c.delete("/share/%s/votes/%d" % (arena["token"], vid), headers=H(arena["gtA"]))
    assert r.status_code == 204, r.data

    con = _db()
    try:
        assert con.execute("SELECT 1 FROM votes WHERE id = ?", (vid,)).fetchone() is None
        restes = con.execute("SELECT COUNT(*) AS n FROM memo_votes WHERE vote_id = ?",
                             (vid,)).fetchone()["n"]
    finally:
        con.close()
    assert restes == 0, "supprimer un scrutin emporte ses voix, pas seulement son en-tête"


def test_option_that_left_the_folder_is_no_longer_votable(arena):
    """Une option reste inscrite au scrutin mais son mémo a déménagé hors du dossier porteur :
    elle n'est plus votable. Le périmètre est revalidé À CHAQUE voix, jamais figé à la création."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Resto", [arena["m1"], arena["m2"]])
    assert c.put("/api/memos/%d" % arena["m1"],
                 json={"project_id": arena["out_pid"]}).status_code == 200

    r = _cast(arena, arena["gtA"], arena["m1"], vote_id=vid)
    assert r.status_code in (400, 404), r.data
    assert _voters_of(arena["m1"], vote_id=vid) == []


def test_named_vote_deadline_freezes_lazily(arena):
    """Même gel paresseux que pour le vote de dossier, sur un scrutin nommé."""
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Resto", [arena["m1"]])
    assert _cast(arena, arena["gtA"], arena["m1"], vote_id=vid).status_code == 200
    assert c.put("/api/votes/%d" % vid, json={"vote_deadline": PASSE}).status_code == 200

    r = _cast(arena, arena["gtB"], arena["m1"], vote_id=vid)
    assert r.status_code == 409, r.data
    con = _db()
    try:
        row = con.execute("SELECT vote_winner_ids FROM votes WHERE id = ?", (vid,)).fetchone()
    finally:
        con.close()
    assert str(arena["m1"]) in (row["vote_winner_ids"] or "")


def test_create_vote_ignores_unreadable_ids(arena):
    """Un `project_id` ou des `memo_ids` illisibles n'ouvrent pas de brèche et ne font pas de
    500 : ils sont simplement écartés — le refus vient ensuite des gardes normales."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")

    r = _create(arena, arena["gtA"], name="Resto", project_id="pas-un-entier",
                memo_ids=[arena["m1"]])
    assert r.status_code == 201, r.data      # repli sur la racine du partage

    r2 = _create(arena, arena["gtA"], name="Resto2", memo_ids=["abc", None, arena["m2"]])
    assert r2.status_code == 201, r2.data
    con = _db()
    try:
        opts = [x["memo_id"] for x in con.execute(
            "SELECT memo_id FROM vote_options WHERE vote_id = ?",
            (r2.get_json()["id"],)).fetchall()]
    finally:
        con.close()
    assert opts == [arena["m2"]]


def test_demoted_creator_loses_management_of_his_own_vote(arena):
    """[GUEST-ROLES V2 · T1 — E8] LE test de ce lot. Ces routes ne regardaient que « qui l'a
    créé » : un invité rétrogradé gardait le droit de rouvrir, de RÉINITIALISER (effacer les
    voix de tous) et de supprimer ses anciens scrutins. La capacité est revérifiée à l'usage —
    la paternité ne survit pas à la perte du rôle."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]
    t, gt = arena["token"], arena["gtA"]
    assert c.post("/share/%s/votes/%d/close" % (t, vid), headers=H(gt)).status_code == 200

    _set_role(c, arena["idA"], arena["pid"], "commenter")     # rétrogradation

    assert c.post("/share/%s/votes/%d/reopen" % (t, vid), headers=H(gt)).status_code == 403
    assert c.post("/share/%s/votes/%d/reset" % (t, vid), headers=H(gt)).status_code == 403
    assert c.delete("/share/%s/votes/%d" % (t, vid), headers=H(gt)).status_code == 403
    assert c.put("/share/%s/votes/%d" % (t, vid), headers=H(gt),
                 json={"name": "X"}).status_code == 403

    con = _db()
    try:
        assert con.execute("SELECT 1 FROM votes WHERE id = ?", (vid,)).fetchone()
    finally:
        con.close()


def test_reopen_with_an_already_passed_deadline_400(arena):
    """Rouvrir en posant une échéance déjà dépassée n'a pas de sens : refus explicite."""
    c = arena["c"]
    _enable_vote(c, arena["pid"], vote_create="guests")
    _set_role(c, arena["idA"], arena["pid"], "editor")
    vid = _create(arena, arena["gtA"], name="Resto", memo_ids=[arena["m1"]]).get_json()["id"]
    t, gt = arena["token"], arena["gtA"]
    assert c.post("/share/%s/votes/%d/close" % (t, vid), headers=H(gt)).status_code == 200

    r = c.post("/share/%s/votes/%d/reopen" % (t, vid), headers=H(gt),
               json={"vote_deadline": PASSE})
    assert r.status_code == 400, r.data
    assert "dépassée" in r.get_json()["error"]


def test_vote_routes_unknown_token_404(arena):
    c = arena["c"]
    vid = _owner_named_vote(c, arena["pid"], "Resto", [arena["m1"]])
    assert c.post("/share/jeton-invente/votes", headers=H(arena["gtA"]),
                  json={"name": "X", "memo_ids": [arena["m1"]]}).status_code == 404
    assert c.post("/share/jeton-invente/votes/%d/close" % vid,
                  headers=H(arena["gtA"])).status_code == 404
    assert c.delete("/share/jeton-invente/votes/%d" % vid,
                    headers=H(arena["gtA"])).status_code == 404
