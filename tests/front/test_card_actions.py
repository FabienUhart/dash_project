"""[CARD-ACTIONS-FIXED] Les actions d'une card vivent dans une barre en PIED, pas sur le titre.

Le propriétaire a déjà ce pied (`.task-foot` : dossier à gauche, actions à droite, filet de
séparation). L'invité et le hub posaient encore leurs actions sur la ligne du titre, en
`margin-left:auto` : selon ce que porte cette ligne — un badge de dossier, une vignette photo,
une pastille de priorité — l'œil 👁 se cale ailleurs d'une card à l'autre et « se balade ».

Ces tests mesurent l'ANCRE réelle dans le navigateur, sur des cards de types différents, par la
vraie page invitée. Ils sont écrits avant le correctif et doivent être rouges.
"""
import io
import time

import pytest

pytestmark = pytest.mark.e2e


_compteur = [0]


def _boot_share(page, live_server):
    """Monte un partage lisible avec deux cards de types DIFFÉRENTS, et l'ouvre côté invité.

    C'est là que le défaut se voit : une card « lien » et une card « photo » n'ont pas la même
    ligne de titre, donc pas la même place restante pour les actions.
    """
    from PIL import Image as _Image

    # ⚠ Nom UNIQUE par test : le `live_server` est partagé par la session et les noms de dossier
    # racine sont uniques (v25) — deux tests appelant ce montage recevaient un 409 au second.
    _compteur[0] += 1
    r = page.request.post(live_server + "/api/projects",
                          data={"name": "Cards variées %d" % _compteur[0]})
    assert r.status == 201, r.text()
    proj = r.json()
    lien = page.request.post(live_server + "/api/memos", data={
        "content": "Une card de type LIEN https://exemple.test/quelque-chose",
        "project_id": proj["id"]}).json()
    photo = page.request.post(live_server + "/api/memos", data={
        "content": "Une card de type PHOTO", "project_id": proj["id"]}).json()

    buf = io.BytesIO()
    _Image.new("RGB", (900, 500), (60, 90, 140)).save(buf, "JPEG")
    up = page.request.post(live_server + "/api/memos/%d/images" % photo["id"],
                           multipart={"image": {"name": "p.jpg", "mimeType": "image/jpeg",
                                                "buffer": buf.getvalue()}})
    assert up.ok, up.text()

    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"],
                                 "role": "editor"}).json()
    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    return {"lien": lien, "photo": photo, "share": sh}


def _attendre(page, cond, timeout_ms=10_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.15)
    return False


def _oeils(page):
    """Les boutons 👁 de chaque card, avec leur ancre horizontale et leur conteneur."""
    return page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.task').forEach((t) => {
        const b = t.querySelector('button[title="Voir le mémo"]');
        if (!b) return;
        const rc = t.getBoundingClientRect(), rb = b.getBoundingClientRect();
        out.push({
          texte: (t.textContent || '').slice(0, 24),
          droite: Math.round(rc.right - rb.right),   // distance au bord DROIT de la card
          bas: Math.round(rc.bottom - rb.bottom),    // distance au bord BAS de la card
          parent: (b.parentElement && b.parentElement.className) || '',
          grandParent: (b.parentElement && b.parentElement.parentElement
                        && b.parentElement.parentElement.className) || '',
        });
      });
      return out;
    }""")


def test_guest_card_actions_are_anchored(live_server, page):
    """L'ancre du 👁 doit être la MÊME sur une card lien et sur une card photo.

    On mesure sa distance au bord droit ET au bord bas de sa propre card : c'est ce que l'œil
    de l'utilisateur perçoit quand il parcourt une colonne. Une barre en pied donne deux
    distances constantes ; des actions posées sur la ligne du titre, non.
    """
    _boot_share(page, live_server)
    assert _attendre(page, lambda: len(_oeils(page)) >= 2), "il faut deux cards pour comparer"
    vus = _oeils(page)

    droites = {o["droite"] for o in vus}
    bas = {o["bas"] for o in vus}
    assert len(droites) == 1, (
        "le 👁 n'est pas à la même distance du bord droit selon la card : %r" % vus)
    assert len(bas) == 1, (
        "le 👁 n'est pas à la même hauteur selon la card (il « se balade ») : %r" % vus)


def test_guest_actions_live_in_the_card_foot(live_server, page):
    """Structure : les actions ne sont plus enfant de la ligne de titre mais du pied de card."""
    _boot_share(page, live_server)
    assert _attendre(page, lambda: len(_oeils(page)) >= 2)

    for o in _oeils(page):
        assert "task-acts" in o["parent"], "le 👁 doit rester groupé avec les autres actions"
        assert "task-foot" in o["grandParent"], (
            "les actions doivent vivre dans le pied de card, pas sur la ligne du titre "
            "(conteneur trouvé : %r)" % o["grandParent"])


def test_owner_card_foot_is_not_regressed(live_server, page):
    """Le propriétaire avait déjà son pied : on vérifie qu'il l'a toujours, et qu'il reste
    utilisable (le lot ne doit rien casher côté owner)."""
    proj = page.request.post(live_server + "/api/projects", data={"name": "Dossier owner"}).json()
    page.request.post(live_server + "/api/memos",
                      data={"content": "Card owner", "project_id": proj["id"]})

    page.goto(live_server, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=15_000)
    page.wait_for_load_state("networkidle")
    page.locator(".cat-item", has_text="Mémos").first.click()

    assert _attendre(page, lambda: page.locator(".task .task-foot").count() > 0), (
        "le pied de card du propriétaire a disparu")
    actions = page.locator(".task .task-foot .task-actions button")
    assert actions.count() > 0, "les actions du pied owner ont disparu"
    assert actions.first.is_enabled(), "les actions du pied owner doivent rester cliquables"


def test_hub_cards_also_use_the_card_foot(live_server, page):
    """Le hub reçoit le même pied — et ce test existe surtout parce que `hub.html` n'avait
    AUCUNE couverture e2e : je venais d'y éditer du JS à l'aveugle, une faute de frappe y serait
    passée inaperçue jusqu'à ce qu'un invité ouvre la page.
    """
    import os as _os
    import sqlite3 as _sqlite3

    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)

    _compteur[0] += 1
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier hub %d" % _compteur[0]}).json()
    page.request.post(live_server + "/api/memos",
                      data={"content": "Card vue depuis le hub", "project_id": proj["id"]})
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"],
                                 "role": "editor"}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Hubert", "email": "hubert@ex.com", "pin": sh["pin"]})
    assert reg.ok, reg.text()

    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        hub_token, pin = con.execute(
            "SELECT hub_token, pin FROM guest_hubs WHERE email = ?", ("hubert@ex.com",)).fetchone()
    finally:
        con.close()

    page.goto(live_server + "/share/hub/" + hub_token, wait_until="domcontentloaded")
    approuve = page.request.post(live_server + "/share/hub/%s/approve" % hub_token,
                                 data={"pin": pin})
    assert approuve.ok, approuve.text()
    # ⚠ On remet le compteur d'erreurs à zéro APRÈS l'approbation : le premier chargement, lui,
    # reçoit légitimement un 403 sur `/data` — c'est l'écran « saisis ton code », pas un défaut.
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    erreurs.clear()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    assert _attendre(page, lambda: len(_oeils(page)) >= 1, timeout_ms=15_000), (
        "aucune card lisible dans le hub — la page a-t-elle démarré ?")
    for o in _oeils(page):
        assert "task-foot" in o["grandParent"], (
            "les actions du hub doivent vivre dans le pied de card (trouvé : %r)" % o["grandParent"])
    assert erreurs == [], "Erreurs JS sur la page hub :\n%s" % erreurs
