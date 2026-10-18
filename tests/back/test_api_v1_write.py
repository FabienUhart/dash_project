"""[DASH-API] § 3 — écriture : mêmes validations que l'UI, même code d'insertion, `source` posée.

Brief : `docs/briefs/DASH-API.md` § 3 et § 1.5. Ce que ces tests PROTÈGENT :
- `content_text` devient des `<p>` ÉCHAPPÉS (jamais de HTML brut) ; `content` passe par un
  nettoyeur (script/on*/javascript: retirés) ;
- `source` = la source du jeton, posée à la création ET à la dernière modification par API ; un
  mémo créé dans l'UI reste `''` ; l'export v30 porte `source` brut ; un export sans `source`
  (v1→v29) s'importe en `''` (invariant 2) ;
- les sous-routes (append, move, done/undone, subtasks, urls, comments) font ce qu'elles disent
  et refusent l'invalide comme l'UI (400/404/409) ;
- DELETE → corbeille (jamais de DELETE SQL, invariant 7) → restore ;
- dossiers : création, déplacement, 409 si le nom est pris chez le même parent ;
- l'API ne touche jamais aux partages/invités/réglages/import (routes absentes de /api/v1).
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def api(client):
    t = client.post("/api/tokens", json={"name": "scribe", "scopes": "read,write", "source": "claude-code"}).get_json()
    h = {"Authorization": "Bearer " + t["token"]}

    class _Api:
        token = t

        def get(self, path, **kw):
            return client.get(path, headers=h, **kw)

        def post(self, path, **kw):
            return client.post(path, headers=h, **kw)

        def patch(self, path, **kw):
            return client.patch(path, headers=h, **kw)

        def delete(self, path, **kw):
            return client.delete(path, headers=h, **kw)

    return _Api()


def _ui_memo(client, **kw):
    r = client.post("/api/memos", json=kw)
    assert r.status_code == 201, r.data
    return r.get_json()


def _ui_memo_by_id(client, mid):
    return [m for m in client.get("/api/memos").get_json() if m["id"] == mid][0]


# ------------------------------------------------------------------ create


def test_create_content_text_devient_des_paragraphes_echappes(client, api):
    r = api.post("/api/v1/memos", json={"title": "Plan", "content_text": "Ligne 1 <b>pas du html</b>\n\nLigne 2 & fin"})
    assert r.status_code == 201, r.data
    m = r.get_json()
    assert m["content"] == "<p>Ligne 1 &lt;b&gt;pas du html&lt;/b&gt;</p><p>Ligne 2 &amp; fin</p>"
    assert m["content_text"] == "Ligne 1 <b>pas du html</b> Ligne 2 & fin"
    assert m["source"] == "claude-code"
    assert _ui_memo_by_id(client, m["id"])["source"] == "claude-code"


def test_create_content_html_nettoye(client, api):
    sale = '<p onclick="x()">ok <a href="javascript:alert(1)">lien</a> <a href="https://ok.test">bon</a></p><script>evil()</script><p>fin</p>'
    r = api.post("/api/v1/memos", json={"content": sale})
    assert r.status_code == 201, r.data
    c = r.get_json()["content"]
    assert "<script" not in c and "evil" not in c
    assert "onclick" not in c
    assert "javascript:" not in c
    assert 'href="https://ok.test"' in c
    assert "<p>fin</p>" in c and "ok" in c


def test_create_valide_comme_l_ui(client, api):
    assert api.post("/api/v1/memos", json={}).status_code == 400, "titre ou contenu requis"
    assert api.post("/api/v1/memos", json={"title": "x", "due_end": "2026-10-20"}).status_code == 400, "fin sans début"
    assert api.post("/api/v1/memos", json={"title": "x", "due_date": "2026-10-20", "due_end": "2026-10-10"}).status_code == 400
    assert api.post("/api/v1/memos", json={"title": "x", "folder_id": 999999}).status_code == 404, "dossier inconnu"
    r = api.post("/api/v1/memos", json={"title": "x", "due_date": "pas-une-date"})
    assert r.status_code == 400
    ok = api.post("/api/v1/memos", json={"title": "x", "due_date": "2026-10-20", "due_time": "09:30"})
    assert ok.status_code == 201 and ok.get_json()["due_time"] == "09:30"


def test_create_champs_riches(client, api):
    f = client.post("/api/projects", json={"name": "Dossier"}).get_json()
    r = api.post("/api/v1/memos", json={
        "title": "Complet", "content_text": "corps", "folder_id": f["id"],
        "due_date": "2026-11-01", "due_end": "2026-11-03", "priority": 1,
        "subtasks": [{"content": "a"}, {"content": "b", "done": True}],
        "assignees": ["Gaspard", "gaspard"], "tags": ["voyage", "#japon"],
        "urls": [{"url": "https://ex.test/1", "label": "Un"}],
    })
    assert r.status_code == 201, r.data
    m = r.get_json()
    assert m["project_id"] == f["id"] and m["due_end"] == "2026-11-03" and m["priority"] == 1
    assert [s["content"] for s in m["subtasks"]] == ["a", "b"] and m["subtasks"][1]["done"] is True
    assert m["assignees"] == ["Gaspard"], "dédup insensible à la casse, comme l'UI"
    assert [u["url"] for u in m["urls"]] == ["https://ex.test/1"]
    assert "#voyage" in m["content"] and "#japon" in m["content"], "les tags deviennent des hashtags du corps"
    assert m["content"].count("#japon") == 1


def test_le_memo_cree_dans_l_ui_reste_sans_source(client, api):
    m = _ui_memo(client, title="UI")
    assert m["source"] == ""
    assert api.get("/api/v1/memos/%d" % m["id"]).get_json()["source"] == ""


# ------------------------------------------------------------------ patch / append


def test_patch_partiel_pose_source(client, api):
    m = _ui_memo(client, title="UI", content="<p>a</p>", due_date="2026-10-20")
    r = api.patch("/api/v1/memos/%d" % m["id"], json={"title": "Renommé"})
    assert r.status_code == 200, r.data
    d = r.get_json()
    assert d["title"] == "Renommé" and d["content"] == "<p>a</p>" and d["due_date"] == "2026-10-20"
    assert d["source"] == "claude-code", "dernière modification par API → source du jeton"
    assert api.patch("/api/v1/memos/%d" % m["id"], json={"due_end": "2026-10-01"}).status_code == 400
    assert api.patch("/api/v1/memos/999999", json={"title": "x"}).status_code == 404
    r = api.patch("/api/v1/memos/%d" % m["id"], json={"content_text": "neuf & propre"})
    assert r.get_json()["content"] == "<p>neuf &amp; propre</p>"


def test_append_ajoute_a_la_fin(client, api):
    m = _ui_memo(client, title="Journal", content="<p>un</p>")
    r = api.post("/api/v1/memos/%d/append" % m["id"], json={"content_text": "deux"})
    assert r.status_code == 200, r.data
    assert r.get_json()["content"] == "<p>un</p><p>deux</p>"
    r = api.post("/api/v1/memos/%d/append" % m["id"], json={"content": "<p>trois</p><script>x</script>"})
    assert r.get_json()["content"] == "<p>un</p><p>deux</p><p>trois</p>"
    assert api.post("/api/v1/memos/%d/append" % m["id"], json={}).status_code == 400


# ------------------------------------------------------------------ move / done / undone


def test_move_done_undone(client, api):
    f = client.post("/api/projects", json={"name": "Cible"}).get_json()
    m = _ui_memo(client, title="bouge")
    r = api.post("/api/v1/memos/%d/move" % m["id"], json={"folder_id": f["id"]})
    assert r.status_code == 200 and r.get_json()["project_id"] == f["id"]
    assert api.post("/api/v1/memos/%d/move" % m["id"], json={"folder_id": 999999}).status_code == 404
    r = api.post("/api/v1/memos/%d/move" % m["id"], json={"folder_id": None})
    assert r.status_code == 200 and r.get_json()["project_id"] is None, "null = Inbox"
    r = api.post("/api/v1/memos/%d/done" % m["id"])
    assert r.status_code == 200 and r.get_json()["done"] is True
    assert len(client.get("/api/history").get_json()) == 1, "terminer écrit l'historique, comme l'UI"
    r = api.post("/api/v1/memos/%d/undone" % m["id"])
    assert r.status_code == 200 and r.get_json()["done"] is False
    assert client.get("/api/history").get_json() == [], "rouvrir retire la ligne, comme l'UI"


# ------------------------------------------------------------------ subtasks


def test_subtasks_ajout_et_modification(client, api):
    m = _ui_memo(client, title="liste", subtasks=[{"content": "a", "done": False}])
    r = api.post("/api/v1/memos/%d/subtasks" % m["id"], json={"content": "b"})
    assert r.status_code == 201, r.data
    assert [s["content"] for s in r.get_json()["subtasks"]] == ["a", "b"]
    r = api.patch("/api/v1/memos/%d/subtasks/1" % m["id"], json={"done": True, "content": "b bis"})
    assert r.status_code == 200
    assert r.get_json()["subtasks"][1] == {"content": "b bis", "done": True}
    assert api.patch("/api/v1/memos/%d/subtasks/7" % m["id"], json={"done": True}).status_code == 404
    assert api.post("/api/v1/memos/%d/subtasks" % m["id"], json={"content": "  "}).status_code == 400


# ------------------------------------------------------------------ urls / comments


def test_urls_reutilisent_memo_urls(client, api):
    m = _ui_memo(client, title="liens")
    r = api.post("/api/v1/memos/%d/urls" % m["id"], json={"url": "https://ex.test/a", "label": "A"})
    assert r.status_code == 201, r.data
    uid = r.get_json()["id"]
    assert api.post("/api/v1/memos/%d/urls" % m["id"], json={"url": "https://ex.test/a"}).status_code == 409
    assert api.post("/api/v1/memos/%d/urls" % m["id"], json={"url": "javascript:x"}).status_code == 400
    assert [u["url"] for u in client.get("/api/memos/%d/urls" % m["id"]).get_json()] == ["https://ex.test/a"]
    assert api.delete("/api/v1/memos/%d/urls/%d" % (m["id"], uid)).status_code == 204
    assert client.get("/api/memos/%d/urls" % m["id"]).get_json() == []


def test_comment_auteur_owner(client, api):
    m = _ui_memo(client, title="fil")
    r = api.post("/api/v1/memos/%d/comments" % m["id"], json={"content": "Depuis Claude <b>x</b>"})
    assert r.status_code == 201, r.data
    c = r.get_json()
    assert c["body"] == "Depuis Claude bx" or "<" not in c["body"]
    fil = client.get("/api/memos/%d/comments" % m["id"]).get_json()
    assert len(fil) == 1 and fil[0]["author"] == "moi"
    assert api.post("/api/v1/memos/%d/comments" % m["id"], json={"content": ""}).status_code == 400


# ------------------------------------------------------------------ corbeille


def test_delete_est_une_corbeille_puis_restore(client, api, app_module):
    m = _ui_memo(client, title="poubelle")
    assert api.delete("/api/v1/memos/%d" % m["id"]).status_code == 204
    con = sqlite3.connect(app_module.DB_PATH)
    try:
        row = con.execute("SELECT deleted_at FROM memos WHERE id = ?", (m["id"],)).fetchone()
    finally:
        con.close()
    assert row and row[0], "suppression douce : la ligne existe, deleted_at posé (invariant 7)"
    assert api.get("/api/v1/memos/%d" % m["id"]).status_code == 404
    assert m["id"] in [x["id"] for x in client.get("/api/trash").get_json()]
    r = api.post("/api/v1/memos/%d/restore" % m["id"])
    assert r.status_code == 200 and r.get_json()["id"] == m["id"]
    assert api.get("/api/v1/memos/%d" % m["id"]).status_code == 200
    assert api.post("/api/v1/memos/%d/restore" % m["id"]).status_code == 404, "pas en corbeille → 404"
    assert api.delete("/api/v1/memos/999999").status_code == 404


# ------------------------------------------------------------------ folders


def test_folders_create_patch_409(client, api):
    r = api.post("/api/v1/folders", json={"name": "Japon", "emoji": "🇯🇵", "color": "#ff0000"})
    assert r.status_code == 201, r.data
    j = r.get_json()
    assert j["emoji"] == "🇯🇵" and j["parent_id"] is None and "uid" in j
    r = api.post("/api/v1/folders", json={"name": "Kyoto", "parent_id": j["id"]})
    assert r.status_code == 201 and r.get_json()["parent_id"] == j["id"]
    k = r.get_json()
    assert api.post("/api/v1/folders", json={"name": "Kyoto", "parent_id": j["id"]}).status_code == 409
    assert api.post("/api/v1/folders", json={"name": "Kyoto"}).status_code == 201, "même nom ailleurs = OK"
    assert api.post("/api/v1/folders", json={"name": ""}).status_code == 400
    assert api.post("/api/v1/folders", json={"name": "x", "parent_id": 999999}).status_code == 404
    r = api.patch("/api/v1/folders/%d" % k["id"], json={"name": "Kyōto", "emoji": "⛩️"})
    assert r.status_code == 200 and r.get_json()["name"] == "Kyōto" and r.get_json()["emoji"] == "⛩️"
    r = api.patch("/api/v1/folders/%d" % k["id"], json={"parent_id": None})
    assert r.status_code == 200 and r.get_json()["parent_id"] is None
    assert api.patch("/api/v1/folders/%d" % k["id"], json={"name": "Kyoto"}).status_code == 409, "frère racine « Kyoto » existe"
    assert api.patch("/api/v1/folders/%d" % j["id"], json={"parent_id": j["id"]}).status_code == 400, "pas son propre parent"
    assert api.patch("/api/v1/folders/999999", json={"name": "x"}).status_code == 404


# ------------------------------------------------------------------ export / import v30


def test_export_porte_source_et_import_sans_source_vaut_vide(client, api):
    m = api.post("/api/v1/memos", json={"title": "via api"}).get_json()
    _ui_memo(client, title="via ui")
    exp = client.get("/api/export").get_json()
    assert exp["version"] == 30
    by = {x["title"]: x for x in exp["memos"]}
    assert by["via api"]["source"] == "claude-code" and by["via ui"]["source"] == ""
    # import sur base vierge d'un export SANS source (v29) → ''
    import uuid
    r = client.post("/api/import", json={"version": 29, "memos": [{"uid": str(uuid.uuid4()), "title": "ancien", "content": "<p>x</p>"}]})
    assert r.status_code == 200, r.data
    assert [x for x in client.get("/api/export").get_json()["memos"] if x["title"] == "ancien"][0]["source"] == ""
    # ré-import de l'export v30 : la source survit au round-trip
    r = client.post("/api/import", json=exp)
    assert r.status_code == 200
    assert [x for x in client.get("/api/export").get_json()["memos"] if x["title"] == "via api"][0]["source"] == "claude-code"


def test_import_n_ecrase_pas_une_source_posee_par_du_vide(client, api):
    """Invariant 2 : un export v29 (sans `source`) réimporté sur un mémo qui en a une ne l'efface pas."""
    m = api.post("/api/v1/memos", json={"title": "via api"}).get_json()
    full = [x for x in client.get("/api/export").get_json()["memos"] if x.get("uid") == m["uid"]][0]   # l'export n'a pas d'id
    sans = dict(full)
    sans.pop("source", None)
    sans["updated_at"] = "2099-01-01T00:00:00+00:00"   # plus récent → mise à jour
    r = client.post("/api/import", json={"version": 29, "memos": [sans]})
    assert r.status_code == 200, r.data
    assert _ui_memo_by_id(client, m["id"])["source"] == "claude-code"


# ------------------------------------------------------------------ périmètre


def test_l_api_ne_gere_ni_partages_ni_reglages_ni_import(app_module):
    rules = [r.rule for r in app_module.app.url_map.iter_rules() if r.rule.startswith("/api/v1/")]
    interdits = ("share", "guest", "hub", "settings", "import", "backup", "trash", "tokens")
    for r in rules:
        for mot in interdits:
            assert mot not in r, "route hors périmètre lot A : %s" % r
