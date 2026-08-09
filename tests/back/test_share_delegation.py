"""[TESTS-PORT] Délégation invitée sous /share/* — invariant 5.

Tests de CARACTÉRISATION : le code est en prod et éprouvé, on fige le comportement
CORRECT ACTUEL des trois routes de délégation, restées à nu au rapport de couverture
(`share_set_guest_role`, `share_decide_role_request`, `share_admin_view`) — leurs ~36
tests précédents vivaient hors dépôt et n'existent plus.

Ce ne sont donc pas des tests « rouge d'abord ». Corollaire, écrit ici pour la prochaine
personne qui les verra tomber : **un rouge dans ce fichier est un bug dans une route de
sécurité**, pas une assertion à réaligner sur le nouveau comportement.

Ordre des gardes tel qu'il est dans `app.py`, et il compte (on le fige, pas seulement les
codes) : partage inconnu → 404 · invité non approuvé → 403 · `project_id` illisible → 400 ·
hors périmètre du partage → 400 · pas `administrer` sur le dossier VISÉ → 403 · soi-même →
403 · cible d'un autre lien → 404.
"""
import json
import sqlite3

import pytest

pytestmark = pytest.mark.invariant


H = lambda gt: {"X-Guest-Token": gt}          # en-tête invité


# ─────────────────────────────────────────────────────────────── montage ────

def _db():
    """Connexion directe à la base TEMP du test (le conftest y a pointé `app.DB_PATH`).

    Plusieurs contrats ne passent par aucune route : l'id d'un invité (le `register` ne le
    renvoie pas), l'id d'une demande, la trace au journal `admin_actions`. On les lit ici.
    """
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _project(c, name, parent_id=None):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    pid = r.get_json()["id"]
    if parent_id is not None:
        # POST crée toujours à la racine ; c'est le PUT qui déplace (et revalide).
        assert c.put("/api/projects/%d" % pid,
                     json={"parent_id": parent_id}).status_code == 200
    return pid


def _share_project(c, pid):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()                       # {token, pin, ...}


def _register(c, token, pin, email, name="Invite"):
    r = c.post("/share/%s/register" % token,
               json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _guest_id(email, share_id=None):
    con = _db()
    try:
        if share_id is None:
            row = con.execute(
                "SELECT id FROM share_guests WHERE email = ? ORDER BY id DESC LIMIT 1",
                (email.lower(),)).fetchone()
        else:
            row = con.execute(
                "SELECT id FROM share_guests WHERE email = ? AND share_id = ?",
                (email.lower(), share_id)).fetchone()
        return row["id"] if row else None
    finally:
        con.close()


def _make_admin(c, guest_id, project_id):
    """Élève un invité en Administrateur sur un dossier (route owner, derrière Authelia en
    prod, donc sans auth ici)."""
    r = c.put("/api/guests/%d/role" % guest_id,
              json={"project_id": project_id, "role": "admin"})
    assert r.status_code in (200, 204), r.data


def _role_row(guest_id, project_id):
    con = _db()
    try:
        return con.execute(
            "SELECT * FROM guest_roles WHERE guest_id = ? AND project_id = ?",
            (guest_id, project_id)).fetchone()
    finally:
        con.close()


def _request_id(guest_id):
    con = _db()
    try:
        row = con.execute(
            "SELECT id FROM role_requests WHERE guest_id = ? ORDER BY id DESC LIMIT 1",
            (guest_id,)).fetchone()
        return row["id"] if row else None
    finally:
        con.close()


def _request_status(req_id):
    con = _db()
    try:
        row = con.execute("SELECT status FROM role_requests WHERE id = ?", (req_id,)).fetchone()
        return row["status"] if row else None
    finally:
        con.close()


@pytest.fixture
def world(client):
    """Le décor de tous les tests : un partage de DOSSIER avec un sous-arbre et trois invités.

        R (partagé)          ← A est Administrateur ici (sauf mention contraire)
        ├── C1
        └── C2
        X (hors partage)

    A = l'Admin invité, B = celui qu'on nomme / qui demande, D = invité d'un AUTRE lien.
    """
    c = client
    R = _project(c, "Racine partagee")
    C1 = _project(c, "Sous-dossier 1", parent_id=R)
    C2 = _project(c, "Sous-dossier 2", parent_id=R)
    X = _project(c, "Hors partage")

    sh = _share_project(c, R)
    ta, pin = sh["token"], sh["pin"]
    gtA = _register(c, ta, pin, "a@ex.com", "Alice")
    gtB = _register(c, ta, pin, "b@ex.com", "Bob")
    idA, idB = _guest_id("a@ex.com", sh["id"]), _guest_id("b@ex.com", sh["id"])

    P2 = _project(c, "Autre projet")
    sh2 = _share_project(c, P2)
    gtD = _register(c, sh2["token"], sh2["pin"], "d@ex.com", "Dan")
    idD = _guest_id("d@ex.com", sh2["id"])

    return {
        "c": c, "R": R, "C1": C1, "C2": C2, "X": X,
        "token": ta, "share_id": sh["id"],
        "gtA": gtA, "gtB": gtB, "idA": idA, "idB": idB,
        "token2": sh2["token"], "gtD": gtD, "idD": idD, "P2": P2,
    }


def _put_role(w, gt, target_id, **payload):
    return w["c"].put("/share/%s/guests/%d/role" % (w["token"], target_id),
                      json=payload, headers=(H(gt) if gt else {}))


# ══════════════════ A. share_set_guest_role — nomination par un Admin ══════════════════

def test_anonymous_cannot_nominate(world):
    """Sans jeton invité, la route ne s'ouvre pas — même avec un lien valide en main."""
    r = _put_role(world, None, world["idB"], project_id=world["R"], role="moderator")
    assert r.status_code == 403, r.data
    assert r.get_json()["status"] == "anonymous"
    assert _role_row(world["idB"], world["R"]) is None


def test_approved_non_admin_cannot_nominate(world):
    """Approuvé ≠ Administrateur : entrer par le lien ne donne pas le droit d'élever autrui."""
    r = _put_role(world, world["gtB"], world["idA"], project_id=world["R"], role="editor")
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"
    assert _role_row(world["idA"], world["R"]) is None


def test_nominate_out_of_scope_project_400(world):
    """Un dossier hors du partage est refusé AVANT même la question du rôle : ce serait
    fabriquer un accès à un endroit que le lien n'ouvre pas."""
    _make_admin(world["c"], world["idA"], world["R"])
    r = _put_role(world, world["gtA"], world["idB"], project_id=world["X"], role="editor")
    assert r.status_code == 400, r.data
    assert "périmètre" in r.get_json()["error"]
    assert _role_row(world["idB"], world["X"]) is None


def test_invalid_project_id_400(world):
    """`project_id` illisible → 400 explicite, jamais un 500."""
    _make_admin(world["c"], world["idA"], world["R"])
    r = _put_role(world, world["gtA"], world["idB"], project_id="pas-un-entier", role="editor")
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "project_id invalide"


def test_cannot_nominate_self(world):
    """Un Admin élève les autres, jamais lui-même (sinon la borne du sous-arbre ne tient plus :
    il s'accorderait la racine)."""
    _make_admin(world["c"], world["idA"], world["C1"])
    r = _put_role(world, world["gtA"], world["idA"], project_id=world["C1"], role="admin")
    assert r.status_code == 403, r.data
    assert "propre rôle" in r.get_json()["error"]


def test_cannot_nominate_guest_of_other_link(world):
    """La cible doit être un invité DU MÊME lien — on ne redistribue pas les droits d'autrui.
    404 (et pas 403) : l'existence d'un invité d'un autre partage n'est pas confirmée."""
    _make_admin(world["c"], world["idA"], world["R"])
    r = _put_role(world, world["gtA"], world["idD"], project_id=world["R"], role="editor")
    assert r.status_code == 404, r.data
    assert _role_row(world["idD"], world["R"]) is None


def test_nominate_on_unknown_token_404(world):
    """Un jeton inventé ne divulgue rien : 404 avant toute question d'identité."""
    r = world["c"].put("/share/jeton-invente/guests/%d/role" % world["idB"],
                       json={"project_id": world["R"], "role": "editor"},
                       headers=H(world["gtA"]))
    assert r.status_code == 404, r.data
    assert _role_row(world["idB"], world["R"]) is None


def test_admin_nominates_moderator_ok(world):
    """Le cas nominal, vérifié jusqu'à l'EFFET : la nomination se voit dans « Gérer les accès »."""
    _make_admin(world["c"], world["idA"], world["R"])
    r = _put_role(world, world["gtA"], world["idB"], project_id=world["R"], role="moderator")
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["guest_id"] == world["idB"]
    assert body["project_id"] == world["R"]
    assert body["role"] == "moderator"
    assert body["source"] == "override"

    view = world["c"].get("/share/%s/admin" % world["token"], headers=H(world["gtA"]))
    assert view.status_code == 200, view.data
    rows = {g["id"]: g for g in view.get_json()["guests"]}
    assert rows[world["idB"]]["role_effective"] == "moderator"
    assert rows[world["idB"]]["role_source"] == "override"


def test_nominated_act_is_journaled_and_revocable(world):
    """Un délégué n'a AUCUN chemin d'écriture qui échappe au journal : sans `prev_role`,
    « révoquer d'un clic » ne saurait pas quoi restaurer."""
    _make_admin(world["c"], world["idA"], world["R"])
    assert _put_role(world, world["gtA"], world["idB"],
                     project_id=world["R"], role="moderator").status_code == 200

    con = _db()
    try:
        acts = con.execute(
            "SELECT * FROM admin_actions WHERE target_guest_id = ? ORDER BY id DESC",
            (world["idB"],)).fetchall()
    finally:
        con.close()
    assert len(acts) == 1, "la nomination d'un délégué doit laisser une trace, et une seule"
    act = acts[0]
    assert act["action"] == "set_role"
    assert act["role"] == "moderator"
    assert act["actor_guest_id"] == world["idA"]
    assert "a@ex.com" in (act["actor"] or "")
    assert act["project_id"] == world["R"]
    assert act["prev_role"] == ""     # état d'AVANT : ce que la révocation restaurera
    assert act["had_row"] == 0


def test_owner_own_acts_are_not_journaled(world):
    """L'owner est le point de référence, pas un délégué à surveiller : ses propres actes
    n'encombrent pas le journal des actes d'administration."""
    _make_admin(world["c"], world["idA"], world["R"])
    con = _db()
    try:
        n = con.execute("SELECT COUNT(*) AS n FROM admin_actions").fetchone()["n"]
    finally:
        con.close()
    assert n == 0


def test_role_capped_at_admin(world):
    """« Délègue jusqu'à Administrateur, comme eux » : un rôle non assignable est NEUTRALISÉ
    par `_clean_role` (chaîne vide), pas accordé au rabais ni promu."""
    _make_admin(world["c"], world["idA"], world["R"])

    r = _put_role(world, world["gtA"], world["idB"], project_id=world["R"], role="owner")
    assert r.status_code == 200, r.data
    assert r.get_json()["role"] == ""            # « owner » n'existe pas comme rôle attribuable
    assert r.get_json()["source"] == "link"      # aucune surcharge posée
    assert _role_row(world["idB"], world["R"]) is None

    # …et le plafond légitime, lui, passe : `admin` est bien assignable.
    r2 = _put_role(world, world["gtA"], world["idB"], project_id=world["R"], role="admin")
    assert r2.status_code == 200, r2.data
    assert r2.get_json()["role"] == "admin"


# ══════════════ B. share_decide_role_request — accorder / écarter ══════════════

def _ask(w, gt, role="editor"):
    """B demande un rôle : la demande se pose sur le dossier RACINE du partage."""
    r = w["c"].post("/share/%s/role-request" % w["token"], json={"role": role}, headers=H(gt))
    assert r.status_code in (200, 201), r.data
    return r


def test_decide_requires_valid_decision(world):
    """La décision est validée AVANT toute autre garde (y compris l'identité) : une valeur
    hors `grant|ignore` est un 400, jamais une décision par défaut."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])
    for payload in ({}, {"decision": ""}, {"decision": "maybe"}):
        r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                            json=payload, headers=H(world["gtA"]))
        assert r.status_code == 400, (payload, r.data)
    assert _request_status(req) == "pending"


def test_anonymous_cannot_decide(world):
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])
    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "grant"})
    assert r.status_code == 403, r.data
    assert _request_status(req) == "pending"
    assert _role_row(world["idB"], world["R"]) is None


def test_decide_unknown_or_settled_request_404(world):
    """Une demande inconnue ET une demande déjà tranchée répondent pareil : la file ne
    contient que du `pending`, on ne rejoue pas une décision."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])

    ghost = world["c"].post("/share/%s/role-request/999999" % world["token"],
                            json={"decision": "grant"}, headers=H(world["gtA"]))
    assert ghost.status_code == 404, ghost.data

    ok = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                         json={"decision": "grant"}, headers=H(world["gtA"]))
    assert ok.status_code == 200, ok.data
    again = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                            json={"decision": "grant"}, headers=H(world["gtA"]))
    assert again.status_code == 404, again.data


def test_decide_on_unknown_token_404(world):
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])
    r = world["c"].post("/share/jeton-invente/role-request/%d" % req,
                        json={"decision": "grant"}, headers=H(world["gtA"]))
    assert r.status_code == 404, r.data
    assert _request_status(req) == "pending"


def test_cannot_decide_request_of_other_link(world):
    """La demande d'un invité d'un AUTRE lien ne se tranche pas depuis ce partage, même en
    étant Administrateur ici — sinon un Admin arbitrerait chez le voisin."""
    _make_admin(world["c"], world["idA"], world["R"])
    assert world["c"].post("/share/%s/role-request" % world["token2"],
                           json={"role": "editor"},
                           headers=H(world["gtD"])).status_code in (200, 201)
    req = _request_id(world["idD"])

    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "grant"}, headers=H(world["gtA"]))
    assert r.status_code == 404, r.data
    assert _request_status(req) == "pending"
    assert _role_row(world["idD"], world["P2"]) is None


def test_cannot_decide_own_request(world):
    """On ne s'accorde pas soi-même ce qu'on a demandé — même en étant Administrateur."""
    _make_admin(world["c"], world["idB"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])
    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "grant"}, headers=H(world["gtB"]))
    assert r.status_code == 403, r.data
    assert "propre demande" in r.get_json()["error"]
    assert _request_status(req) == "pending"


def test_decide_request_out_of_admin_scope_403(world):
    """Admin d'un sous-dossier : la demande porte sur la RACINE, hors de son périmètre → 403.
    C'est la même borne que la nomination, résolue sur le dossier visé."""
    _make_admin(world["c"], world["idA"], world["C1"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])
    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "grant"}, headers=H(world["gtA"]))
    assert r.status_code == 403, r.data
    assert _request_status(req) == "pending"
    assert _role_row(world["idB"], world["R"]) is None


def test_grant_applies_role_and_marks_granted(world):
    """Accorder passe par la MÊME porte que la nomination manuelle : rôle posé, demande
    classée, et acte journalisé (donc révocable)."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"], role="editor")
    req = _request_id(world["idB"])

    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "grant"}, headers=H(world["gtA"]))
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["status"] == "granted"
    assert body["guest_id"] == world["idB"]
    assert body["project_id"] == world["R"]
    assert body["role"] == "editor"

    assert _request_status(req) == "granted"
    assert _role_row(world["idB"], world["R"])["role"] == "editor"

    con = _db()
    try:
        acts = con.execute("SELECT * FROM admin_actions WHERE target_guest_id = ?",
                           (world["idB"],)).fetchall()
    finally:
        con.close()
    assert len(acts) == 1 and acts[0]["role"] == "editor", \
        "accorder DOIT journaliser comme nommer, sinon la moitié des actes d'un délégué " \
        "échapperait à la révocation"


def test_grant_preserves_fine_grained_caps(world):
    """Le point délicat : `_apply_guest_role` réécrit la LIGNE ENTIÈRE. Accorder une demande
    ne doit pas balayer les ajustements fins posés par l'owner — accorder n'est pas remettre
    à zéro."""
    _make_admin(world["c"], world["idA"], world["R"])
    # L'owner pose d'abord un ajustement fin sur (B, R), sans rôle.
    assert world["c"].put("/api/guests/%d/role" % world["idB"],
                          json={"project_id": world["R"], "role": "",
                                "caps_add": ["creer"], "caps_remove": ["voter"]}
                          ).status_code == 200
    _ask(world, world["gtB"], role="editor")
    req = _request_id(world["idB"])

    assert world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                           json={"decision": "grant"},
                           headers=H(world["gtA"])).status_code == 200

    row = _role_row(world["idB"], world["R"])
    assert row["role"] == "editor"
    assert json.loads(row["caps_add"]) == ["creer"], "l'ajout fin de l'owner a été effacé"
    assert json.loads(row["caps_remove"]) == ["voter"], "le retrait fin de l'owner a été effacé"


def test_ignore_writes_no_role(world):
    """Écarter sort la demande de la file sans rien accorder — et sans signifier un refus."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    req = _request_id(world["idB"])

    r = world["c"].post("/share/%s/role-request/%d" % (world["token"], req),
                        json={"decision": "ignore"}, headers=H(world["gtA"]))
    assert r.status_code == 200, r.data
    assert r.get_json()["status"] == "refused"
    assert r.get_json()["role"] == ""
    assert _request_status(req) == "refused"
    assert _role_row(world["idB"], world["R"]) is None

    view = world["c"].get("/share/%s/admin" % world["token"], headers=H(world["gtA"]))
    assert [q["id"] for q in view.get_json()["requests"]] == []


# ═══════════ C. share_admin_view — ce qu'un Admin invité voit (et ne voit pas) ═══════════

def test_admin_view_anonymous_403(world):
    r = world["c"].get("/share/%s/admin" % world["token"])
    assert r.status_code == 403, r.data


def test_admin_view_non_admin_403(world):
    """Un invité approuvé sans aucun dossier administré n'ouvre pas le panneau : le bouton
    « Gérer les accès » n'est pas seulement caché côté UI, la route refuse."""
    r = world["c"].get("/share/%s/admin" % world["token"], headers=H(world["gtB"]))
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"


def test_admin_view_unknown_token_404(world):
    r = world["c"].get("/share/jeton-invente/admin", headers=H(world["gtA"]))
    assert r.status_code == 404, r.data


def test_admin_view_folders_scoped_to_subtree(world):
    """Admin d'un sous-dossier : `folders` s'arrête à SON sous-arbre. Le panneau n'est pas
    la page Partages de l'owner en petit."""
    C11 = _project(world["c"], "Petit-fils", parent_id=world["C1"])
    _make_admin(world["c"], world["idA"], world["C1"])

    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    ids = {f["id"] for f in body["folders"]}
    assert ids == {world["C1"], C11}, ids
    assert world["R"] not in ids and world["C2"] not in ids
    assert body["root_id"] == world["C1"]
    assert body["me"]["id"] == world["idA"]
    assert set(body["roles"]) == {"viewer", "commenter", "contributor", "editor",
                                  "moderator", "admin"}


def test_admin_view_excludes_self_and_owner(world):
    """Soi-même absent de la liste (on ne se nomme pas), et l'owner n'y figure JAMAIS —
    il n'est pas un `share_guest`, aucune ligne ne le désigne."""
    _make_admin(world["c"], world["idA"], world["R"])
    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    ids = [g["id"] for g in body["guests"]]
    assert world["idA"] not in ids
    assert ids == [world["idB"]]        # seul B, donc ni owner ni invité d'un autre lien


def test_admin_view_excludes_guests_of_other_links(world):
    """Le panneau est borné au LIEN : l'invité d'un autre partage n'y apparaît pas, même si
    l'Admin administre un dossier plus large."""
    _make_admin(world["c"], world["idA"], world["R"])
    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    assert world["idD"] not in [g["id"] for g in body["guests"]]


def test_admin_view_hides_email(world):
    """L'e-mail reste owner-only : le nom suffit à nommer quelqu'un (doctrine des votants de
    [COMMENT-REACTIONS])."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtB"])
    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()

    assert body["guests"], "il faut au moins une rangée pour que le test prouve quelque chose"
    assert body["requests"], "idem pour les demandes"
    for row in body["guests"] + body["requests"]:
        assert "email" not in row, row
    assert "@" not in json.dumps(body, ensure_ascii=False)


def test_admin_view_does_not_leak_neighbor_folder_role(world):
    """Admin de C1 : le rôle qu'il lit sur quelqu'un est celui de SON périmètre. Une surcharge
    posée sur le dossier voisin C2 ne doit pas transparaître — sinon le panneau raconterait
    l'état d'une zone que cet Admin n'administre pas."""
    _make_admin(world["c"], world["idA"], world["C1"])
    assert world["c"].put("/api/guests/%d/role" % world["idB"],
                          json={"project_id": world["C2"], "role": "editor"}).status_code == 200

    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    row = [g for g in body["guests"] if g["id"] == world["idB"]][0]
    assert row["project_id"] == world["C1"], "le rôle doit être lu sur un dossier administré"
    assert row["role_effective"] != "editor"
    assert row["role_source"] == "link"


def test_admin_view_reads_role_on_administered_folder(world):
    """Le pendant du précédent : une surcharge posée DANS son périmètre, elle, se voit — sans
    quoi la rangée dirait « Lecteur » à quelqu'un qu'on vient de nommer Éditeur."""
    _make_admin(world["c"], world["idA"], world["C1"])
    assert world["c"].put("/api/guests/%d/role" % world["idB"],
                          json={"project_id": world["C1"], "role": "editor"}).status_code == 200

    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    row = [g for g in body["guests"] if g["id"] == world["idB"]][0]
    assert row["project_id"] == world["C1"]
    assert row["role_effective"] == "editor"
    assert row["role_source"] == "override"


def test_admin_view_requests_scoped(world):
    """Une demande portant sur un dossier hors du périmètre ne remonte pas — un Admin de
    sous-dossier ne tranche pas ce qu'il ne peut pas appliquer."""
    _make_admin(world["c"], world["idA"], world["C1"])
    _ask(world, world["gtB"])       # la demande se pose sur R, la racine du partage

    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    assert body["requests"] == []

    # …et elle remonte dès que le périmètre l'englobe.
    _make_admin(world["c"], world["idA"], world["R"])
    body2 = world["c"].get("/share/%s/admin" % world["token"],
                           headers=H(world["gtA"])).get_json()
    assert [q["guest_id"] for q in body2["requests"]] == [world["idB"]]


def test_admin_view_on_memo_share_scopes_to_carrier_folder(world):
    """Partage de MÉMO : il n'y a pas de sous-arbre à parcourir, le périmètre est le dossier
    PORTEUR du mémo — et il faut y être Admin, sans quoi la route refuse comme ailleurs."""
    c = world["c"]
    m = c.post("/api/memos", json={"content": "Mémo partagé", "project_id": world["C1"]})
    assert m.status_code in (200, 201), m.data
    sh = c.post("/api/shares", json={"kind": "memo", "target_id": m.get_json()["id"]})
    assert sh.status_code in (200, 201), sh.data
    sh = sh.get_json()
    gt = _register(c, sh["token"], sh["pin"], "e@ex.com", "Eve")
    ide = _guest_id("e@ex.com", sh["id"])

    # Approuvé mais pas Admin → même refus que sur un partage de dossier.
    assert c.get("/share/%s/admin" % sh["token"], headers=H(gt)).status_code == 403

    _make_admin(c, ide, world["C1"])
    body = c.get("/share/%s/admin" % sh["token"], headers=H(gt)).get_json()
    assert [f["id"] for f in body["folders"]] == [world["C1"]]
    assert body["root_id"] == world["C1"]


def test_admin_view_hides_own_request(world):
    """Sa propre demande ne remonte pas dans sa file : on ne se la tranche pas (403 côté
    écriture), autant ne pas la proposer."""
    _make_admin(world["c"], world["idA"], world["R"])
    _ask(world, world["gtA"])
    body = world["c"].get("/share/%s/admin" % world["token"],
                          headers=H(world["gtA"])).get_json()
    assert [q["guest_id"] for q in body["requests"]] == []
