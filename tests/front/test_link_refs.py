"""[LINK-REFS] Front : relier un lien à un mémo ou un dossier, et s'y rendre.

Brief : `docs/briefs/LINK-REFS.md` + son addendum du 25 sept. (filtre « Reliés » dans la vue
Liens). Le back est couvert par `tests/back/test_link_refs.py` ; ici on éprouve ce qu'on VOIT.

Ce que ces parcours PROTÈGENT :

- **la relation se voit des deux côtés** : chip 🔗 sur la card du mémo, chips 📝/📁 sur la card
  du lien — sinon « relié » resterait une donnée sans surface ;
- **deux gestes, jamais d'ambiguïté** (décision 1 du brief) : cliquer le chip mène à la CARD du
  lien, le ↗ ouvre le site. Un seul geste pour les deux serait un piège ;
- **le filtre « Reliés » dit la vérité en direct** (addendum) : le compteur est calculé sur tous
  les liens, et retirer une relation fait basculer le lien de camp sans rechargement ;
- **l'invité ne reçoit qu'une projection** : il voit le nom et peut ouvrir le site, mais n'a ni
  « + relier » ni ✕ — et un service du LAN (sans `url_public`) ne lui est pas montré du tout.
"""
import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1500, "height": 1000}

_LIENS, _MEMOS, _PROJETS, _SHARES = [], [], [], []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    for l in (_LIENS, _MEMOS, _PROJETS, _SHARES):
        l.clear()
    yield
    import requests
    for sid in _SHARES:
        try:
            requests.delete(live_server + "/api/shares/%d" % sid, timeout=5)
        except Exception:
            pass
    for lid in _LIENS:
        try:
            requests.delete(live_server + "/api/links/%d" % lid, timeout=5)
        except Exception:
            pass
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
            requests.delete(live_server + "/api/trash/%d" % mid, timeout=5)
        except Exception:
            pass
    for pid in _PROJETS:
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    for l in (_LIENS, _MEMOS, _PROJETS, _SHARES):
        l.clear()


def _lien(live_server, nom, url_public="", url_local=""):
    import requests
    r = requests.post(live_server + "/api/links",
                      json={"name": nom, "url_public": url_public, "url_local": url_local}, timeout=5)
    assert r.status_code == 201, r.text
    _LIENS.append(r.json()["id"])
    return r.json()["id"]


def _memo(live_server, titre, pid=None):
    import requests
    body = {"title": titre, "content": titre + " — décor LR"}
    if pid:
        body["project_id"] = pid
    r = requests.post(live_server + "/api/memos", json=body, timeout=5)
    assert r.status_code in (200, 201), r.text
    _MEMOS.append(r.json()["id"])
    return r.json()["id"]


def _projet(live_server, nom):
    import requests
    r = requests.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
    assert r.status_code == 201, r.text
    _PROJETS.append(r.json()["id"])
    return r.json()["id"]


def _relier(live_server, link_id, kind, target_id):
    import requests
    r = requests.post(live_server + "/api/links/%d/refs" % link_id,
                      json={"kind": kind, "target_id": target_id}, timeout=5)
    assert r.status_code in (200, 201), r.text


def _boot(page, live_server, vue="memos"):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    if vue == "memos":
        page.evaluate(
            "() => [...document.querySelectorAll('#sidebar .cat-item')]"
            "       .find(i => ((i.querySelector('.cat-label')||{}).textContent||'') === 'Mémos').click()")
    else:
        page.evaluate(
            "() => [...document.querySelectorAll('#sidebar .cat-item')]"
            "       .find(i => ((i.querySelector('.cat-label')||{}).textContent||'') === 'Tous').click()")
    page.wait_for_timeout(400)
    page.wait_for_load_state("networkidle")


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- 1


def test_chip_sur_la_card_memo_mene_a_la_card_du_lien(page, live_server, console_errors, urls_404):
    """Le chip 🔗 de la card mémo mène à la CARD du lien — pas au site (décision 1)."""
    lid = _lien(live_server, "LR Rentila", url_public="https://rentila.example")
    mid = _memo(live_server, "LR Declarer les loyers")
    _relier(live_server, lid, "memo", mid)
    _boot(page, live_server, vue="memos")

    chip = page.locator('.task[data-memo-id="%d"] .lref-chip' % mid)
    assert chip.count() == 1, "pas de chip 🔗 sur la card du mémo"
    # ⚠ L'entrée des cards est animée (GSAP `autoAlpha`) : tant que le stagger n'a pas atteint
    # la nôtre, le chip est `visibility:hidden` et `inner_text()` rend ''. Avec peu de mémos on
    # ne le voit jamais ; avec le décor cumulé de toute la suite, si. On ATTEND l'affichage au
    # lieu de supposer qu'il est déjà là — le défaut serait dans le test, pas dans la page.
    chip.wait_for(state="visible", timeout=5_000)
    assert "LR Rentila" in chip.inner_text()

    chip.click()
    page.wait_for_timeout(600)
    assert page.evaluate("() => state.view") == "links", "le chip doit mener à la vue Liens"
    card = page.locator('#links .card[data-id="%d"]' % lid)
    assert card.count() == 1 and card.is_visible()
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 2


def test_la_fleche_ouvre_le_site(page, live_server, console_errors, urls_404):
    """Le ↗ du chip ouvre `url_public` dans un nouvel onglet, et LUI seul."""
    lid = _lien(live_server, "LR Actual", url_public="https://actual.example")
    mid = _memo(live_server, "LR Budget")
    _relier(live_server, lid, "memo", mid)
    _boot(page, live_server, vue="memos")
    page.evaluate("() => { window.__ouverts = []; window.open = (u) => { window.__ouverts.push(u); return null; }; }")

    page.locator('.task[data-memo-id="%d"] .lref-go' % mid).click()
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__ouverts") == ["https://actual.example"]
    assert page.evaluate("() => state.view") == "memos", "le ↗ ne doit PAS changer de vue"
    # …et il ne doit RIEN déclencher d'autre : sans `stopPropagation`, le clic remonte à la card
    # et ouvre l'éditeur du mémo par-dessus le nouvel onglet. Deux actions pour un geste.
    assert page.evaluate("() => editingMemoId") in (None, 0), \
        "le ↗ a aussi ouvert l'éditeur du mémo (clic non arrêté)"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 3


def test_card_lien_montre_memo_et_dossier(page, live_server, console_errors, urls_404):
    """Depuis la card du lien : 📝 ouvre la fiche du mémo, 📁 ouvre le board du dossier."""
    pid = _projet(live_server, "LR Finance")
    lid = _lien(live_server, "LR Impots", url_public="https://impots.example")
    mid = _memo(live_server, "LR Declaration")
    _relier(live_server, lid, "memo", mid)
    _relier(live_server, lid, "project", pid)
    _boot(page, live_server, vue="links")

    cibles = page.locator('#links .card[data-id="%d"] .lref-target' % lid)
    assert cibles.count() == 2
    kinds = page.evaluate(
        "id => [...document.querySelectorAll('#links .card[data-id=\"' + id + '\"] .lref-target')]"
        "       .map(e => e.dataset.kind)", lid)
    assert sorted(kinds) == ["memo", "project"]

    page.locator('#links .card[data-id="%d"] .lref-target[data-kind="project"]' % lid).click()
    page.wait_for_timeout(500)
    assert page.evaluate("() => [state.view, state.memoProject]") == ["memos", pid]
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 4


def test_ligne_liens_relies_sur_le_board_du_dossier(page, live_server, console_errors, urls_404):
    """La ligne « Liens reliés » n'existe que s'il y a de quoi la remplir — jamais de rangée vide."""
    vide = _projet(live_server, "LR Vide")
    plein = _projet(live_server, "LR Plein")
    lid = _lien(live_server, "LR Jellyfin", url_public="https://jellyfin.example")
    _relier(live_server, lid, "project", plein)
    _boot(page, live_server, vue="memos")

    page.locator(".cat-item", has_text="LR Plein").first.click()
    page.wait_for_timeout(500)
    page.locator("#board-link-refs").wait_for(state="visible", timeout=5_000)
    assert "LR Jellyfin" in page.locator("#board-link-refs").inner_text()

    page.locator(".cat-item", has_text="LR Vide").first.click()
    page.wait_for_timeout(500)
    assert page.locator("#board-link-refs").count() == 0, "rangée vide affichée sans aucun lien"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 5


def test_filtre_relies_et_compteur(page, live_server, console_errors, urls_404):
    """Tous / Reliés (n) / Non reliés — le compteur porte sur TOUS les liens, pas sur la liste vue."""
    pid = _projet(live_server, "LR Media")
    mid = _memo(live_server, "LR Films")
    a = _lien(live_server, "LR AvecMemo", url_public="https://a.example")
    b = _lien(live_server, "LR AvecDossier", url_public="https://b.example")
    c = _lien(live_server, "LR Sans", url_public="https://c.example")
    _relier(live_server, a, "memo", mid)
    _relier(live_server, b, "project", pid)
    _boot(page, live_server, vue="links")

    def noms():
        return page.evaluate(
            "() => [...document.querySelectorAll('#links .card .name')]"
            "       .map(e => e.textContent).filter(t => t.startsWith('LR '))")

    assert sorted(noms()) == ["LR AvecDossier", "LR AvecMemo", "LR Sans"]
    libelle = page.locator('#links-refs-filter button[data-reffilter="linked"]').inner_text()
    assert "2" in libelle, "le compteur ne dit pas le nombre de liens reliés : %r" % libelle

    page.locator('#links-refs-filter button[data-reffilter="linked"]').click()
    page.wait_for_timeout(300)
    assert sorted(noms()) == ["LR AvecDossier", "LR AvecMemo"]

    page.locator('#links-refs-filter button[data-reffilter="unlinked"]').click()
    page.wait_for_timeout(300)
    assert noms() == ["LR Sans"]
    # Le compteur ne se laisse pas entraîner par le filtre courant : « Reliés (2) » dit combien
    # il y en a, pas combien il en reste sous le filtre actif (sinon il afficherait 0 ici).
    assert "2" in page.locator('#links-refs-filter button[data-reffilter="linked"]').inner_text(), \
        "le compteur est calculé sur la liste filtrée, pas sur tous les liens"

    # Retirer la relation fait basculer le lien de camp, sans rechargement de page.
    page.locator('#links-refs-filter button[data-reffilter="linked"]').click()
    page.wait_for_timeout(300)
    page.locator('#links .card[data-id="%d"] .lref-target .lref-x' % a).click()
    page.wait_for_timeout(700)
    assert noms() == ["LR AvecDossier"], "le lien délié reste listé comme « relié »"
    assert "1" in page.locator('#links-refs-filter button[data-reffilter="linked"]').inner_text()
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 6


def test_picker_relie_depuis_la_card_du_lien(page, live_server, console_errors, urls_404):
    """« + relier » ouvre le picker unifié ; la recherche est foldée ([SEARCH-FOLD])."""
    lid = _lien(live_server, "LR Picker", url_public="https://picker.example")
    mid = _memo(live_server, "LR Éclipse solaire")
    _boot(page, live_server, vue="links")

    page.locator('#links .card[data-id="%d"] .lref-add' % lid).click()
    page.wait_for_selector("#link-ref-picker[open]", timeout=5_000)
    page.fill("#lrp-search", "eclipse")          # sans accent : doit trouver « Éclipse »
    page.wait_for_timeout(350)
    item = page.locator('.lrp-item[data-pick="memo:%d"]' % mid)
    assert item.count() == 1, "la recherche foldée ne retrouve pas « Éclipse »"
    item.click()
    page.locator("#lrp-ok").click()
    page.wait_for_timeout(800)

    assert page.locator('#links .card[data-id="%d"] .lref-target[data-kind="memo"]' % lid).count() == 1
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 7


def test_invite_lecture_seule_et_pas_de_lien_lan(page, live_server, console_errors, urls_404):
    """Chez l'invité : le chip s'affiche, ouvre le site, et n'offre AUCUNE écriture.

    Et le lien qui n'a qu'une URL locale n'apparaît pas du tout : il n'existe que sur le réseau
    de Fabien (projection stricte, invariant 5).
    """
    import requests
    pid = _projet(live_server, "LR Voyage")
    mid = _memo(live_server, "LR Hotel Kyoto", pid=pid)
    public = _lien(live_server, "LR Public", url_public="https://public.example")
    lan = _lien(live_server, "LR LAN", url_local="http://192.168.1.39:4533")
    _relier(live_server, public, "memo", mid)
    _relier(live_server, lan, "memo", mid)
    sh = requests.post(live_server + "/api/shares",
                       json={"kind": "project", "target_id": pid}, timeout=5).json()
    _SHARES.append(sh["id"])

    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    page.wait_for_load_state("networkidle")

    chips = page.locator(".lref-chip")
    assert chips.count() == 1, "l'invité doit voir le lien public, et lui seul"
    chips.first.wait_for(state="visible", timeout=5_000)
    assert "LR Public" in chips.first.inner_text()
    assert page.locator(".lref-add").count() == 0, "« + relier » exposé à un invité"
    assert page.locator(".lref-x").count() == 0, "un invité peut délier"
    assert "192.168.1.39" not in page.content(), "une URL locale a fuité dans la page invitée"

    page.evaluate("() => { window.__ouverts = []; window.open = (u) => { window.__ouverts.push(u); return null; }; }")
    chips.first.click()
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__ouverts") == ["https://public.example"], \
        "chez l'invité, le chip ouvre directement le site (il n'a pas de vue Liens)"

    # Le ↗ ouvre le site, et RIEN d'autre. C'est ici que la garde `stopPropagation` porte :
    # la card invitée, elle, est cliquable (elle ouvre l'éditeur). Sans elle, un clic sur la
    # flèche ouvrirait le site ET l'éditeur par-dessus.
    page.evaluate("() => { window.__ouverts = []; }")
    page.locator(".lref-go").first.click()
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__ouverts") == ["https://public.example"]
    assert page.evaluate("() => (typeof editingId === 'undefined' ? null : editingId)") is None, \
        "le ↗ a aussi ouvert l'éditeur du mémo (clic non arrêté)"
    assert _erreurs_js(console_errors, urls_404) == []
