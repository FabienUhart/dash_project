"""[DASH-API] § 2 — lecture : arbre, mémos filtrés/triés/paginés, mémo complet, compteurs,
recherche pliée, plan, export v30, OpenAPI complet, corbeille invisible.

Brief : `docs/briefs/DASH-API.md` § 2. Les règles des six tuiles sont éprouvées à part par la
fixture jumelle (`test_tiles_twin.py`) ; ici on vérifie la FORME des réponses et les contrats :
- un mémo en corbeille n'est JAMAIS renvoyé (404, absent des listes et des compteurs) ;
- `content_text` est le HTML déshabillé ; le contenu riche reste dans `content` ;
- tri `due` : datés d'abord (date, sans heure avant avec heure, heure), puis sans date en manuel ;
- pagination par `cursor` opaque + `limit` plafonné à 200 ; `since` filtre sur `updated_at` ;
- la recherche ignore accents et casse (« eclipse » trouve « Éclipse ») et regarde titre, contenu,
  sous-tâches, assignés, libellés/URL ;
- `/plan` a la structure de la vue Plan (dossiers → sous-dossiers + mémos actifs, Inbox à part) ;
- `/export` = le même JSON que Paramètres, version 30 ;
- `/openapi.json` décrit CHAQUE route enregistrée sous /api/v1 (test d'introspection).
"""
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def api(client):
    t = client.post("/api/tokens", json={"name": "lecteur", "scopes": "read,write", "source": "claude-code"}).get_json()
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


def _folder(client, name, parent_id=None, **kw):
    r = client.post("/api/projects", json=dict(name=name, **kw))
    assert r.status_code == 201, r.data
    p = r.get_json()
    if parent_id:
        assert client.put("/api/projects/%d" % p["id"], json={"parent_id": parent_id}).status_code == 200
    return p


def _memo(client, **kw):
    r = client.post("/api/memos", json=kw)
    assert r.status_code == 201, r.data
    return r.get_json()


# ------------------------------------------------------------------ tree


def test_tree_dossiers_et_memos_sans_contenu(client, api):
    racine = _folder(client, "Japon", emoji="🇯🇵")
    sous = _folder(client, "Kyoto", parent_id=racine["id"])
    m = _memo(client, title="Sanjo", content="<p>secret long</p>", project_id=sous["id"], due_date="2026-11-02")
    _memo(client, title="fait", project_id=racine["id"], done=True)
    r = api.get("/api/v1/tree")
    assert r.status_code == 200
    t = r.get_json()
    fol = {f["id"]: f for f in t["folders"]}
    assert fol[racine["id"]]["emoji"] == "🇯🇵" and fol[racine["id"]]["parent_id"] is None
    assert fol[sous["id"]]["parent_id"] == racine["id"]
    assert "uid" in fol[sous["id"]] and "color" in fol[sous["id"]]
    assert fol[sous["id"]]["counts"] == {"open": 1, "done": 0}
    assert fol[racine["id"]]["counts"] == {"open": 0, "done": 1}
    mm = {x["id"]: x for x in t["memos"]}
    assert set(mm[m["id"]].keys()) >= {"id", "title", "done", "due_date", "due_end", "priority", "project_id"}
    assert "content" not in mm[m["id"]] and "content_text" not in mm[m["id"]]
    assert mm[m["id"]]["due_date"] == "2026-11-02"


# ------------------------------------------------------------------ memos (liste)


def test_memos_forme_et_content_text(client, api):
    m = _memo(client, title="Riche", content="<p>Bonjour <b>monde</b></p><p>ligne 2</p>")
    r = api.get("/api/v1/memos")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body.keys()) == {"items", "next_cursor"}
    it = [x for x in body["items"] if x["id"] == m["id"]][0]
    assert it["content"] == "<p>Bonjour <b>monde</b></p><p>ligne 2</p>"
    assert it["content_text"] == "Bonjour monde ligne 2"
    assert it["urls"] == [] and it["subtasks"] == [] and "uid" in it and it["source"] == ""


def test_memos_corbeille_invisible(client, api):
    m = _memo(client, title="à jeter")
    assert client.delete("/api/memos/%d" % m["id"]).status_code == 204
    assert [x["id"] for x in api.get("/api/v1/memos").get_json()["items"]] == []
    assert api.get("/api/v1/memos/%d" % m["id"]).status_code == 404
    assert api.get("/api/v1/counts").get_json()["all"] == 0
    assert m["id"] not in [x["id"] for x in api.get("/api/v1/tree").get_json()["memos"]]


def test_memos_filtre_dossier_et_sous_arbre(client, api):
    racine = _folder(client, "A")
    sous = _folder(client, "B", parent_id=racine["id"])
    a = _memo(client, title="dans A", project_id=racine["id"])
    b = _memo(client, title="dans B", project_id=sous["id"])
    inbox = _memo(client, title="inbox")
    ids = lambda r: sorted(x["id"] for x in r.get_json()["items"])
    assert ids(api.get("/api/v1/memos?folder=%d" % racine["id"])) == [a["id"]]
    assert ids(api.get("/api/v1/memos?folder=%d&subtree=1" % racine["id"])) == sorted([a["id"], b["id"]])
    assert ids(api.get("/api/v1/memos?folder=inbox")) == [inbox["id"]]
    assert api.get("/api/v1/memos?folder=999999").status_code == 404
    assert api.get("/api/v1/memos?filter=bidon").status_code == 400
    assert api.get("/api/v1/memos?sort=bidon").status_code == 400


def test_memos_tri_due(client, api):
    sans = _memo(client, title="sans date")
    tard = _memo(client, title="tard", due_date="2026-12-01")
    tot_h = _memo(client, title="tôt 09h", due_date="2026-11-01", due_time="09:00")
    tot = _memo(client, title="tôt sans heure", due_date="2026-11-01")
    r = api.get("/api/v1/memos?sort=due")
    assert [x["id"] for x in r.get_json()["items"]] == [tot["id"], tot_h["id"], tard["id"], sans["id"]]
    r = api.get("/api/v1/memos?sort=newest")
    assert [x["id"] for x in r.get_json()["items"]][0] == tot["id"]
    r = api.get("/api/v1/memos?sort=manual")
    assert [x["id"] for x in r.get_json()["items"]] == [sans["id"], tard["id"], tot_h["id"], tot["id"]]


def test_memos_pagination_et_since(client, api):
    created = [_memo(client, title="p%d" % i) for i in range(5)]
    r = api.get("/api/v1/memos?limit=2")
    b = r.get_json()
    assert len(b["items"]) == 2 and b["next_cursor"]
    r2 = api.get("/api/v1/memos?limit=2&cursor=" + b["next_cursor"])
    b2 = r2.get_json()
    assert len(b2["items"]) == 2 and b2["next_cursor"]
    r3 = api.get("/api/v1/memos?limit=2&cursor=" + b2["next_cursor"])
    b3 = r3.get_json()
    assert len(b3["items"]) == 1 and b3["next_cursor"] is None
    vus = [x["id"] for x in b["items"] + b2["items"] + b3["items"]]
    assert sorted(vus) == sorted(m["id"] for m in created), "pagination sans trou ni doublon"
    assert api.get("/api/v1/memos?limit=500").get_json()["items"].__len__() == 5, "limit plafonné, pas refusé"
    assert api.get("/api/v1/memos?cursor=pasunnombre").status_code == 400
    # since : seulement ce qui a bougé après
    stamp = api.get("/api/v1/memos/%d" % created[4]["id"]).get_json()["updated_at"]   # le plus récent
    import time
    time.sleep(0.01)
    assert client.put("/api/memos/%d" % created[3]["id"], json={"title": "p3 modifié"}).status_code == 200
    from urllib.parse import quote
    r = api.get("/api/v1/memos?since=" + quote(stamp))   # le « + » du fuseau doit être encodé
    assert [x["id"] for x in r.get_json()["items"]] == [created[3]["id"]]
    assert api.get("/api/v1/memos?since=hier").status_code == 400


def test_memos_filtre_history_rend_l_historique(client, api):
    m = _memo(client, title="à finir")
    assert client.put("/api/memos/%d" % m["id"], json={"done": True}).status_code == 200
    r = api.get("/api/v1/memos?filter=history")
    items = r.get_json()["items"]
    assert len(items) == 1 and items[0]["memo_uid"] == m["uid"] and items[0]["done_at"]
    assert api.get("/api/v1/counts").get_json()["history"] == 1


# ------------------------------------------------------------------ memo (détail)


def test_memo_complet(client, api):
    m = _memo(client, title="Détail", content="<p>texte</p>", subtasks=[{"content": "a", "done": False}])
    assert client.post("/api/memos/%d/urls" % m["id"], json={"url": "https://ex.test/x", "label": "Ex"}).status_code == 201
    assert client.post("/api/memos/%d/comments" % m["id"], json={"body": "hello"}).status_code == 201
    r = api.get("/api/v1/memos/%d" % m["id"])
    assert r.status_code == 200
    d = r.get_json()
    assert d["title"] == "Détail" and d["content_text"] == "texte"
    assert [c["body"] for c in d["comments"]] == ["hello"]
    assert [u["url"] for u in d["urls"]] == ["https://ex.test/x"] and d["urls"][0]["label"] == "Ex"
    assert d["attachments"] == [] and d["images"] == []
    assert d["subtasks"] == [{"content": "a", "done": False}]
    assert api.get("/api/v1/memos/999999").status_code == 404


# ------------------------------------------------------------------ counts


def test_counts_scope_dossier(client, api):
    racine = _folder(client, "R")
    sous = _folder(client, "S", parent_id=racine["id"])
    _memo(client, title="r", project_id=racine["id"])
    _memo(client, title="s", project_id=sous["id"])
    _memo(client, title="ailleurs")
    assert api.get("/api/v1/counts").get_json()["all"] == 3
    assert api.get("/api/v1/counts?folder=%d" % racine["id"]).get_json()["all"] == 1
    assert api.get("/api/v1/counts?folder=%d&subtree=1" % racine["id"]).get_json()["all"] == 2
    c = api.get("/api/v1/counts").get_json()
    assert set(c.keys()) == {"all", "overdue", "today", "scheduled", "done", "history"}


# ------------------------------------------------------------------ search


def test_search_plie_accents_et_regarde_partout(client, api):
    e = _memo(client, title="Éclipse à Kyōto")
    s = _memo(client, title="Courses", subtasks=[{"content": "Café moulu", "done": False}])
    a = _memo(client, title="Réunion", assignees=["Gaspard"])
    u = _memo(client, title="Colis")
    assert client.post("/api/memos/%d/urls" % u["id"], json={"url": "https://suivi.test/1", "label": "Suivi colis La Poste"}).status_code == 201
    c = _memo(client, title="Vieux", content="<p>contenu <i>eclipsé</i></p>")
    ids = lambda q: sorted(x["id"] for x in api.get("/api/v1/search?q=" + q).get_json()["items"])
    assert ids("eclipse") == sorted([e["id"], c["id"]])
    assert ids("kyoto") == [e["id"]]
    assert ids("cafe") == [s["id"]]
    assert ids("gaspard") == [a["id"]]
    assert ids("poste") == [u["id"]]
    assert ids("sanjo%20kyoto") == [], "tous les mots doivent être là"
    assert ids("kyoto%20eclipse") == [e["id"]], "n'importe quel ordre"
    assert api.get("/api/v1/search").status_code == 400, "q requis"


def test_search_bornes_dates_dossier_tag(client, api):
    f = _folder(client, "F")
    d1 = _memo(client, title="d1", due_date="2026-10-01", project_id=f["id"])
    d2 = _memo(client, title="d2", due_date="2026-10-20")
    t = _memo(client, title="t", content="<p>note #urgent</p>")
    ids = lambda qs: sorted(x["id"] for x in api.get("/api/v1/search?" + qs).get_json()["items"])
    assert ids("q=d&due_from=2026-10-10") == [d2["id"]]
    assert ids("q=d&due_to=2026-10-10") == [d1["id"]]
    assert ids("q=d&folder=%d" % f["id"]) == [d1["id"]]
    assert ids("tag=urgent") == [t["id"]], "tag seul suffit (pas de q)"
    assert ids("q=d&created_from=2099-01-01") == []
    assert api.get("/api/v1/search?q=d&due_from=pas-une-date").status_code == 400


# ------------------------------------------------------------------ plan


def test_plan_structure_de_la_vue_plan(client, api):
    racine = _folder(client, "Voyage", emoji="✈️")
    sous = _folder(client, "Kyoto", parent_id=racine["id"])
    actif = _memo(client, title="à faire", project_id=sous["id"])
    fait = _memo(client, title="fait", project_id=sous["id"], done=True)
    inbox = _memo(client, title="en vrac")
    jete = _memo(client, title="jeté", project_id=racine["id"])
    assert client.delete("/api/memos/%d" % jete["id"]).status_code == 204
    r = api.get("/api/v1/plan")
    assert r.status_code == 200
    p = r.get_json()
    assert [x["name"] for x in p["roots"]] == ["Voyage"]
    v = p["roots"][0]
    assert v["emoji"] == "✈️" and v["count"] == 1, "count = actifs NON terminés du sous-arbre"
    assert v["memos"] == [], "le mémo jeté n'apparaît pas"
    assert [k["name"] for k in v["children"]] == ["Kyoto"]
    k = v["children"][0]
    assert sorted(m["title"] for m in k["memos"]) == ["fait", "à faire"], "la vue Plan montre les mémos actifs, terminés compris"
    assert k["count"] == 1
    assert set(k["memos"][0].keys()) >= {"id", "title", "done", "due_date", "due_end", "due_time", "priority", "assignees", "location"}
    assert [m["id"] for m in p["inbox"]["memos"]] == [inbox["id"]]


# ------------------------------------------------------------------ export / openapi


def test_export_v30_identique_a_parametres(client, api):
    _memo(client, title="x")
    a = api.get("/api/v1/export")
    assert a.status_code == 200
    b = client.get("/api/export")
    assert a.get_json()["version"] == 30
    assert a.get_json()["memos"] == b.get_json()["memos"]
    assert set(a.get_json().keys()) == set(b.get_json().keys())


def test_openapi_decrit_chaque_route(client, api, app_module):
    r = api.get("/api/v1/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert spec["openapi"].startswith("3.1")
    paths = spec["paths"]
    for rule in app_module.app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1/"):
            continue
        # Flask `<int:memo_id>` → OpenAPI `{memo_id}`
        import re
        chemin = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule[len("/api/v1"):]) or "/"
        assert chemin in paths, "route absente de l'OpenAPI : %s" % rule.rule
        for m in rule.methods - {"HEAD", "OPTIONS"}:
            assert m.lower() in paths[chemin], "%s %s absent" % (m, chemin)
    assert spec["components"]["securitySchemes"]["bearer"]["scheme"] == "bearer"
