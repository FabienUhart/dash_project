"""[GUEST-COMMENTS-POPIN] Le fil de commentaires invité s'ouvre en pop-in, comme chez l'owner.

Côté invité, tout le fil s'affichait **en ligne sur la card** : bulles, réponses, réactions et
composeur empilés sous le mémo. Une card avec dix messages devenait une colonne illisible, alors
que le propriétaire ouvre le même fil dans une pop-in dédiée depuis toujours.

Ces tests passent par la vraie page invitée : ils vérifient que le fil a quitté la card, qu'un 💬
avec compteur le remplace au pied, et que la pop-in porte bien les bulles — puis que les droits
sont respectés des deux côtés (commentateur : composeur présent ; lecteur : consultation seule).
"""
import time

import pytest

pytestmark = pytest.mark.e2e

_n = [0]


def _attendre(page, cond, timeout_ms=10_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.15)
    return False


def _monter(page, live_server, role="commenter", approuve=False, messages=("Premier message",)):
    """Un partage contenant un mémo commenté, ouvert côté invité.

    `approuve=True` inscrit un invité et pose son jeton dans le `localStorage` — c'est ce que
    fait la page après la saisie du code, et c'est la seule façon d'obtenir un composeur
    (`canCommentMemo` exige un invité approuvé).
    """
    _n[0] += 1
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier commenté %d" % _n[0]}).json()
    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Mémo qui discute %d" % _n[0],
                                   "project_id": proj["id"]}).json()
    for m in messages:
        r = page.request.post(live_server + "/api/memos/%d/comments" % memo["id"], data={"body": m})
        assert r.ok, r.text()

    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"], "role": role}).json()
    if approuve:
        reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                                data={"name": "Gaston", "email": "gaston%d@ex.com" % _n[0],
                                      "pin": sh["pin"]})
        assert reg.ok, reg.text()
        page.add_init_script("localStorage.setItem('dashguest:%s', '%s')"
                             % (sh["token"], reg.json()["guest_token"]))

    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    return {"memo": memo, "share": sh}


def _bulles_hors_popin(page):
    """Bulles de commentaire présentes AILLEURS que dans une pop-in — c'est-à-dire sur la card."""
    return page.evaluate("""() => Array.from(document.querySelectorAll('.cmt'))
        .filter(c => !c.closest('dialog')).length""")


def _bulles_dans_popin(page):
    return page.evaluate("""() => document.querySelectorAll('dialog[open] .cmt').length""")


def _bouton_commentaires(page):
    return page.locator(".task-foot button[title='Commentaires']").first


def test_guest_comments_open_in_a_popin(live_server, page):
    """Le fil quitte la card et devient une pop-in, ouverte par un 💬 compté au pied."""
    # ⚠ On écoute la console : la pop-in invitée est bâtie à la main et j'y ai d'abord appelé
    # `memoHeadline`, un helper qui n'existe que chez le propriétaire. Une `ReferenceError` de
    # cette espèce n'empêche pas le DOM d'exister — elle vide juste la pop-in en silence.
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)

    _monter(page, live_server, messages=("Un mot", "Un autre"))
    assert _attendre(page, lambda: page.locator(".task").count() > 0), "aucune card"

    assert _bulles_hors_popin(page) == 0, (
        "le fil ne doit plus s'empiler sur la card : %d bulle(s) trouvée(s) hors pop-in"
        % _bulles_hors_popin(page))

    btn = _bouton_commentaires(page)
    assert btn.count() == 1, "un bouton 💬 doit remplacer le fil, au pied de la card"
    assert "2" in (btn.text_content() or ""), (
        "le 💬 doit porter le compteur de messages humains (texte vu : %r)" % btn.text_content())

    btn.click()
    assert _attendre(page, lambda: page.locator("dialog[open]").count() > 0), (
        "le clic sur 💬 doit ouvrir une pop-in")
    assert _attendre(page, lambda: _bulles_dans_popin(page) == 2), (
        "la pop-in doit contenir les bulles du fil (trouvé : %d)" % _bulles_dans_popin(page))
    assert erreurs == [], "Erreurs JS sur la page invitée :\n%s" % erreurs


def test_guest_commenter_can_post_from_the_popin(live_server, page):
    """Rôle commentateur : le composeur vit dans la pop-in, et un envoi ajoute la bulle."""
    _monter(page, live_server, role="commenter", approuve=True, messages=("Message d'origine",))
    assert _attendre(page, lambda: _bouton_commentaires(page).count() == 1)
    _bouton_commentaires(page).click()
    assert _attendre(page, lambda: page.locator("dialog[open]").count() > 0)

    # ⚠ Le composeur invité est un `input[type=text]` validé par ENTRÉE (son placeholder le dit),
    # pas un bouton « Envoyer » : ma première version cherchait un bouton qui n'existe pas.
    champ = page.locator("dialog[open] input[type='text']").first
    assert _attendre(page, lambda: champ.count() > 0), (
        "un commentateur doit trouver le composeur DANS la pop-in")
    champ.fill("Réponse envoyée depuis la pop-in")
    champ.press("Enter")

    assert _attendre(page, lambda: _bulles_dans_popin(page) >= 2, timeout_ms=15_000), (
        "le message posté depuis la pop-in doit apparaître dans le fil")


def test_guest_reader_sees_the_thread_without_a_composer(live_server, page):
    """Rôle lecteur : le fil reste consultable, mais rien pour écrire — les droits ne bougent
    pas (invariant 5 : le serveur reste seul juge, la pop-in ne fait qu'afficher)."""
    _monter(page, live_server, role="viewer", approuve=False, messages=("Lecture seule",))
    assert _attendre(page, lambda: _bouton_commentaires(page).count() == 1)
    _bouton_commentaires(page).click()
    assert _attendre(page, lambda: _bulles_dans_popin(page) == 1)

    # ⚠ Viser `textarea` ici rendait le bon verdict pour la MAUVAISE raison : le composeur invité
    # est un `input[type=text]`, il n'y a jamais eu de textarea à trouver. On vise le vrai champ.
    champs = page.locator("dialog[open] input[type='text']").count()
    assert champs == 0, "un lecteur ne doit pas se voir proposer d'écrire (%d champ(s))" % champs


def test_owner_comments_popin_is_not_regressed(live_server, page):
    """Le propriétaire avait déjà sa pop-in : ce lot ne doit pas y toucher."""
    _n[0] += 1
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier owner cmt %d" % _n[0]}).json()
    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Mémo owner commenté", "project_id": proj["id"]}).json()
    page.request.post(live_server + "/api/memos/%d/comments" % memo["id"],
                      data={"body": "Un message côté propriétaire"})

    page.goto(live_server, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=15_000)
    page.wait_for_load_state("networkidle")
    page.locator(".cat-item", has_text="Mémos").first.click()

    picto = page.locator(".task", has_text="Mémo owner commenté").first.locator("text=/💬/").first
    assert _attendre(page, lambda: picto.count() > 0), "le picto 💬 owner a disparu de la card"
    picto.click()
    assert _attendre(page, lambda: page.locator("dialog[open] .cmt").count() >= 1), (
        "la pop-in de commentaires du propriétaire ne s'ouvre plus")
