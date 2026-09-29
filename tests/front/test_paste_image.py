"""[PASTE-IMAGE] Coller une image du presse-papiers dans « 📷 Photos » du mémo.

Brief : `docs/briefs/PASTE-IMAGE.md` (demande Fabien du 29 sept. 2026 : « je peux copier l'image
dans le navigateur et je voudrais la coller dans les mémos, pas devoir l'enregistrer et
l'importer »). Tout vit dans `renderMemoPhotos` (partial partagé) : owner, invité et hub.

Un collage se simule par un `ClipboardEvent('paste')` porteur d'un `DataTransfer` (PNG 1×1 aux
octets réels : le serveur vérifie la signature). ⚠ Un événement synthétique n'a pas d'action par
défaut du navigateur : un collage de TEXTE dans un `<input>` n'y écrit rien. Pour le texte on
vérifie donc que l'app ne l'a PAS confisqué (`defaultPrevented` faux) et n'a rien envoyé ;
Quill, lui, traite le collage en JS et reçoit bien le texte.
"""
import os
import re
import sqlite3
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOBILE = {"width": 412, "height": 915}

PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5E"
           "rkJggg==")

_n = [0]
_BRUIT_404 = "the server responded with a status of 404"


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _attendre(cond, timeout_ms=10_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.1)
    return False


_COLLER = """({ sel, n, text, html, pdf }) => {
  const bin = atob('%s'), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const dt = new DataTransfer();
  for (let i = 0; i < n; i++) dt.items.add(new File([u], 'image.png', { type: 'image/png' }));
  if (pdf) dt.items.add(new File(['%PDF-1.4 PI'], 'doc.pdf', { type: 'application/pdf' }));
  if (text) dt.setData('text/plain', text);
  if (html) dt.setData('text/html', html);
  const t = sel ? document.querySelector(sel) : (document.activeElement || document.body);
  const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
  t.dispatchEvent(ev);
  return ev.defaultPrevented;
}""".replace('%PDF', '%%PDF') % PNG_B64


def _coller(page, sel=None, n=1, text=None, html=None, pdf=False):
    return page.evaluate(_COLLER, {"sel": sel, "n": n, "text": text, "html": html, "pdf": pdf})


def _posts(page, motif):
    """Compte les POST d'upload d'image (motif = regex d'URL), et garde les requêtes."""
    vus = []
    page.on("request", lambda r: vus.append(r) if r.method == "POST" and re.search(motif, r.url) else None)
    return vus


def _memo(page, live_server, **extra):
    _n[0] += 1
    r = page.request.post(live_server + "/api/memos",
                          data={"title": "PI mémo %d" % _n[0], "content": "corps PI %d" % _n[0], **extra})
    assert r.ok, r.text()
    return r.json()


def _image_owner(page, live_server, mid):
    """Pose une vraie image sur le mémo par la route owner (multipart)."""
    import base64
    r = page.request.post(live_server + "/api/memos/%d/images" % mid, multipart={
        "image": {"name": "seed.png", "mimeType": "image/png", "buffer": base64.b64decode(PNG_B64)}})
    assert r.ok, r.text()


# ------------------------------------------------------------------ owner


def _owner(page, live_server, vp=BUREAU):
    m = _memo(page, live_server)
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof openMemoEditor === 'function' && state.memos && state.memos.length")
    return m


def _ouvrir_owner(page, mid):
    page.evaluate("id => openMemoEditor(state.memos.find(x => x.id === id))", mid)
    page.wait_for_selector("#memo-edit-dialog[open] #me-photos .attach-sec", timeout=5_000)


def _fermer_owner(page):
    page.evaluate("() => document.getElementById('memo-edit-dialog').close()")
    page.wait_for_selector("#memo-edit-dialog[open]", state="detached", timeout=5_000)


def _vignettes(page, box="#me-photos"):
    return page.locator(box + " .mp-thumb:not(.mp-pending)").count()


def _images_state(page, mid):
    return page.evaluate("id => (state.memos.find(x => x.id === id).images || []).length", mid)


def _scenario_owner(page, live_server, vp):
    m = _owner(page, live_server, vp)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/api/memos/%d/images$" % m["id"])
    # Réponse retenue : la vignette d'attente doit être visible PENDANT l'envoi.
    relache = []
    page.route("**/api/memos/%d/images" % m["id"], lambda route: relache.append(route))
    page.locator("#memo-edit-dialog .ql-editor").click()
    assert _coller(page) is True, "le collage d'une image seule doit être pris (preventDefault)"
    # `wait_for_timeout` (pas `time.sleep`) : les handlers `route` ne tournent que dans la boucle Playwright.
    assert _attendre(lambda: page.wait_for_timeout(50) or len(relache) == 1), "aucun POST d'image parti"
    assert page.locator("#me-photos .mp-thumb.mp-pending").count() == 1, "pas de vignette d'attente"
    relache[0].continue_()
    page.unroute("**/api/memos/%d/images" % m["id"])
    assert _attendre(lambda: _vignettes(page) == 1), "la vraie vignette n'est pas apparue"
    assert page.locator("#me-photos .mp-pending").count() == 0, "vignette d'attente restée"
    assert len(posts) == 1, "un collage = un seul POST (%d)" % len(posts)
    assert _images_state(page, m["id"]) == 1, "memo.images non synchronisé"
    # Quill ne doit pas avoir reçu l'image en ligne (insertion inline interdite).
    assert page.locator("#memo-edit-dialog .ql-editor img").count() == 0, "image insérée dans Quill"
    return m


def test_owner_colle_une_image_dans_photos(page, live_server, console_errors):
    _scenario_owner(page, live_server, BUREAU)
    assert _erreurs_js(console_errors) == []


def test_owner_mobile_colle_une_image(page, live_server, console_errors):
    _scenario_owner(page, live_server, MOBILE)
    assert _erreurs_js(console_errors) == []


def test_texte_et_image_laisse_le_texte_a_quill(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/images$")
    page.locator("#memo-edit-dialog .ql-editor").click()
    # Cas réel (sélection d'une page web, Word) : texte + HTML + image. Sans HTML, Quill 2
    # préfère le fichier au texte : ce n'est plus un collage « de texte ».
    _coller(page, text="bonjour collé PI", html="<p>bonjour collé PI</p>")
    page.wait_for_timeout(500)
    assert posts == [], "texte + image : aucun upload attendu"
    assert "bonjour collé PI" in page.locator("#memo-edit-dialog .ql-editor").inner_text(), \
        "le texte doit être collé dans Quill"
    assert page.locator("#me-photos .mp-pending").count() == 0
    assert _erreurs_js(console_errors) == []


def test_copier_l_image_de_chrome_html_sans_texte_est_pris(page, live_server, console_errors):
    """Chrome « Copier l'image » dépose l'image ET un text/html `<img src=…>` sans texte :
    ce HTML-là ne compte pas comme du texte, sinon le cas principal ne marcherait jamais."""
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/api/memos/%d/images$" % m["id"])
    page.locator("#memo-edit-dialog .ql-editor").click()
    assert _coller(page, html='<meta charset="utf-8"><img src="https://ex.com/a.png">') is True
    assert _attendre(lambda: _vignettes(page) == 1), "l'image copiée depuis Chrome n'a pas été ajoutée"
    assert len(posts) == 1
    assert _erreurs_js(console_errors) == []


def test_texte_seul_dans_le_titre_n_est_pas_confisque(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/images$")
    titre = page.locator("#memo-edit-dialog input[type='text']").first
    titre.click()
    assert _coller(page, n=0, text="un titre") is False, "un collage de texte seul ne doit pas être bloqué"
    page.wait_for_timeout(300)
    assert posts == []
    assert page.locator("#me-photos .mp-pending").count() == 0
    assert _erreurs_js(console_errors) == []


def test_fichier_non_image_ignore(page, live_server, console_errors):
    """Un PDF collé n'est pas une photo (hors périmètre : jamais dans Fichiers non plus)."""
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/images$|/attachments$")
    # Dans le titre, pas dans Quill : Quill confisque TOUT collage (preventDefault systématique).
    page.locator("#memo-edit-dialog input[type='text']").first.click()
    assert _coller(page, n=0, pdf=True) is False, "un PDF collé ne doit pas être pris par les Photos"
    page.wait_for_timeout(400)
    assert posts == []
    assert page.locator("#me-photos .mp-pending").count() == 0
    assert _erreurs_js(console_errors) == []


def test_deux_images_deux_posts_noms_collage(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/api/memos/%d/images$" % m["id"])
    page.locator("#memo-edit-dialog .ql-editor").click()
    _coller(page, n=2)
    assert _attendre(lambda: _vignettes(page) == 2), "les deux images n'ont pas été ajoutées"
    assert len(posts) == 2
    noms = [re.search(rb'filename="([^"]+)"', r.post_data_buffer).group(1).decode("utf-8") for r in posts]
    assert re.fullmatch(r"Collage \d{4}-\d{2}-\d{2} \d{2}h\d{2}\.png", noms[0]), noms
    assert re.fullmatch(r"Collage \d{4}-\d{2}-\d{2} \d{2}h\d{2}-2\.png", noms[1]), noms
    assert _erreurs_js(console_errors) == []


def test_editeur_ferme_rien_ne_part(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    _fermer_owner(page)
    posts = _posts(page, r"/images$")
    assert _coller(page, sel="body") is False, "éditeur fermé : le collage ne doit pas être pris"
    page.wait_for_timeout(500)
    assert posts == []
    assert page.locator(".mp-pending").count() == 0
    assert _erreurs_js(console_errors) == []


def test_erreur_serveur_retire_la_vignette_et_previent(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    page.route("**/api/memos/%d/images" % m["id"], lambda route: route.fulfill(
        status=400, content_type="application/json", body='{"error": "Signature invalide"}'))
    page.locator("#memo-edit-dialog .ql-editor").click()
    _coller(page)
    page.wait_for_selector("#notify-dialog[open]", timeout=5_000)
    assert "Signature invalide" in page.locator("#notify-dialog").inner_text()
    page.locator("#notify-ok").click()
    assert _attendre(lambda: page.locator("#me-photos .mp-pending").count() == 0), "vignette d'attente restée"
    assert _vignettes(page) == 0, "grille modifiée malgré l'échec"
    assert _images_state(page, m["id"]) == 0
    assert [e for e in _erreurs_js(console_errors) if "400" not in e] == []


def test_erreur_reseau_retire_la_vignette_et_previent(page, live_server, console_errors):
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    page.route("**/api/memos/%d/images" % m["id"], lambda route: route.abort())
    page.locator("#memo-edit-dialog .ql-editor").click()
    _coller(page)
    page.wait_for_selector("#notify-dialog[open]", timeout=5_000)
    assert "Collage impossible" in page.locator("#notify-dialog").inner_text()
    page.locator("#notify-ok").click()
    assert _attendre(lambda: page.locator("#me-photos .mp-pending").count() == 0), "vignette d'attente restée"


def test_ouvrir_fermer_trois_fois_un_seul_post(page, live_server, console_errors):
    m = _owner(page, live_server)
    for _ in range(3):
        _ouvrir_owner(page, m["id"])
        _fermer_owner(page)
    _ouvrir_owner(page, m["id"])
    posts = _posts(page, r"/images$")
    page.locator("#memo-edit-dialog .ql-editor").click()
    _coller(page)
    assert _attendre(lambda: _vignettes(page) == 1)
    page.wait_for_timeout(500)
    assert len(posts) == 1, "écouteurs empilés : %d POST pour un collage" % len(posts)
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ invité (share.html)


def _share(page, live_server, role):
    _n[0] += 1
    proj = page.request.post(live_server + "/api/projects", data={"name": "PI dossier %d" % _n[0]}).json()
    m = _memo(page, live_server, project_id=proj["id"])
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"], "role": role}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Paula", "email": "paula%d@ex.com" % _n[0], "pin": sh["pin"]})
    assert reg.ok, reg.text()
    page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (sh["token"], reg.json()["guest_token"]))
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof openEditor === 'function' && DATA && (DATA.memos || []).length")
    return m, sh


def test_invite_editeur_colle_une_image(page, live_server, console_errors):
    m, sh = _share(page, live_server, "editor")
    page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id))", m["id"])
    page.wait_for_selector("#edit-dialog[open] #q-photos .attach-sec", timeout=5_000)
    posts = _posts(page, r"/share/%s/memo/%d/images$" % (sh["token"], m["id"]))
    page.locator("#edit-dialog .ql-editor, #edit-dialog textarea").first.click()
    assert _coller(page) is True
    assert _attendre(lambda: _vignettes(page, "#q-photos") == 1), "vignette invitée non ajoutée"
    assert len(posts) == 1
    assert posts[0].headers.get("x-guest-token"), "X-Guest-Token absent"
    assert _erreurs_js(console_errors) == []


# ------------------------------------------------------------------ hub


def _hub(page, live_server, role, avec_image=False):
    _n[0] += 1
    email = "pihub%d@ex.com" % _n[0]
    proj = page.request.post(live_server + "/api/projects", data={"name": "PI hub %d" % _n[0]}).json()
    m = _memo(page, live_server, project_id=proj["id"])
    if avec_image:
        _image_owner(page, live_server, m["id"])
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"], "role": role}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Hugo", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    con = sqlite3.connect(os.path.join(os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        hub_token, pin = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?", (email,)).fetchone()
    finally:
        con.close()
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
    assert page.request.post(live_server + "/share/hub/%s/approve" % hub_token, data={"pin": pin}).ok
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof openEditor === 'function' && DATA && (DATA.memos || []).length")
    page.evaluate("id => openEditor(DATA.memos.find(x => x.id === id))", m["id"])
    page.wait_for_selector("#ed[open]", timeout=5_000)
    return m, sh


def test_hub_editeur_colle_une_image(page, live_server):
    m, sh = _hub(page, live_server, "editor")
    page.wait_for_selector("#ed-images .attach-sec", timeout=5_000)
    posts = _posts(page, r"/share/%s/memo/%d/images$" % (sh["token"], m["id"]))
    page.locator("#ed .ql-editor, #ed textarea").first.click()
    assert _coller(page) is True
    assert _attendre(lambda: _vignettes(page, "#ed-images") == 1), "vignette hub non ajoutée"
    assert len(posts) == 1


def test_hub_lecteur_ne_peut_pas_coller(page, live_server):
    """Section rendue en LECTURE (le mémo a déjà une image) : un collage n'envoie rien."""
    m, sh = _hub(page, live_server, "viewer", avec_image=True)
    page.wait_for_selector("#ed-images .attach-sec", timeout=5_000)
    posts = _posts(page, r"/images$")
    assert _coller(page, sel="#ed") is False, "lecteur : le collage ne doit pas être pris"
    page.wait_for_timeout(500)
    assert posts == []
    assert page.locator("#ed-images .mp-pending").count() == 0


# ------------------------------------------------------------------ addendum : bouton « Coller une image »
# Pour qui ne pense pas à ⌘V (ou sur mobile, où le menu « Coller » exige un champ focalisé) :
# un bouton lit `navigator.clipboard.read()` au clic et reprend le MÊME chemin que le collage.

_MOCK_CLIP = """({ kind }) => {
  const bin = atob('%s'), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const items = kind === 'image'
    ? [new ClipboardItem({ 'image/png': new Blob([u], { type: 'image/png' }) })]
    : [new ClipboardItem({ 'text/plain': new Blob(['juste du texte'], { type: 'text/plain' }) })];
  Object.defineProperty(navigator.clipboard, 'read', { configurable: true, value: async () => items });
}""" % PNG_B64


def _bouton_coller(page, box="#me-photos"):
    return page.locator(box + " button", has_text="Coller une image")


def test_bouton_coller_une_image(page, live_server, console_errors):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    assert _bouton_coller(page).count() == 1, "bouton « Coller une image » absent"
    page.evaluate(_MOCK_CLIP, {"kind": "image"})
    posts = _posts(page, r"/api/memos/%d/images$" % m["id"])
    _bouton_coller(page).click()
    assert _attendre(lambda: _vignettes(page) == 1), "l'image du presse-papiers n'a pas été ajoutée"
    assert len(posts) == 1
    nom = re.search(rb'filename="([^"]+)"', posts[0].post_data_buffer).group(1).decode("utf-8")
    assert re.fullmatch(r"Collage \d{4}-\d{2}-\d{2} \d{2}h\d{2}\.png", nom), nom
    assert _erreurs_js(console_errors) == []


def test_bouton_coller_sans_image_previent(page, live_server, console_errors):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    page.evaluate(_MOCK_CLIP, {"kind": "texte"})
    posts = _posts(page, r"/images$")
    _bouton_coller(page).click()
    page.wait_for_selector("#notify-dialog[open]", timeout=5_000)
    assert "Aucune image" in page.locator("#notify-dialog").inner_text()
    page.locator("#notify-ok").click()
    assert posts == [], "un presse-papiers sans image ne doit rien envoyer"
    assert page.locator("#me-photos .mp-pending").count() == 0
    assert _erreurs_js(console_errors) == []


def test_bouton_coller_masque_sans_api(page, live_server, console_errors):
    page.add_init_script("try { Object.defineProperty(navigator.clipboard, 'read', { value: undefined }); } catch (e) {}")
    m = _owner(page, live_server)
    _ouvrir_owner(page, m["id"])
    assert page.evaluate("() => typeof navigator.clipboard.read") == "undefined", "décor : API non retirée"
    assert _bouton_coller(page).count() == 0, "sans clipboard.read, le bouton doit être masqué"
    assert _erreurs_js(console_errors) == []


def test_bouton_coller_absent_pour_un_lecteur(page, live_server):
    _hub(page, live_server, "viewer", avec_image=True)
    page.wait_for_selector("#ed-images .attach-sec", timeout=5_000)
    assert _bouton_coller(page, "#ed-images").count() == 0
