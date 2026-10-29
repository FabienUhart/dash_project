"""[MEMO-PDF v2] Le bouton 📄 « PDF » télécharge le PDF fabriqué par le serveur ; la vue Fichiers
du dossier porte en tête une entrée « PDF du dossier » avec son état (à jour / périmé).

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
    p = page.request.post(live_server + "/api/projects", data={"name": "PDF dossier %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])
    r = page.request.post(live_server + "/api/memos", data={
        "title": "PDF mémo %s" % k, "content": "<p>入口 entrée</p>", "project_id": p["id"]})
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


def _telecharger(page, clic):
    with page.expect_download(timeout=30_000) as info:
        clic()
    dl = info.value
    with open(dl.path(), "rb") as f:
        return dl.suggested_filename, f.read()


def test_bouton_pdf_du_board_telecharge_le_pdf(page, live_server, console_errors):
    p, m = _semer(page, live_server)
    _owner(page, live_server, p["id"])
    barre = page.locator("#memo-board .hdr-toolbar")
    assert barre.locator('[title^="Vue imprimable du dossier"]').count() == 1, "Imprimer doit RESTER à côté du 📄"
    btn = barre.locator('[title^="Télécharger le PDF du dossier"]')
    assert btn.count() == 1, "bouton 📄 PDF absent de la barre d'actions"
    nom, data = _telecharger(page, btn.click)
    assert nom == p["name"] + ".pdf", nom
    assert data[:5] == b"%PDF-"
    assert [e for e in console_errors if _BRUIT_404 not in e] == []


def test_fichiers_porte_le_pdf_du_dossier_et_son_etat(page, live_server, console_errors):
    p, m = _semer(page, live_server)
    _owner(page, live_server, p["id"])
    page.locator('#memo-board .hdr-toolbar [title^="Retrouver tous les fichiers"]').click()
    ligne = page.locator("#files-dialog .pdf-row")
    ligne.wait_for(timeout=5_000)
    page.wait_for_function("() => /généré|pas encore/.test(document.querySelector('#files-dialog .pdf-row-txt').textContent)")
    assert "périmé" in ligne.inner_text(), ligne.inner_text()          # jamais généré
    nom, data = _telecharger(page, ligne.locator('[title^="Télécharger le PDF"]').click)
    assert data[:5] == b"%PDF-"
    page.wait_for_function("() => document.querySelector('#files-dialog .pdf-row').dataset.fresh === '1'")
    assert "à jour" in ligne.inner_text()
    # la fiche 👁 du mémo porte aussi son 📄
    page.locator("#files-dialog").evaluate("d => d.close()")
    page.locator('.task[data-memo-id="%d"] .tview' % m["id"]).first.click()
    pb = page.locator('dialog[open] button[title="Télécharger le PDF du mémo"]')
    pb.wait_for(timeout=5_000)
    nom, data = _telecharger(page, pb.click)
    assert nom == m["title"] + ".pdf" and data[:5] == b"%PDF-"
    assert [e for e in console_errors if _BRUIT_404 not in e] == []
