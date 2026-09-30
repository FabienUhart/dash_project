"""[QUICK-NOTE-SEND] La note rapide de la colonne MÉMOS dit qu'elle est partie.

Brief : `docs/briefs/QUICK-NOTE-SEND.md` (Fabien, 30 sept. 2026 : « sur mobile la note rapide n'a
pas de bouton pour sauvegarder, on se demande si la sauvegarde a bien été envoyée »).

- bouton « Ajouter » (#memo-quick-send) masqué tant que le champ est vide, même fonction que Entrée ;
- retour visuel : toast non bloquant « Note ajoutée dans Inbox » + card `.memo-note.is-new` ;
- mobile : `enterkeyhint="send"`, card neuve ramenée dans le viewport, champ dégagé des lanceurs ;
- hors ligne : toast « en attente », note dans la file locale, rejouée au retour du réseau.
"""
import re
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}

_BRUIT_404 = "the server responded with a status of 404"
_LANCEURS = ["#qm-reshow", "#fx-reshow", "#pomo-reshow", "#qm-launch", "#fx-launch", "#pomo-launch"]
_n = [0]


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)   # jamais time.sleep : bloquerait les handlers Playwright
    return False


def _posts(page):
    vus = []
    page.on("request", lambda r: vus.append(r)
            if r.method == "POST" and re.search(r"/api/memos$", r.url) else None)
    return vus


def _ouvrir(page, live_server, vp=BUREAU, graines=0, init=None):
    for _ in range(graines):
        _n[0] += 1
        r = page.request.post(live_server + "/api/memos", data={"content": "graine QNS %d" % _n[0]})
        assert r.ok, r.text()
    if init:
        page.add_init_script(init)
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof loadAll === 'function' && Array.isArray(state.memos)")
    page.evaluate("() => { const d = document.getElementById('memo-details'); if (d) d.open = true; }")


def _texte_unique(prefixe):
    _n[0] += 1
    return "%s %d %d" % (prefixe, _n[0], int(time.time() * 1000) % 100000)


def _toast(page):
    """Texte du toast de statut non bloquant (ni pop-in modale, ni `notify`)."""
    return page.evaluate("""() => {
      const t = document.getElementById('undo-toast');
      return t ? t.textContent : '';
    }""")


def _id_cree(page, texte):
    return page.evaluate("t => { const m = state.memos.find(x => (x.content || '').includes(t)); return m ? m.id : null; }", texte)


def _verifier_envoi(page, posts, texte):
    assert _attendre(page, lambda: len(posts) == 1), "aucun POST /api/memos"
    assert page.locator("#memo-quick").input_value() == "", "le champ n'a pas été vidé"
    assert _attendre(page, lambda: "Note ajoutée dans Inbox" in _toast(page)), \
        "pas de toast « Note ajoutée dans Inbox » (%r)" % _toast(page)
    assert page.locator("#notify-dialog[open]").count() == 0, "retour par pop-in modale : bloque la saisie"
    assert _attendre(page, lambda: _id_cree(page, texte) is not None), "mémo absent de state.memos"
    mid = _id_cree(page, texte)
    assert _attendre(page, lambda: page.locator(
        '#memos .memo-note.is-new[data-memo-id="%d"]' % mid).count() == 1), "card du mémo créé non surlignée (.is-new)"
    page.wait_for_timeout(300)
    assert len(posts) == 1, "double envoi (%d POST)" % len(posts)
    return mid


# ------------------------------------------------------------------ desktop


def test_bouton_ajouter_desktop(page, live_server, console_errors):
    _ouvrir(page, live_server)
    btn = page.locator("#memo-quick-wrap #memo-quick-send")
    assert btn.count() == 1, "pas de bouton Ajouter dans #memo-quick-wrap"
    assert not btn.is_visible(), "bouton visible alors que le champ est vide"
    assert btn.get_attribute("type") == "button"
    assert "Entrée pour ajouter" not in (page.locator("#memo-quick").get_attribute("placeholder") or "")
    posts = _posts(page)
    texte = _texte_unique("QNS bouton")
    page.locator("#memo-quick").fill(texte)
    assert btn.is_visible(), "bouton toujours masqué après saisie"
    btn.click()
    _verifier_envoi(page, posts, texte)
    assert not btn.is_visible(), "bouton resté visible après envoi (champ vide)"
    assert _erreurs_js(console_errors) == []


def test_entree_envoie_une_seule_fois(page, live_server, console_errors):
    _ouvrir(page, live_server)
    posts = _posts(page)
    texte = _texte_unique("QNS entree")
    page.locator("#memo-quick").fill(texte)
    page.locator("#memo-quick").press("Enter")
    _verifier_envoi(page, posts, texte)
    assert _erreurs_js(console_errors) == []


def test_maj_entree_retour_ligne_sans_envoi(page, live_server, console_errors):
    _ouvrir(page, live_server)
    posts = _posts(page)
    champ = page.locator("#memo-quick")
    champ.click()
    champ.type("ligne 1")
    champ.press("Shift+Enter")
    champ.type("ligne 2")
    page.wait_for_timeout(400)
    assert len(posts) == 0, "Maj+Entrée a envoyé la note"
    assert champ.input_value() == "ligne 1\nligne 2"
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ mobile


def _rect(page, sel):
    return page.evaluate("""s => { const e = document.querySelector(s);
      if (!e || !e.getClientRects().length) return null;
      const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }""", sel)


def _chevauche(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("languettes", [True, False], ids=["languettes", "lanceurs-ronds"])
def test_mobile_envoyer_defile_et_degage_les_lanceurs(page, live_server, console_errors, languettes):
    init = None
    if languettes:   # le cas de la capture de Fabien : widgets masqués → languettes ✏️ ¥€ ⏱ au bord gauche
        init = "try { ['qmHidden','fxHidden','pomoHidden'].forEach(k => localStorage.setItem(k, '1')); } catch (e) {}"
    _ouvrir(page, live_server, vp=MOBILE, graines=25, init=init)
    champ = page.locator("#memo-quick")
    assert champ.get_attribute("enterkeyhint") == "send"
    champ.scroll_into_view_if_needed()
    page.evaluate("() => document.getElementById('memo-quick-wrap').scrollIntoView({block: 'end'})")
    page.wait_for_timeout(200)

    texte = _texte_unique("QNS mobile")
    champ.fill(texte)
    # Le champ ET le bouton ne chevauchent aucun lanceur visible (au moins un doit l'être).
    visibles = [(s, _rect(page, s)) for s in _LANCEURS]
    visibles = [(s, r) for s, r in visibles if r]
    assert visibles, "aucun lanceur visible : le test tournerait à vide"
    for cible in ("#memo-quick", "#memo-quick-send"):
        rc = _rect(page, cible)
        assert rc, "%s invisible en mobile" % cible
        for s, r in visibles:
            assert not _chevauche(rc, r), "%s chevauche %s (%r / %r)" % (cible, s, rc, r)

    posts = _posts(page)
    page.locator("#memo-quick-send").click()
    mid = _verifier_envoi(page, posts, texte)
    card = '#memos .memo-note[data-memo-id="%d"]' % mid
    # Dans le viewport ET au-dessus du champ collé en bas (sinon elle est « visible » mais cachée dessous).
    _vue = """s => { const e = document.querySelector(s); if (!e) return null;
      const r = e.getBoundingClientRect(), w = document.getElementById('memo-quick-wrap').getBoundingClientRect();
      return [r.top, r.bottom, Math.min(innerHeight, w.top)]; }"""
    assert _attendre(page, lambda: (lambda v: bool(v) and v[0] >= 0 and v[1] <= v[2] + 0.5)(page.evaluate(_vue, card))), \
        "card neuve hors du viewport ou sous le champ après envoi %r" % page.evaluate(_vue, card)
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ hors ligne


def test_hors_ligne_toast_attente_puis_rejeu(page, live_server, console_errors):
    _ouvrir(page, live_server)
    page.evaluate("() => { try { localStorage.removeItem('offlineQueue'); } catch (e) {} }")
    posts = _posts(page)
    page.context.set_offline(True)
    assert _attendre(page, lambda: page.evaluate("() => isOffline === true")), "setOffline non déclenché"
    texte = _texte_unique("QNS horsligne")
    page.locator("#memo-quick").fill(texte)
    page.locator("#memo-quick-send").click()
    assert _attendre(page, lambda: "en attente" in _toast(page)), "pas de toast « en attente » (%r)" % _toast(page)
    assert "Note ajoutée" not in _toast(page), "toast de succès alors que la note n'est pas partie"
    assert page.locator("#memo-quick").input_value() == ""
    file = page.evaluate("() => JSON.parse(localStorage.getItem('offlineQueue') || '[]').map(n => n.content)")
    assert texte in file, "note absente de la file locale"
    assert len(posts) == 0, "POST parti hors ligne"
    page.context.set_offline(False)
    assert _attendre(page, lambda: len(posts) == 1), "note non rejouée au retour du réseau"
    assert _attendre(page, lambda: _id_cree(page, texte) is not None), "note rejouée absente"
    erreurs = [e for e in _erreurs_js(console_errors) if "ERR_INTERNET_DISCONNECTED" not in e]
    assert erreurs == []
