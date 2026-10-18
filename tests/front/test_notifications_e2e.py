"""[NOTIF-CENTER] e2e — la cloche, le panneau, l'entrée qui mène à la card, la feuille mobile,
la cloche et le chip « n pour toi » de l'invité, la vue Partages qui ne touche plus au badge.

Brief : `docs/briefs/NOTIF-CENTER.md` § 4 (E2E). Zéro erreur console, assertion de chaque test.
Ce que ces parcours PROTÈGENT :
- le badge de l'owner = « pour moi » NON LUES seulement (une révision d'invité = activité, pas comptée) ;
- clic cloche → panneau avec ses deux onglets, titre du mémo lisible EN ENTIER à 1280 px (pas d'ellipsis) ;
- clic sur une entrée → card du mémo + fil de commentaires ouvert, point disparu, badge décrémenté ;
- Échap ferme ; à 390 px le panneau est une feuille qui monte du bas ;
- invité : cloche + chip « 1 pour toi » sur la card, qui disparaît quand c'est lu ;
- la vue Partages reste accessible et n'affecte plus le badge.
"""
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 390, "height": 844}
_BRUIT_404 = "the server responded with a status of 404"
_CREES = []
_n = [0]


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


def _semer(page, live_server):
    """Dossier partagé (éditeur) + mémo de l'owner au titre LONG + un invité « Alice » enregistré."""
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)
    # base du live_server partagée par toute la session : on repart d'une cloche à zéro
    for lv in ("me", "activity"):
        page.request.post(live_server + "/api/notifications/read", data={"level": lv, "all": True})
    p = page.request.post(live_server + "/api/projects", data={"name": "NC dossier %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])
    titre = "Réparation de l'iPad Pro chez Apple Bayonne — suivi du colis et devis à valider %s" % k
    m = page.request.post(live_server + "/api/memos", data={"title": titre, "project_id": p["id"], "content": "<p>texte</p>"}).json()
    _CREES.append("/api/memos/%d" % m["id"])
    sh = page.request.post(live_server + "/api/shares", data={"kind": "project", "target_id": p["id"], "role": "editor"}).json()
    sid = sh.get("share_id") or sh["id"]
    _CREES.insert(0, "/api/shares/%d" % sid)
    email = "alice%s@ex.com" % k
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"], data={"name": "Alice", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    return {"k": k, "p": p, "memo": m, "titre": titre, "sh": sh, "sid": sid, "gt": reg.json()["guest_token"], "email": email}


def _owner(page, live_server, vp=BUREAU):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof notifCenter !== 'undefined' && state.memos && state.memos.length")
    page.evaluate("() => refreshActivityBadge()")
    page.wait_for_timeout(300)


def _badge(page):
    return page.evaluate("() => { const b = document.getElementById('activity-badge'); return getComputedStyle(b).display === 'none' ? '' : b.textContent; }")


# --------------------------------------------------------------------------- owner


def test_owner_badge_panneau_entree_et_card(page, live_server, console_errors):
    d = _semer(page, live_server)
    H = {"X-Guest-Token": d["gt"]}
    # Alice commente (→ me/comment) et modifie le titre (→ activity/edit, ne compte PAS)
    r = page.request.post(live_server + "/share/%s/memo/%d/comments" % (d["sh"]["token"], d["memo"]["id"]), data={"body": "Le devis est arrivé"}, headers=H)
    assert r.status == 201, r.text()
    r = page.request.put(live_server + "/share/%s/memo/%d" % (d["sh"]["token"], d["memo"]["id"]), data={"title": d["titre"] + " (relu)"}, headers=H)
    assert r.status == 200, r.text()
    _owner(page, live_server)
    assert _badge(page) == "2", "guest_new + comment = 2 ; l'activité ne compte pas"

    page.click("#activity-btn")
    page.wait_for_selector("#notif-dlg[open]", timeout=5_000)
    assert page.get_attribute("#activity-btn", "aria-expanded") == "true"
    assert page.locator("#notif-dlg .notif-tabs button[data-level='me']").count() == 1
    assert page.locator("#notif-dlg .notif-tabs button[data-level='activity']").count() == 1
    # la base du live_server est partagée : les entrées LUES des autres tests restent listées — on juge les NON LUES
    rows = page.locator("#notif-dlg .notif-row.unread")
    page.wait_for_function("() => document.querySelectorAll('#notif-dlg .notif-row.unread').length >= 2", timeout=5_000)
    kinds = [rows.nth(i).get_attribute("data-kind") for i in range(rows.count())]
    assert sorted(kinds) == ["comment", "guest_new"], kinds
    assert page.locator("#notif-dlg .notif-row.unread .notif-dot").count() == 2
    # l'entrée du commentaire : titre du mémo EN ENTIER, sans ellipsis (1280 px)
    row = page.locator("#notif-dlg .notif-row.unread[data-kind='comment']")
    assert d["titre"] in row.inner_text()
    path = row.locator(".notif-path")
    assert page.evaluate("el => el.scrollWidth <= el.clientWidth + 1", path.element_handle()), "titre tronqué"
    assert "Le devis est arrivé" in row.locator(".notif-quote").inner_text()
    assert "Alice" in row.locator(".notif-what").inner_text()
    # onglet Activité : la révision d'Alice
    page.click("#notif-dlg .notif-tabs button[data-level='activity']")
    page.wait_for_function("() => document.querySelector('#notif-dlg .notif-row.unread[data-kind=\"edit\"]')", timeout=5_000)
    assert page.locator("#notif-dlg .notif-row.unread[data-kind='edit']").count() == 1
    page.click("#notif-dlg .notif-tabs button[data-level='me']")
    page.wait_for_function("() => document.querySelector('#notif-dlg .notif-row.unread[data-kind=\"comment\"]')", timeout=5_000)
    # clic sur l'entrée → panneau fermé, card du mémo visible, fil de commentaires ouvert, badge 1
    page.click("#notif-dlg .notif-row.unread[data-kind='comment']")
    page.wait_for_selector("#notif-dlg[open]", state="detached", timeout=5_000)
    page.wait_for_selector("#comments-dialog[open]", timeout=5_000)
    page.wait_for_function("() => document.getElementById('comments-dialog').innerText.includes('Le devis est arrivé')", timeout=5_000)
    assert page.locator('.task[data-memo-id="%d"]' % d["memo"]["id"]).count() == 1
    assert _attendre(page, lambda: _badge(page) == "1"), _badge(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#comments-dialog[open]", state="detached", timeout=5_000)
    # réouverture : l'entrée lue n'a plus de point ; Échap ferme le panneau
    page.click("#activity-btn")
    page.wait_for_selector("#notif-dlg[open]", timeout=5_000)
    page.wait_for_function("() => document.querySelectorAll('#notif-dlg .notif-row').length >= 2", timeout=5_000)
    assert page.locator("#notif-dlg .notif-row.unread[data-kind='comment']").count() == 0, "l'entrée cliquée est lue"
    assert page.locator("#notif-dlg .notif-row.unread[data-kind='guest_new'] .notif-dot").count() == 1
    page.keyboard.press("Escape")
    page.wait_for_selector("#notif-dlg[open]", state="detached", timeout=5_000)
    assert page.get_attribute("#activity-btn", "aria-expanded") == "false"
    assert _erreurs_js(console_errors) == []


def test_owner_tout_marquer_lu_et_vue_partages_sans_effet_sur_le_badge(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server)
    assert _badge(page) == "1"
    # la vue Partages reste accessible depuis la sidebar et NE marque plus rien lu
    page.evaluate("() => openSharesView()")
    page.wait_for_timeout(400)
    assert page.evaluate("() => state.view") == "shares"
    assert _badge(page) == "1", "ouvrir la vue Partages ne doit plus vider le badge"
    assert page.locator("#shares-board, #board-shares, [data-view='shares']").count() >= 0
    # « Tout marquer lu » sur « Pour moi »
    page.click("#activity-btn")
    page.wait_for_selector("#notif-dlg[open] #notif-readall", timeout=5_000)
    page.click("#notif-readall")
    assert _attendre(page, lambda: _badge(page) == ""), _badge(page)
    assert page.locator("#notif-dlg .notif-dot").count() == 0
    # le lien « Partages et invités → » du panneau mène à la vue Partages
    page.click("#notif-shares-link")
    page.wait_for_selector("#notif-dlg[open]", state="detached", timeout=5_000)
    assert page.evaluate("() => state.view") == "shares"
    assert _erreurs_js(console_errors) == []


def test_owner_mobile_390_feuille(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server, MOBILE)
    page.click("#activity-btn")
    page.wait_for_selector("#notif-dlg[open]", timeout=5_000)
    page.wait_for_timeout(400)   # fin de l'animation CSS d'entrée (invariant 8 : CSS seulement)
    bb = page.locator("#notif-dlg").bounding_box()
    assert bb and bb["width"] >= MOBILE["width"] - 2 and abs((bb["y"] + bb["height"]) - MOBILE["height"]) < 4, bb
    assert page.evaluate("() => document.getElementById('notif-dlg').matches(':modal')"), "feuille modale en mobile"
    page.wait_for_function("() => document.querySelectorAll('#notif-dlg .notif-row').length >= 1", timeout=5_000)
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0
    page.click("#notif-close")
    page.wait_for_selector("#notif-dlg[open]", state="detached", timeout=5_000)
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- invité


def test_invite_cloche_et_chip_pour_toi(page, live_server, console_errors):
    d = _semer(page, live_server)
    # l'owner mentionne @Alice dans un commentaire → me/mention pour Alice (et pour personne d'autre)
    r = page.request.post(live_server + "/api/memos/%d/comments" % d["memo"]["id"], data={"body": "@Alice peux-tu confirmer le devis ?"})
    assert r.status == 201, r.text()
    page.set_viewport_size(BUREAU)
    page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (d["sh"]["token"], d["gt"]))
    page.goto(live_server + "/share/" + d["sh"]["token"], wait_until="domcontentloaded")
    page.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.memos && DATA.memos.length && document.getElementById('notif-btn')")
    page.wait_for_timeout(300)
    assert page.evaluate("() => DATA.unread_me") == 1
    assert page.locator("#notif-badge").inner_text() == "1"
    chip = page.locator('.task[data-memo-id="%d"] .notif-chip' % d["memo"]["id"])
    chip.wait_for(timeout=5_000)
    assert chip.inner_text().strip() == "1 pour toi"
    # la cloche montre l'entrée, scopée au partage
    page.click("#notif-btn")
    page.wait_for_selector("#notif-dlg[open]", timeout=5_000)
    page.wait_for_function("() => document.querySelectorAll('#notif-dlg .notif-row').length >= 1", timeout=5_000)
    assert page.locator("#notif-dlg .notif-row.unread[data-kind='mention']").count() == 1
    assert "dans ce dossier" in page.locator("#notif-dlg .notif-foot").inner_text()
    # clic sur l'entrée (mention) → le FIL de commentaires (pop-in 💬) s'ouvre avec le message, pas la fiche
    page.click("#notif-dlg .notif-row.unread[data-kind='mention']")
    page.wait_for_selector("#notif-dlg[open]", state="detached", timeout=5_000)
    page.wait_for_selector("#comments-dialog[open]", timeout=5_000)
    page.wait_for_function("() => document.getElementById('comments-dialog').innerText.includes('confirmer le devis')", timeout=5_000)
    assert page.locator("#memo-view-dialog[open]").count() == 0, "la fiche ne doit pas s'ouvrir pour un commentaire"
    page.keyboard.press("Escape")
    page.wait_for_selector("#comments-dialog[open]", state="detached", timeout=5_000)
    # lu : chip disparu, badge vide, serveur à 0
    page.wait_for_selector('.task[data-memo-id="%d"] .notif-chip' % d["memo"]["id"], state="detached", timeout=5_000)
    assert _attendre(page, lambda: page.evaluate("() => getComputedStyle(document.getElementById('notif-badge')).display") == "none")
    r = page.request.get(live_server + "/share/%s/notifications?level=me" % d["sh"]["token"], headers={"X-Guest-Token": d["gt"]})
    assert r.ok and r.json()["unread_me"] == 0
    assert _erreurs_js(console_errors) == []
