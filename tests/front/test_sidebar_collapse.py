"""[SIDEBAR-COLLAPSE] Replier l'arbre des dossiers, sortir « Invités », deux icônes.

Brief : `docs/briefs/SIDEBAR-COLLAPSE.md` (demande Fabien du 29 sept. 2026, démo validée).

Ce que ces parcours PROTÈGENT :

- **l'en-tête « 📂 Dossiers »** se replie comme LIENS / PROJETS / ÉTIQUETTES, mémorisé
  (`sbSection:dossiers`) ; replié, il affiche le total des mémos de l'arbre HORS Invités ;
- **Inbox reste visible** quand l'arbre est replié : c'est la boîte d'entrée ;
- **⇅** replie / déplie tous les dossiers d'un coup, sans basculer la section ; il écrit les clés
  `sbProjOpen:<id>` — les MÊMES que le panneau mobile, qui suit donc ;
- **« Invités »** (dossier système, racine) passe en dernier derrière un filet, hors compteur,
  non déplaçable — côté sidebar comme côté panneau mobile ;
- **la tuile « En cours »** ne copie plus l'icône 📥 de l'Inbox (contresens relevé par Fabien) ;
- **la pastille de la tuile Carte** dit ce qu'elle compte (`title`).

⚠ Écart au brief, assumé : le brief nomme `treeOpen:<id>` pour ⇅. Cette clé est celle de la vue
Plan ; la clé que la sidebar ET le panneau mobile partagent est `sbProjOpen:<id>` — c'est elle qui
tient la promesse « le panneau mobile suit ».
"""
import pytest
import requests
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

MOBILE = {"width": 412, "height": 915}
BUREAU = {"width": 1280, "height": 900}
INVITES = "Invités"

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


def _projet(live_server, nom, parent=None):
    r = requests.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    if parent:
        # `POST /api/projects` crée à la racine et ignore `parent_id` : on déplace ensuite.
        r = requests.put(live_server + "/api/projects/%d" % pid, json={"parent_id": parent}, timeout=5)
        assert r.status_code == 200, r.text
    return pid


def _invites(live_server):
    """Le dossier racine système « Invités » : réutilisé s'il existe déjà dans la base de test."""
    for p in requests.get(live_server + "/api/projects", timeout=5).json():
        if p["name"] == INVITES and not p.get("parent_id"):
            return p["id"]
    return _projet(live_server, INVITES)


def _memo(live_server, titre, pid=None, **extra):
    body = {"title": titre, "content": titre + " — décor SC"}
    if pid:
        body["project_id"] = pid
    body.update(extra)
    r = requests.post(live_server + "/api/memos", json=body, timeout=5)
    assert r.status_code in (200, 201), r.text
    _MEMOS.append(r.json()["id"])
    return r.json()["id"]


def _semer(live_server):
    """4 dossiers racine (dont un avec enfant) + « Invités » avec un enfant ; 6 mémos, 2 en Inbox."""
    alpha = _projet(live_server, "SC Alpha")
    alpha1 = _projet(live_server, "SC Alpha Un", parent=alpha)
    beta = _projet(live_server, "SC Beta")
    _projet(live_server, "SC Gamma")
    _projet(live_server, "SC Delta")
    inv = _invites(live_server)
    zoe = _projet(live_server, "SC Zoé", parent=inv)
    _memo(live_server, "SC m1", pid=alpha)
    _memo(live_server, "SC m2", pid=alpha1)
    _memo(live_server, "SC m3", pid=beta)
    _memo(live_server, "SC m4", pid=zoe)
    _memo(live_server, "SC inbox 1")
    _memo(live_server, "SC inbox 2")
    return {"alpha": alpha, "alpha1": alpha1, "beta": beta, "inv": inv, "zoe": zoe}


def _total_hors_invites(live_server):
    projs = requests.get(live_server + "/api/projects", timeout=5).json()
    inv = [p["id"] for p in projs if p["name"] == INVITES and not p.get("parent_id")]
    exclus = set(inv)
    changed = True
    while changed:
        changed = False
        for p in projs:
            if p.get("parent_id") in exclus and p["id"] not in exclus:
                exclus.add(p["id"]); changed = True
    return sum(p.get("memo_count") or 0 for p in projs if p["id"] not in exclus)


def _boot(page, live_server, viewport=BUREAU):
    page.set_viewport_size(viewport)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(
        "#folders-btn" if viewport is MOBILE else "nav#sidebar .cat-item", timeout=10_000)
    page.wait_for_timeout(400)


_BRUIT_404 = "the server responded with a status of 404"


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


HEAD = "nav#sidebar .sb-section-head[data-section='dossiers']"


def _ordre_sidebar(page):
    """Libellés de la sidebar, dans l'ordre du DOM, depuis Inbox (en-têtes marqués « # »)."""
    return page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('nav#sidebar .cat-item, nav#sidebar .sb-section-head').forEach(e => {
        if (e.classList.contains('sb-section-head')) out.push('#' + (e.dataset.section || ''));
        else out.push(((e.querySelector('.cat-label') || {}).textContent || '').trim());
      });
      return out.slice(out.indexOf('Inbox'));
    }""")


def _racines_visibles(page):
    """Dossiers racine de la sidebar, dans l'ordre (les enfants vivent dans .sb-kids)."""
    return page.evaluate("""() => [...document.querySelectorAll('nav#sidebar > .cat-item[data-proj-id]')]
      .map(e => e.querySelector('.cat-label').textContent.trim())""")


def _sb_item(page, nom):
    return page.locator("nav#sidebar .cat-item[data-proj-id]",
                        has=page.locator(".cat-label", has_text=nom)).first


# --------------------------------------------------------------------------- 1


def test_entete_dossiers_entre_inbox_et_les_dossiers(page, live_server, console_errors):
    _semer(live_server)
    _boot(page, live_server)
    ordre = _ordre_sidebar(page)
    assert ordre[0] == "Inbox", ordre
    assert ordre[1] == "#dossiers", "l'en-tête DOSSIERS doit suivre Inbox : %s" % ordre[:4]
    assert page.locator(HEAD + " .sb-section-label").inner_text().strip().lower().endswith("dossiers")
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 2


def test_replier_la_section(page, live_server, console_errors):
    _semer(live_server)
    _boot(page, live_server)
    attendu = _total_hors_invites(live_server)
    assert page.locator(HEAD + " .count").count() == 0, "déplié : pas de compteur"

    page.locator(HEAD).click()
    page.wait_for_timeout(250)
    assert page.locator("nav#sidebar .cat-item[data-proj-id]").count() == 0, \
        "replié : des dossiers restent affichés"
    expect(page.locator("nav#sidebar .cat-item", has=page.locator(".cat-label", has_text="Inbox")).first,
           "replié : Inbox doit rester visible").to_be_visible()
    assert page.locator(HEAD + " .count").inner_text().strip() == str(attendu), \
        "compteur = total des mémos de l'arbre HORS Invités"
    assert page.evaluate("() => localStorage.getItem('sbSection:dossiers')") == "0"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("nav#sidebar .cat-item", timeout=10_000)
    assert page.locator("nav#sidebar .cat-item[data-proj-id]").count() == 0, "repli non mémorisé"

    page.locator(HEAD).click()
    page.wait_for_timeout(250)
    expect(_sb_item(page, "SC Alpha")).to_be_visible()
    assert page.locator(HEAD + " .count").count() == 0, "re-déplié : le compteur doit disparaître"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 3


def test_tout_replier_tout_deplier(page, live_server, console_errors):
    ids = _semer(live_server)
    _boot(page, live_server)
    btn = page.locator(HEAD + " .sb-section-add")
    expect(_sb_item(page, "SC Alpha Un"), "précondition : Alpha déplié par défaut").to_be_visible()

    btn.click()
    page.wait_for_timeout(250)
    assert page.evaluate("(id) => localStorage.getItem('sbProjOpen:' + id)", ids["alpha"]) == "0"
    assert _sb_item(page, "SC Alpha Un").count() == 0, "tout replier : l'enfant reste affiché"
    assert page.evaluate("() => localStorage.getItem('sbSection:dossiers')") != "0", \
        "⇅ a aussi replié la section (stopPropagation manquant)"
    expect(_sb_item(page, "SC Alpha")).to_be_visible()

    btn.click()
    page.wait_for_timeout(250)
    assert page.evaluate("(id) => localStorage.getItem('sbProjOpen:' + id)", ids["alpha"]) == "1"
    expect(_sb_item(page, "SC Alpha Un"), "tout déplier : l'enfant n'est pas revenu").to_be_visible()
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 4


def test_invites_en_dernier(page, live_server, console_errors):
    _semer(live_server)
    _boot(page, live_server)
    racines = _racines_visibles(page)
    assert racines[-1] == INVITES, "Invités doit être la DERNIÈRE racine : %s" % racines
    inv = _sb_item(page, INVITES)
    # Filet = le séparateur EXISTANT `.sidebar-sep`, juste avant (un style inline sur l'item serait
    # effacé par le `clearProps: 'all'` de l'entrée GSAP de la sidebar).
    assert inv.evaluate("e => (e.previousElementSibling || {}).className") == "sidebar-sep", "filet absent"
    assert inv.get_attribute("draggable") != "true", "Invités ne doit pas être déplaçable"
    # Son chevron déplie / replie son enfant.
    expect(_sb_item(page, "SC Zoé")).to_be_visible()
    inv.locator(".sb-proj-chev").click()
    page.wait_for_timeout(250)
    assert _sb_item(page, "SC Zoé").count() == 0
    # Un nouveau dossier racine ne le fait pas remonter.
    _projet(live_server, "SC Zeta")
    page.evaluate("() => loadAll()")
    page.wait_for_timeout(600)
    assert _racines_visibles(page)[-1] == INVITES
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 5


def test_panneau_mobile_invites_en_dernier_et_cle_partagee(page, live_server, console_errors):
    ids = _semer(live_server)
    _boot(page, live_server)
    btn = page.locator(HEAD + " .sb-section-add")
    btn.click()                       # tout replier (Alpha était ouvert)
    page.wait_for_timeout(200)
    btn.click()                       # tout déplier → sbProjOpen:<id> = '1'
    page.wait_for_timeout(200)

    _boot(page, live_server, viewport=MOBILE)
    page.locator("#folders-btn").click()
    page.wait_for_selector("#folders-sheet[open]", timeout=5_000)
    page.wait_for_timeout(300)
    racines = page.evaluate("""() => [...document.querySelectorAll('#fs-tree .cat-item[data-proj-id]')]
      .filter(e => !e.style.marginLeft).map(e => e.querySelector('.cat-label').textContent.trim())""")
    assert racines[-1] == INVITES, "panneau : Invités doit être en dernier : %s" % racines
    assert page.evaluate("""() => { const i = [...document.querySelectorAll('#fs-tree .cat-item[data-proj-id]')]
      .find(e => e.querySelector('.cat-label').textContent.trim() === 'Invités');
      return (i.previousElementSibling || {}).className; }""") == "sidebar-sep", "panneau : filet absent"
    noms = page.evaluate("() => [...document.querySelectorAll('#fs-tree .cat-label')].map(e => e.textContent)")
    assert "SC Alpha Un" in noms, "⇅ desktop « tout déplier » non suivi par le panneau"

    page.locator("#fs-close").click()
    page.wait_for_timeout(200)
    _boot(page, live_server)
    page.locator(HEAD + " .sb-section-add").click()   # tout replier
    page.wait_for_timeout(200)
    assert page.evaluate("(id) => localStorage.getItem('sbProjOpen:' + id)", ids["alpha"]) == "0"
    _boot(page, live_server, viewport=MOBILE)
    page.locator("#folders-btn").click()
    page.wait_for_selector("#folders-sheet[open]", timeout=5_000)
    page.wait_for_timeout(300)
    noms = page.evaluate("() => [...document.querySelectorAll('#fs-tree .cat-label')].map(e => e.textContent)")
    assert "SC Alpha Un" not in noms, "⇅ desktop « tout replier » non suivi par le panneau"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 6


def test_tuile_en_cours_n_a_plus_l_icone_inbox(page, live_server, console_errors):
    _semer(live_server)
    _boot(page, live_server)
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    page.wait_for_selector(".mfilter.f-inbox", timeout=5_000)
    tuile = page.locator(".mfilter.f-inbox .mf-icon")
    assert "📥" not in tuile.inner_text(), "la tuile « En cours » copie l'icône de l'Inbox"
    assert tuile.locator("svg.ic").count() == 1, "icône trait attendue"
    inbox = page.locator("nav#sidebar .cat-item", has=page.locator(".cat-label", has_text="Inbox")).first
    assert "📥" in inbox.inner_text(), "l'Inbox garde 📥"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 7


def test_pastille_carte_titree(page, live_server, console_errors):
    ids = _semer(live_server)
    _memo(live_server, "SC géo", pid=ids["beta"],
          location={"lat": 35.0116, "lng": 135.7681, "label": "Kyoto"})
    _boot(page, live_server)
    page.evaluate("(id) => { state.view = 'memos'; state.memoProject = id; renderAll(); }", ids["beta"])
    carte = page.locator(".hdr-btn", has=page.locator(".hdr-lbl", has_text="Carte")).first
    carte.wait_for(timeout=5_000)
    pastille = carte.locator(".hdr-count")
    assert pastille.inner_text().strip() == "1"
    assert pastille.get_attribute("title") == "1 point géolocalisé", pastille.get_attribute("title")
    assert _erreurs_js(console_errors) == []
