"""
Import — invariants 1, 2 et 3 : compat ascendante, non-destruction, uid stable.

La promesse du projet est qu'une sauvegarde reste restaurable *pour toujours* : un export v1 de
2024 doit s'importer dans la version d'aujourd'hui. Et un import n'efface jamais rien — il ajoute,
met à jour si plus récent, enrichit les vides. Ces deux règles sont ce qui permet d'oser importer.
"""
import uuid

import pytest

pytestmark = pytest.mark.invariant


def _memos(c):
    r = c.get("/api/export")
    assert r.status_code == 200, r.data
    return sorted(m.get("content", "") for m in r.get_json().get("memos", []))


def _by_uid(c, uid):
    for m in c.get("/api/export").get_json().get("memos", []):
        if m.get("uid") == uid:
            return m
    return None


# --- Invariant 1 : les vieux formats restent importables ------------------

def test_import_v1_list_of_strings(client):
    """v1 : `memos` est une liste de CHAÎNES, sans uid ni aucun champ. Doit passer sans 500.

    (Le squelette `test_v1_export_still_importable` attend un fixture tiré d'un *vrai* vieux
    export ; celui-ci couvre déjà la forme minimale, qui est ce qui casse en premier.)"""
    r = client.post("/api/import", json={"version": 1, "memos": ["Note de 2024", "Autre note"]})
    assert r.status_code == 200, r.data
    after = _memos(client)
    assert "Note de 2024" in after and "Autre note" in after


def test_import_v1_is_deduplicated_by_content(client):
    """Sans uid, le contenu est la seule identité disponible : l'anti-doublon doit tenir."""
    payload = {"version": 1, "memos": ["Doublon legacy"]}
    assert client.post("/api/import", json=payload).status_code == 200
    n = len(_memos(client))
    assert client.post("/api/import", json=payload).status_code == 200
    assert len(_memos(client)) == n, "Un import v1 rejoué a créé un doublon."


def test_import_tolerates_unknown_future_keys(client):
    """Un champ inconnu ne fait pas tomber l'import — on ignore, on ne rejette pas."""
    r = client.post("/api/import", json={
        "version": 99,
        "memos": [{"uid": str(uuid.uuid4()), "content": "Venu du futur",
                   "champ_invente": {"quoi": "que ce soit"}}],
    })
    assert r.status_code == 200, r.data
    assert "Venu du futur" in _memos(client)


# --- Invariant 2 : l'import n'est jamais destructif -----------------------

def test_import_does_not_erase_a_filled_field_with_an_empty_one(client):
    """Un titre présent en base ne doit pas être effacé par un import qui n'en a pas."""
    uid = str(uuid.uuid4())
    assert client.post("/api/import", json={"version": 27, "memos": [
        {"uid": uid, "content": "Avec titre", "title": "Mon titre",
         "updated_at": "2026-01-01T10:00:00+00:00"},
    ]}).status_code == 200
    assert (_by_uid(client, uid) or {}).get("title") == "Mon titre"

    # Même uid, plus ANCIEN, sans titre : ne doit rien écraser.
    assert client.post("/api/import", json={"version": 27, "memos": [
        {"uid": uid, "content": "Avec titre", "title": "",
         "updated_at": "2025-01-01T10:00:00+00:00"},
    ]}).status_code == 200
    assert (_by_uid(client, uid) or {}).get("title") == "Mon titre", (
        "Un import plus ANCIEN a écrasé un champ rempli (invariant 2)."
    )


def test_import_never_deletes_local_memos(client):
    """Importer un fichier partiel n'emporte pas ce qui n'y figure pas."""
    client.post("/api/memos", json={"content": "Bien à moi"})
    assert client.post("/api/import", json={"version": 27, "memos": [
        {"uid": str(uuid.uuid4()), "content": "Nouveau venu"},
    ]}).status_code == 200
    after = _memos(client)
    assert "Bien à moi" in after, "L'import a supprimé un mémo local absent du fichier."
    assert "Nouveau venu" in after


# --- Invariant 3 : l'uid suit la ligne, on ne le régénère jamais ----------

def test_uid_is_stable_across_reimport(client):
    uid = str(uuid.uuid4())
    payload = {"version": 27, "memos": [{"uid": uid, "content": "Identité stable"}]}
    assert client.post("/api/import", json=payload).status_code == 200
    assert _by_uid(client, uid) is not None
    assert client.post("/api/import", json=payload).status_code == 200
    same = [m for m in client.get("/api/export").get_json()["memos"] if m.get("uid") == uid]
    assert len(same) == 1, "Le ré-import a dupliqué la ligne au lieu de la reconnaître par uid."


def test_memo_created_by_api_gets_a_uid(client):
    m = client.post("/api/memos", json={"content": "Doit avoir un uid"}).get_json()
    assert m.get("uid"), "Un mémo créé sans uid n'en a pas reçu : il ne survivra pas à un export."
