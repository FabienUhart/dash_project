"""[MEMO-URLS] Front : des liens attachés au mémo, comme les fichiers — owner, partage, hub.

Brief : `docs/briefs/MEMO-URLS.md` § 3 (scénarios 9 → 14). Le back est couvert par
`tests/back/test_memo_urls.py` ; ici on éprouve ce qu'on VOIT, sur les trois pages, en bureau et
en mobile 412 px.

Ce que ces parcours PROTÈGENT :

- **la section « Liens » de l'éditeur produit un chip sur la card** (9) : le libellé l'emporte sur
  l'URL, et le ↗ ouvre le site dans un nouvel onglet — rien d'autre ;
- **une URL du texte est VUE sans être STOCKÉE** (10) : chip grisé « dans le texte », zéro ligne en
  base tant qu'on n'a pas cliqué « Épingler » — après quoi elle est attachée ;
- **retirer depuis l'éditeur retire partout** (11) ;
- **la recherche connaît le libellé** (12) : « colis » trouve le mémo dont seul le lien parle ;
- **parité invitée avec droits** (13) : l'éditeur ajoute, le lecteur voit le chip mais pas le
  formulaire ;
- **zéro erreur console** (14), assertion de CHAQUE test.

La base du `live_server` est partagée par toute la session : le décor est supprimé en sortie.
"""
import os
import sqlite3
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}
SUIVI = "https://exemple.test/suivi?x=1"
_BRUIT_404 = "the server responded with a status of 404"
_n = [0]
_CREES = []   # urls de suppression, dossiers en DERNIER


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _db():
    return sqlite3.connect(os.path.join(os.environ["E2E_DATA_DIR"], "dashboard.db"))


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return False


# ------------------------------------------------------------------ décor


def _semer(page, live_server, contenu=None):
    """Dossier « MU racine k » + mémo « MU iPad k » dont le texte porte SUIVI (non attachée)."""
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)
    p = page.request.post(live_server + "/api/projects", data={"name": "MU racine %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])
    r = page.request.post(live_server + "/api/memos", data={
        "title": "MU iPad %s" % k, "project_id": p["id"],
        # l'URL figure DEUX fois (texte + href d'un lien) : la dédup d'`extractUrls` doit en faire UN chip
        "content": contenu if contenu is not None else
            '<p>réparation en cours, suivi : %s merci.</p><p>rappel : <a href="%s">%s</a></p>' % (SUIVI, SUIVI, SUIVI),
    })
    assert r.ok, r.text()
    m = r.json()
    _CREES.append("/api/memos/%d" % m["id"])
    return {"k": k, "projet": p, "memo": m}


def _urls_api(page, live_server, mid):
    r = page.request.get(live_server + "/api/memos/%d/urls" % mid)
    assert r.ok, r.text()
    return r.json()


def _ajouter_api(page, live_server, mid, url, label=""):
    r = page.request.post(live_server + "/api/memos/%d/urls" % mid, data={"url": url, "label": label})
    assert r.ok, r.text()
    return r.json()


def _owner(page, live_server, vp=BUREAU):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof openMemoEditor === 'function' && state.memos && state.memos.length")
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    page.wait_for_timeout(300)


def _invite(page, live_server, d, ou, role="editor", vp=BUREAU):
    """Ouvre le décor côté invité APPROUVÉ : `ou` = 'share' ou 'hub' (montage de
    test_guest_search_grammar). Rend le jeton du partage."""
    _n[0] += 1
    email = "mu%d@ex.com" % _n[0]
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["projet"]["id"], "role": role}).json()
    _CREES.insert(0, "/api/shares/%d" % sh["share_id"]) if sh.get("share_id") else None
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Gaspard", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    page.set_viewport_size(vp)
    if ou == "share":
        page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (sh["token"], reg.json()["guest_token"]))
        page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
        page.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.memos && DATA.memos.length")
    else:
        con = _db()
        try:
            hub_token, pin = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?", (email,)).fetchone()
        finally:
            con.close()
        ok = page.request.post(live_server + "/share/hub/%s/approve" % hub_token, data={"pin": pin})
        assert ok.ok, ok.text()
        page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
        page.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.memos && DATA.memos.length")
    page.wait_for_timeout(300)
    return sh["token"]


def _card(page, mid):
    return page.locator('.task[data-memo-id="%d"]' % mid)


def _ouvrir_editeur_owner(page, mid):
    page.evaluate("id => openMemoEditor(state.memos.find(x => x.id === id))", mid)
    page.wait_for_selector("#memo-edit-dialog[open] #me-urls .murls-sec", timeout=5_000)


def _croix_cliquable(page, box):
    """Retouche post-smoke : le × de retrait doit être un VRAI bouton icône (≥ 24×24 px, title
    « Retirer ce lien ») — le × interne du chip faisait 10×15 px et des clics réels le manquaient."""
    x = page.locator(box + " .murl-item .murl-x").first
    assert x.count() == 1, "pas de bouton de retrait dans la ligne"
    assert x.get_attribute("title") == "Retirer ce lien"
    bb = x.bounding_box()
    assert bb and bb["width"] >= 24 and bb["height"] >= 24, "zone de clic du × trop petite : %r" % bb
    assert page.locator(box + " .murl-item .lref-x").count() == 0, "le × interne du chip ne doit plus exister ici"


def _fermer_editeur(page, sel):
    page.keyboard.press("Escape")
    page.wait_for_selector(sel + "[open]", state="detached", timeout=5_000)
    page.wait_for_timeout(300)


# --------------------------------------------------------------------------- 9


@pytest.mark.parametrize("vp", [BUREAU, MOBILE], ids=["bureau", "mobile412"])
def test_editeur_ajoute_un_lien_avec_libelle_et_la_fleche_ouvre_le_site(page, live_server, console_errors, vp):
    d = _semer(page, live_server, contenu="<p>rien à détecter ici</p>")
    mid = d["memo"]["id"]
    _owner(page, live_server, vp)
    _ouvrir_editeur_owner(page, mid)
    assert page.locator("#me-urls .murl-item").count() == 0

    page.locator("#me-urls .murl-url").fill("https://apple.test/suivi/ABC123?lang=fr")
    page.locator("#me-urls .murl-label").fill("Suivi Apple")
    page.locator("#me-urls .murl-url").press("Enter")
    page.wait_for_selector('#me-urls .murl-item[data-url="https://apple.test/suivi/ABC123?lang=fr"]', timeout=5_000)
    assert "Suivi Apple" in page.locator("#me-urls .murl-item .murl-chip").inner_text()
    assert page.locator("#me-urls .murl-url").input_value() == "", "le champ doit se vider après l'ajout"
    _croix_cliquable(page, "#me-urls")
    assert [u["label"] for u in _urls_api(page, live_server, mid)] == ["Suivi Apple"]

    # validation côté client : le message, pas un appel serveur
    page.locator("#me-urls .murl-url").fill("javascript:alert(1)")
    page.locator("#me-urls .murl-url").press("Enter")
    page.wait_for_timeout(300)
    assert "http" in page.locator("#me-urls .murl-msg").inner_text().lower()
    assert len(_urls_api(page, live_server, mid)) == 1

    _fermer_editeur(page, "#memo-edit-dialog")
    chip = _card(page, mid).locator('.murls-row .murl-chip[data-url="https://apple.test/suivi/ABC123?lang=fr"]')
    chip.wait_for(state="visible", timeout=5_000)
    assert "Suivi Apple" in chip.inner_text(), "le libellé doit l'emporter sur l'URL"
    assert chip.locator(".lref-x").count() == 0, "pas de × sur la card (on retire depuis l'éditeur)"

    # Le nouvel onglet n'a pas internet (garde zéro-réseau) : on sert nous-mêmes le site cible
    # au niveau du CONTEXTE, sinon l'onglet retombe sur `chrome-error://` et perd son URL.
    page.context.route("https://apple.test/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<html><body>site</body></html>"))
    with page.context.expect_page(timeout=5_000) as nouvel:
        chip.locator(".lref-go").click()
    popup = nouvel.value
    popup.wait_for_load_state("domcontentloaded")
    assert popup.url.startswith("https://apple.test/suivi/ABC123"), popup.url
    popup.close()
    assert page.locator("#memo-edit-dialog[open]").count() == 0, "le ↗ a aussi ouvert l'éditeur"
    assert _erreurs_js(console_errors) == []


# -------------------------------------------------------------------------- 10


def test_url_du_texte_detectee_puis_epinglee(page, live_server, console_errors):
    d = _semer(page, live_server)
    mid = d["memo"]["id"]
    _owner(page, live_server)
    chip = _card(page, mid).locator('.murls-row .murl-detected[data-url="%s"]' % SUIVI)
    chip.first.wait_for(state="visible", timeout=5_000)
    assert chip.count() == 1, "l'URL est écrite deux fois dans le texte : UN seul chip attendu (dédup)"
    assert "dans le texte" in (chip.get_attribute("title") or "").lower()
    assert _urls_api(page, live_server, mid) == [], "une URL détectée ne doit RIEN écrire en base"

    _ouvrir_editeur_owner(page, mid)
    assert page.locator("#me-urls .murl-item").count() == 0
    pin = page.locator('#me-urls .murl-pin[data-url="%s"]' % SUIVI)
    assert pin.count() == 1, "pas de bouton « Épingler » sur l'URL du texte"
    pin.click()
    page.wait_for_selector('#me-urls .murl-item[data-url="%s"]' % SUIVI, timeout=5_000)
    assert page.locator("#me-urls .murl-pin").count() == 0, "une URL épinglée ne reste pas « dans le texte »"
    vus = _urls_api(page, live_server, mid)
    assert [u["url"] for u in vus] == [SUIVI] and vus[0]["label"] == ""

    _fermer_editeur(page, "#memo-edit-dialog")
    att = _card(page, mid).locator('.murls-row .murl-chip[data-url="%s"]' % SUIVI)
    att.wait_for(state="visible", timeout=5_000)
    assert att.count() == 1 and not att.evaluate("c => c.classList.contains('murl-detected')")
    assert _erreurs_js(console_errors) == []


# -------------------------------------------------------------------------- 11


def test_la_croix_retire_le_lien(page, live_server, console_errors):
    d = _semer(page, live_server, contenu="<p>sans URL</p>")
    mid = d["memo"]["id"]
    _ajouter_api(page, live_server, mid, "https://a.test/1", "Un")
    _ajouter_api(page, live_server, mid, "https://a.test/2", "Deux")
    _owner(page, live_server)
    assert _card(page, mid).locator(".murls-row .murl-chip").count() == 2
    _ouvrir_editeur_owner(page, mid)
    assert page.locator("#me-urls .murl-item").count() == 2
    page.locator('#me-urls .murl-item[data-url="https://a.test/1"] .murl-x').click()
    page.wait_for_selector('#me-urls .murl-item[data-url="https://a.test/1"]', state="detached", timeout=5_000)
    assert [u["url"] for u in _urls_api(page, live_server, mid)] == ["https://a.test/2"]
    _fermer_editeur(page, "#memo-edit-dialog")
    assert _attendre(page, lambda: _card(page, mid).locator(".murls-row .murl-chip").count() == 1)
    assert _erreurs_js(console_errors) == []


# -------------------------------------------------------------------------- 12


def test_la_recherche_trouve_par_le_libelle(page, live_server, console_errors):
    d = _semer(page, live_server, contenu="<p>réparation iPad</p>")
    mid = d["memo"]["id"]
    _ajouter_api(page, live_server, mid, "https://a.test/colis", "suivi colis %s" % d["k"])
    temoin = page.request.post(live_server + "/api/memos", data={
        "title": "MU témoin %s" % d["k"], "project_id": d["projet"]["id"], "content": "<p>rien</p>"}).json()
    _CREES.append("/api/memos/%d" % temoin["id"])
    _owner(page, live_server)
    champ = page.locator("#search")
    champ.fill("colis %s" % d["k"])
    # [SEARCH-ALL] en portée « Tout » les résultats vivent dans la vue Résultats (`.sr-memo`) ;
    # `m#` reste sur le board (`.task`). Les deux passent par `visibleMemos`.
    # (le board masqué garde ses `.task` dans le DOM : on ne compte que le VISIBLE)
    hit = lambda i: page.locator('.sr-memo[data-memo-id="%d"]:visible' % i)
    assert _attendre(page, lambda: hit(mid).count() == 1 and hit(temoin["id"]).count() == 0), \
        "le mémo dont seul le LIEN parle de « colis » n'est pas trouvé"
    champ.fill("m#colis %s" % d["k"])
    vis = lambda i: page.locator('.task[data-memo-id="%d"]:visible' % i)
    assert _attendre(page, lambda: vis(mid).count() >= 1 and vis(temoin["id"]).count() == 0)
    assert _erreurs_js(console_errors) == []


# -------------------------------------------------------------------------- 13


@pytest.mark.parametrize("ou,vp", [("share", BUREAU), ("share", MOBILE), ("hub", BUREAU)],
                         ids=["share-bureau", "share-mobile412", "hub-bureau"])
def test_invite_editeur_ajoute_un_lien(page, live_server, console_errors, ou, vp):
    d = _semer(page, live_server)
    mid = d["memo"]["id"]
    _invite(page, live_server, d, ou, role="editor", vp=vp)
    # la card invitée montre déjà l'URL du texte (grisée), sans rien en base
    _card(page, mid).locator('.murls-row .murl-detected[data-url="%s"]' % SUIVI).first.wait_for(state="visible", timeout=5_000)

    if ou == "share":
        page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id), el('span', ''), el('span', ''))", mid)
        sel, box = "#edit-dialog", "#q-urls"
    else:
        page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id))", mid)
        sel, box = "#ed", "#ed-urls"
    page.wait_for_selector(sel + "[open] " + box + " .murls-sec", timeout=5_000)
    page.locator(box + " .murl-url").fill("https://apple.test/guest")
    page.locator(box + " .murl-label").fill("Posé par Gaspard")
    page.locator(box + " .murl-add-btn").click()
    page.wait_for_selector(box + ' .murl-item[data-url="https://apple.test/guest"]', timeout=5_000)
    _croix_cliquable(page, box)
    vus = _urls_api(page, live_server, mid)
    assert [u["url"] for u in vus] == ["https://apple.test/guest"]
    assert "Gaspard" in vus[0]["created_by"], "la provenance invitée doit être tracée"

    # « Épingler » marche aussi chez l'invité éditeur
    page.locator(box + ' .murl-pin[data-url="%s"]' % SUIVI).click()
    page.wait_for_selector(box + ' .murl-item[data-url="%s"]' % SUIVI, timeout=5_000)
    assert len(_urls_api(page, live_server, mid)) == 2

    _fermer_editeur(page, sel)
    chip = _card(page, mid).locator('.murls-row .murl-chip[data-url="https://apple.test/guest"]')
    chip.wait_for(state="visible", timeout=5_000)
    assert "Posé par Gaspard" in chip.inner_text()
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0 or vp is BUREAU
    assert _erreurs_js(console_errors) == []


@pytest.mark.parametrize("ou", ["share", "hub"])
def test_invite_lecteur_voit_le_chip_mais_pas_le_formulaire(page, live_server, console_errors, ou):
    d = _semer(page, live_server, contenu="<p>sans URL</p>")
    mid = d["memo"]["id"]
    _ajouter_api(page, live_server, mid, "https://apple.test/owner", "Suivi owner")
    _invite(page, live_server, d, ou, role="viewer")
    chip = _card(page, mid).locator('.murls-row .murl-chip[data-url="https://apple.test/owner"]')
    chip.wait_for(state="visible", timeout=5_000)
    assert "Suivi owner" in chip.inner_text()
    assert chip.locator(".lref-x").count() == 0

    # la fiche 👁 porte la même rangée
    page.evaluate("id => openMemoView(%s(), id)" % ("shareMemoViewCfg" if ou == "share" else "hubMemoViewCfg"), mid)
    page.wait_for_selector("#memo-view-dialog[open]", timeout=5_000)
    assert page.locator('#memo-view-dialog .murls-row .murl-chip[data-url="https://apple.test/owner"]').count() == 1
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # lecteur : pas d'éditeur (share) ou éditeur en lecture seule (hub) → aucun formulaire d'ajout
    if ou == "hub":
        page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id))", mid)
        page.wait_for_selector("#ed[open]", timeout=5_000)
        assert page.locator("#ed-urls .murl-add").count() == 0, "un lecteur ne doit pas voir le formulaire"
        assert page.locator("#ed-urls .murl-pin").count() == 0
        assert page.locator("#ed-urls .murl-x").count() == 0
        page.keyboard.press("Escape")
    brut = page.evaluate("() => JSON.stringify((DATA.memos.find(x => x.id === %d) || {}).urls)" % mid)
    assert "created_by" not in brut and '"id"' not in brut, "projection invitée trop large : %s" % brut
    assert _erreurs_js(console_errors) == []
