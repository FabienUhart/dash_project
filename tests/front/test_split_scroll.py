"""[SPLIT-SCROLL] La colonne MÉMOS défile toute seule (propriétaire, desktop).

Le défaut mesuré : `aside#memo-panel` n'a ni hauteur ni `overflow`, donc c'est la FENÊTRE qui
défile. Molette sur les mémos → le board du milieu part avec eux, et inversement. La sidebar,
elle, a son propre défileur depuis [SIDEBAR-TREE] : on lui donne le même gabarit.

Ces parcours mesurent le DÉCOUPAGE, pas la présence d'une règle CSS : on regarde qui bouge —
`#memo-panel.scrollTop` d'un côté, `window.scrollY` de l'autre — après une vraie molette posée
au-dessus de la bonne colonne.
"""
import os as _os

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1400, "height": 800}
MOBILE = {"width": 420, "height": 800}

_LIENS = []
_MEMOS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    """Le `live_server` est session-scoped : ce que ce fichier crée doit disparaître avec lui.

    Leçon payée en [LINK-OG] — des liens laissés derrière faisaient 404 sur leur favicon dans la
    console de TOUS les tests suivants, qui rougissaient sans avoir rien à se reprocher.
    """
    _LIENS.clear(); _MEMOS.clear()
    yield
    import requests
    for lid in _LIENS:
        try:
            requests.delete(live_server + "/api/links/%d" % lid, timeout=5)
        except Exception:
            pass
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
        except Exception:
            pass
    _LIENS.clear(); _MEMOS.clear()


def _semer(live_server, liens=26, memos=30):
    """Assez de matière pour que les DEUX colonnes débordent : sans débordement, tout test de
    défilement est vert pour la mauvaise raison (rien ne peut bouger nulle part)."""
    import requests
    for i in range(liens):
        r = requests.post(live_server + "/api/links",
                          json={"name": "SS lien %02d" % i, "descr": "colonne du milieu"},
                          timeout=5)
        assert r.status_code == 201, r.text
        _LIENS.append(r.json()["id"])
    for i in range(memos):
        r = requests.post(live_server + "/api/memos",
                          json={"content": "SS memo %02d — de quoi faire deborder la colonne" % i},
                          timeout=5)
        assert r.status_code in (200, 201), r.text
        _MEMOS.append(r.json()["id"])


def _boot(page, live_server, viewport=BUREAU):
    page.set_viewport_size(viewport)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    page.wait_for_selector("#memo-panel", timeout=10_000)
    page.wait_for_load_state("networkidle")


def _molette_sur(page, selecteur, dy=2000):
    """Pose la souris au CENTRE de l'élément visé, puis tourne la molette. Le centre compte :
    une molette lancée ailleurs part sur le mauvais défileur et le test ne prouve plus rien."""
    boite = page.locator(selecteur).first.bounding_box()
    assert boite, "%s n'a pas de boîte : rien à survoler" % selecteur
    page.mouse.move(boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2)
    page.mouse.wheel(0, dy)
    page.wait_for_timeout(250)


def _etat(page):
    return page.evaluate("""() => {
      const p = document.getElementById('memo-panel');
      return {
        panel: p.scrollTop,
        panelMax: p.scrollHeight - p.clientHeight,
        fenetre: Math.round(window.scrollY),
        overflowY: getComputedStyle(p).overflowY,
      };
    }""")


def _stable(page, lire, essais=25):
    """Attend que la valeur cesse de bouger. `behavior:'smooth'` n'est pas instantané dans un
    navigateur piloté : comparer trop tôt, c'est mesurer le milieu d'une animation."""
    precedent = None
    for _ in range(essais):
        courant = lire()
        if courant == precedent:
            return courant
        precedent = courant
        page.wait_for_timeout(120)
    return precedent


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    """Erreurs de console, débarrassées du seul bruit attendu : le 404 de `/api/favicon/<id>`.

    Chaque card de lien demande son favicon ; le navigateur est coupé du réseau (garde e2e) et le
    serveur ne peut pas davantage aller le chercher. La ligne de console ne dit pas QUELLE
    ressource a manqué — on ne la retire donc qu'après avoir vérifié, sur les réponses réelles,
    qu'aucun AUTRE 404 n'a eu lieu.
    """
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- #

def test_memo_panel_scrolls_independently(page, live_server, console_errors, urls_404):
    """#1, LE test du lot : la molette sur les mémos ne doit bouger QUE les mémos."""
    _semer(live_server)
    _boot(page, live_server)

    depart = _etat(page)
    assert depart["overflowY"] == "auto", \
        "la colonne mémos n'a pas son propre défileur (overflow-y = %s)" % depart["overflowY"]
    assert depart["panelMax"] > 0, "la colonne mémos ne déborde pas : le test ne prouverait rien"

    _molette_sur(page, "#memo-panel")
    apres = _etat(page)

    assert apres["panel"] > 0, "la colonne mémos n'a pas défilé"
    assert apres["fenetre"] == 0, \
        "la molette sur les mémos a entraîné la page (scrollY = %s)" % apres["fenetre"]

    # Le liseré : le `padding` de l'aside fait partie du scrollport, donc sans précaution les
    # mémos défilent DERRIÈRE une bande visible au-dessus de l'en-tête collant (12 px, mesurés
    # avant correctif) et sous la note rapide. Les deux collants doivent affleurer les bords.
    bandes = page.evaluate("""() => {
      const p = document.getElementById('memo-panel').getBoundingClientRect();
      const s = document.querySelector('#memo-details summary').getBoundingClientRect();
      const q = document.getElementById('memo-quick-wrap').getBoundingClientRect();
      return { haut: +(s.top - p.top).toFixed(1), bas: +(p.bottom - q.bottom).toFixed(1) };
    }""")
    assert bandes["haut"] <= 1, \
        "liseré de %spx au-dessus de l'en-tête collant : les mémos passent derrière" % bandes["haut"]
    assert bandes["bas"] <= 1, \
        "liseré de %spx sous la note rapide : les mémos passent derrière" % bandes["bas"]

    # `overscroll-behavior: contain` : ARRIVÉE EN BOUT de colonne, la molette doit s'arrêter là
    # au lieu de « déborder » sur la page. C'est le seul moment où la propriété se manifeste —
    # tant que la colonne a de la course devant elle, elle absorbe tout et la règle ne sert à
    # rien. On va donc d'abord au fond, puis on insiste.
    page.evaluate("() => { const p = document.getElementById('memo-panel');"
                  "         p.scrollTop = p.scrollHeight; }")
    page.wait_for_timeout(150)
    _molette_sur(page, "#memo-panel", 1200)
    assert _etat(page)["fenetre"] == 0, (
        "la molette a débordé de la colonne sur la page une fois en bout de course "
        "(overscroll-behavior: contain manquant ?)")


def test_board_scroll_does_not_move_memos(page, live_server, console_errors, urls_404):
    """#2, la réciproque : la molette sur le board ne doit pas emporter les mémos."""
    _semer(live_server)
    _boot(page, live_server)
    assert page.evaluate("() => document.documentElement.scrollHeight > window.innerHeight"), \
        "le board ne déborde pas : le test ne prouverait rien"

    _molette_sur(page, "main")
    apres = _etat(page)

    assert apres["fenetre"] > 0, "le board n'a pas défilé"
    assert apres["panel"] == 0, \
        "la molette sur le board a entraîné les mémos (scrollTop = %s)" % apres["panel"]
    assert _erreurs_js(console_errors, urls_404) == []


def test_memo_jump_targets_panel(page, live_server, console_errors, urls_404):
    """#3 : ⤓ vise désormais la COLONNE, plus la page — et ⤒ la ramène en haut."""
    _semer(live_server)
    _boot(page, live_server)
    bouton = page.locator("#memo-jump-btn")
    assert bouton.inner_text().strip() == "⤓"

    bouton.click()
    bas = _stable(page, lambda: _etat(page)["panel"])
    etat = _etat(page)
    assert bas >= etat["panelMax"] - 4, \
        "⤓ n'a pas descendu la colonne (%s au lieu de ~%s)" % (bas, etat["panelMax"])
    assert etat["fenetre"] == 0, "⤓ a fait défiler la PAGE au lieu de la colonne"
    assert bouton.inner_text().strip() == "⤒", "le libellé n'a pas basculé en ⤒"

    bouton.click()
    haut = _stable(page, lambda: _etat(page)["panel"])
    assert haut == 0, "⤒ n'a pas remonté la colonne (scrollTop = %s)" % haut
    assert _etat(page)["fenetre"] == 0
    assert _erreurs_js(console_errors, urls_404) == []


def test_mobile_layout_is_untouched(page, live_server, console_errors, urls_404):
    """#4, non-régression : en empilé (≤ 900 px) la colonne redevient un bloc de page — pas de
    défileur propre, et le ⤓ garde son geste borné au bloc ([MEMO-JUMP-MOBILE])."""
    _semer(live_server)
    _boot(page, live_server, MOBILE)

    etat = _etat(page)
    assert etat["overflowY"] == "visible", \
        "un défileur propre s'est invité en mobile (overflow-y = %s)" % etat["overflowY"]
    assert page.evaluate(
        "() => getComputedStyle(document.querySelector('#memo-details summary')).position"
    ) == "static", "le summary est resté collant en mobile"

    page.locator("#memo-jump-btn").click()
    fin = _stable(page, lambda: round(page.evaluate("() => window.scrollY")))
    assert fin > 0, "en mobile, ⤓ doit faire défiler la PAGE jusqu'au bloc mémos"
    assert _etat(page)["panel"] == 0, "le bloc mémos ne doit pas avoir de défilement propre"
    assert _erreurs_js(console_errors, urls_404) == []
