"""[SEARCH-ALL] Scope « Tout » = une vraie page de résultats au milieu.

Brief : `docs/briefs/SEARCH-ALL.md` (Fabien, 29 sept. 2026 : « quand on cherche en Tout, je veux
tous les liens et tous les mémos, dossiers, sous-dossiers, et le texte qui matche dans un mémo, au
milieu »). La recherche active en scope Tout ouvre `state.view = 'search'` : Liens · Dossiers
(chemin) · Mémos (avec l'indice « où ça a matché »). L'effacer ramène à la vue précédente.

La base du `live_server` est partagée par toute la session : chaque test sème un décor autour d'un
MOT UNIQUE (`jeton`), pour que les comptes ne dépendent jamais des autres fichiers.
"""
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}
_BRUIT_404 = "the server responded with a status of 404"
_n = [0]
_CREES = []   # (url de suppression) — la base est PARTAGÉE : un décor qui traîne pollue les tests suivants


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    """Supprime le décor en sortie : sinon ses liens (favicons en 404) et ses mémos faussent les
    tests suivants de la session (smoke « zéro erreur », comptes de la vue Liens, cascade…)."""
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return False


def _semer(page, live_server):
    """Décor : dossier « <jeton> news » (2 mémos), « IDEE-k › <jeton> project » (1 mémo), mémo
    trouvé par sa sous-tâche, mémo trouvé par son contenu, mémo trouvé par son titre, mémo au
    contenu HTML piégé, 1 lien qui matche + 1 lien sans rapport."""
    _n[0] += 1
    k = _n[0]
    jeton = "zorb%dq%d" % (k, int(time.time()) % 1000)
    post = lambda url, d: page.request.post(live_server + url, data=d)

    def dossier(nom, parent=None):
        p = post("/api/projects", {"name": nom}).json()
        _CREES.insert(0, "/api/projects/%d" % p["id"])   # dossiers supprimés EN DERNIER
        if parent:
            r = page.request.put(live_server + "/api/projects/%d" % p["id"], data={"parent_id": parent})
            assert r.ok, r.text()
        return p

    def memo(**d):
        r = post("/api/memos", d)
        assert r.ok, r.text()
        _CREES.append("/api/memos/%d" % r.json()["id"])
        return r.json()

    news = dossier("%s news" % jeton.capitalize())
    idee = dossier("IDEE-%d" % k)
    proj = dossier("%s project" % jeton, idee["id"])
    m = {
        "a1": memo(title="alpha A1 %d" % k, content="rien", project_id=news["id"]),
        "a2": memo(title="alpha A2 %d" % k, content="rien", project_id=news["id"]),
        "b1": memo(title="beta B1 %d" % k, content="rien", project_id=proj["id"]),
        "sous": memo(title="Idées %d" % k, content="rien",
                     subtasks=[{"content": "%s sous tache" % jeton.capitalize(), "done": False}]),
        "contenu": memo(title="gamma %d" % k,
                        content="<p>Un long texte avant le mot recherché : %s, et la suite du texte.</p>" % jeton),
        "titre": memo(title="Titre %s %d" % (jeton, k), content="rien"),
        "piege": memo(title="delta %d" % k,
                      content="<p>&lt;b&gt;%s&lt;/b&gt;&lt;img src=x onerror=alert(1)&gt;</p>" % jeton),
    }
    for d in ({"name": "%s letter" % jeton.capitalize(), "url_public": "https://zorb.example.org"},
              {"name": "Sans rapport %d" % k, "url_public": "https://autre.example.org"}):
        r = post("/api/links", d)
        assert r.ok, r.text()
        _CREES.append("/api/links/%d" % r.json()["id"])
    return {"jeton": jeton, "news": news, "idee": idee, "proj": proj, "m": m}


def _ouvrir(page, live_server, vp=BUREAU):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector("#search", timeout=10_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof renderAll === 'function' && Array.isArray(state.memos) && state.memos.length")


def _chercher(page, texte):
    page.locator("#search").fill(texte)
    page.wait_for_timeout(150)


def _compte(page, sec):
    loc = page.locator('#search-board [data-sec="%s"] .sr-count' % sec)
    return int(loc.inner_text()) if loc.count() else None


def _hit(page, mid):
    """(libellé de l'indice, texte marqué) sous la card du mémo, ou None sans ligne d'indice."""
    return page.evaluate("""id => {
      const w = document.querySelector('#search-board .sr-memo[data-memo-id="' + id + '"]');
      if (!w) return 'absent';
      const h = w.querySelector('.sr-hit');
      if (!h) return null;
      const where = h.querySelector('.sr-where'), mk = h.querySelector('mark');
      return [where ? where.textContent : '', mk ? mk.textContent : '', h.textContent];
    }""", mid)


# ------------------------------------------------------------------ 1. la page de résultats


def test_tout_depuis_liens_ouvre_la_vue_resultats(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    page.evaluate("() => { state.view = 'links'; renderAll(); }")
    _chercher(page, d["jeton"])
    assert page.evaluate("() => state.view") == "search"
    assert page.locator("#search-board").is_visible(), "vue Résultats invisible"
    tete = page.locator("#search-board .sr-head").inner_text()
    assert "Résultats pour « %s »" % d["jeton"] in tete, tete
    assert (_compte(page, "links"), _compte(page, "folders"), _compte(page, "memos")) == (1, 2, 7)
    chemins = page.locator("#search-board .sr-folder .sr-path").all_inner_texts()
    assert any("IDEE-%d" % _n[0] in c and "›" in c and "%s project" % d["jeton"] in c for c in chemins), chemins
    assert _erreurs_js(console_errors) == []


def test_indice_ou_ca_a_matche(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    _chercher(page, d["jeton"])
    j = d["jeton"].lower()
    h = _hit(page, d["m"]["sous"]["id"])
    assert h and "SOUS-TÂCHE" in h[0].upper() and h[1].lower() == j, h
    h = _hit(page, d["m"]["contenu"]["id"])
    assert h and "CONTENU" in h[0].upper() and h[1].lower() == j and "texte avant" in h[2], h
    h = _hit(page, d["m"]["a1"]["id"])
    assert h and "DOSSIER" in h[0].upper() and d["news"]["name"] in h[2], h
    h = _hit(page, d["m"]["b1"]["id"])
    assert h and "DOSSIER" in h[0].upper() and "project" in h[2], h
    # Titre qui matche : pas de ligne d'indice, un <mark> dans le titre.
    assert _hit(page, d["m"]["titre"]["id"]) is None
    mk = page.locator('#search-board .sr-memo[data-memo-id="%d"] .task-title mark' % d["m"]["titre"]["id"])
    assert mk.count() == 1 and mk.inner_text().lower() == j
    assert _erreurs_js(console_errors) == []


def test_contenu_piege_reste_du_texte(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    page.evaluate("() => { window.__xss = 0; window.alert = () => { window.__xss++; }; }")
    _chercher(page, d["jeton"])
    h = _hit(page, d["m"]["piege"]["id"])
    assert h and "<b>" in h[2] and "<img" in h[2], "l'extrait doit montrer le HTML en TEXTE : %r" % (h,)
    assert page.locator("#search-board .sr-hit img, #search-board .sr-hit b").count() == 0
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__xss") == 0
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ 2. retour à la vue précédente


def test_echap_et_effacer_ramenent_la_vue_precedente(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    page.evaluate("id => { state.view = 'links'; state.memoProject = id; renderAll(); }", d["news"]["id"])
    _chercher(page, d["jeton"])
    assert page.evaluate("() => state.view") == "search"
    # Depuis Liens, le dossier retenu en mémoire ne borne PAS la recherche (tout le dashboard).
    assert _compte(page, "links") == 1 and _compte(page, "memos") == 7
    page.locator("#search").press("Escape")
    assert page.evaluate("() => [state.view, state.memoProject]") == ["links", d["news"]["id"]]
    assert page.locator("#search-board").is_hidden()
    # Idem par le bouton « Effacer la recherche ».
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    _chercher(page, d["jeton"])
    assert page.evaluate("() => state.view") == "search"
    page.locator("#search-board .sr-clear").click()
    assert page.evaluate("() => [state.view, state.memoProject, state.search]") == ["memos", "all", ""]
    assert page.locator("#search").input_value() == ""
    assert _erreurs_js(console_errors) == []


def test_chip_dossier_borne_les_resultats(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    page.evaluate("id => { state.view = 'memos'; state.memoProject = id; renderAll(); }", d["news"]["id"])
    _chercher(page, d["jeton"])
    assert page.evaluate("() => state.view") == "search"
    assert page.locator("#search-chip").is_visible(), "chip « dans : dossier » absent"
    assert (_compte(page, "links"), _compte(page, "folders"), _compte(page, "memos")) == (0, 1, 2)
    assert _erreurs_js(console_errors) == []


def test_prefixes_gardent_le_comportement_actuel(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    _chercher(page, "m#" + d["jeton"])
    assert page.evaluate("() => state.view") == "memos", "m# ne doit pas ouvrir la vue Résultats"
    _chercher(page, "")
    page.evaluate("() => { state.view = 'links'; renderAll(); }")
    _chercher(page, "l#" + d["jeton"])
    assert page.evaluate("() => [state.view, visibleLinks().length]") == ["links", 1]
    # Un préfixe tapé PENDANT la vue Résultats ramène à la vue précédente, filtrée.
    _chercher(page, d["jeton"])
    assert page.evaluate("() => state.view") == "search"
    _chercher(page, "l#" + d["jeton"])
    assert page.evaluate("() => state.view") == "links"
    assert _erreurs_js(console_errors) == []


def test_clics_dossier_et_memo(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server)
    _chercher(page, d["jeton"])
    page.locator("#search-board .sr-folder", has_text="%s project" % d["jeton"]).click()
    assert page.evaluate("() => [state.view, state.memoProject]") == ["memos", d["proj"]["id"]]
    assert page.evaluate("() => state.search") == "", "ouvrir un dossier quitte la recherche"
    page.evaluate("() => { state.memoProject = 'all'; renderAll(); }")   # sinon la recherche serait bornée au dossier
    _chercher(page, d["jeton"])
    page.locator('#search-board .sr-memo[data-memo-id="%d"] .tedit' % d["m"]["contenu"]["id"]).click()
    page.wait_for_selector("#memo-edit-dialog[open]", timeout=5_000)
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ 3. mobile : même moteur


def test_mobile_feuille_et_vue_memes_comptes(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir(page, live_server, MOBILE)
    page.locator("#search").click()
    page.wait_for_selector("#search-sheet[open]", timeout=5_000)
    page.fill("#search-sheet input[type=text]", d["jeton"])
    page.wait_for_timeout(300)
    n_feuille = page.locator("#search-sheet .ss-item").count()
    titres = page.locator("#search-sheet .ss-item .ss-t").all_inner_texts()
    assert any("letter" in t for t in titres) and any("project" in t for t in titres), titres
    page.keyboard.press("Escape")   # ferme la feuille ; la recherche reste active
    assert _attendre(page, lambda: page.locator("#search-sheet[open]").count() == 0)
    assert page.evaluate("() => state.search") == d["jeton"], "fermer la feuille a vidé la recherche"
    assert page.evaluate("() => state.view") == "search"
    assert page.locator("#search-board").is_visible()
    n_vue = _compte(page, "links") + _compte(page, "folders") + _compte(page, "memos")
    assert n_feuille == n_vue == 10, (n_feuille, n_vue)
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0
    assert _erreurs_js(console_errors) == []
