"""
Batterie d'INVARIANTS — garde-fous non négociables. Un rouge ici = pas de deploy.

Ces tests n'encodent pas « ce que fait le code », mais ce qu'il ne doit **jamais** cesser de
faire : le format d'export figé, l'import qui n'avale ni ne duplique rien. Ils protègent un
existant qu'on ne réécrit pas (doctrine hybride, §10 du brief).
"""
import pytest

pytestmark = pytest.mark.invariant


def _mk_project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _mk_memo(c, pid, content, uid=None):
    payload = {"content": content, "project_id": pid}
    if uid:
        payload["uid"] = uid
    r = c.post("/api/memos", json=payload)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _memos(c):
    # /api/export ne renvoie que les mémos non supprimés → parfait pour mesurer la perte.
    r = c.get("/api/export")
    assert r.status_code == 200, r.data
    return sorted(m.get("content", "") for m in r.get_json().get("memos", []))


# --- Format d'export figé v27 --------------------------------------------

def test_export_version_is_27(client):
    v = client.get("/api/version").get_json()
    assert v["export"] == 27, "Format d'export modifié sans bump de version majeure."


def test_export_has_stable_top_level_keys(client):
    exp = client.get("/api/export").get_json()
    for key in ("links", "memos", "categories", "projects"):
        assert key in exp, "Clé de haut niveau manquante dans l'export : %s" % key


# --- FLAGSHIP : l'import n'est JAMAIS destructif (round-trip sans perte) ---

def test_roundtrip_export_import_no_loss(new_base):
    """Export d'une base peuplée -> import dans une base VIERGE : aucun mémo perdu,
    aucun doublon. Encode directement le bug de perte de données à l'import."""
    a = new_base()
    pid = _mk_project(a, "Voyage Japon")
    _mk_memo(a, pid, "Reservation")       # doublon de contenu volontaire...
    _mk_memo(a, pid, "Reservation")       # ...uid serveur distinct -> DOIT survivre
    _mk_memo(a, pid, "Vol AF Tokyo")
    _mk_memo(a, pid, "Hotel Kyoto Sanjo")

    payload = a.get("/api/export").get_json()
    before = sorted(m["content"] for m in payload["memos"])
    assert before.count("Reservation") == 2

    b = new_base()                        # base vierge = le "fichier importé ailleurs"
    assert b.get("/api/export").get_json()["memos"] == []
    assert b.post("/api/import", json=payload).status_code == 200

    after = _memos(b)
    assert after == before, (
        "Round-trip export->import a perdu ou dupliqué des memos.\n"
        "avant=%r\napres=%r" % (before, after)
    )
    assert after.count("Reservation") == 2, (
        "Deux memos meme contenu / uid distinct : l'un a ete avale (regression "
        "du bug de dedup par contenu)."
    )


# --- Réimport idempotent (rejouer le même fichier n'ajoute rien) ----------

def test_reimport_same_file_is_idempotent(client):
    pid = _mk_project(client, "Idempotence")
    _mk_memo(client, pid, "A")
    _mk_memo(client, pid, "B")
    payload = client.get("/api/export").get_json()
    before = _memos(client)
    assert client.post("/api/import", json=payload).status_code == 200
    assert _memos(client) == before, "Reimport a l'identique a cree des doublons."


# --- v1 toujours importable (invariant 1) — squelette à compléter ---------

@pytest.mark.skip(reason="TODO CC : charger un fixture export v1 minimal et l'importer")
def test_v1_export_still_importable(client):
    import json, os
    p = os.path.join(os.path.dirname(__file__), "fixtures", "export_v1_min.json")
    with open(p, encoding="utf-8") as f:
        payload = json.load(f)
    assert client.post("/api/import", json=payload).status_code == 200
    assert len(_memos(client)) >= 1


# --- Cascades sans orphelin (invariant à écrire quand on attaquera le lot) -

@pytest.mark.skip(reason="TODO CC : DELETE /api/shares/<id> doit purger share_guests "
                         "(+ guest_roles, role_requests, admin_actions) — à écrire en "
                         "rouge-vert lors du prochain lot partages")
def test_delete_share_leaves_no_orphan_guest(client):
    raise NotImplementedError
