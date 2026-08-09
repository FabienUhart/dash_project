"""
Surface publique invitée — invariant 5.

L'app n'a pas d'authentification : la sécurité vient du reverse proxy, SAUF sous `/share/*`, la
seule zone publique (bypass Authelia), protégée par le seul jeton. Deux règles y tiennent tout :
une route de partage n'expose **rien d'autre** que la ressource partagée, et **écrire** exige un
invité approuvé. Ces tests sont la ceinture de sécurité de cette zone.
"""
import pytest

pytestmark = pytest.mark.invariant


def _mk_project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _mk_memo(c, content, pid=None):
    payload = {"content": content}
    if pid:
        payload["project_id"] = pid
    r = c.post("/api/memos", json=payload)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _share(c, kind, target_id, **kw):
    body = {"kind": kind, "target_id": target_id}
    body.update(kw)
    r = c.post("/api/shares", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _share_contents(c, token, guest_token=None):
    h = {"X-Guest-Token": guest_token} if guest_token else {}
    r = c.get("/share/%s/data" % token, headers=h)
    assert r.status_code == 200, r.data
    return sorted(m.get("content", "") for m in r.get_json().get("memos", []))


# --- Le partage n'expose QUE sa cible -------------------------------------

def test_memo_share_exposes_only_that_memo(client):
    secret = _mk_memo(client, "Confidentiel — hors partage")
    shared = _mk_memo(client, "Partage volontairement")
    sh = _share(client, "memo", shared["id"])

    seen = _share_contents(client, sh["token"])
    assert "Partage volontairement" in seen
    assert "Confidentiel — hors partage" not in seen, (
        "FUITE : un partage de mémo expose un mémo qui n'est pas le sien (invariant 5)."
    )


def test_project_share_stops_at_its_subtree(client):
    inside = _mk_project(client, "Voyage partagé")
    outside = _mk_project(client, "Dossier privé")
    _mk_memo(client, "Dedans", inside)
    _mk_memo(client, "Dehors", outside)
    sh = _share(client, "project", inside)

    seen = _share_contents(client, sh["token"])
    assert "Dedans" in seen
    assert "Dehors" not in seen, "FUITE : un partage de dossier déborde sur un dossier voisin."


def test_trashed_memo_is_not_shared(client):
    """Invariant 7 × invariant 5 : ce qui est en corbeille sort aussi du périmètre partagé."""
    pid = _mk_project(client, "Avec corbeille")
    keep = _mk_memo(client, "Visible", pid)
    gone = _mk_memo(client, "Jeté", pid)
    client.delete("/api/memos/%d" % gone["id"])
    sh = _share(client, "project", pid)

    seen = _share_contents(client, sh["token"])
    assert "Visible" in seen
    assert "Jeté" not in seen, "Un mémo en corbeille reste visible des invités."
    assert keep


def test_invalid_token_is_404_not_a_leak(client):
    _mk_memo(client, "Rien à voir")
    r = client.get("/share/jeton-qui-nexiste-pas/data")
    assert r.status_code == 404, "Un jeton inconnu doit répondre 404, sans rien divulguer."
    assert b"Rien" not in r.data


# --- Écrire exige un invité approuvé --------------------------------------

def test_anonymous_cannot_write_through_share(client):
    pid = _mk_project(client, "Ecriture gardee")
    sh = _share(client, "project", pid, can_edit=True)

    r = client.post("/share/%s/memos" % sh["token"], json={"content": "Ecrit sans droit"})
    assert r.status_code in (401, 403), (
        "Un anonyme a pu écrire via /share/* : le contrôle d'invité approuvé a sauté."
    )
    assert "Ecrit sans droit" not in _share_contents(client, sh["token"])


def test_read_only_link_refuses_writes(client):
    """Un lien en lecture reste en lecture, même pour un invité approuvé."""
    pid = _mk_project(client, "Lecture seule")
    sh = _share(client, "project", pid, can_edit=False, role="viewer")

    reg = client.post("/share/%s/register" % sh["token"],
                      json={"name": "Curieux", "email": "curieux@test.local", "pin": sh["pin"]})
    assert reg.status_code in (200, 201), reg.data
    gt = (reg.get_json() or {}).get("guest_token", "")
    assert gt, "L'inscription n'a pas rendu de jeton invité."

    r = client.post("/share/%s/memos" % sh["token"],
                    headers={"X-Guest-Token": gt}, json={"content": "Tentative"})
    assert r.status_code in (401, 403), "Un lien lecture seule a accepté une écriture."
