"""[MEMO-PANEL-DESKTOP] La colonne MÉMOS est TOUJOURS ouverte en desktop (> 900 px).

Régression de [MOBILE-NAV] (V28.1) : la clé `dash:memoPanelOpen` (repli mémorisé du bloc MÉMOS)
devait ne servir qu'au téléphone. Elle était lue aussi en desktop : posée à « 0 » depuis un
mobile sur le même navigateur (ici par une passe Cowork mobile), elle chargeait la colonne
REPLIÉE à 1280 px — et le clic sur le summary, intercepté en desktop (il bascule la vue Mémos),
ne la rouvrait jamais : colonne vide coincée.

Ce que ces parcours PROTÈGENT :

- **desktop** : la clé n'est ni lue (test 1) ni écrite (test 2) ;
- **mobile** : la clé reste honorée (test 3, non-régression [MOBILE-NAV]) ;
- **bascule mobile → desktop** dans la même session : la colonne se rouvre, et cette réouverture
  forcée n'écrase pas le choix mobile (test 4).
"""
import pytest

pytestmark = pytest.mark.e2e

MOBILE = {"width": 412, "height": 915}
BUREAU = {"width": 1280, "height": 800}
CLE = "dash:memoPanelOpen"
NB = 3

_MEMOS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    _MEMOS.clear()
    yield
    import requests
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
            requests.delete(live_server + "/api/trash/%d" % mid, timeout=5)
        except Exception:
            pass
    _MEMOS.clear()


def _semer(live_server):
    import requests
    for i in range(NB):
        r = requests.post(live_server + "/api/memos",
                          json={"content": "MPD note %d" % i}, timeout=5)
        assert r.status_code in (200, 201), r.text
        _MEMOS.append(r.json()["id"])


def _poser_cle(page, valeur):
    # Posée AVANT tout script de la page : c'est l'état d'un navigateur qui a déjà servi en mobile.
    page.add_init_script(
        "try { if (!sessionStorage.getItem('mpd-init')) {"
        "  sessionStorage.setItem('mpd-init', '1');"
        "  localStorage.setItem(%r, %r); } } catch (e) {}" % (CLE, valeur))


def _boot(page, live_server, viewport):
    page.set_viewport_size(viewport)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def _ouvert(page):
    return page.evaluate("() => document.getElementById('memo-details').open")


def _cle(page):
    return page.evaluate("(k) => localStorage.getItem(k)", CLE)


def _memos_visibles(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#memos *')]"
        "  .filter(e => e.children.length === 0 && /MPD note/.test(e.textContent)"
        "            && e.getClientRects().length > 0).length")


_BRUIT_404 = "the server responded with a status of 404"


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def test_desktop_ignore_la_cle_a_zero(page, live_server, console_errors):
    _semer(live_server)
    _poser_cle(page, "0")
    _boot(page, live_server, BUREAU)
    assert _ouvert(page) is True, "clé mobile « 0 » lue en desktop : colonne MÉMOS repliée"
    assert _memos_visibles(page) >= NB, "les mémos ne sont pas visibles dans la colonne"
    assert _erreurs_js(console_errors) == []


def test_desktop_n_ecrit_pas_la_cle(page, live_server, console_errors):
    _semer(live_server)
    _poser_cle(page, "0")
    _boot(page, live_server, BUREAU)
    page.locator("#memo-details > summary").click()
    page.wait_for_timeout(300)
    assert _ouvert(page) is True
    assert _cle(page) == "0", "le desktop a réécrit la préférence mobile"
    assert _erreurs_js(console_errors) == []


def test_mobile_honore_la_cle(page, live_server, console_errors):
    _semer(live_server)
    _poser_cle(page, "0")
    _boot(page, live_server, MOBILE)
    assert _ouvert(page) is False, "le repli mémorisé en mobile n'est plus honoré"
    assert _erreurs_js(console_errors) == []


def test_bascule_mobile_vers_desktop_rouvre(page, live_server, console_errors):
    _semer(live_server)
    _poser_cle(page, "0")
    _boot(page, live_server, MOBILE)
    assert _ouvert(page) is False
    page.set_viewport_size(BUREAU)
    page.wait_for_timeout(400)
    assert _ouvert(page) is True, "passage en desktop : la colonne reste repliée"
    assert _memos_visibles(page) >= NB
    assert _cle(page) == "0", "la réouverture forcée desktop a écrasé le choix mobile"
    page.set_viewport_size(MOBILE)
    page.wait_for_timeout(400)
    assert _ouvert(page) is False, "retour en mobile : le choix mémorisé est perdu"
    assert _erreurs_js(console_errors) == []
