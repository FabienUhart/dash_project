"""[SEARCH-FOLD] Une recherche qui trouve ce qu'on tape.

Quatre défauts mesurés en prod le 6 sept. 2026 (244 mémos), tous dus au même `includes(q)` brut :
les accents comptent (« eclipse » et « éclipse » ne rendent pas le même ensemble), l'ordre des
mots compte (« sanjo kyoto » ne trouve pas « Kyoto · Sanjo »), la portée « Tout » annonce un
dossier sans montrer ses mémos, et « Aucun résultat » ne dit pas qu'on cherche dans un dossier.

Ces parcours mesurent ce que l'utilisateur VOIT : on tape dans la vraie barre et on lit les cards
rendues. Le normaliseur est éprouvé sur les TROIS pages (owner, partage, hub) — c'est un helper
partagé, donc un test par page, sinon « identique » n'est qu'une intention.
"""
import os as _os
import sqlite3 as _sqlite3

import pytest

pytestmark = pytest.mark.e2e

_N = [0]
_CREE = {"projets": [], "memos": [], "liens": []}


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    """Ce fichier ne laisse rien derrière lui.

    Le `live_server` est session-scoped : un mémo « Éclipse » oublié fausserait le test suivant,
    et un dossier « Voyage Japon » oublié ferait un 409 à la création suivante (unicité des noms
    frères, v25). Leçon payée en [LINK-OG], où des liens survivants ont fait rougir sept tests
    qu'ils ne touchaient pas.
    """
    for k in _CREE:
        _CREE[k].clear()
    yield
    for mid in _CREE["memos"]:
        try:
            _req_delete(live_server, "/api/memos/%d" % mid)
        except Exception:
            pass
    for lid in _CREE["liens"]:
        try:
            _req_delete(live_server, "/api/links/%d" % lid)
        except Exception:
            pass
    for pid in reversed(_CREE["projets"]):          # enfants avant parents
        try:
            _req_delete(live_server, "/api/projects/%d" % pid)
        except Exception:
            pass
    for k in _CREE:
        _CREE[k].clear()


def _req_delete(live_server, path):
    import requests
    requests.delete(live_server + path, timeout=5)


# ------------------------------------------------------------------ seed ---

def _projet(page, live_server, nom, parent=None):
    """⚠ `POST /api/projects` crée TOUJOURS à la racine et ignore `parent_id` : le déplacement
    se fait par un `PUT` ensuite (c'est ce que fait le front). Un seed qui postait le parent
    directement fabriquait deux dossiers FRÈRES — et le test « les descendants remontent »
    n'avait alors aucun descendant à remonter."""
    r = page.request.post(live_server + "/api/projects", data={"name": nom})
    assert r.status == 201, r.text()
    pid = r.json()["id"]
    _CREE["projets"].append(pid)
    if parent:
        mv = page.request.put(live_server + "/api/projects/%d" % pid,
                              data={"name": nom, "parent_id": parent})
        assert mv.ok, mv.text()
        assert mv.json().get("parent_id") == parent, \
            "le dossier n'a pas été rattaché : %s" % mv.text()
    return pid


def _memo(page, live_server, contenu, projet=None):
    corps = {"content": contenu}
    if projet:
        corps["project_id"] = projet
    r = page.request.post(live_server + "/api/memos", data=corps)
    assert r.status in (200, 201), r.text()
    m = r.json()
    _CREE["memos"].append(m["id"])
    return m


def _lien(page, live_server, nom, tags=""):
    r = page.request.post(live_server + "/api/links", data={"name": nom, "tags": tags})
    assert r.status == 201, r.text()
    l = r.json()
    _CREE["liens"].append(l["id"])
    return l


def _semer(page, live_server):
    """Le décor du brief. Le jeton rend les NOMS DE DOSSIER uniques (unicité des frères, v25)
    sans polluer les mots qu'on cherche : « eclipse », « sanjo », « jumeaux » restent nus."""
    _N[0] += 1
    tok = "zk%d" % _N[0]
    japon = _projet(page, live_server, "Voyage Japon" + tok)
    kyoto = _projet(page, live_server, "Activités Kyoto" + tok, parent=japon)
    hotel = _memo(page, live_server, "🏨 Kyoto · Sanjo — ch. lits jumeaux", projet=kyoto)
    temple = _memo(page, live_server, "Temple Kiyomizu au lever du jour", projet=kyoto)
    # Un mémo du dossier RACINE, pour prouver que la fusion descend ET reste au niveau du dessus.
    vol = _memo(page, live_server, "Vol Paris Tokyo", projet=japon)
    # Le mot cherché est dans le NOM du dossier, pas dans ces mémos : ils ne peuvent arriver
    # que par la fusion. Celui-ci, lui, le porte dans son texte → il éprouve la déduplication.
    textuel = _memo(page, live_server, "Acheter un guide du Japon" + tok)
    acc = _memo(page, live_server, "Éclipse totale, prévoir les lunettes")
    sans = _memo(page, live_server, "eclipse partielle depuis le balcon")
    _lien(page, live_server, "Notes perso", tags="notes")
    return {"tok": tok, "japon": japon, "kyoto": kyoto, "hotel": hotel, "temple": temple,
            "vol": vol, "textuel": textuel, "acc": acc, "sans": sans}


# ------------------------------------------------------------- pilotage ---

def _boot(page, live_server, path="/"):
    page.set_viewport_size({"width": 1400, "height": 900})
    page.goto(live_server + path, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")


def _vue_memos(page):
    item = page.locator(".cat-item", has_text="Mémos").first
    item.click()
    page.wait_for_selector("#memo-board", state="visible", timeout=10_000)


def _chercher(page, texte):
    """Tape dans la VRAIE barre (événement `input` → `refreshSearch`), pas dans l'état."""
    champ = page.locator("#search")
    champ.fill("")
    champ.fill(texte)
    page.wait_for_timeout(250)


_LIRE_MEMOS = """() => {
  const out = [];
  document.querySelectorAll('#memo-board .memo-section').forEach(sec => {
    const h = sec.querySelector('h2');
    if (h && h.textContent.trim().startsWith('PROJETS')) return;   // la section dossiers
    sec.querySelectorAll('.task .task-content').forEach(c => out.push(c.textContent.trim()));
  });
  return out;
}"""

_LIRE_PROJETS = """() => {
  const secs = [...document.querySelectorAll('#memo-board .memo-section')];
  const sec = secs.find(s => { const h = s.querySelector('h2');
                               return h && h.textContent.trim().startsWith('PROJETS'); });
  if (!sec) return null;
  return [...sec.querySelectorAll('.task')].map(t => ({
    nom: (t.querySelector('.task-content') || {}).textContent.trim(),
    badges: [...t.querySelectorAll('.badge')].map(b => b.textContent.trim()),
  }));
}"""


def _memos_owner(page):
    return page.evaluate(_LIRE_MEMOS)


def _memos_invite(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('.task .task-content')].map(c => c.textContent.trim())")


def _contient(liste, fragment):
    return any(fragment in t for t in liste)


def _ouvrir_hub(page, live_server, projet_id):
    """Un hub invité approuvé sur ce dossier. Le hub n'est pas atteignable au seul jeton de
    partage : il faut inscrire l'invité, lire son `hub_token` en base (il ne sort que par
    e-mail) et l'approuver par son code — même montage que `test_hub_comments_popin`."""
    _N[0] += 1
    email = "chercheuse%d@ex.com" % _N[0]
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": projet_id}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Chercheuse", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        hub_token, pin = con.execute(
            "SELECT hub_token, pin FROM guest_hubs WHERE email = ?", (email,)).fetchone()
    finally:
        con.close()
    page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
    ok = page.request.post(live_server + "/share/hub/%s/approve" % hub_token, data={"pin": pin})
    assert ok.ok, ok.text()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    return hub_token


def _ouvrir_dossier(page, nom):
    """Clique le dossier dans la sidebar — la vraie porte, celle qui pose `state.memoProject`."""
    item = page.locator(".cat-item", has_text=nom).first
    item.click()
    page.wait_for_timeout(300)


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    """Erreurs de console, débarrassées du seul bruit attendu : le 404 de `/api/favicon/<id>`.
    Une card de lien demande son favicon, que le navigateur coupé du réseau (garde e2e) ne peut
    pas atteindre. La ligne de console ne dit pas quelle ressource a manqué : on ne la retire
    donc qu'après avoir vérifié, sur les réponses réelles, qu'aucun AUTRE 404 n'a eu lieu."""
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# ----------------------------------------------------------------- #1 -----

def test_search_ignores_accents_owner(live_server, page, console_errors, urls_404):
    """« eclipse » et « éclipse » doivent rendre le MÊME ensemble.

    On compare les deux résultats ENTRE EUX plutôt qu'à un compte figé : c'est exactement la
    propriété visée, et ça reste vrai quel que soit le bruit laissé par d'autres tests.
    """
    _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)

    _chercher(page, "eclipse")
    sans = sorted(_memos_owner(page))
    _chercher(page, "éclipse")
    avec = sorted(_memos_owner(page))

    assert sans == avec, "l'accent change le résultat :\nsans = %s\navec = %s" % (sans, avec)
    assert _contient(sans, "Éclipse totale"), "le mémo accentué manque"
    assert _contient(sans, "eclipse partielle"), "le mémo non accentué manque"
    assert _erreurs_js(console_errors, urls_404) == []


def test_search_ignores_accents_share(live_server, page):
    d = _semer(page, live_server)
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["japon"]}).json()
    _memo(page, live_server, "Éclipse vue du Japon", projet=d["kyoto"])
    _memo(page, live_server, "eclipse nuageuse", projet=d["kyoto"])
    _boot(page, live_server, "/share/" + sh["token"])

    _chercher(page, "eclipse")
    sans = sorted(_memos_invite(page))
    _chercher(page, "éclipse")
    avec = sorted(_memos_invite(page))

    assert sans == avec, "partage : l'accent change le résultat\n%s\n%s" % (sans, avec)
    assert len(sans) == 2, sans


def test_search_ignores_accents_hub(live_server, page):
    d = _semer(page, live_server)
    _memo(page, live_server, "Éclipse vue du hub", projet=d["kyoto"])
    _memo(page, live_server, "eclipse du hub, sans accent", projet=d["kyoto"])
    _ouvrir_hub(page, live_server, d["japon"])

    _chercher(page, "eclipse")
    sans = sorted(_memos_invite(page))
    _chercher(page, "éclipse")
    avec = sorted(_memos_invite(page))

    assert sans == avec, "hub : l'accent change le résultat\n%s\n%s" % (sans, avec)
    assert len(sans) == 2, sans


# ----------------------------------------------------------------- #2 -----

def test_search_any_word_order_owner(live_server, page, console_errors, urls_404):
    """« sanjo kyoto » doit trouver « Kyoto · Sanjo » — tous les mots, n'importe quel ordre."""
    _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)

    _chercher(page, "kyoto sanjo")
    ordre = sorted(_memos_owner(page))
    _chercher(page, "sanjo kyoto")
    inverse = sorted(_memos_owner(page))

    assert _contient(ordre, "Sanjo"), "l'ordre naturel ne trouve déjà rien : seed cassé"
    assert ordre == inverse, "l'ordre des mots change le résultat :\n%s\n%s" % (ordre, inverse)

    _chercher(page, "jumeaux lits")
    assert _contient(_memos_owner(page), "lits jumeaux"), \
        "« jumeaux lits » ne trouve pas « lits jumeaux »"
    assert _erreurs_js(console_errors, urls_404) == []


def test_search_any_word_order_share(live_server, page):
    d = _semer(page, live_server)
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["japon"]}).json()
    _boot(page, live_server, "/share/" + sh["token"])

    _chercher(page, "kyoto sanjo")
    ordre = sorted(_memos_invite(page))
    _chercher(page, "sanjo kyoto")
    inverse = sorted(_memos_invite(page))
    assert _contient(ordre, "Sanjo"), "seed cassé côté partage : %s" % ordre
    assert ordre == inverse, "partage : l'ordre des mots compte encore\n%s\n%s" % (ordre, inverse)


def test_search_any_word_order_hub(live_server, page):
    d = _semer(page, live_server)
    _ouvrir_hub(page, live_server, d["japon"])

    _chercher(page, "kyoto sanjo")
    ordre = sorted(_memos_invite(page))
    _chercher(page, "sanjo kyoto")
    inverse = sorted(_memos_invite(page))
    assert _contient(ordre, "Sanjo"), "seed cassé côté hub : %s" % ordre
    assert ordre == inverse, "hub : l'ordre des mots compte encore\n%s\n%s" % (ordre, inverse)


# ----------------------------------------------------------------- #3 -----

def test_search_all_merges_folder_subtree(live_server, page, console_errors, urls_404):
    """Portée « Tout » : un dossier trouvé apporte SES mémos et ceux de ses DESCENDANTS.

    Le mot cherché n'est que dans le nom du dossier — les mémos du sous-arbre ne peuvent donc
    arriver que par la fusion. Un mémo le porte aussi dans son texte : il éprouve la dédup.
    """
    d = _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)
    _chercher(page, "japon" + d["tok"])

    memos = _memos_owner(page)
    assert _contient(memos, "guide du Japon"), "le mémo trouvé par le TEXTE a disparu"
    assert _contient(memos, "Vol Paris Tokyo"), "le mémo direct du dossier n'est pas remonté"
    assert _contient(memos, "lits jumeaux"), \
        "le mémo du SOUS-dossier n'est pas remonté (fusion sans descendants)"
    assert len(memos) == len(set(memos)), "doublon : la dédup n'a pas eu lieu (%s)" % memos

    assert _contient(memos, "Temple Kiyomizu"), "le second mémo du sous-dossier manque"

    # Le compteur doit dire le SOUS-ARBRE (3 : vol + hôtel + temple), pas les seuls mémos
    # DIRECTS (1 : le vol) — c'est tout l'écart que le défaut #3 laissait voir en prod.
    projets = page.evaluate(_LIRE_PROJETS)
    assert projets, "la ligne PROJETS a disparu"
    badge = " ".join(projets[0]["badges"])
    assert "3 mémo" in badge, \
        "le compteur ne dit pas le total du sous-arbre (badge = %r, attendu « 3 mémos »)" % badge

    # Contrôle de non-régression : `m#` reste « texte seul », il ne fusionne pas.
    _chercher(page, "m#japon" + d["tok"])
    seuls = _memos_owner(page)
    assert _contient(seuls, "guide du Japon")
    assert not _contient(seuls, "lits jumeaux"), "m# a fusionné le dossier : ce n'est pas son rôle"
    assert _erreurs_js(console_errors, urls_404) == []


# ----------------------------------------------------------------- #4 -----

def test_search_projects_scope_includes_descendants(live_server, page, console_errors, urls_404):
    """`p#` : les mémos des DESCENDANTS du dossier trouvé comptent aussi."""
    d = _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)
    _chercher(page, "p#japon" + d["tok"])

    memos = _memos_owner(page)
    assert _contient(memos, "Vol Paris Tokyo"), "le mémo direct manque"
    assert _contient(memos, "lits jumeaux"), \
        "le mémo du sous-dossier manque : p# ignore encore les descendants"
    assert _erreurs_js(console_errors, urls_404) == []


# ----------------------------------------------------------------- #5 -----

def test_no_result_names_folder_and_widens(live_server, page, console_errors, urls_404):
    """Dans un dossier, zéro résultat doit DIRE où l'on cherche et proposer d'en sortir."""
    d = _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)
    _ouvrir_dossier(page, "Voyage Japon" + d["tok"])
    _chercher(page, "eclipse")

    assert _memos_owner(page) == [], "le seed place un « eclipse » dans le dossier : test faussé"
    vide = page.locator("#memo-board .empty-state")
    assert vide.count() == 1, "aucun état vide rendu"
    hint = vide.locator(".es-hint").inner_text()
    assert "dans" in hint.lower() and "Voyage Japon" in hint, \
        "le message ne nomme pas le dossier : %r" % hint

    partout = vide.locator("button", has_text="Chercher partout")
    assert partout.count() == 1, "pas de bouton « Chercher partout » : impasse pour l'utilisateur"
    partout.click()
    page.wait_for_timeout(300)

    apres = _memos_owner(page)
    assert _contient(apres, "Éclipse totale") and _contient(apres, "eclipse partielle"), \
        "« Chercher partout » n'a pas élargi : %s" % apres
    assert page.locator("#search-chip").is_hidden(), "le chip « dans : » aurait dû disparaître"
    assert _erreurs_js(console_errors, urls_404) == []


# ------------------------------------------------- non-régressions (#6) ---

def test_tag_search_stays_exact(live_server, page, console_errors, urls_404):
    """`#tag` garde son sens : match EXACT d'une étiquette, pas un mot parmi d'autres."""
    _semer(page, live_server)
    _boot(page, live_server)

    _chercher(page, "#notes")
    assert page.locator("#links .card", has_text="Notes perso").count() == 1
    _chercher(page, "#note")
    assert page.locator("#links .card", has_text="Notes perso").count() == 0, \
        "#note a matché l'étiquette #notes : le tag n'est plus exact"
    assert _erreurs_js(console_errors, urls_404) == []


def test_search_in_folder_still_bounded(live_server, page, console_errors, urls_404):
    """[SEARCH-IN-FOLDER] : dans un dossier, la recherche y reste bornée AVANT élargissement."""
    d = _semer(page, live_server)
    _boot(page, live_server)
    _vue_memos(page)
    _ouvrir_dossier(page, "Voyage Japon" + d["tok"])
    # ⚠ Un SEUL mot, délibérément : avec deux mots ce test dépendrait du correctif « ordre des
    # mots » et cesserait d'être une non-régression — il doit être vert AVANT comme APRÈS.
    _chercher(page, "sanjo")

    assert _contient(_memos_owner(page), "Sanjo"), "le mémo du sous-dossier devrait être visible"
    assert page.locator("#search-chip").is_visible(), "le chip « dans : » a disparu"
    assert _erreurs_js(console_errors, urls_404) == []
