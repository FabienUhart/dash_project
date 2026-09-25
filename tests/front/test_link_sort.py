"""[LINK-SORT] Trier la vue Liens — Manuel / Plus récents / Plus anciens / A → Z.

Demande Fabien du 25 sept. 2026 : « la page Liens pourrait avoir un système de tri, du plus
récent au plus ancien, ça m'aiderait à les retrouver ». Brief : `docs/briefs/LINK-SORT.md`.

Ce que ces parcours mesurent — et surtout ce qu'ils PROTÈGENT :

- le tri est une **VUE** : il ne touche ni `position` ni `/api/links/reorder` (test 7), et
  repasser en Manuel rend l'ordre d'origine — ce qui ne peut être vrai que si `state.links`
  n'est jamais trié EN PLACE ;
- le départage par `id` n'est pas une coquetterie (test 3) : les liens antérieurs à la
  migration uid/created_at partagent la MÊME `created_at`, leur ordre serait sinon celui,
  arbitraire, dans lequel ils arrivent ;
- le A → Z passe par `searchFold` ([SEARCH-FOLD], partial) : « Éclipse » se range avec
  « eclipse », pas après « Zèbre » (test 5) ;
- hors Manuel, le glisser-déposer de réordonnancement est **coupé** (test 8) : laisser la main
  écrire des positions sur une liste triée mélangerait la base sans que personne l'ait demandé.

Le décor est posé avec des `position` VOLONTAIREMENT distinctes de l'ordre de création : sans
ça, « manuel » et « plus anciens » seraient le même ordre et les tests seraient verts pour la
mauvaise raison.
"""
import os as _os
import sqlite3 as _sqlite3
import time as _time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1400, "height": 900}

# Les quatre noms servent DEUX tests à la fois : l'ordre de création (2/3/4) et l'alphabet
# foldé (5). « LS » les isole des liens des autres fichiers dans la même base de session.
NOM_A = "LS alpha"
NOM_B = "LS Éclipse"
NOM_C = "LS eclipse"
NOM_D = "LS Zèbre"

_LIENS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    """Le `live_server` est session-scoped : ce que ce fichier crée doit repartir avec lui.

    Leçon payée en [LINK-OG] — un lien laissé derrière fait 404 sur son favicon dans la console
    de TOUS les tests suivants, qui rougissent sans avoir rien à se reprocher.
    """
    _LIENS.clear()
    yield
    import requests
    for lid in _LIENS:
        try:
            requests.delete(live_server + "/api/links/%d" % lid, timeout=5)
        except Exception:
            pass
    _LIENS.clear()


def _semer(live_server, ordre_positions=(2, 0, 3, 1)):
    """Crée A, B, C, D dans cet ordre (A le plus ancien) puis pose des `position` choisies.

    `ordre_positions` = les INDICES (0=A, 1=B, 2=C, 3=D) dans l'ordre manuel voulu. Le défaut
    (C, A, D, B) ne coïncide avec AUCUN des trois tris — c'est ce qui rend le test « défaut =
    manuel » capable de rougir.

    Rend `(ids, ordre_manuel)` où `ids` suit l'ordre de création.
    """
    import requests
    ids = []
    for nom in (NOM_A, NOM_B, NOM_C, NOM_D):
        r = requests.post(live_server + "/api/links", json={"name": nom}, timeout=5)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        _LIENS.append(ids[-1])
        _time.sleep(0.02)   # des `created_at` franchement distincts, pas à la microseconde près
    # On réordonne la base ENTIÈRE (d'autres fichiers ont pu laisser des liens) : les nôtres
    # partent en queue, dans l'ordre manuel demandé.
    tous = [l["id"] for l in requests.get(live_server + "/api/links", timeout=5).json()]
    autres = [i for i in tous if i not in ids]
    manuel = [ids[i] for i in ordre_positions]
    r = requests.post(live_server + "/api/links/reorder",
                      json={"ids": autres + manuel}, timeout=5)
    assert r.status_code == 200, r.text
    return ids, manuel


def _boot(page, live_server, tri=None):
    """Ouvre la vue Liens. `tri` pose la valeur localStorage AVANT le premier rendu."""
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.evaluate(
        "v => { try { v === null ? localStorage.removeItem('dash:linkSort')"
        "                        : localStorage.setItem('dash:linkSort', v); } catch (e) {} }",
        tri,
    )
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#links .card", timeout=10_000)
    page.wait_for_load_state("networkidle")


def _noms(page):
    """Les noms de NOS liens, dans l'ordre affiché (les autres fichiers sont hors sujet)."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#links .card .name')]"
        "       .map(e => e.textContent).filter(t => t.startsWith('LS '))"
    )


def _ids_affiches(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#links .card')]"
        "       .filter(c => (c.querySelector('.name') || {}).textContent"
        "                    && c.querySelector('.name').textContent.startsWith('LS '))"
        "       .map(c => Number(c.dataset.id))"
    )


def _trier(page, mode):
    """Clique le bouton de tri `mode` et attend que le rendu soit retombé."""
    btn = page.locator('#links-sort button[data-sort="%s"]' % mode)
    btn.click()
    page.wait_for_timeout(200)
    assert btn.get_attribute("aria-pressed") == "true"


def _positions(live_server):
    import requests
    return [(l["id"], l["position"])
            for l in requests.get(live_server + "/api/links", timeout=5).json()]


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    """Erreurs de console, débarrassées du seul bruit attendu : le 404 de `/api/favicon/<id>`.
    Nos liens de décor n'ont pas d'URL — la card demande quand même son favicon et prend un 404.
    La ligne de console ne dit pas quelle ressource a manqué : on ne la retire donc qu'après
    avoir vérifié, sur les réponses réelles, qu'aucun AUTRE 404 n'a eu lieu (même montage que
    `test_search_fold`)."""
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- 1


def test_defaut_manuel(page, live_server, console_errors, urls_404):
    """Sans réglage, la vue Liens est EXACTEMENT celle d'avant le lot : l'ordre `position`."""
    ids, manuel = _semer(live_server)
    _boot(page, live_server, tri=None)
    assert _ids_affiches(page) == manuel
    assert page.locator('#links-sort button[data-sort="manual"]').get_attribute("aria-pressed") == "true"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 2


def test_plus_recents(page, live_server, console_errors, urls_404):
    """« Plus récents » = `created_at` DESC : le dernier créé passe en tête.

    Et surtout PAS `updated_at` : retoucher le plus ancien des liens ne doit pas le faire
    remonter en tête — sinon le classement dirait « dernier touché » au lieu de « dernier
    ajouté », et un simple rafraîchissement d'aperçu OG rebattrait la liste.
    """
    import requests
    ids, manuel = _semer(live_server)
    _boot(page, live_server)
    _trier(page, "newest")
    assert _ids_affiches(page) == list(reversed(ids))
    assert _noms(page)[0] == NOM_D

    r = requests.put(live_server + "/api/links/%d" % ids[0],
                     json={"descr": "retouché après coup"}, timeout=5)
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] > r.json()["created_at"]   # la retouche a bien eu lieu
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#links .card", timeout=10_000)
    page.wait_for_load_state("networkidle")
    assert _ids_affiches(page) == list(reversed(ids)), "le lien retouché ne remonte pas"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 3


def test_meme_date_departage_par_id(page, live_server, console_errors, urls_404):
    """Deux liens de MÊME `created_at` : le plus grand `id` d'abord.

    C'est le cas des liens antérieurs à la migration uid/created_at (app.py ~l.1553), qui
    portent tous la date de migration. Le décor place B AVANT C dans l'ordre manuel : sans
    départage explicite, un tri stable les laisserait dans cet ordre et le test serait muet.
    """
    ids, manuel = _semer(live_server, ordre_positions=(1, 2, 0, 3))   # B, C, A, D
    a, b, c, d = ids
    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        (date_c,) = con.execute("SELECT created_at FROM links WHERE id = ?", (c,)).fetchone()
        con.execute("UPDATE links SET created_at = ? WHERE id = ?", (date_c, b))
        con.commit()
    finally:
        con.close()
    _boot(page, live_server)
    assert _ids_affiches(page)[:2] == [b, c]          # l'ordre manuel du décor, bien en place
    _trier(page, "newest")
    vus = _ids_affiches(page)
    assert vus.index(c) < vus.index(b), "id DESC doit départager deux dates identiques"
    assert vus[0] == d and vus[-1] == a
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 4


def test_plus_anciens_est_le_miroir(page, live_server, console_errors, urls_404):
    """« Plus anciens » = le miroir exact de « Plus récents »."""
    ids, manuel = _semer(live_server)
    _boot(page, live_server)
    _trier(page, "newest")
    recents = _ids_affiches(page)
    _trier(page, "oldest")
    anciens = _ids_affiches(page)
    assert anciens == list(reversed(recents))
    assert anciens == ids
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 5


def test_alphabetique_folde(page, live_server, console_errors, urls_404):
    """A → Z passe par `searchFold` : « Éclipse » se range avec « eclipse », pas après « Zèbre ».

    Les deux homonymes sont départagés par `id` ASC — B a été créé avant C.
    """
    ids, manuel = _semer(live_server)
    _boot(page, live_server)
    _trier(page, "name")
    assert _noms(page) == [NOM_A, NOM_B, NOM_C, NOM_D]
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 6


def test_memorise_et_valeur_corrompue(page, live_server, console_errors, urls_404):
    """Le tri survit au rechargement ; une valeur inconnue retombe sur Manuel, sans casser."""
    ids, manuel = _semer(live_server)
    _boot(page, live_server)
    _trier(page, "newest")
    assert page.evaluate("() => localStorage.getItem('dash:linkSort')") == "newest"
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#links .card", timeout=10_000)
    page.wait_for_load_state("networkidle")
    assert _ids_affiches(page) == list(reversed(ids))
    assert page.locator('#links-sort button[data-sort="newest"]').get_attribute("aria-pressed") == "true"

    _boot(page, live_server, tri="n-importe-quoi")
    assert _ids_affiches(page) == manuel
    assert page.locator('#links-sort button[data-sort="manual"]').get_attribute("aria-pressed") == "true"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 7


def test_le_tri_nest_pas_une_ecriture(page, live_server, console_errors, urls_404):
    """Trier ne réordonne RIEN en base, et le retour au Manuel retrouve l'ordre d'origine.

    La seconde moitié est le garde-fou du tri EN PLACE : si `sortLinks` triait `state.links`
    au lieu d'une copie, l'ordre manuel serait détruit dès le premier clic et ne reviendrait
    qu'au prochain `loadAll()`.
    """
    ids, manuel = _semer(live_server)
    avant = _positions(live_server)
    _boot(page, live_server)
    ecritures = []
    page.on("request", lambda r: ecritures.append(r.url)
            if r.method == "POST" and "/api/links/reorder" in r.url else None)
    _trier(page, "newest")
    _trier(page, "name")
    _trier(page, "manual")
    assert ecritures == [], "le tri est une vue, il n'écrit jamais de position"
    assert _positions(live_server) == avant
    assert _ids_affiches(page) == manuel, "retour au Manuel = ordre serveur intact"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 8


_DND = """
() => {
  const cards = [...document.querySelectorAll('#links .card')]
      .filter(c => c.querySelector('.name').textContent.startsWith('LS '));
  const src = cards[0], cible = cards[2];
  src.dispatchEvent(new DragEvent('dragstart', {
    bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
  const r = cible.getBoundingClientRect();
  cible.dispatchEvent(new DragEvent('dragover', {
    bubbles: true, cancelable: true, clientY: r.top + r.height - 2 }));
  src.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true }));
}
"""


def test_dnd_coupe_hors_manuel(page, live_server, console_errors, urls_404):
    """Le réordonnancement à la main n'existe qu'en Manuel.

    On vérifie d'abord qu'il MARCHE en Manuel — sans ça, « il ne bouge pas en tri » serait vert
    parce que le geste synthétique ne fait rien du tout, pas parce que la garde tient.
    """
    ids, manuel = _semer(live_server)
    _boot(page, live_server)
    page.evaluate(_DND)
    page.wait_for_timeout(150)
    assert _ids_affiches(page) != manuel, "en Manuel, le D&D doit déplacer la card"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#links .card", timeout=10_000)
    page.wait_for_load_state("networkidle")
    _trier(page, "newest")
    avant = _ids_affiches(page)
    page.evaluate(_DND)
    page.wait_for_timeout(150)
    assert _ids_affiches(page) == avant, "hors Manuel, un dragover ne déplace rien"

    _trier(page, "manual")
    page.evaluate(_DND)
    page.wait_for_timeout(150)
    assert _ids_affiches(page) != manuel, "repasser en Manuel réactive le D&D"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 9


def test_recherche_puis_tri(page, live_server, console_errors, urls_404):
    """Le tri s'applique APRÈS la recherche : seuls les résultats, dans l'ordre demandé."""
    ids, manuel = _semer(live_server)
    a, b, c, d = ids
    _boot(page, live_server)
    _trier(page, "newest")
    page.fill("#search", "eclipse")
    page.wait_for_timeout(300)
    assert _ids_affiches(page) == [c, b], "les deux « eclipse », le plus récent d'abord"
    assert _noms(page) == [NOM_C, NOM_B]
    assert _erreurs_js(console_errors, urls_404) == []
