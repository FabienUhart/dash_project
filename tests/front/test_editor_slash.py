"""[EDITOR-SLASH] + [EDITOR-AUTOLIST] : l'éditeur n'avale plus les « / », et « 1. » ne fait plus une liste.

Brief : `docs/briefs/EDITOR-SLASH.md` § 2 (scénarios 1 → 8). Deux bugs P1 constatés en saisissant le
mémo prod 409 **au clavier** sur V29.1.280 :

- le raccourci « / » (focus recherche, `index.html`) testait le `tagName` du focus mais pas
  `isContentEditable` : dans le `.ql-editor` de Quill chaque « / » était mangé par `preventDefault()`
  (« 18/10/2026 » → « 18102026 », `/api/v1/openapi.json` → `apiv1openapi.json`) ;
- le binding Quill 2 par défaut `list autofill` transforme « 1. » + espace en liste ordonnée : un
  mémo en sections numérotées devenait une seule `<ol>`.

Toute la saisie de ce fichier est **clavier RÉEL** (`page.keyboard.type`), jamais `setText` : le
contournement par `setText` depuis la console marchait déjà — c'est la frappe qu'on protège.

Ce que ces parcours PROTÈGENT :

1. owner : les 6 « / » tapés dans le contenu restent dans `quill.getText()` ET dans le mémo sauvegardé,
   la recherche reste vide et sans focus ; le prédicat `inTextEntry()` couvre aussi un `contenteditable`
   nu hors pop-in (la branche `isContentEditable`, pour les éditions inline à venir) ;
2. owner, éditeur fermé : « / » donne toujours le focus à la recherche (non-régression) ;
3. owner, éditeur ouvert, focus sur un BOUTON de la pop-in : « / » ne touche pas la recherche, et
   `inTextEntry()` dit vrai (contrat des futurs raccourcis à une touche [KEYS-1-9] / [SHORTCUT-HELP],
   qui eux ne seraient pas neutralisés par l'inertie du `showModal`) ;
4. share (invité éditeur) et hub : même frappe, 6 « / » conservés — il n'y a pas de raccourci sur ces
   pages, le test fige qu'il n'en apparaîtra pas sans garde ;
5. « 1. Titre » ⏎ « texte » ⏎ « 2. Suite » → trois `<p>`, aucune liste ; idem « 1) » — sur les 3 pages
   (le binding est posé par `applyTableBetter`, partagé) ;
6. « - un » ⏎ « deux » → liste à puces de 2 items ; « [ ] tâche » → case à cocher (les puces restent) ;
7. le bouton « liste ordonnée » de la barre fonctionne toujours ;
8. zéro erreur console, assertion de CHAQUE test, sur les 3 pages.

⚠ Quill 2 rend TOUTE liste en `<ol><li data-list="bullet|ordered|checked|unchecked">` (plus de `<ul>`) :
« aucune liste » s'écrit donc « aucun `<ol>` », et une puce se reconnaît à `data-list="bullet"`.

La base du `live_server` est partagée par toute la session : le décor est supprimé en sortie.
"""
import os
import sqlite3
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}
FRAPPE = "a/b 18/10/2026 http://x.y/z"     # 6 « / » (le brief en comptait 4 : 1 + 2 + 3)
N_SLASH = FRAPPE.count("/")
_BRUIT_404 = "the server responded with a status of 404"
_n = [0]
_CREES = []   # urls de suppression, dossiers en DERNIER

# Où vit l'éditeur sur chaque page : dialog, racine Quill, bouton Sauver.
PAGES = {
    "owner": {"dlg": "#memo-edit-dialog", "save": "#memo-edit-save"},
    "share": {"dlg": "#edit-dialog", "save": "#edit-save"},
    "hub":   {"dlg": "#ed", "save": "#ed-save"},
}


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _db():
    return sqlite3.connect(os.path.join(os.environ["E2E_DATA_DIR"], "dashboard.db"))


def _contenu_en_base(mid):
    con = _db()
    try:
        row = con.execute("SELECT content FROM memos WHERE id = ?", (mid,)).fetchone()
    finally:
        con.close()
    return (row or [""])[0] or ""


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return False


# ------------------------------------------------------------------ décor


def _semer(page, live_server):
    """Dossier « ES racine k » + mémo « ES saisie k » au contenu VIDE (on tape tout au clavier)."""
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)
    p = page.request.post(live_server + "/api/projects", data={"name": "ES racine %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])
    r = page.request.post(live_server + "/api/memos", data={
        "title": "ES saisie %s" % k, "project_id": p["id"], "content": "",
    })
    assert r.ok, r.text()
    m = r.json()
    _CREES.append("/api/memos/%d" % m["id"])
    return {"k": k, "projet": p, "memo": m}


def _owner(page, live_server, vp=BUREAU):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof openMemoEditor === 'function' && state.memos && state.memos.length")
    page.evaluate("() => { state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    page.wait_for_timeout(300)


def _invite(page, live_server, d, ou, role="editor", vp=BUREAU):
    """Ouvre le décor côté invité APPROUVÉ : `ou` = 'share' ou 'hub' (montage de
    test_memo_urls / test_guest_search_grammar)."""
    _n[0] += 1
    email = "es%d@ex.com" % _n[0]
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["projet"]["id"], "role": role}).json()
    if sh.get("share_id"):
        _CREES.insert(0, "/api/shares/%d" % sh["share_id"])
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
        ok = page.request.post(live_server + "/share/hub/%s/approve" % hub_token, data={"pin": pin})
        assert ok.ok, ok.text()
        page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.memos && DATA.memos.length")
    page.wait_for_timeout(300)
    return sh["token"]


def _ouvrir(page, live_server, ou, vp=BUREAU):
    """Sème, charge la page `ou`, ouvre l'éditeur du mémo semé. Rend (id mémo, sélecteur racine Quill)."""
    d = _semer(page, live_server)
    mid = d["memo"]["id"]
    if ou == "owner":
        _owner(page, live_server, vp)
        page.evaluate("id => openMemoEditor(state.memos.find(x => x.id === id))", mid)
    else:
        _invite(page, live_server, d, ou, vp=vp)
        if ou == "share":
            page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id), el('span', ''), el('span', ''))", mid)
        else:
            page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id))", mid)
    dlg = PAGES[ou]["dlg"]
    page.wait_for_selector(dlg + "[open] .ql-editor", timeout=5_000)
    page.wait_for_timeout(200)
    return mid, dlg + " .ql-editor"


def _quill(page, racine):
    """Expression JS qui rend l'instance Quill de la racine donnée."""
    return "Quill.find(document.querySelector(%r).parentElement)" % racine


def _texte(page, racine):
    return page.evaluate("() => %s.getText()" % _quill(page, racine))


def _listes(page, racine):
    """Valeurs `list` des blocs du delta courant (bullet / ordered / checked / unchecked)."""
    return page.evaluate(
        "() => %s.getContents().ops.filter(o => o.attributes && o.attributes.list).map(o => o.attributes.list)"
        % _quill(page, racine))


def _taper(page, racine, texte):
    page.click(racine)
    page.keyboard.type(texte, delay=10)


def _sauver_et_lire(page, ou, mid, attendu):
    page.click(PAGES[ou]["save"])
    assert _attendre(page, lambda: attendu in _contenu_en_base(mid)), \
        "contenu sauvegardé : %r" % _contenu_en_base(mid)
    return _contenu_en_base(mid)


# ----------------------------------------------------------------------- 1 / 4


@pytest.mark.parametrize("ou", ["owner", "share", "hub"])
def test_les_slashs_tapes_restent_dans_le_contenu(page, live_server, console_errors, ou):
    mid, racine = _ouvrir(page, live_server, ou)
    _taper(page, racine, FRAPPE)
    txt = _texte(page, racine)
    assert txt.count("/") == N_SLASH, "des « / » ont été avalés à la frappe : %r" % txt
    assert "18/10/2026" in txt and "http://x.y/z" in txt
    if ou == "owner":
        assert page.evaluate("() => document.getElementById('search').value") == "", "la recherche a reçu la frappe"
        assert page.evaluate("() => document.activeElement && document.activeElement.id") != "search", \
            "le focus a sauté dans la recherche"
    contenu = _sauver_et_lire(page, ou, mid, "18/10/2026")
    assert "x.y/z" in contenu
    assert _erreurs_js(console_errors) == []


def test_owner_un_contenteditable_nu_garde_ses_slashs(page, live_server, console_errors):
    """La branche `isContentEditable` du prédicat, hors de toute pop-in : un `div contenteditable`
    posé dans la page (éditions inline à venir) ne doit pas non plus perdre ses « / »."""
    _semer(page, live_server)
    _owner(page, live_server)
    page.evaluate("""() => {
      const d = document.createElement('div'); d.id = 'es-ce'; d.contentEditable = 'true';
      d.style.cssText = 'position:fixed;top:4px;left:4px;width:300px;min-height:24px;z-index:9999;background:#fff;color:#000';
      document.body.appendChild(d); d.focus();
    }""")
    assert page.evaluate("() => typeof inTextEntry === 'function' && inTextEntry()") is True, \
        "inTextEntry() doit dire vrai sur un contenteditable nu"
    page.keyboard.type("a/b/c", delay=10)
    assert page.evaluate("() => document.getElementById('es-ce').textContent") == "a/b/c"
    assert page.evaluate("() => document.getElementById('search').value") == ""
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "es-ce"
    page.evaluate("() => document.getElementById('es-ce').remove()")
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 2


def test_owner_slash_hors_saisie_ouvre_la_recherche(page, live_server, console_errors):
    _semer(page, live_server)
    _owner(page, live_server)
    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    assert page.evaluate("() => document.activeElement === document.body")
    page.keyboard.press("/")
    page.wait_for_timeout(150)
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "search", \
        "« / » hors zone de saisie doit toujours donner le focus à la recherche"
    assert page.evaluate("() => document.getElementById('search').value") == "", "le « / » lui-même ne doit pas être tapé"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 3


def test_owner_focus_sur_un_bouton_de_la_popin(page, live_server, console_errors):
    mid, racine = _ouvrir(page, live_server, "owner")
    page.click(racine)
    page.keyboard.press("Tab")        # on quitte l'éditeur vers le chrome de la pop-in
    page.wait_for_timeout(100)
    tag = page.evaluate("() => document.activeElement && document.activeElement.tagName")
    if tag not in ("BUTTON", "A"):   # selon la barre d'outils, Tab peut tomber ailleurs : on vise un bouton
        page.focus("#memo-edit-cancel")
    assert page.evaluate("() => document.activeElement.closest('#memo-edit-dialog') !== null")
    assert page.evaluate("() => !document.activeElement.isContentEditable && document.activeElement.tagName !== 'INPUT'")
    assert page.evaluate("() => inTextEntry()") is True, \
        "pop-in ouverte + focus sur un bouton : un raccourci à une touche ne doit pas tirer"
    avant = page.evaluate("() => document.activeElement.id || document.activeElement.className")
    page.keyboard.press("/")
    page.wait_for_timeout(150)
    assert page.evaluate("() => document.getElementById('search').value") == ""
    assert page.evaluate("() => document.activeElement.id || document.activeElement.className") == avant
    assert page.locator("#memo-edit-dialog[open]").count() == 1
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 5


@pytest.mark.parametrize("ou", ["owner", "share", "hub"])
@pytest.mark.parametrize("num", ["1.", "1)"], ids=["point", "parenthese"])
def test_les_sections_numerotees_restent_des_paragraphes(page, live_server, console_errors, ou, num):
    mid, racine = _ouvrir(page, live_server, ou)
    _taper(page, racine, num + " Titre")
    page.keyboard.press("Enter")
    page.keyboard.type("texte", delay=10)
    page.keyboard.press("Enter")
    page.keyboard.type("2" + num[1] + " Suite", delay=10)
    assert _listes(page, racine) == [], "« %s » + espace a déclenché une liste" % num
    assert page.evaluate("() => document.querySelectorAll(%r + ' ol, ' + %r + ' ul').length" % (racine, racine)) == 0
    paras = page.evaluate("() => [...document.querySelectorAll(%r + ' > p')].map(p => p.textContent)" % racine)
    assert paras == [num + " Titre", "texte", "2" + num[1] + " Suite"], paras
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 6


def test_owner_les_puces_et_les_cases_restent_automatiques(page, live_server, console_errors):
    mid, racine = _ouvrir(page, live_server, "owner")
    _taper(page, racine, "- un")
    page.keyboard.press("Enter")
    page.keyboard.type("deux", delay=10)
    assert _listes(page, racine) == ["bullet", "bullet"], _listes(page, racine)
    assert page.evaluate("() => document.querySelectorAll(%r + ' li[data-list=\"bullet\"]').length" % racine) == 2
    assert "- " not in _texte(page, racine), "le tiret doit avoir été consommé par l'autofill"

    page.keyboard.press("Enter")
    page.keyboard.press("Enter")        # Entrée sur un item vide : on sort de la liste (Quill inchangé)
    page.keyboard.type("[ ] tâche", delay=10)
    assert _listes(page, racine) == ["bullet", "bullet", "unchecked"], _listes(page, racine)
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 7


def test_owner_le_bouton_liste_ordonnee_marche_toujours(page, live_server, console_errors):
    mid, racine = _ouvrir(page, live_server, "owner")
    _taper(page, racine, "Premier")
    page.click('#memo-edit-dialog .ql-toolbar .ql-list[value="ordered"]')
    page.keyboard.press("Enter")
    page.keyboard.type("Second", delay=10)
    assert _listes(page, racine) == ["ordered", "ordered"], _listes(page, racine)
    assert page.evaluate("() => document.querySelectorAll(%r + ' li[data-list=\"ordered\"]').length" % racine) == 2
    contenu = _sauver_et_lire(page, "owner", mid, "Second")
    assert "<ol>" in contenu or 'data-list="ordered"' in contenu, contenu
    assert _erreurs_js(console_errors) == []
