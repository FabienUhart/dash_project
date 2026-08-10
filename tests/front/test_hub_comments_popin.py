"""[HUB-COMMENTS-POPIN] Dans le hub aussi, le 💬 ouvre le fil — pas l'éditeur complet.

[GUEST-COMMENTS-POPIN] a corrigé le partage direct (`share.html`), mais les invités passent en
réalité par le **hub** (« Mes dossiers »). Là, le 💬 d'une card appelait `openEditor(m)` : on
tombait sur la fiche complète du mémo — titre, contenu, échéance, priorité, assigné·es, images,
fichiers — avec les commentaires tout en bas. Pour lire trois messages, on ouvrait un formulaire
d'édition ; c'est le « tous les paramètres » signalé par Fabien.

Ces tests passent par la vraie page hub (approbation par code comprise) : le 💬 doit ouvrir la
pop-in de commentaires et **pas** l'éditeur, y poster doit marcher selon le rôle, et la fiche
complète doit rester accessible par le clic de card.
"""
import os
import sqlite3
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


def _monter_hub(page, live_server, role="editor", messages=("Premier message",)):
    """Un hub invité approuvé, contenant un mémo commenté.

    Le hub n'est pas atteignable par le seul jeton de partage : il faut inscrire l'invité, lire
    son `hub_token` en base (il n'est exposé que par e-mail) et l'approuver par son code.
    """
    _n[0] += 1
    email = "hubert%d@ex.com" % _n[0]
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier hub cmt %d" % _n[0]}).json()
    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Mémo commenté du hub %d" % _n[0],
                                   "project_id": proj["id"]}).json()
    for m in messages:
        r = page.request.post(live_server + "/api/memos/%d/comments" % memo["id"], data={"body": m})
        assert r.ok, r.text()

    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": proj["id"], "role": role}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Hubert", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()

    con = sqlite3.connect(os.path.join(os.environ["E2E_DATA_DIR"], "dashboard.db"))
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
    return {"memo": memo, "share": sh, "hub_token": hub_token}


def _picto_commentaires(page):
    """Le 💬 d'une card du hub (une pastille `.badge` cliquable posée par `memoPictosRow`)."""
    return page.locator(".badge.clickable", has_text="💬").first


def _bulles_popin(page):
    return page.evaluate(
        """() => document.querySelectorAll('#comments-dialog[open] .cmt').length""")


def _editeur_ouvert(page):
    return page.evaluate("""() => !!document.querySelector('#ed[open]')""")


def test_hub_comment_opens_popin_not_editor(live_server, page):
    """Le 💬 ouvre le fil en pop-in, et surtout PAS la fiche complète du mémo."""
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)

    _monter_hub(page, live_server, messages=("Un mot", "Un autre"))
    # ⚠ La page hub émet un 403 LÉGITIME avant approbation (l'écran « saisis ton code ») : on
    # remet le compteur à zéro puis on re-rend, pour ne juger que le rendu approuvé.
    erreurs.clear()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    assert _attendre(page, lambda: _picto_commentaires(page).count() == 1), (
        "aucune card commentée lisible dans le hub — la page a-t-elle démarré ?")
    _picto_commentaires(page).click()

    assert _attendre(page, lambda: _bulles_popin(page) == 2), (
        "le 💬 doit ouvrir la pop-in de commentaires avec le fil (bulles vues : %d)"
        % _bulles_popin(page))
    # La garde qui compte : c'est l'éditeur complet qui s'ouvrait avant ce lot.
    assert not _editeur_ouvert(page), (
        "le 💬 ne doit plus ouvrir l'éditeur complet du mémo, seulement le fil")
    # Corollaire visible : aucun champ de la fiche (titre, échéance, priorité) n'est à l'écran.
    for champ in ("#ed-title", "#ed-date", "#ed-prio"):
        assert page.locator(champ + ":visible").count() == 0, (
            "un champ de la fiche complète (%s) est visible : c'est encore l'éditeur" % champ)
    assert erreurs == [], "Erreurs JS sur la page hub :\n%s" % erreurs


def test_hub_comment_popin_posts(live_server, page):
    """Rôle commentateur : le composeur vit dans la pop-in, et l'envoi s'y voit.

    C'est le test du RAFRAÎCHISSEMENT, le trou déjà rencontré côté `share.html` : le rendu du
    fil vise un conteneur, et si ce conteneur reste celui de l'éditeur (fermé), le message part
    bien en base et n'apparaît nulle part.
    """
    _monter_hub(page, live_server, role="commenter", messages=("Message d'origine",))
    assert _attendre(page, lambda: _picto_commentaires(page).count() == 1)
    _picto_commentaires(page).click()
    assert _attendre(page, lambda: _bulles_popin(page) == 1)

    champ = page.locator("#comments-dialog[open] input[type='text']").first
    assert _attendre(page, lambda: champ.count() > 0), (
        "un commentateur doit trouver le composeur DANS la pop-in")
    champ.fill("Envoyé depuis la pop-in du hub")
    champ.press("Enter")

    assert _attendre(page, lambda: _bulles_popin(page) >= 2, timeout_ms=15_000), (
        "le message posté doit apparaître dans la pop-in ouverte, pas seulement en base")


def test_hub_comment_popin_is_read_only_for_a_viewer(live_server, page):
    """Rôle lecteur : le fil reste consultable, rien pour écrire (invariant 5 : le serveur juge)."""
    _monter_hub(page, live_server, role="viewer", messages=("Lecture seule",))
    assert _attendre(page, lambda: _picto_commentaires(page).count() == 1)
    _picto_commentaires(page).click()
    assert _attendre(page, lambda: _bulles_popin(page) == 1)

    champs = page.locator("#comments-dialog[open] input[type='text']").count()
    assert champs == 0, "un lecteur ne doit pas se voir proposer d'écrire (%d champ(s))" % champs


def test_hub_full_view_still_available(live_server, page):
    """Non-régression : la fiche complète reste accessible par le clic de card.

    ⚠ Le brief annonçait « le 👁 / le clic de card (`openEditor`) » ; mesuré dans le hub, ce
    sont deux portes DIFFÉRENTES — le 👁 ouvre `openMemoView` (fiche en lecture) et le clic sur
    le contenu ouvre `openEditor`. C'est ce second chemin que ce lot ne doit pas casser, et
    c'est le contenu qu'on clique : viser le centre de `.task` tombe sur le pied de card, qui
    n'a aucun gestionnaire depuis [CARD-ACTIONS-FIXED].
    """
    _monter_hub(page, live_server, messages=("Un message",))
    contenu = page.locator(".task .memo-content, .task .task-content").first
    if not _attendre(page, lambda: contenu.count() > 0):
        contenu = page.locator(".task", has_text="Mémo commenté du hub").first.locator(
            "text=Mémo commenté du hub").first
    assert _attendre(page, lambda: contenu.count() > 0), "aucune card dans le hub"
    contenu.click()
    assert _attendre(page, lambda: _editeur_ouvert(page)), (
        "le clic sur le contenu de la card doit toujours ouvrir la fiche complète du mémo")
    assert page.locator("#ed-title").count() > 0, "l'éditeur a perdu son champ Titre"
    # Le rendu du fil vise désormais un conteneur passé en paramètre : son chemin PAR DÉFAUT,
    # celui de l'éditeur, doit continuer de fonctionner. Sans cette ligne, la pop-in pourrait
    # marcher pendant que l'éditeur, lui, n'afficherait plus aucun message.
    assert _attendre(page, lambda: page.locator("#ed-comments .cmt").count() >= 1), (
        "l'éditeur n'affiche plus le fil de commentaires")


# ─────────── [HUB-COMMENTS-POPIN-ADDENDUM] le 💬 apparaît dès qu'on peut commenter ───────────
# Parité exacte avec `share.html` : « il y a des messages OU la personne peut commenter », icône
# seule à 0, compteur seulement à partir de 1. Sans ça, un commentateur devait passer par la
# fiche complète pour LANCER une discussion — soit exactement l'ouverture d'éditeur que le lot
# précédent venait de supprimer.

def test_hub_comment_icon_shows_for_commenter_without_message(live_server, page):
    """Rôle commentateur, mémo VIERGE : le 💬 est là, sans compteur, et ouvre la pop-in."""
    _monter_hub(page, live_server, role="commenter", messages=())
    assert _attendre(page, lambda: _picto_commentaires(page).count() == 1), (
        "un commentateur doit voir le 💬 même sans message, pour ouvrir la discussion")
    texte = _picto_commentaires(page).text_content() or ""
    assert "0" not in texte, "à zéro message, l'icône est seule — pas de « 💬 0 » (vu : %r)" % texte

    _picto_commentaires(page).click()
    assert _attendre(page, lambda: page.locator("#comments-dialog[open]").count() > 0), (
        "le 💬 doit ouvrir la pop-in même quand le fil est vide")
    assert page.locator("#comments-dialog[open] input[type='text']").count() == 1, (
        "la pop-in ouverte à vide doit porter le composeur, sinon elle ne sert à rien")


def test_hub_comment_icon_absent_for_viewer_without_message(live_server, page):
    """Rôle lecture seule, mémo vierge : pas de 💬 — rien à lire, pas le droit d'écrire."""
    _monter_hub(page, live_server, role="viewer", messages=())
    assert _attendre(page, lambda: page.locator(".task").count() > 0), "aucune card dans le hub"
    assert _picto_commentaires(page).count() == 0, (
        "un lecteur sans message ne doit pas se voir proposer un fil vide")


def test_hub_comment_count_still_shown(live_server, page):
    """Dès qu'il y a des messages, le compteur humain reste affiché (comportement inchangé)."""
    _monter_hub(page, live_server, role="commenter", messages=("Un", "Deux", "Trois"))
    assert _attendre(page, lambda: _picto_commentaires(page).count() == 1)
    assert "3" in (_picto_commentaires(page).text_content() or ""), (
        "le 💬 doit porter le compteur de messages humains (vu : %r)"
        % _picto_commentaires(page).text_content())


def test_shared_pictos_row_still_hides_an_empty_comment_chip(live_server, page):
    """Non-régression du composant PARTAGÉ : l'affichage-à-vide est opt-in.

    `memoPictosRow` sert les trois pages. Faire apparaître un 💬 vide pour tout le monde serait
    un effet de bord : le propriétaire, qui ne passe pas le drapeau, ne doit voir aucune pastille
    de commentaire sur un mémo sans message.
    """
    _n[0] += 1
    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier owner pictos %d" % _n[0]}).json()
    page.request.post(live_server + "/api/memos",
                      data={"content": "Mémo owner sans commentaire %d" % _n[0],
                            "project_id": proj["id"]})

    page.goto(live_server, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=15_000)
    page.wait_for_load_state("networkidle")
    page.locator(".cat-item", has_text="Mémos").first.click()

    carte = page.locator(".task", has_text="Mémo owner sans commentaire %d" % _n[0]).first
    assert _attendre(page, lambda: carte.count() > 0), "card propriétaire introuvable"
    assert carte.locator(".task-pictos .badge", has_text="💬").count() == 0, (
        "le propriétaire ne passe pas le drapeau : aucune pastille 💬 ne doit apparaître à zéro")
