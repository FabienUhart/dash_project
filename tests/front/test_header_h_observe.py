"""[HEADER-H-OBSERVE] `--header-h` suit le header quand il grandit APRÈS le chargement.

Le défaut (prod V28.1.264) : `syncHeaderHeight` n'était appelée qu'au load et au resize. Quand la
3e ligne d'horloge `#clock-extra` (« 🇯🇵 Tokyo 18:52 ») apparaît plus tard, le header grandit mais
la variable reste à l'ancienne hauteur : `nav#sidebar`, `aside#memo-panel` et l'en-tête MÉMOS
(collés sur `--header-h`) glissent SOUS le header, boutons ⤢ ⤓ ⇅ ＋ coupés.

Ces parcours font grandir le header SANS resize de fenêtre, puis mesurent les boîtes : ce qui est
épinglé sous le header doit commencer sous son bord bas. ⚠ Fenêtre DÉFILÉE obligatoire : en haut
de page les colonnes sont encore dans le flux, sous le header, et le test serait vert pour la
mauvaise raison (prouvé : sans défilement, il passait sur le code fautif).
"""
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1400, "height": 800}


def _attendre(cond, timeout_ms=3_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


def _bas_header(page):
    return page.evaluate("document.querySelector('header').getBoundingClientRect().bottom")


def _haut(page, selecteur):
    return page.evaluate("document.querySelector(%r).getBoundingClientRect().top" % selecteur)


def _defiler(page):
    # Mi-page, pas le fond : au fond, un élément sticky bute sur le bas de son conteneur et
    # remonte tout seul — le test mesurerait cet effet-là, pas --header-h.
    page.evaluate("window.scrollTo(0, 400)")
    assert page.evaluate("window.scrollY") > 100, "la page ne défile pas : décor trop maigre"


def test_owner_memo_header_stays_below_a_growing_header(live_server, page):
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    liens = []
    for i in range(30):
        r = page.request.post(live_server + "/api/links",
                              data={"name": "HH lien %02d" % i, "descr": "de quoi défiler"})
        assert r.ok, r.text()
        liens.append(r.json()["id"])
    try:
        _owner(page, live_server, erreurs)
    finally:
        for lid in liens:
            page.request.delete(live_server + "/api/links/%d" % lid)


def _owner(page, live_server, erreurs):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector("#memo-details summary", timeout=10_000)
    page.wait_for_load_state("networkidle")
    _defiler(page)

    avant = _bas_header(page)
    # La 3e ligne d'horloge apparaît, comme le fait `updateClock` quand un fuseau voyage est posé.
    # La hauteur minimale garantit que le header grandit vraiment, quelle que soit la police.
    page.evaluate("""() => {
        const e = document.getElementById('clock-extra');
        e.style.display = '';
        e.style.minHeight = '40px';
        e.textContent = '🇯🇵 Tokyo 18:52';
    }""")
    apres = _bas_header(page)
    assert apres > avant + 10, "le décor n'a pas fait grandir le header (%s → %s)" % (avant, apres)

    ok = _attendre(lambda: _haut(page, "#memo-details summary") >= _bas_header(page) - 1
                   and _haut(page, "nav#sidebar") >= _bas_header(page) - 1)
    assert ok, ("l'en-tête MÉMOS (%s) ou la sidebar (%s) passe sous le header (bas = %s) : "
                "--header-h = %s n'a pas suivi"
                % (_haut(page, "#memo-details summary"), _haut(page, "nav#sidebar"),
                   _bas_header(page),
                   page.evaluate("getComputedStyle(document.documentElement)"
                                 ".getPropertyValue('--header-h')")))
    assert not erreurs, erreurs


def test_guest_sidebar_stays_below_a_growing_header(live_server, page):
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier header grandi"}).json()
    for i in range(25):
        page.request.post(live_server + "/api/memos",
                          data={"content": "Mémo du header %02d" % i, "project_id": proj["id"]})
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"],
                                 "role": "reader"}).json()
    try:
        page.set_viewport_size(BUREAU)
        page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#snav:not([hidden])", timeout=10_000)
        _defiler(page)

        avant = _bas_header(page)
        page.evaluate("document.querySelector('header h1').style.minHeight = '90px'")
        apres = _bas_header(page)
        assert apres > avant + 10, "le décor n'a pas fait grandir le header"

        ok = _attendre(lambda: _haut(page, "#snav") >= _bas_header(page) - 1)
        assert ok, "la sidebar invitée (%s) passe sous le header (bas = %s)" % (
            _haut(page, "#snav"), _bas_header(page))
        assert not erreurs, erreurs
    finally:
        page.request.delete(live_server + "/api/projects/%d" % proj["id"])


# ── 2e cause (passe Cowork) : le footer allongeait la page ────────────────────────────────────
# `#app-footer` vivait APRÈS `#layout` : body = header + (100dvh − header) + footer, donc la
# FENÊTRE défilait de la hauteur du footer. Une molette sur `main` faisait défiler la page, et les
# colonnes sticky — bornées à leur conteneur — remontaient sous le header d'autant.

def _boot_owner(page, live_server, viewport=BUREAU):
    page.set_viewport_size(viewport)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector("#memo-panel", timeout=10_000)
    page.wait_for_load_state("networkidle")


def test_short_page_does_not_scroll_past_the_viewport(live_server, page):
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    _boot_owner(page, live_server)
    page.wait_for_selector("#memo-details summary", timeout=10_000)
    fond = page.evaluate("""() => Math.max(0, ...[...document.querySelector('main').children]
        .filter(e => e.offsetParent && e.id !== 'app-footer')
        .map(e => e.getBoundingClientRect().bottom))""")
    assert fond < BUREAU["height"] - 60, \
        "décor trop riche (contenu de main jusqu'à %s px) : il doit tenir dans l'écran" % fond
    page.evaluate("window.scrollBy(0, 500)")
    assert page.evaluate("window.scrollY") == 0, (
        "la fenêtre défile de %s px : scrollHeight %s > innerHeight %s"
        % (page.evaluate("window.scrollY"),
           page.evaluate("document.documentElement.scrollHeight"),
           page.evaluate("innerHeight")))
    assert _haut(page, "#memo-details summary") >= _bas_header(page) - 1
    assert _haut(page, "nav#sidebar") >= _bas_header(page) - 1
    # Le footer reste visible, en bas de l'écran.
    bas = page.evaluate("document.getElementById('app-footer').getBoundingClientRect().bottom")
    assert abs(bas - BUREAU["height"]) <= 1, "footer pas en bas de l'écran (%s)" % bas
    assert not erreurs, erreurs


def test_long_page_bottom_keeps_columns_below_header(live_server, page):
    """Page longue défilée jusqu'au FOND : c'est là que le footer poussait le conteneur et que
    les colonnes sticky remontaient sous le header."""
    liens = []
    for i in range(30):
        r = page.request.post(live_server + "/api/links",
                              data={"name": "HF lien %02d" % i, "descr": "de quoi défiler"})
        assert r.ok, r.text()
        liens.append(r.json()["id"])
    try:
        _boot_owner(page, live_server)
        page.wait_for_selector("#memo-details summary", timeout=10_000)
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        assert page.evaluate("window.scrollY") > 100, "la page ne défile pas : décor trop maigre"
        assert _haut(page, "#memo-details summary") >= _bas_header(page) - 1, \
            "au fond de page, l'en-tête MÉMOS (%s) passe sous le header (%s)" % (
                _haut(page, "#memo-details summary"), _bas_header(page))
        assert _haut(page, "nav#sidebar") >= _bas_header(page) - 1
        # Le footer est au fond de main, sans recouvrir la dernière card.
        pied = page.evaluate("document.getElementById('app-footer').getBoundingClientRect().top")
        dernier = page.evaluate("""() => { const c = [...document.querySelectorAll('main .card')]
            .filter(e => e.offsetParent); return c.length ? c[c.length-1].getBoundingClientRect().bottom : 0 }""")
        assert dernier <= pied + 0.5, "le footer recouvre la dernière card (%s > %s)" % (dernier, pied)
    finally:
        for lid in liens:
            page.request.delete(live_server + "/api/links/%d" % lid)


def test_mobile_footer_stays_at_page_end(live_server, page):
    _boot_owner(page, live_server, {"width": 420, "height": 800})
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    r = page.evaluate("""() => {
        const f = document.getElementById('app-footer').getBoundingClientRect();
        return [f.bottom, f.width, document.documentElement.scrollHeight - scrollY];
    }""")
    assert abs(r[0] - r[2]) <= 1, "footer pas en fin de page mobile (%s)" % r
    assert r[1] >= 419, "footer plus pleine largeur en mobile (%s px)" % r[1]
