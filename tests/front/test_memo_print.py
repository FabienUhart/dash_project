"""[MEMO-PRINT] Le bouton 🖨 « Imprimer » ouvre la vue imprimable dans un NOUVEL onglet.

Deux portes owner : la barre d'actions du board (dossier + sous-dossiers) et le pied de la fiche
👁 (un mémo). La page ouverte est autonome et sans JS ; son `<title>` porte le nom du dossier (ou
le titre du mémo) — c'est aussi le nom de fichier que proposera « Enregistrer en PDF ».

La base du `live_server` est partagée par toute la session : le décor est supprimé en sortie.
"""
import time

import pytest

pytestmark = pytest.mark.e2e

_BRUIT_404 = "the server responded with a status of 404"
_CREES = []   # urls de suppression, dossiers en DERNIER


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _semer(page, live_server):
    k = str(int(time.time() * 1000) % 100000)
    p = page.request.post(live_server + "/api/projects", data={"name": "MP dossier %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])
    r = page.request.post(live_server + "/api/memos", data={
        "title": "MP mémo %s" % k, "content": "<p>入口 entrée</p>", "project_id": p["id"],
        "due_date": "2026-11-03"})
    assert r.ok, r.text()
    m = r.json()
    _CREES.append("/api/memos/%d" % m["id"])
    return p, m


def _owner(page, live_server, pid):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof renderBoard === 'function' && state.memos")
    page.evaluate("pid => { state.view = 'memos'; state.memoProject = pid; state.memoFilter = 'all'; renderAll(); }", pid)
    page.wait_for_selector("#memo-board .hdr-toolbar", timeout=5_000)


def _ouvrir(page, clic):
    with page.expect_popup() as info:
        clic()
    pop = info.value
    erreurs = []
    pop.on("console", lambda msg: msg.type == "error" and erreurs.append(msg.text))
    pop.on("pageerror", lambda exc: erreurs.append(str(exc)))
    pop.wait_for_load_state("load")
    return pop, erreurs


def test_bouton_imprimer_du_board_ouvre_le_dossier(page, live_server, console_errors):
    p, m = _semer(page, live_server)
    _owner(page, live_server, p["id"])
    btn = page.locator('#memo-board .hdr-toolbar [title^="Vue imprimable du dossier"]')
    assert btn.count() == 1, "le bouton 🖨 manque dans la barre d'actions du board"
    pop, erreurs = _ouvrir(page, btn.click)
    assert pop.url.endswith("/print/project/%d" % p["id"])
    assert pop.title() == p["name"]
    assert m["title"] in pop.content() and "入口" in pop.content()
    assert pop.locator("script").count() == 0
    assert erreurs == []
    pop.close()
    assert [e for e in console_errors if _BRUIT_404 not in e] == []


def test_bouton_imprimer_de_la_fiche_ouvre_le_memo(page, live_server, console_errors):
    p, m = _semer(page, live_server)
    _owner(page, live_server, p["id"])
    page.locator('.task[data-memo-id="%d"] .tview' % m["id"]).first.click()
    btn = page.locator('dialog[open] button[title^="Vue imprimable"]')
    btn.wait_for(timeout=5_000)
    pop, erreurs = _ouvrir(page, btn.click)
    assert pop.url.endswith("/print/memo/%d" % m["id"])
    assert pop.title() == m["title"]
    assert erreurs == []
    pop.close()
    assert [e for e in console_errors if _BRUIT_404 not in e] == []
