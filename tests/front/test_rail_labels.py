"""[RAIL-LABELS] Le rail d'icônes devient lisible, et l'œil masque vraiment la barre.

Brief : `docs/briefs/RAIL-LABELS.md` (demande Fabien du 29 sept. 2026, maquette validée).

Ce que ces parcours PROTÈGENT, en rail (`nav#sidebar.sb-rail`, 64 px, desktop) :

- **une infobulle maison** (`#rail-tip`) nomme l'icône survolée OU focalisée au clavier, avec son
  compteur ; les `title` natifs sont retirés en rail (sinon double bulle) ;
- **l'initiale** d'un dossier sans emoji s'affiche sur sa pastille — en rail seulement ;
- **les replis sont respectés** : le rail n'aplatit plus l'arbre (47 pastilles anonymes en prod) ;
- **l'œil masque vraiment la barre** : avant, `.sb-rail` (déclarée après `.sb-hidden`, même
  spécificité) gardait la barre à 64 px ; le hamburger, sans objet, disparaît avec elle.
"""
import pytest
import requests
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}

_PROJETS, _MEMOS = [], []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    _PROJETS.clear(); _MEMOS.clear()
    yield
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
            requests.delete(live_server + "/api/trash/%d" % mid, timeout=5)
        except Exception:
            pass
    for pid in reversed(_PROJETS):
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    _PROJETS.clear(); _MEMOS.clear()


def _projet(live_server, nom, parent=None, **extra):
    r = requests.post(live_server + "/api/projects", json={"name": nom, **extra}, timeout=5)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    if parent:
        # `POST /api/projects` crée à la racine et ignore `parent_id` : on déplace ensuite.
        r = requests.put(live_server + "/api/projects/%d" % pid, json={"parent_id": parent}, timeout=5)
        assert r.status_code == 200, r.text
    return pid


def _memo(live_server, titre, pid):
    r = requests.post(live_server + "/api/memos",
                      json={"title": titre, "content": titre + " — décor RL", "project_id": pid}, timeout=5)
    assert r.status_code in (200, 201), r.text
    _MEMOS.append(r.json()["id"])


def _semer(live_server):
    """3 racines : une avec emoji, « Maison » (sans emoji, enfant « Cuisine »), une repliée."""
    voyage = _projet(live_server, "RL Voyage", emoji="✈️")
    maison = _projet(live_server, "Maison")
    cuisine = _projet(live_server, "Cuisine", parent=maison)
    garage = _projet(live_server, "RL Garage")
    outils = _projet(live_server, "RL Outils", parent=garage)
    _memo(live_server, "RL m1", maison)
    _memo(live_server, "RL m2", maison)
    return {"voyage": voyage, "maison": maison, "cuisine": cuisine, "garage": garage, "outils": outils}


def _prefs(page, **kv):
    """localStorage posé AVANT les scripts, une seule fois par onglet (un rechargement le garde)."""
    sets = "".join("localStorage.setItem(%r, %r);" % (k, v) for k, v in kv.items())
    page.add_init_script(
        "try { if (!sessionStorage.getItem('rl-init')) { sessionStorage.setItem('rl-init', '1');"
        + sets + " } } catch (e) {}")


def _boot(page, live_server):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("nav#sidebar .cat-item", state="attached", timeout=10_000)
    page.wait_for_timeout(700)


def _item(page, pid):
    return page.locator("nav#sidebar .cat-item[data-proj-id='%d']" % pid)


_BRUIT_404 = "the server responded with a status of 404"


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- 1


def test_infobulle_au_survol_et_pas_de_title(page, live_server, console_errors):
    ids = _semer(live_server)
    _prefs(page, sbRail="1")
    _boot(page, live_server)
    tip = page.locator("#rail-tip")
    _item(page, ids["maison"]).hover()
    expect(tip).to_be_visible()
    texte = tip.inner_text().strip()
    assert texte.startswith("Maison"), texte
    assert "2" in texte.replace("Maison", ""), "le compteur manque : %r" % texte
    page.mouse.move(700, 400)
    expect(tip).to_be_hidden()
    avec_title = page.evaluate(
        "() => [...document.querySelectorAll('nav#sidebar .cat-item')].filter(e => e.hasAttribute('title')).length")
    assert avec_title == 0, "%d .cat-item gardent un title natif en rail" % avec_title
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 2


def test_initiale_sur_la_pastille(page, live_server, console_errors):
    ids = _semer(live_server)
    _prefs(page, sbRail="1")
    _boot(page, live_server)
    assert _item(page, ids["maison"]).locator(".cat-dot").inner_text().strip() == "M"
    # Un dossier à emoji n'a pas de pastille, donc pas d'initiale.
    assert _item(page, ids["voyage"]).locator(".cat-dot").count() == 0
    # Mode normal : pastille vide.
    page.locator("#sidebar-rail-btn").click()
    page.wait_for_timeout(600)
    assert page.evaluate("() => document.getElementById('sidebar').classList.contains('sb-rail')") is False
    assert _item(page, ids["maison"]).locator(".cat-dot").inner_text().strip() == ""
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 3


def test_le_rail_respecte_les_replis(page, live_server, console_errors):
    ids = _semer(live_server)
    _prefs(page, sbRail="1", **{"sbProjOpen:%d" % ids["garage"]: "0"})
    _boot(page, live_server)
    assert _item(page, ids["outils"]).count() == 0, "dossier replié : son enfant ne doit pas s'afficher"
    assert _item(page, ids["cuisine"]).count() == 1, "dossier ouvert : son enfant s'affiche"

    # Mode normal : ⇅ « tout replier », puis retour en rail → replis respectés.
    page.locator("#sidebar-rail-btn").click()
    page.wait_for_timeout(600)
    page.locator("nav#sidebar .sb-section-head[data-section='dossiers'] .sb-section-add").click()
    page.wait_for_timeout(250)
    page.locator("#sidebar-rail-btn").click()
    page.wait_for_timeout(600)
    assert page.evaluate("() => document.getElementById('sidebar').classList.contains('sb-rail')") is True
    assert _item(page, ids["cuisine"]).count() == 0, "⇅ replié puis rail : l'enfant réapparaît"
    assert _item(page, ids["maison"]).count() == 1
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 4


def test_oeil_masque_vraiment_en_rail(page, live_server, console_errors):
    _semer(live_server)
    _prefs(page, sbRail="1", sbHidden="0")
    _boot(page, live_server)
    largeur = lambda: page.evaluate("() => document.getElementById('sidebar').getBoundingClientRect().width")
    rail_btn = page.locator("#sidebar-rail-btn")
    assert round(largeur()) == 64
    page.locator("#sidebar-eye-btn").click()
    page.wait_for_timeout(700)
    assert largeur() == 0, "œil en rail : la barre reste à %s px" % largeur()
    expect(rail_btn).to_be_hidden()
    assert page.evaluate("() => localStorage.getItem('sbHidden')") == "1"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)
    assert largeur() == 0, "rechargé : la barre doit rester masquée"
    expect(rail_btn).to_be_hidden()

    page.locator("#sidebar-eye-btn").click()
    page.wait_for_timeout(800)
    assert round(largeur()) == 64, "rouvert : le rail doit être conservé (%s px)" % largeur()
    expect(rail_btn).to_be_visible()
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 5


def test_infobulle_au_focus_clavier(page, live_server, console_errors):
    ids = _semer(live_server)
    _prefs(page, sbRail="0")
    _boot(page, live_server)
    # Passage en rail par le hamburger : seul `renderSidebar` tourne (pas `renderAll`/`applyA11y`),
    # les items doivent pourtant rester atteignables au clavier.
    page.locator("#sidebar-rail-btn").click()
    page.wait_for_timeout(600)
    item = _item(page, ids["maison"])
    item.evaluate("e => e.previousElementSibling ? e.previousElementSibling.focus() : null")
    page.keyboard.press("Tab")
    assert page.evaluate("(id) => document.activeElement.dataset.projId === String(id)", ids["maison"]), \
        "Tab n'atteint pas l'item du rail"
    tip = page.locator("#rail-tip")
    expect(tip).to_be_visible()
    assert tip.inner_text().strip().startswith("Maison")
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 6


def test_pas_d_infobulle_en_mode_normal(page, live_server, console_errors):
    ids = _semer(live_server)
    _prefs(page, sbRail="0")
    _boot(page, live_server)
    _item(page, ids["maison"]).hover()
    page.wait_for_timeout(300)
    tip = page.locator("#rail-tip")
    assert tip.count() == 0 or not tip.is_visible(), "infobulle affichée hors rail"
    assert _item(page, ids["maison"]).get_attribute("title"), "mode normal : le title natif doit rester"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 7


def test_le_rail_defile_a_la_molette(page, live_server, console_errors):
    """Renvoi Cowork : `.sb-rail { overflow: hidden }` écrasait l'`overflow-y: auto` desktop —
    en prod 1245 px de contenu pour 848 visibles, les derniers dossiers étaient inatteignables."""
    for i in range(30):
        _projet(live_server, "RL S%02d" % i)
    _prefs(page, sbRail="1")
    _boot(page, live_server)
    nav = page.locator("nav#sidebar")
    assert nav.evaluate("e => e.scrollHeight > e.clientHeight"), "décor : le rail devrait déborder"
    box = nav.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 5000)
    page.wait_for_timeout(400)
    assert nav.evaluate("e => e.scrollTop") > 0, "la molette ne fait pas défiler le rail"
    assert nav.evaluate("e => e.scrollWidth <= e.clientWidth"), "défilement horizontal dans le rail"
    assert round(box["width"]) == 64, "le rail doit garder 64 px (%s)" % box["width"]

    dernier = page.locator("nav#sidebar .cat-item").last
    d = dernier.bounding_box()
    assert d["y"] + d["height"] <= box["y"] + box["height"] + 1, "dernier item inatteignable"
    # Les lanceurs flottants (✏️ ¥€ ⏱, fixed en bas à gauche) ne doivent pas le recouvrir.
    assert dernier.evaluate("""e => { const r = e.getBoundingClientRect();
      const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!h && e.contains(h); }"""), "dernier item recouvert par un lanceur flottant"
    dernier.hover()
    tip = page.locator("#rail-tip")
    expect(tip).to_be_visible()
    t = tip.bounding_box()
    assert abs((t["y"] + t["height"] / 2) - (d["y"] + d["height"] / 2)) < 4, \
        "l'infobulle ne suit pas l'item après défilement"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 8


def test_mode_normal_dernier_item_au_dessus_des_lanceurs(page, live_server, console_errors):
    """Demande Fabien (29 sept.) : en mode NORMAL aussi, les lanceurs flottants (✏️ ¥€ ⏱, fixed
    en bas à gauche) recouvraient le bas de la sidebar (« Fichiers », « Inbox »)."""
    for i in range(30):
        _projet(live_server, "RL N%02d" % i)
    _prefs(page, sbRail="0")
    _boot(page, live_server)
    nav = page.locator("nav#sidebar")
    assert nav.evaluate("e => e.scrollHeight > e.clientHeight"), "décor : la sidebar devrait déborder"
    box = nav.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 20000)
    page.wait_for_timeout(400)
    # Géométrie plutôt que hit-test (un item encore en fondu GSAP fausse elementFromPoint) :
    # le dernier item ne doit croiser AUCUN lanceur visible.
    dessus = page.locator("nav#sidebar .cat-item").last.evaluate("""e => {
      const r = e.getBoundingClientRect();
      return ['qm-launch', 'fx-launch', 'pomo-launch'].filter(id => {
        const l = document.getElementById(id);
        if (!l || l.hidden || !l.getClientRects().length) return false;
        const b = l.getBoundingClientRect();
        return b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top;
      }); }""")
    assert dessus == [], "dernier item recouvert par : %s" % dessus
    assert _erreurs_js(console_errors) == []
