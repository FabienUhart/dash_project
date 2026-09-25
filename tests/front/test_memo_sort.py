"""[MEMO-SORT-DATES] — moitié TRI : ordonner les mémos (board + colonne MÉMOS).

Demande Fabien du 25 sept. 2026, prototype validé dans localhost:8099. Brief :
`docs/briefs/MEMO-SORT-DATES.md`. Doctrine reprise de [LINK-SORT] (V27.45.260) : **le tri est
une VUE**, jamais une écriture.

Ce que ces parcours PROTÈGENT :

- **un seul état pour deux surfaces** : le board et la colonne lisent la même clé, donc choisir
  « Échéance » sur le board trie aussi la colonne, et réciproquement (test 5) — deux réglages
  jumeaux qui divergeraient seraient pires que pas de tri du tout ;
- **`position` n'est jamais écrite** (test 7) : aucun POST `/api/memos/reorder`, et le retour au
  Manuel retrouve l'ordre d'origine — ce qui n'est vrai que si `state.memos` n'est pas trié
  en place ;
- **« sans date » descend, il ne remonte pas** (test 4) : en tri Échéance, une date absente n'est
  pas « le 0000-00-00 », c'est « pas de date » — ces mémos vont en bas, dans leur ordre manuel ;
- **le D&D de réordonnancement est coupé hors Manuel, mais le D&D vers un DOSSIER reste actif**
  (test 8) : changer de dossier n'est pas réordonner, et le confondre coûterait un geste
  quotidien.

⚠ Le « Manuel » n'est pas le même objet des deux côtés, et c'est voulu : la colonne rend l'ordre
de l'API (`position, id`), le board garde son tri intra-section par date/heure (`byTime`, qui
existait avant ce lot). « Manuel » veut dire « exactement ce qu'on voyait avant », pas « non
trié » — c'est la décision n° 1 du brief (rien ne bouge tant qu'on ne clique pas).
"""
import os as _os
import sqlite3 as _sqlite3
import time as _time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1500, "height": 1000}

# Ordre de CRÉATION (A le plus ancien). Les dates sont en novembre 2026, donc toutes à venir :
# les six mémos se répartissent entre « À VENIR » et « SANS DATE », jamais « EN RETARD ».
_DECOR = [
    ("MS alpha", "2026-11-05", ""),
    ("MS bravo", "2026-11-06", "2026-11-08"),   # une PLAGE, classée par son début
    ("MS charlie", "2026-11-20", ""),
    ("MS delta", "", ""),
    ("MS echo", "", ""),
    ("MS foxtrot", "2026-11-02", ""),
]
# Ordre MANUEL voulu (indices dans _DECOR) : ne coïncide avec aucun des trois tris.
_MANUEL = (3, 2, 0, 5, 4, 1)          # delta, charlie, alpha, foxtrot, echo, bravo

_MEMOS = []
_PROJETS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    """Le `live_server` est session-scoped : ce fichier remballe son décor.

    Un mémo laissé derrière pollue la colonne MÉMOS de TOUS les tests suivants — elle agrège
    l'ensemble des mémos, sans filtre de dossier.
    """
    _MEMOS.clear(); _PROJETS.clear()
    yield
    import requests
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
        except Exception:
            pass
    for pid in _PROJETS:
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    _MEMOS.clear(); _PROJETS.clear()


def _semer(live_server):
    """Six mémos dans un dossier à part, `position` mélangée. Rend `(ids, ordre_manuel)`."""
    import requests
    r = requests.post(live_server + "/api/projects", json={"name": "Tri des mémos"}, timeout=5)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    ids = []
    for titre, due, end in _DECOR:
        corps = {"content": titre + " — décor de tri", "title": titre, "project_id": pid}
        if due:
            corps["due_date"] = due
        if end:
            corps["due_end"] = end
        r = requests.post(live_server + "/api/memos", json=corps, timeout=5)
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
        _MEMOS.append(ids[-1])
        _time.sleep(0.02)          # des `created_at` franchement distincts
    tous = [m["id"] for m in requests.get(live_server + "/api/memos", timeout=5).json()]
    autres = [i for i in tous if i not in ids]
    manuel = [ids[i] for i in _MANUEL]
    r = requests.post(live_server + "/api/memos/reorder",
                      json={"ids": autres + manuel}, timeout=5)
    assert r.status_code == 200, r.text
    return pid, ids, manuel


def _ouvrir(page, label):
    """Clique l'entrée de sidebar dont le libellé est EXACTEMENT `label` — la vraie porte.

    ⚠ Les deux surfaces ne vivent pas dans la même vue : le BOARD est la vue Mémos, la COLONNE
    MÉMOS n'est affichée qu'en vue Liens (`#memo-panel` est masqué ailleurs). Un test qui
    cliquerait le ⇅ depuis le board attendrait un bouton invisible jusqu'au timeout.
    """
    page.evaluate(
        "l => [...document.querySelectorAll('#sidebar .cat-item')]"
        "      .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === l).click()",
        label,
    )
    page.wait_for_timeout(300)


def _boot(page, live_server, tri=None, projet=None):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.evaluate(
        "v => { try { v === null ? localStorage.removeItem('dash:memoSort')"
        "                        : localStorage.setItem('dash:memoSort', v); } catch (e) {} }",
        tri,
    )
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    if projet:
        page.locator(".cat-item", has_text=projet).first.click()
        page.wait_for_timeout(300)
    page.wait_for_load_state("networkidle")


def _titres_board(page):
    """Les titres de NOS mémos dans le board, dans l'ordre affiché, sections aplaties."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#memo-board .task')]"
        "       .map(t => (t.textContent.match(/MS [a-z]+/) || [''])[0]).filter(Boolean)"
    )


def _titres_colonne(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#memos .memo-note')]"
        "       .map(n => (n.textContent.match(/MS [a-z]+/) || [''])[0]).filter(Boolean)"
    )


def _trier_board(page, mode):
    btn = page.locator('#memo-sort-seg button[data-msort="%s"]' % mode)
    btn.click()
    page.wait_for_timeout(250)
    assert btn.get_attribute("aria-pressed") == "true"


def _trier_colonne(page, mode):
    page.locator("#memo-sort-btn").click()
    page.wait_for_timeout(150)
    page.locator('#memo-sort-menu button[data-msort="%s"]' % mode).click()
    page.wait_for_timeout(250)


def _positions(live_server):
    import requests
    return [(m["id"], m["position"])
            for m in requests.get(live_server + "/api/memos", timeout=5).json()]


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    """Erreurs de console, moins le seul bruit attendu : le 404 de `/api/favicon/<id>` des cards
    de liens laissées par d'autres fichiers. Le filtre n'est levé qu'après avoir vérifié, sur les
    réponses réelles, qu'aucun AUTRE 404 n'a eu lieu (montage de `test_search_fold`)."""
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- 1


def test_defaut_manuel(page, live_server, console_errors, urls_404):
    """Sans réglage, board ET colonne sont EXACTEMENT ce qu'on voyait avant le lot.

    Board : le tri intra-section par date/heure qui existait déjà (foxtrot 2 nov, alpha 5,
    bravo 6→8, charlie 20 ; puis SANS DATE). Colonne : l'ordre `position` de l'API.
    """
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, tri=None, projet="Tri des mémos")
    assert _titres_board(page) == ["MS foxtrot", "MS alpha", "MS bravo", "MS charlie",
                                   "MS delta", "MS echo"]
    assert _titres_colonne(page) == ["MS delta", "MS charlie", "MS alpha",
                                     "MS foxtrot", "MS echo", "MS bravo"]
    assert page.locator('#memo-sort-seg button[data-msort="manual"]').get_attribute("aria-pressed") == "true"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 2


def test_board_plus_recents(page, live_server, console_errors, urls_404):
    """« Plus récents » = `created_at` DESC dans chaque section, `id` DESC en cas d'égalité.

    Le départage par `id` n'est pas une coquetterie : des mémos importés d'un même export
    partagent la date posée à l'import. Le décor le reproduit — et la PAIRE est choisie pour
    que le départage change quelque chose : charlie arrive avant foxtrot dans l'ordre manuel,
    donc sans départage un tri stable les laisserait dans cet ordre ; avec, foxtrot passe
    devant (son id est le plus grand). Une paire mal choisie aurait rendu le même résultat
    des deux côtés — le test aurait été vert sans rien prouver.
    """
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, projet="Tri des mémos")
    _trier_board(page, "newest")
    # À VENIR : foxtrot (créé 6e), charlie (3e), bravo (2e), alpha (1er) ; puis SANS DATE : echo, delta.
    assert _titres_board(page) == ["MS foxtrot", "MS charlie", "MS bravo", "MS alpha",
                                   "MS echo", "MS delta"]

    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        (date_charlie,) = con.execute(
            "SELECT created_at FROM memos WHERE id = ?", (ids[2],)).fetchone()
        con.execute("UPDATE memos SET created_at = ? WHERE id = ?", (date_charlie, ids[5]))
        con.commit()
    finally:
        con.close()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    _ouvrir(page, "Tri des mémos")
    page.wait_for_load_state("networkidle")
    assert _titres_board(page) == ["MS foxtrot", "MS charlie", "MS bravo", "MS alpha",
                                   "MS echo", "MS delta"], "à date égale, le plus grand id d'abord"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 3


def test_modifies(page, live_server, console_errors, urls_404):
    """« Modifiés » = `updated_at` DESC : le mémo le plus ancien qu'on vient de toucher passe devant."""
    import requests
    _pid, ids, manuel = _semer(live_server)
    r = requests.put(live_server + "/api/memos/%d" % ids[0],       # alpha, le plus ancien
                     json={"content": "MS alpha — retouché"}, timeout=5)
    assert r.status_code == 200, r.text
    _boot(page, live_server, projet="Tri des mémos")
    _trier_board(page, "updated")
    assert _titres_board(page)[0] == "MS alpha"
    assert _titres_colonne(page)[0] == "MS alpha"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 4


def test_echeance_sans_date_en_bas(page, live_server, console_errors, urls_404):
    """« Échéance » : la plus proche d'abord, la PLAGE classée par son début, sans date EN BAS.

    Mesuré sur la COLONNE : le board sépare déjà les sans-date dans leur propre section, donc
    il ne peut pas prouver la règle. Entre eux, les sans-date gardent l'ordre manuel.
    """
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server)
    _ouvrir(page, "Tous")          # la colonne MÉMOS n'existe qu'en vue Liens
    _trier_colonne(page, "due")
    assert _titres_colonne(page) == ["MS foxtrot", "MS alpha", "MS bravo", "MS charlie",
                                     "MS delta", "MS echo"]
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 5


def test_board_et_colonne_partagent_le_reglage(page, live_server, console_errors, urls_404):
    """UN seul réglage : le board commande la colonne, et la colonne commande le board."""
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, projet="Tri des mémos")

    _trier_board(page, "due")
    assert _titres_colonne(page)[0] == "MS foxtrot", "la colonne suit le board"

    _ouvrir(page, "Tous")          # vue Liens : c'est là que vit la colonne MÉMOS
    page.locator("#memo-sort-btn").click()
    page.wait_for_timeout(200)
    actif = page.locator("#memo-sort-menu button.on").get_attribute("data-msort")
    assert actif == "due", "le menu de la colonne montre le mode choisi sur le board"
    page.keyboard.press("Escape")

    _trier_colonne(page, "newest")
    assert page.evaluate("() => localStorage.getItem('dash:memoSort')") == "newest"
    _ouvrir(page, "Tri des mémos")
    assert page.locator('#memo-sort-seg button[data-msort="newest"]').get_attribute("aria-pressed") == "true"
    assert _titres_board(page)[0] == "MS foxtrot"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 6


def test_memorise_et_valeur_corrompue(page, live_server, console_errors, urls_404):
    """Le tri survit au rechargement ; une valeur inconnue retombe sur Manuel sans rien casser."""
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, tri="due", projet="Tri des mémos")
    assert _titres_colonne(page)[0] == "MS foxtrot"
    assert page.locator('#memo-sort-seg button[data-msort="due"]').get_attribute("aria-pressed") == "true"

    _boot(page, live_server, tri="n-importe-quoi", projet="Tri des mémos")
    assert _titres_colonne(page) == ["MS delta", "MS charlie", "MS alpha",
                                     "MS foxtrot", "MS echo", "MS bravo"]
    assert page.locator('#memo-sort-seg button[data-msort="manual"]').get_attribute("aria-pressed") == "true"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 7


def test_le_tri_nest_pas_une_ecriture(page, live_server, console_errors, urls_404):
    """Trier ne réordonne rien en base, et revenir au Manuel retrouve l'ordre d'origine.

    La seconde moitié est le garde-fou du tri EN PLACE : si `sortMemos` triait `state.memos`,
    l'ordre manuel serait détruit au premier clic et ne reviendrait qu'au prochain `loadAll()`.
    """
    _pid, ids, manuel = _semer(live_server)
    avant = _positions(live_server)
    _boot(page, live_server, projet="Tri des mémos")
    ecritures = []
    page.on("request", lambda r: ecritures.append(r.url)
            if r.method == "POST" and "/api/memos/reorder" in r.url else None)
    _trier_board(page, "newest")
    _trier_board(page, "due")
    _trier_board(page, "manual")
    assert ecritures == [], "le tri est une vue, il n'écrit jamais de position"
    assert _positions(live_server) == avant
    assert _titres_colonne(page) == ["MS delta", "MS charlie", "MS alpha",
                                     "MS foxtrot", "MS echo", "MS bravo"]
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 8


_DND_REORDER = """
() => {
  const tasks = [...document.querySelectorAll('#memo-board .task')];
  const src = tasks[0], cible = tasks[2];
  src.dispatchEvent(new DragEvent('dragstart', {
    bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
  const r = cible.getBoundingClientRect();
  cible.dispatchEvent(new DragEvent('dragover', {
    bubbles: true, cancelable: true, clientY: r.top + r.height - 2 }));
  src.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true }));
}
"""


def test_dnd_reordre_coupe_mais_deplacement_conserve(page, live_server, console_errors, urls_404):
    """Hors Manuel : réordonner à la main n'existe plus, DÉPLACER dans un dossier existe toujours.

    On vérifie d'abord que le réordonnancement MARCHE en Manuel — sinon « il ne bouge pas en
    tri » serait vert parce que le geste synthétique ne fait rien du tout.
    """
    import requests
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, projet="Tri des mémos")
    avant = _titres_board(page)
    page.evaluate(_DND_REORDER)
    page.wait_for_timeout(150)
    assert _titres_board(page) != avant, "en Manuel, le D&D doit déplacer la card"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    page.locator(".cat-item", has_text="Tri des mémos").first.click()
    page.wait_for_timeout(300)
    _trier_board(page, "newest")
    trie = _titres_board(page)
    page.evaluate(_DND_REORDER)
    page.wait_for_timeout(150)
    assert _titres_board(page) == trie, "hors Manuel, un dragover ne réordonne rien"

    # …mais le D&D vers un dossier de la sidebar reste actif : déplacer n'est pas réordonner.
    cible = page.locator('#sidebar .cat-item', has_text="Inbox").first
    assert cible.count() or True
    page.evaluate("""
    () => {
      const t = document.querySelector('#memo-board .task');
      window.__msId = Number(t.dataset.memoId);
      t.dispatchEvent(new DragEvent('dragstart', {
        bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
      const cible = [...document.querySelectorAll('#sidebar .cat-item')]
        .find(i => /Inbox/.test(i.textContent));
      cible.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true }));
      cible.dispatchEvent(new DragEvent('drop', {
        bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
    }
    """)
    page.wait_for_timeout(700)
    deplace = page.evaluate("() => window.__msId")
    r = requests.get(live_server + "/api/memos", timeout=5).json()
    ligne = [m for m in r if m["id"] == deplace][0]
    assert not ligne["project_id"], "le D&D vers un dossier reste actif en mode trié"
    assert _erreurs_js(console_errors, urls_404) == []


# --------------------------------------------------------------------------- 9


def test_filtre_puis_tri(page, live_server, console_errors, urls_404):
    """Le tri s'applique APRÈS les filtres : tuile « À venir » + « Échéance » → les seuls à venir."""
    _pid, ids, manuel = _semer(live_server)
    _boot(page, live_server, projet="Tri des mémos")
    _trier_board(page, "due")
    page.evaluate("() => { state.memoFilter = 'scheduled'; renderAll(); }")
    page.wait_for_timeout(250)
    assert _titres_board(page) == ["MS foxtrot", "MS alpha", "MS bravo", "MS charlie"]
    assert _erreurs_js(console_errors, urls_404) == []
