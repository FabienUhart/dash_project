"""
Corbeille — invariant 7 : supprimer un mémo ne fait JAMAIS de `DELETE` SQL.

C'est une règle de sûreté des données, pas un détail d'implémentation : la ligne survit avec
`deleted_at`, disparaît des vues et de l'export, et ne s'efface pour de bon que par la corbeille
(ou la purge auto après `BACKUP_KEEP_DAYS`). Un régression ici perd des données sans bruit.
"""
import pytest

pytestmark = pytest.mark.invariant


def _mk_memo(c, content):
    r = c.post("/api/memos", json={"content": content})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _contents(c, url="/api/memos"):
    r = c.get(url)
    assert r.status_code == 200, r.data
    data = r.get_json()
    rows = data if isinstance(data, list) else data.get("memos", [])
    return sorted(m.get("content", "") for m in rows)


def test_delete_memo_is_soft(client):
    """Le mémo quitte les vues mais reste en base — c'est la corbeille, pas la trappe."""
    m = _mk_memo(client, "A supprimer")
    assert client.delete("/api/memos/%d" % m["id"]).status_code in (200, 204)

    assert "A supprimer" not in _contents(client), "Le mémo est encore listé après suppression."
    assert "A supprimer" not in _contents(client, "/api/export"), (
        "Un mémo en corbeille ne doit PAS partir dans l'export (invariant 7)."
    )
    assert "A supprimer" in _contents(client, "/api/trash"), (
        "Le mémo supprimé est introuvable dans la corbeille : suppression DURE, données perdues."
    )


def test_restore_from_trash_brings_it_back(client):
    m = _mk_memo(client, "Repechage")
    client.delete("/api/memos/%d" % m["id"])
    r = client.post("/api/trash/%d/restore" % m["id"])
    assert r.status_code in (200, 204), r.data
    assert "Repechage" in _contents(client), "La restauration n'a pas remis le mémo dans la liste."
    assert "Repechage" not in _contents(client, "/api/trash")


def test_purge_from_trash_is_definitive(client):
    m = _mk_memo(client, "Adieu")
    client.delete("/api/memos/%d" % m["id"])
    assert client.delete("/api/trash/%d" % m["id"]).status_code in (200, 204)
    assert "Adieu" not in _contents(client, "/api/trash")
    assert "Adieu" not in _contents(client)
    # Purgé pour de bon : plus rien à restaurer.
    assert client.post("/api/trash/%d/restore" % m["id"]).status_code == 404


def test_trashed_memo_absent_from_export_roundtrip(client):
    """Un mémo en corbeille ne doit pas ressusciter par un aller-retour d'export."""
    keep = _mk_memo(client, "Je reste")
    gone = _mk_memo(client, "Je pars")
    client.delete("/api/memos/%d" % gone["id"])

    payload = client.get("/api/export").get_json()
    exported = sorted(m.get("content", "") for m in payload.get("memos", []))
    assert "Je reste" in exported
    assert "Je pars" not in exported, "Un mémo en corbeille a fui dans l'export."
    assert keep and gone
