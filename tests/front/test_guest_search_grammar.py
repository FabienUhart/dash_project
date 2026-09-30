"""[GUEST-SEARCH-GRAMMAR] La recherche invitée (partage + hub) parle la grammaire de l'owner.

Brief : `docs/briefs/GUEST-SEARCH-GRAMMAR.md` (cible V28.9.276). Constat Cowork
(`docs/tests/test-page-invite.md` § 3) : côté invité, `d#2026-09` répond « Aucun » alors qu'un
mémo est daté en septembre, les sous-tâches ne sont pas cherchées, `#mot` n'est pas compris.

⚠ SQUELETTE posé le 30 sept. 2026, AVANT le code : chaque scénario est marqué `skip` (« GSG —
code à venir »). La séance d'implémentation commence par retirer les skips et les voir ROUGES
(doctrine TDD), puis écrit le code. Les numéros de scénario suivent le § 4 du brief ; le n° 8
(non-régression owner) est porté par `test_search_dates.py` / `test_search_fold.py` inchangés, le
n° 9 (zéro erreur console) est une assertion de CHAQUE test ci-dessous.

La base du `live_server` est partagée par toute la session : le décor est supprimé en sortie
(fixture `_nettoyer`, même modèle que `test_search_all.py`).
"""
import os
import sqlite3
import time

import pytest

pytestmark = pytest.mark.e2e

SKIP = pytest.mark.skip(reason="GSG — code à venir")
BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}
PAGES = ["share", "hub"]
_BRUIT_404 = "the server responded with a status of 404"
_n = [0]
_CREES = []   # urls de suppression, dossiers en DERNIER


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """`c#` se lit dans le fuseau LOCAL de l'invité : on le fixe, comme `test_search_dates.py`."""
    return {**browser_context_args, "timezone_id": "Europe/Paris"}


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
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


def _db():
    return sqlite3.connect(os.path.join(os.environ["E2E_DATA_DIR"], "dashboard.db"))


# ------------------------------------------------------------------ décor


def _semer(page, live_server):
    """Dossier partagé « GSG racine k » + sous-dossier « GSG sous k ».

    Racine : kyoto (3 → 6 nov.), août (10 août), septembre (15 sept., le bug d'origine), tardif
    (CRÉÉ le 30/09 à 22 h 30 Z = 1er oct. à Paris), courses (sous-tâche « acheter du wasabi »),
    resa (`#resa` dans le contenu), resas (`#resas`). Sous-dossier : « GSG sous kyoto » (4 nov.).
    Les titres portent `k` : aucun décor d'un autre fichier ne peut matcher.
    """
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)

    def dossier(nom, parent=None):
        p = page.request.post(live_server + "/api/projects", data={"name": nom}).json()
        _CREES.insert(0, "/api/projects/%d" % p["id"])
        if parent:   # POST /api/projects ignore parent_id : le parent se pose par PUT
            r = page.request.put(live_server + "/api/projects/%d" % p["id"], data={"parent_id": parent})
            assert r.ok, r.text()
        return p

    def memo(titre, pid, **extra):
        corps = {"title": "%s %s" % (titre, k), "content": extra.pop("content", "décor GSG"),
                 "project_id": pid, **extra}
        r = page.request.post(live_server + "/api/memos", data=corps)
        assert r.ok, r.text()
        _CREES.append("/api/memos/%d" % r.json()["id"])
        return r.json()

    racine = dossier("GSG racine %s" % k)
    sous = dossier("GSG sous %s" % k, racine["id"])
    R = racine["id"]
    m = {
        "kyoto": memo("GSG kyoto", R, due_date="2026-11-03", due_end="2026-11-06"),
        "aout": memo("GSG août", R, due_date="2026-08-10"),
        "sept": memo("GSG septembre", R, due_date="2026-09-15"),
        "tardif": memo("GSG tardif", R),
        "courses": memo("GSG courses", R, subtasks=[{"content": "acheter du wasabi", "done": False}]),
        "resa": memo("GSG resa", R, content="<p>train réservé #resa</p>"),
        "resas": memo("GSG resas", R, content="<p>plusieurs #resas</p>"),
        "sous_kyoto": memo("GSG sous kyoto", sous["id"], due_date="2026-11-04"),
    }
    con = _db()
    try:
        con.execute("UPDATE memos SET created_at = ? WHERE id = ?", ("2026-09-30T22:30:00+00:00", m["tardif"]["id"]))
        con.execute("UPDATE memos SET created_at = ? WHERE id = ?", ("2026-08-15T10:00:00+00:00", m["aout"]["id"]))
        con.commit()
    finally:
        con.close()
    return {"k": k, "racine": racine, "sous": sous, "m": m}


def _ouvrir(page, live_server, ou, d, vp=BUREAU):
    """Ouvre le décor côté invité APPROUVÉ : `ou` = 'share' (jeton + localStorage) ou 'hub'
    (inscription, `hub_token` lu en base, approbation par code — montage de `test_search_fold`)."""
    _n[0] += 1
    email = "gsg%d@ex.com" % _n[0]
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["racine"]["id"], "role": "editor"}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Gaspard", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    page.set_viewport_size(vp)
    if ou == "share":
        page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (sh["token"], reg.json()["guest_token"]))
        page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    else:
        con = _db()
        try:
            hub_token, pin = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?", (email,)).fetchone()
        finally:
            con.close()
        # Approuver AVANT le premier chargement : sinon `/data` répond 403 une fois (écran code),
        # et ce 403 en console ferait rougir l'assertion « zéro erreur » pour une raison de harnais.
        ok = page.request.post(live_server + "/share/hub/%s/approve" % hub_token, data={"pin": pin})
        assert ok.ok, ok.text()
        page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#search", timeout=10_000)


def _chercher(page, texte):
    """Tape dans la VRAIE barre (événement `input`), comme l'invité."""
    champ = page.locator("#search")
    champ.fill("")
    champ.fill(texte)
    page.wait_for_timeout(250)


def _titres(page, k):
    """Titres des cards affichées qui appartiennent à CE décor (suffixe `k`), sans le suffixe."""
    vus = page.evaluate("() => [...document.querySelectorAll('.task .task-content')].map(c => c.textContent.trim())")
    out = []
    for t in vus:
        for nom in ("GSG sous kyoto", "GSG kyoto", "GSG août", "GSG septembre", "GSG tardif",
                    "GSG courses", "GSG resas", "GSG resa"):
            if (nom + " " + k) in t:
                out.append(nom)
                break
    return sorted(set(out))


def _aller_sous_dossier(page, ou, d):
    """Se placer dans le sous-dossier (PFILTER côté share, FOCUS côté hub)."""
    if ou == "share":
        page.evaluate("pid => { PFILTER = pid; GVIEW = 'board'; render(); }", d["sous"]["id"])
    else:
        page.evaluate("pid => { FOCUS = pid; VIEW = 'board'; render(); }", d["sous"]["id"])
    page.wait_for_timeout(200)


def _aide_desktop(page):
    page.locator("#search").click()
    page.wait_for_timeout(250)
    return page.evaluate("() => [...document.querySelectorAll('.sh-panel .sh-row')].map(r => r.textContent)")


# ------------------------------------------------------------------ scénarios (§ 4 du brief)


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_10_bug_origine_d_septembre(page, live_server, console_errors, ou):
    """§ 4.10 — rouge-avant : `d#2026-09` répondait « Aucun » (cherché comme TEXTE)."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "d#2026-09")
    assert "GSG septembre" in _titres(page, d["k"]), "d#2026-09 ne trouve pas le mémo du 15 sept."
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_01_d_echeance_plage_et_chip(page, live_server, console_errors, ou):
    """§ 4.1 — `d#2026-11` → kyoto seul (racine) ; un jour DANS la plage suffit ; chip + ✕."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "d#2026-11")
    assert _titres(page, d["k"]) == ["GSG kyoto", "GSG sous kyoto"]
    _chercher(page, "d#2026-11-05")
    assert _titres(page, d["k"]) == ["GSG kyoto"], "un jour à l'intérieur de la plage 3→6 doit matcher"
    chip = page.locator("#search-date-chip")
    assert chip.is_visible() and "échéance" in chip.inner_text()
    chip.locator(".sc-x").click()
    page.wait_for_timeout(250)
    assert chip.is_hidden()
    assert page.locator("#search").input_value() == "", "le ✕ retire le préfixe de date"
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_02_c_creation_jour_local(page, live_server, console_errors, ou):
    """§ 4.2 — `c#2026-10` : « tardif » (30/09 22 h 30 Z = 1er oct. à Paris) y est, « août » non."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "c#2026-10")
    vus = _titres(page, d["k"])
    assert "GSG tardif" in vus, "jour UTC au lieu du jour local ?"
    assert "GSG août" not in vus
    assert "créés" in page.locator("#search-date-chip").inner_text()
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_03_date_et_texte_et_forme_invalide(page, live_server, console_errors, ou):
    """§ 4.3 — `d#2026-11 kyoto` = intervalle ET mots ; `d#nimporte` = texte, sans chip."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "d#2026-11 kyoto")
    assert _titres(page, d["k"]) == ["GSG kyoto", "GSG sous kyoto"]
    _chercher(page, "d#2026-11 août")
    assert _titres(page, d["k"]) == []
    _chercher(page, "d#nimporte")
    assert page.locator("#search-date-chip").is_hidden(), "forme non reconnue → pas de chip"
    assert _titres(page, d["k"]) == []
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_04_sous_taches(page, live_server, console_errors, ou):
    """§ 4.4 — `wasabi` (seulement dans une sous-tâche) → « courses » ; `m#wasabi` idem."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "wasabi")
    assert _titres(page, d["k"]) == ["GSG courses"]
    _chercher(page, "m#wasabi")
    assert _titres(page, d["k"]) == ["GSG courses"]
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_05_hashtag_exact(page, live_server, console_errors, ou):
    """§ 4.5 — `#resa` → « resa » seul ; `#resas` ne répond pas à `#resa` (borne de fin)."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _chercher(page, "#resa")
    assert _titres(page, d["k"]) == ["GSG resa"]
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_06_predicat_pas_le_texte(page, live_server, console_errors, ou):
    """§ 4.6 — `d#` SANS mot : borné au sous-dossier (chip « dans : »), ✕ → élargi ; la carte /
    l'agenda suivent la liste ; la feuille mobile donne les mêmes résultats que le board."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    _aller_sous_dossier(page, ou, d)
    _chercher(page, "d#2026-11")
    assert _titres(page, d["k"]) == ["GSG sous kyoto"], "d# sans mot doit rester borné au dossier"
    # TODO séance : lire le chip « dans : » de CHAQUE page (sélecteur à confirmer : share/hub
    # n'ont pas le `#search-chip` owner), cliquer son ✕, puis :
    #   assert _titres(page, d["k"]) == ["GSG kyoto", "GSG sous kyoto"]
    # TODO séance : carte/agenda — comparer les ids de `shareMapPoints()`/`shareDatedPoints()`
    # (share) et de l'agenda hub (`focusedMemos()`) aux cards affichées.
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_06b_feuille_mobile_meme_resultat(page, live_server, console_errors, ou):
    """§ 4.6 (mobile 412 px) — la feuille ne doit plus répondre vide sur `d#` (`if (!q) return []`)."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d, vp=MOBILE)
    page.locator("#search").click()
    page.wait_for_selector("#search-sheet[open]", timeout=5_000)
    page.fill("#search-sheet input[type=text]", "d#2026-11")
    page.wait_for_timeout(300)
    titres = page.locator("#search-sheet .ss-item .ss-t").all_inner_texts()
    assert any("GSG kyoto " + d["k"] in t for t in titres), titres
    assert page.locator("#search-sheet .ss-empty").count() == 0
    assert _erreurs_js(console_errors) == []


@SKIP
@pytest.mark.parametrize("ou", PAGES)
def test_07_11_aide_invitee(page, live_server, console_errors, ou):
    """§ 4.7 — l'aide liste `d#`, `c#`, `#…` ; § 4.11 — ni `l#` ni la vue « Résultats » (owner-only)."""
    d = _semer(page, live_server)
    _ouvrir(page, live_server, ou, d)
    lignes = " ¦ ".join(_aide_desktop(page))
    for cle in ("d#", "c#", "#…"):   # « #… » = la ligne des #mots (« # » seul serait vrai grâce à « d# »)
        assert cle in lignes, "aide sans « %s » : %s" % (cle, lignes)
    assert "l#" not in lignes, "l# est owner-only (les liens ne sont pas partagés)"
    assert "Résultats" not in lignes, "la vue Résultats [SEARCH-ALL] est owner-only"
    assert _erreurs_js(console_errors) == []
