"""[EMPTY-STATE-NEW-MEMO] Dans un dossier vide, « + Nouveau mémo » doit faire quelque chose.

Bug reproduit par Fabien en local le 25 sept. 2026 (desktop, V28.1.263) : dans un dossier vide,
le bouton « + Nouveau mémo » de l'état vide **ne fait rien**. `focusAddMemo` cherche
`#memo-add-bar input`, mais sur un board de DOSSIER la barre de création n'est montée que si
l'outil « Mémo » du dock est ouvert ([TOOLS-DOCK]) — l'input n'existe pas, le `if (i)` avale le
geste, et il n'y a **aucune erreur console** pour le signaler.

C'est le pire genre de panne : un bouton qui a l'air normal et qui ne répond pas. Antérieur au
lot du jour — le dock existait déjà.

Ce que ces parcours PROTÈGENT :

- **le bouton ouvre l'outil qui manque** plutôt que de viser un champ absent (test 1) : même
  action que le bouton « Mémo » du dock, donc même état mémorisé ;
- **il n'ouvre pas ce qui est déjà ouvert** (test 2) : quand la barre est là, le geste se
  résume au focus — rien à basculer, rien à réécrire ;
- **la vue globale ne bouge pas** (test 3) : hors board de dossier, la barre est toujours
  montée et le dock n'a rien à voir là-dedans.
"""
import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1500, "height": 950}

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
    for pid in _PROJETS:
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    _PROJETS.clear(); _MEMOS.clear()


def _projet(live_server, nom):
    import requests
    r = requests.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
    assert r.status_code == 201, r.text
    _PROJETS.append(r.json()["id"])
    return r.json()["id"]


def _boot(page, live_server):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    # ⚠ Au premier chargement d'un profil neuf, le service worker prend le contrôle et la page se
    # RECHARGE : évaluer avant, c'est évaluer dans un contexte condamné (leçon [MOBILE-NAV]).
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("nav#sidebar .cat-item", timeout=10_000)
    page.wait_for_timeout(400)


def _ouvrir_dossier(page, nom):
    page.locator("#sidebar .cat-item", has_text=nom).first.click()
    page.wait_for_timeout(500)


def _dock(page, pid):
    return page.evaluate(
        "pid => { try { return JSON.parse(localStorage.getItem('toolsDock:' + pid) || 'null'); }"
        "         catch (e) { return null; } }", pid)


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


def test_dossier_vide_dock_ferme_le_bouton_ouvre_la_barre(page, live_server, console_errors, urls_404):
    """LE BUG : dossier vide, dock replié (le défaut) → le bouton doit ouvrir l'outil Mémo et focuser."""
    pid = _projet(live_server, "ESN Dossier vide")
    _boot(page, live_server)
    _ouvrir_dossier(page, "ESN Dossier vide")

    assert _dock(page, pid) in (None, {"memo": False, "file": False, "voice": False, "folder": False}), \
        "le décor doit partir dock REPLIÉ — c'est le défaut, et c'est là que le bug vit"
    assert page.locator("#memo-add-bar").count() == 0, \
        "la barre ne doit pas être montée : sans ça, le test ne reproduit rien"

    bouton = page.locator(".empty-state .es-action", has_text="Nouveau mémo")
    assert bouton.count() == 1, "l'état vide du dossier n'offre pas « + Nouveau mémo »"
    bouton.click()
    page.wait_for_timeout(400)

    assert page.locator("#memo-add-bar").count() == 1, \
        "le bouton n'a rien fait : la barre de création n'est toujours pas là"
    assert page.evaluate(
        "() => { const i = document.querySelector('#memo-add-bar input[type=text]');"
        "        return !!i && document.activeElement === i; }"), \
        "la barre est montée mais le curseur n'est pas dans le champ"
    assert (_dock(page, pid) or {}).get("memo") is True, \
        "l'ouverture doit être mémorisée, comme quand on clique le bouton « Mémo » du dock"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 2


def test_dossier_vide_dock_deja_ouvert_ne_bascule_rien(page, live_server, console_errors, urls_404):
    """Barre déjà montée → le geste se résume au focus : on ne referme pas ce qui est ouvert."""
    pid = _projet(live_server, "ESN Deja ouvert")
    _boot(page, live_server)
    page.evaluate(
        "pid => localStorage.setItem('toolsDock:' + pid,"
        "  JSON.stringify({ memo: true, file: false, voice: false, folder: false }))", pid)
    _ouvrir_dossier(page, "ESN Deja ouvert")
    assert page.locator("#memo-add-bar").count() == 1

    page.locator(".empty-state .es-action", has_text="Nouveau mémo").click()
    page.wait_for_timeout(400)

    assert page.locator("#memo-add-bar").count() == 1, "la barre a disparu : le geste a BASCULÉ au lieu de focuser"
    assert page.evaluate(
        "() => { const i = document.querySelector('#memo-add-bar input[type=text]');"
        "        return !!i && document.activeElement === i; }"), "le champ n'a pas le focus"
    assert _dock(page, pid) == {"memo": True, "file": False, "voice": False, "folder": False}
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 3


def test_vue_globale_inchangee(page, live_server, console_errors, urls_404):
    """Hors board de dossier, la barre est toujours montée et le dock n'a rien à y faire."""
    _boot(page, live_server)
    page.evaluate(
        "() => [...document.querySelectorAll('#sidebar .cat-item')]"
        "       .find(i => ((i.querySelector('.cat-label')||{}).textContent||'') === 'Mémos').click()")
    page.wait_for_timeout(500)

    assert page.locator("#memo-add-bar").count() == 1, \
        "la vue globale garde sa barre de création (comportement V1 du dock)"
    assert page.evaluate(
        "() => Object.keys(localStorage).filter(k => k.startsWith('toolsDock:all')"
        "                                         || k.startsWith('toolsDock:inbox')).length") == 0, \
        "la vue globale ne doit écrire aucun état de dock"
    assert _erreurs_js(console_errors, urls_404) == []
