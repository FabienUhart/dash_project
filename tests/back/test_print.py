"""
[MEMO-PRINT] Vue imprimable d'un dossier (et d'un mémo) — v1 de [MEMO-PDF].

Deux routes de LECTURE owner, derrière Authelia : `/print/project/<id>` et `/print/memo/<id>`.
C'est le navigateur qui fait le PDF (⌘P / « Enregistrer en PDF ») : la page doit donc être
autonome, sans JS, et ne porter QUE le sous-arbre demandé — jamais un mémo d'ailleurs, jamais un
mémo en corbeille (invariant 7). Le contenu Quill est rendu tel quel mais sans `<img>` : une photo
n'existe pas hors réseau, on l'annonce par « 📎 n fichier(s) » à la place.
"""
import io
import re

import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def _folder(c, name, parent_id=None, emoji=""):
    r = c.post("/api/projects", json={"name": name, "emoji": emoji})
    assert r.status_code == 201, r.data
    pid = r.get_json()["id"]
    if parent_id is not None:
        r = c.put("/api/projects/%d" % pid, json={"name": name, "parent_id": parent_id})
        assert r.status_code == 200, r.data
    return pid


def _memo(c, title, project_id, **kw):
    body = {"title": title, "content": kw.pop("content", "<p>%s</p>" % title), "project_id": project_id}
    body.update(kw)
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (90, 120, 60)).save(buf, "JPEG")
    buf.seek(0)
    return buf


def _page(c, url):
    r = c.get(url)
    assert r.status_code == 200, r.data
    return r, r.get_data(as_text=True)


@pytest.fixture
def japon(client):
    """Voyage Japon › Kyoto (enfant), + un dossier voisin Courses qui ne doit JAMAIS sortir."""
    root = _folder(client, "Voyage Japon", emoji="🗻")
    kyoto = _folder(client, "Activités Kyoto", parent_id=root)
    autre = _folder(client, "Courses")
    ids = {
        "root": root, "kyoto": kyoto, "autre": autre,
        "vol": _memo(client, "Vol AF276", root, due_date="2026-11-01", due_time="10:30"),
        "ryokan": _memo(client, "Ryokan Gion", kyoto, due_date="2026-11-03", due_end="2026-11-06"),
        "temple": _memo(client, "Kinkaku-ji", kyoto, due_date="2026-11-04"),
        "kanji": _memo(client, "Kanji utiles", root, content="<p><b>入口</b> entrée — Déménagement</p>"),
        "lait": _memo(client, "Lait demi-écrémé", autre),
    }
    return client, ids


def test_project_page_contains_whole_subtree_and_nothing_else(japon):
    c, ids = japon
    r, html = _page(c, "/print/project/%d" % ids["root"])
    for t in ("Vol AF276", "Ryokan Gion", "Kinkaku-ji", "Kanji utiles"):
        assert t in html, "Mémo du sous-arbre absent de la page imprimable : %s" % t
    assert "Lait demi-écrémé" not in html, "Un mémo d'un AUTRE dossier a fuité dans l'impression."
    assert "Courses" not in html
    assert r.headers.get("Cache-Control") == "no-store"
    assert c.get("/print/project/99999").status_code == 404


def test_trashed_memo_absent(japon):
    c, ids = japon
    assert c.delete("/api/memos/%d" % ids["temple"]).status_code in (200, 204)
    _, html = _page(c, "/print/project/%d" % ids["root"])
    assert "Kinkaku-ji" not in html, "Un mémo en corbeille sort à l'impression (invariant 7)."


def test_days_ascending_and_range_under_first_day(japon):
    c, ids = japon
    # Créé APRÈS les autres, mais daté AVANT : un tri par id le mettrait en dernier.
    _memo(c, "Arrivée Haneda", ids["root"], due_date="2026-10-31")
    _, html = _page(c, "/print/project/%d" % ids["root"])
    jour = html.split('id="jour"', 1)[1].split("<h2", 1)[0]
    days = re.findall(r'<div class="day">([^<]+)</div>', jour)
    assert days == ["sam. 31 oct.", "dim. 1 nov.", "mar. 3 nov.", "mer. 4 nov."], days
    # La plage 3 → 6 nov. est rangée sous son PREMIER jour, et annoncée comme plage.
    mar3 = jour.split("mar. 3 nov.</div>", 1)[1].split('<div class="day">', 1)[0]
    assert "Ryokan Gion" in mar3
    assert "3 nov. → " in mar3 and "6 nov." in mar3
    assert "10:30" in jour
    assert jour.index("Arrivée Haneda") < jour.index("Vol AF276") < jour.index("Kinkaku-ji")


def test_unicode_intact(japon):
    c, ids = japon
    r, html = _page(c, "/print/project/%d" % ids["root"])
    assert "charset=utf-8" in r.headers.get("Content-Type", "").lower()
    assert "入口" in html and "Déménagement" in html and "🗻" in html


def test_img_stripped_and_files_announced(japon):
    c, ids = japon
    mid = _memo(c, "Photo du torii", ids["kyoto"],
                content='<p>avant<img src="/uploads/x.jpg">après</p>')
    r = c.post("/api/memos/%d/images" % mid, data={"image": (_jpeg(), "t.jpg")},
               content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    _, html = _page(c, "/print/project/%d" % ids["root"])
    assert "<img" not in html.lower(), "Une <img> est restée : la page imprimée tente le réseau."
    assert "avantaprès" in html
    assert "📎 1 fichier(s)" in html


def test_memo_page_and_404_in_trash(japon):
    c, ids = japon
    _, html = _page(c, "/print/memo/%d" % ids["ryokan"])
    assert "Ryokan Gion" in html and "Vol AF276" not in html
    assert "<title>Ryokan Gion" in html
    c.delete("/api/memos/%d" % ids["ryokan"])
    assert c.get("/print/memo/%d" % ids["ryokan"]).status_code == 404
    assert c.get("/print/memo/99999").status_code == 404


def test_subtasks_and_urls(japon, app_module, monkeypatch):
    c, ids = japon
    monkeypatch.setattr(app_module, "_fetch_og", lambda url: {"title": "Japan Guide"})
    mid = _memo(c, "Valise", ids["root"], subtasks=[{"content": "Passeport", "done": True},
                                                       {"content": "JR Pass", "done": False}])
    r = c.post("/api/memos/%d/urls" % mid, json={"url": "https://www.japan-guide.com/", "label": "Guide"})
    assert r.status_code in (200, 201), r.data
    _, html = _page(c, "/print/memo/%d" % mid)
    assert "☑ Passeport" in html and "☐ JR Pass" in html
    assert "Guide" in html and "https://www.japan-guide.com/" in html


def test_no_script_and_no_share_print_route(japon, app_module):
    c, ids = japon
    for url in ("/print/project/%d" % ids["root"], "/print/memo/%d" % ids["vol"]):
        _, html = _page(c, url)
        assert "<script" not in html.lower()
        assert "<title>" in html
    rules = [r.rule for r in app_module.app.url_map.iter_rules()]
    assert not [r for r in rules if r.startswith("/share") and "print" in r], (
        "Aucune impression invité en v1 : pas de route /share/**/print (invariant 5)."
    )
