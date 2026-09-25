"""[MOBILE-NAV] Sur téléphone : les dossiers dans un panneau, un en-tête d'une ligne.

Brief : `docs/briefs/MOBILE-NAV.md`, issu de la passe mobile Cowork du 25 sept. 2026
(`docs/tests/test-application-mobile.md`, points 1, 3 et 4) et de la démo validée par Fabien.

Le défaut mesuré : en 412 px, la barre latérale devient une bande horizontale de 60 entrées sur
plus de 8 000 px — atteindre « Voyage Japon » demandait de faire glisser vingt écrans. Et
l'en-tête mangeait trois rangées avant le premier mémo.

Ce que ces parcours PROTÈGENT :

- **le desktop ne bouge pas** (test 1) : tout ce lot est sous `max-width: 900px`, et un lot
  « mobile » qui abîmerait l'écran principal serait une régression, pas une amélioration ;
- **un seul état d'arbre, deux rendus** (test 4) : le panneau et la sidebar partagent les MÊMES
  fonctions de repli (`sbProjOpen`/`toggleSbProj`) — déplier au doigt se retrouve au clavier ;
- **le chevron ne ferme pas le panneau** (test 4) : plier un dossier est un geste d'exploration ;
  le confondre avec « ouvrir ce dossier » ferait sortir du panneau à chaque essai ;
- **le filtre est foldé** (test 6, [SEARCH-FOLD]) : « japon » doit trouver « Japón », et un
  dossier dont un DESCENDANT correspond reste visible et déplié — sinon le filtre cacherait le
  chemin qui mène au résultat.
"""
import pytest

pytestmark = pytest.mark.e2e

MOBILE = {"width": 412, "height": 915}
BUREAU = {"width": 1280, "height": 900}

_PROJETS, _MEMOS = [], []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    _PROJETS.clear(); _MEMOS.clear()
    yield
    import requests
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


def _projet(live_server, nom, parent=None):
    import requests
    r = requests.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    if parent:
        # ⚠ `POST /api/projects` crée TOUJOURS à la racine et ignore `parent_id` : le front
        # déplace par un PUT ensuite. Leçon payée en [SEARCH-FOLD] — sans ce second appel, le
        # décor fabriquerait deux dossiers FRÈRES et le test de l'arbre n'aurait rien à plier.
        r = requests.put(live_server + "/api/projects/%d" % pid, json={"parent_id": parent}, timeout=5)
        assert r.status_code == 200, r.text
    return pid


def _memo(live_server, titre, pid=None):
    import requests
    body = {"title": titre, "content": titre + " — décor MN"}
    if pid:
        body["project_id"] = pid
    r = requests.post(live_server + "/api/memos", json=body, timeout=5)
    assert r.status_code in (200, 201), r.text
    _MEMOS.append(r.json()["id"])
    return r.json()["id"]


def _semer(live_server):
    """Trois dossiers dont un enfant : « MN Japón » porte « MN Kyoto »."""
    parent = _projet(live_server, "MN Japón")
    enfant = _projet(live_server, "MN Kyoto", parent=parent)
    autre = _projet(live_server, "MN Maison")
    _memo(live_server, "MN billet", pid=parent)
    _memo(live_server, "MN ryokan", pid=enfant)
    return parent, enfant, autre


def _boot(page, live_server, viewport=MOBILE):
    """Ouvre la page et attend qu'elle soit VRAIMENT posée.

    ⚠ Deux pièges payés ici, aucun des deux dans le code de ce lot :
    1. au tout premier chargement d'un profil neuf, le **service worker** prend le contrôle et la
       page se RECHARGE (`controllerchange` → `location.reload()`) — tout ce qu'on évalue avant
       meurt avec « Execution context was destroyed » ; on attend donc `networkidle` d'abord ;
    2. un sélecteur « A, B » attend le PREMIER nœud trouvé, pas le premier visible : en desktop il
       tombait sur `#folders-btn`, qui y est masqué, et pendait jusqu'au timeout.
    """
    page.set_viewport_size(viewport)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(
        "#folders-btn" if viewport is MOBILE else "nav#sidebar .cat-item", timeout=10_000)
    page.wait_for_timeout(500)


def _ouvrir_panneau(page):
    page.locator("#folders-btn").click()
    page.wait_for_selector("#folders-sheet[open]", timeout=5_000)
    page.wait_for_timeout(300)


def _noms_arbre(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#fs-tree .cat-item')]"
        "       .map(e => (e.querySelector('.cat-label') || {}).textContent || '')"
        "       .filter(t => t.startsWith('MN '))")


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


def test_desktop_non_regresse(page, live_server, console_errors, urls_404):
    """> 900 px : rien ne change. Non-régression, verte d'emblée et assumée."""
    _semer(live_server)
    _boot(page, live_server, viewport=BUREAU)
    assert page.locator("nav#sidebar").is_visible(), "la sidebar desktop a disparu"
    assert page.locator("#theme-btn").is_visible(), "le bouton thème desktop a disparu"
    assert page.locator("#folders-btn").count() == 0 or not page.locator("#folders-btn").is_visible(), \
        "le bouton 📁 n'a rien à faire en desktop"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 2


def test_entete_mobile_une_ligne(page, live_server, console_errors, urls_404):
    """≤ 900 px : la bande de 60 entrées disparaît, l'en-tête tient sur une ligne."""
    _semer(live_server)
    _boot(page, live_server)
    assert not page.locator("nav#sidebar").is_visible(), \
        "la bande horizontale de 60 entrées est toujours là"
    h = page.evaluate("() => document.querySelector('header').getBoundingClientRect().height")
    assert h <= 70, "en-tête de %d px : il en mangeait 175, on visait une seule ligne" % h
    assert page.locator("#home-btn").inner_text().strip() == "D"
    for sel in ("#clock-wrap", "#weather", "#theme-btn"):
        assert not page.locator(sel).is_visible(), "%s devrait être masqué en mobile" % sel
    assert page.locator("#folders-btn").is_visible()
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 3


def test_panneau_dossiers_contenu(page, live_server, console_errors, urls_404):
    """Le panneau porte les raccourcis, l'arbre replié, et des compteurs qui disent vrai."""
    import requests
    parent, enfant, autre = _semer(live_server)
    _boot(page, live_server)
    _ouvrir_panneau(page)

    libelles = page.evaluate(
        "() => [...document.querySelectorAll('#fs-shortcuts .cat-item .cat-label')].map(e => e.textContent)")
    for attendu in ("Favoris", "Partages", "Mémos", "Plan", "Agenda", "Corbeille"):
        assert attendu in libelles, "raccourci manquant : %s (vus : %r)" % (attendu, libelles)

    noms = _noms_arbre(page)
    assert "MN Japón" in noms and "MN Maison" in noms
    assert "MN Kyoto" not in noms, "l'enfant doit être replié à l'ouverture"

    # Le compteur du dossier dit ce que l'API dit.
    api = {p["name"]: p["memo_count"] for p in requests.get(live_server + "/api/projects", timeout=5).json()}
    vu = page.evaluate(
        "() => { const i = [...document.querySelectorAll('#fs-tree .cat-item')]"
        "        .find(e => (e.querySelector('.cat-label')||{}).textContent === 'MN Japón');"
        "        return i ? (i.querySelector('.count')||{}).textContent : null; }")
    assert vu == str(api["MN Japón"]), "compteur %r ≠ API %r" % (vu, api["MN Japón"])
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 4


def test_chevron_deplie_sans_fermer_et_partage_letat(page, live_server, console_errors, urls_404):
    """Le chevron déplie SANS quitter le panneau, et l'état est celui de la sidebar desktop."""
    parent, enfant, autre = _semer(live_server)
    _boot(page, live_server)
    _ouvrir_panneau(page)

    page.locator('#fs-tree .cat-item[data-proj-id="%d"] .sb-proj-chev' % parent).click()
    page.wait_for_timeout(300)
    assert page.locator("#folders-sheet[open]").count() == 1, "le chevron a fermé le panneau"
    assert "MN Kyoto" in _noms_arbre(page)

    # …et l'état est PARTAGÉ avec la sidebar : même clé, mêmes fonctions.
    assert page.evaluate("id => sbProjOpen(id)", parent) is True
    page.locator("#fs-close").click()
    page.wait_for_timeout(200)
    _ouvrir_panneau(page)
    assert "MN Kyoto" in _noms_arbre(page), "le dépli n'a pas survécu à la réouverture"

    page.set_viewport_size(BUREAU)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("nav#sidebar .cat-item", timeout=10_000)
    page.wait_for_timeout(400)
    assert page.evaluate("id => sbProjOpen(id)", parent) is True, \
        "l'arbre du panneau et celui de la sidebar ne partagent pas leur état"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 5


def test_tap_nom_ouvre_le_dossier_et_ferme(page, live_server, console_errors, urls_404):
    """Taper le nom ouvre le dossier et referme le panneau — un geste, un résultat."""
    parent, enfant, autre = _semer(live_server)
    _boot(page, live_server)
    _ouvrir_panneau(page)

    page.locator('#fs-tree .cat-item[data-proj-id="%d"] .cat-label' % autre).click()
    page.wait_for_timeout(500)
    assert page.locator("#folders-sheet[open]").count() == 0, "le panneau est resté ouvert"
    assert page.evaluate("() => [state.view, state.memoProject]") == ["memos", autre]

    _ouvrir_panneau(page)
    classes = page.evaluate(
        "id => (document.querySelector('#fs-tree .cat-item[data-proj-id=\"' + id + '\"]') || {}).className || ''",
        autre)
    assert "active" in classes, "le dossier courant n'est pas marqué dans le panneau"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 6


def test_filtre_folde_et_garde_le_chemin(page, live_server, console_errors, urls_404):
    """Le filtre ignore les accents et garde VISIBLE le parent d'un résultat, déplié."""
    parent, enfant, autre = _semer(live_server)
    _boot(page, live_server)
    _ouvrir_panneau(page)

    page.fill("#fs-filter", "JAPON")           # ni accent ni casse
    page.wait_for_timeout(300)
    noms = _noms_arbre(page)
    assert "MN Japón" in noms and "MN Maison" not in noms

    page.fill("#fs-filter", "kyoto")
    page.wait_for_timeout(300)
    noms = _noms_arbre(page)
    assert "MN Kyoto" in noms, "le descendant qui correspond doit apparaître"
    assert "MN Japón" in noms, "son parent doit rester visible : c'est le chemin qui y mène"

    page.fill("#fs-filter", "")
    page.wait_for_timeout(300)
    assert "MN Kyoto" not in _noms_arbre(page), "champ vidé → l'arbre retrouve son repli"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 7


def test_fermetures(page, live_server, console_errors, urls_404):
    """Fond, ✕ et Échap ferment le panneau — trois sorties, aucune impasse."""
    _semer(live_server)
    _boot(page, live_server)

    _ouvrir_panneau(page)
    page.locator("#fs-close").click()
    page.wait_for_timeout(250)
    assert page.locator("#folders-sheet[open]").count() == 0, "✕ ne ferme pas"

    _ouvrir_panneau(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    assert page.locator("#folders-sheet[open]").count() == 0, "Échap ne ferme pas"

    _ouvrir_panneau(page)
    page.mouse.click(206, 40)                  # le fond, au-dessus de la feuille
    page.wait_for_timeout(250)
    assert page.locator("#folders-sheet[open]").count() == 0, "le tap sur le fond ne ferme pas"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 8


def test_theme_dans_les_parametres(page, live_server, console_errors, urls_404):
    """Le thème quitte l'en-tête mobile pour les Paramètres — même fonction, même clé."""
    _semer(live_server)
    _boot(page, live_server)
    page.locator("#settings-btn").click()
    page.wait_for_timeout(500)

    page.locator("#theme-light").click()
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
    assert page.evaluate("() => localStorage.getItem('theme')") == "light"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)
    assert page.evaluate("() => document.documentElement.dataset.theme") == "light", \
        "le thème choisi dans les Paramètres n'a pas survécu au rechargement"

    page.locator("#settings-btn").click()
    page.wait_for_timeout(400)
    page.locator("#theme-dark").click()
    page.wait_for_timeout(300)
    # ⚠ Le sombre est le DÉFAUT : `setTheme('dark')` RETIRE l'attribut au lieu d'en poser un
    # (c'est le script anti-FOUC du <head> qui lit `localStorage.theme`). On vérifie donc la
    # clef, et l'absence de l'attribut « clair ».
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") is None
    assert page.evaluate("() => localStorage.getItem('theme')") == "dark"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 9


def test_bloc_memos_ouvert_par_defaut_en_mobile(page, live_server, console_errors, urls_404):
    """Avec 96 mémos en retard, l'accueil ne doit pas s'ouvrir sur un bloc MÉMOS replié."""
    _semer(live_server)
    _boot(page, live_server)
    assert page.evaluate("() => document.getElementById('memo-details').open") is True

    page.evaluate("() => { document.getElementById('memo-details').open = false; "
                  "        document.getElementById('memo-details').dispatchEvent(new Event('toggle')); }")
    page.wait_for_timeout(300)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)
    assert page.evaluate("() => document.getElementById('memo-details').open") is False, \
        "le repli choisi à la main n'a pas été mémorisé"
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 10


def test_aucun_debordement_horizontal(page, live_server, console_errors, urls_404):
    """Rien ne dépasse en largeur : ni l'accueil, ni les Liens, ni les Mémos, ni le panneau."""
    _semer(live_server)
    _boot(page, live_server)

    def deborde():
        return page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth")

    assert deborde() <= 0, "accueil : débordement de %d px" % deborde()
    _ouvrir_panneau(page)
    assert deborde() <= 0, "panneau ouvert : débordement de %d px" % deborde()
    page.locator("#fs-close").click()
    page.wait_for_timeout(250)

    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    page.wait_for_timeout(400)
    assert deborde() <= 0, "vue Mémos : débordement de %d px" % deborde()
    page.evaluate("() => { state.view = 'links'; renderAll(); }")
    page.wait_for_timeout(400)
    assert deborde() <= 0, "vue Liens : débordement de %d px" % deborde()
    assert _erreurs_js(console_errors, urls_404) == []
