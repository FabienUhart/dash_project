"""[GUEST-ADD-FOLDER] Côté invité, le mémo se crée dans le dossier AFFICHÉ.

Brief : `docs/briefs/GUEST-ADD-FOLDER.md` (constat Fabien du 30 sept. 2026 : en invité editor, dans
le sous-dossier « test dossier », le mémo créé atterrissait à la racine de l'espace).

Cause : la barre « + Titre… » (`guestMemoAddBar.updateFolders`) restaurait la valeur précédente du
sélecteur, et la Note rapide (`initQuickMemo`) préférait la valeur courante au dossier affiché. Le
sélecteur doit SUIVRE la navigation, sauf choix manuel depuis la dernière navigation.
"""
import json
import re
import time

import pytest

pytestmark = pytest.mark.e2e

_BRUIT_404 = "the server responded with a status of 404"
_n = [0]


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return False


def _monter(page, live_server):
    """Partage editor d'un dossier racine R avec deux sous-dossiers S1, S2 ; invité approuvé."""
    _n[0] += 1
    k = _n[0]
    racine = page.request.post(live_server + "/api/projects", data={"name": "Espace GAF %d" % k}).json()

    def _sous(nom):   # POST /api/projects ignore parent_id : le parent se pose par PUT
        p = page.request.post(live_server + "/api/projects", data={"name": nom}).json()
        r = page.request.put(live_server + "/api/projects/%d" % p["id"], data={"parent_id": racine["id"]})
        assert r.ok, r.text()
        return p
    s1 = _sous("sous GAF %d-a" % k)
    s2 = _sous("sous GAF %d-b" % k)
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": racine["id"], "role": "editor"}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Gaston", "email": "gaf%d@ex.com" % k, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (sh["token"], reg.json()["guest_token"]))
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof render === 'function' && typeof DATA === 'object' && DATA && DATA.root_id")
    posts = []
    page.on("request", lambda r: posts.append(json.loads(r.post_data or "{}"))
            if r.method == "POST" and re.search(r"/share/[^/]+/memos$", r.url) else None)
    return {"R": racine["id"], "S1": s1["id"], "S2": s2["id"], "posts": posts}


def _aller(page, pid):
    """Navigation invitée, comme un clic dans la barre latérale (PFILTER = id ; 'all' = Tous)."""
    page.evaluate("pid => { PFILTER = pid; GVIEW = 'board'; render(); }", pid)
    page.evaluate("() => { setShareDock('memo', true); render(); }")   # barre repliée derrière le dock par défaut
    page.wait_for_selector("#add-bar input[type=text]")


def _creer_barre(page, ctx, titre):
    n = len(ctx["posts"])
    champ = page.locator("#add-bar input[type=text]")
    champ.fill(titre)
    champ.press("Enter")
    assert _attendre(page, lambda: len(ctx["posts"]) == n + 1), "aucun POST de création"
    # La barre vide son champ APRÈS `await load()` : attendre la fin de la soumission, sinon ce
    # vidage tardif efface la saisie suivante.
    assert _attendre(page, lambda: champ.input_value() == ""), "soumission jamais terminée"
    page.wait_for_load_state("networkidle")
    return ctx["posts"][-1].get("project_id")


def _creer_note_rapide(page, ctx, titre):
    n = len(ctx["posts"])
    page.locator("#qm-launch").click()
    page.wait_for_selector("#qm-panel:not([hidden]) .qm-title")
    page.locator("#qm-panel .qm-title").fill(titre)
    page.locator("#qm-panel .qm-go").click()
    assert _attendre(page, lambda: len(ctx["posts"]) == n + 1), "aucun POST de la Note rapide"
    assert _attendre(page, lambda: page.locator("#qm-panel .qm-title").input_value() == ""), "Note rapide jamais terminée"
    page.wait_for_load_state("networkidle")
    page.evaluate("() => { const p = document.getElementById('qm-panel'); if (p) p.hidden = true; }")
    return ctx["posts"][-1].get("project_id")


def test_barre_suit_le_sous_dossier_affiche(page, live_server, console_errors):
    ctx = _monter(page, live_server)
    _aller(page, ctx["R"])
    assert _creer_barre(page, ctx, "GAF barre racine") == ctx["R"]
    _aller(page, ctx["S1"])
    assert _creer_barre(page, ctx, "GAF barre sous") == ctx["S1"], "mémo créé hors du sous-dossier affiché"
    _aller(page, "all")
    assert _creer_barre(page, ctx, "GAF barre tous") == ctx["R"], "« Tous » doit créer à la racine de l'espace"
    assert _erreurs_js(console_errors) == []


def test_note_rapide_suit_le_sous_dossier_affiche(page, live_server, console_errors):
    ctx = _monter(page, live_server)
    _aller(page, ctx["R"])
    assert _creer_note_rapide(page, ctx, "GAF qm racine") == ctx["R"]
    _aller(page, ctx["S1"])
    assert _creer_note_rapide(page, ctx, "GAF qm sous") == ctx["S1"], "Note rapide créée hors du sous-dossier affiché"
    _aller(page, "all")
    assert _creer_note_rapide(page, ctx, "GAF qm tous") == ctx["R"]
    assert _erreurs_js(console_errors) == []


def test_choix_manuel_respecte_puis_la_navigation_reprend_la_main(page, live_server, console_errors):
    ctx = _monter(page, live_server)
    _aller(page, ctx["S1"])
    btn = page.locator("#add-bar .mab-details-btn")
    if btn.get_attribute("aria-expanded") != "true":
        btn.click()
    page.locator("#add-bar .mab-row2 select[title='Dossier de destination']").select_option(str(ctx["R"]))
    assert _creer_barre(page, ctx, "GAF manuel 1") == ctx["R"], "choix manuel ignoré"
    # Le re-rendu après création (même dossier affiché) ne doit pas effacer le choix manuel.
    assert _creer_barre(page, ctx, "GAF manuel 2") == ctx["R"], "choix manuel perdu au re-rendu"
    _aller(page, ctx["S2"])
    assert _creer_barre(page, ctx, "GAF apres nav") == ctx["S2"], "le sélecteur ne suit plus la navigation"
    # Même règle pour la Note rapide.
    page.locator("#qm-launch").click()
    page.wait_for_selector("#qm-panel:not([hidden]) .qm-folder")
    page.locator("#qm-panel .qm-folder").select_option(str(ctx["R"]))
    page.evaluate("() => { document.getElementById('qm-panel').hidden = true; }")
    assert _creer_note_rapide(page, ctx, "GAF qm manuel") == ctx["R"], "choix manuel Note rapide ignoré"
    _aller(page, ctx["S1"])
    assert _creer_note_rapide(page, ctx, "GAF qm apres nav") == ctx["S1"], "Note rapide ne suit plus la navigation"
    assert _erreurs_js(console_errors) == []


def test_badge_invite_ne_deborde_pas_en_mobile_owner(page, live_server, console_errors):
    """Révélé par ce lot : un mémo créé par un invité porte le badge « 👤 Nom » ; en mobile (vue
    Mémos owner) la rangée `.task-badges` prenait 100 % de largeur PLUS sa marge gauche de 2.1rem
    → la page débordait de 8 px (test_mobile_nav rougissait dès qu'un tel mémo existait en base)."""
    ctx = _monter(page, live_server)
    _aller(page, ctx["S1"])
    _creer_barre(page, ctx, "GAF badge invite")
    page.set_viewport_size({"width": 412, "height": 915})
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    page.wait_for_timeout(300)
    trop = page.evaluate("""() => [...document.querySelectorAll('.task .task-badges')]
      .filter(b => b.getBoundingClientRect().right > b.parentElement.getBoundingClientRect().right + 0.5).length""")
    assert page.locator(".task .task-badges .badge", has_text="Gaston").count() >= 1, "badge invité absent : test à vide"
    assert trop == 0, "%d rangée(s) de badges débordent de leur mémo" % trop
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0
    assert _erreurs_js(console_errors) == []
