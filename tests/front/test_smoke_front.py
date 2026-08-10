"""
Parcours navigateur (headless).

Ce que le back ne peut pas dire : la page se rend-elle vraiment, le JS démarre-t-il, un
formulaire aboutit-il jusqu'en base ? Un `node --check` valide la syntaxe mais laisse passer
une `ReferenceError` qui tue la page au chargement — c'est précisément ce que ces tests
attrapent. D'où l'assertion « aucune erreur console » sur chaque parcours.
"""
import time

import pytest

pytestmark = pytest.mark.e2e


def _boot(page, live_server, path="/"):
    """Charge la page ET attend qu'elle soit au REPOS.

    `.cat-item` prouve que le JS a tourné, mais pas que l'app a fini de s'installer : agir
    pendant que ses requêtes initiales sont encore en vol, c'est parier sur la vitesse de la
    machine — le pari qui a rougi la CI trois fois. On attend donc aussi `networkidle`.
    """
    page.goto(live_server + path, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)   # la sidebar est peinte = le JS a tourné
    page.wait_for_load_state("networkidle")


def _force_navigateur_en_ligne(page):
    """Épingle `navigator.onLine` à `true` AVANT le chargement.

    Ce n'est pas un contournement : c'est poser la précondition du parcours qu'on teste. Un
    Chromium headless en conteneur peut se déclarer hors ligne alors que le réseau marche
    (`loadAll()` réussit, la sidebar se peint) ; l'app le croit sur parole, range la note dans
    sa file locale et ne poste rien. Le parcours « créer un mémo par l'UI » n'a pas vocation à
    éprouver ce cas — le repli hors-ligne mérite son propre test, pas de détourner celui-ci au
    hasard des runners. À appeler AVANT `_boot` (un init script ne vaut que pour les
    chargements suivants)."""
    page.add_init_script(
        "Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => true });"
    )


def _wait_app_online(page, timeout_ms=10_000):
    """Attend que l'APP se considère en ligne (`isOffline === false`), pas que le réseau existe.

    C'est LA précondition du chemin nominal, et c'est ce qui manquait : le handler de
    `#memo-quick` commence par `if (isOffline) { enqueueNote(...); return; }`. Si le navigateur
    se déclare hors ligne au chargement — ce que fait parfois un Chromium en conteneur, le temps
    que son interface réseau soit vue —, la note part dans la file locale **sans erreur console
    et sans requête**. Attendre plus longtemps le résultat n'y change rien : il faut attendre
    l'état, ou renoncer en le disant.
    """
    try:
        page.wait_for_function("() => isOffline === false", timeout=timeout_ms)
        return True
    except Exception:
        return False


def _wait_until(fn, timeout_ms=10_000, step_ms=200):
    """Attend qu'une condition devienne vraie, au lieu de dormir un temps fixe.

    Une pause en dur est un pari sur la vitesse de la machine : `wait_for_timeout(800)`
    passait sur un portable et **échouait sur le runner CI**, plus lent — un test instable,
    ce qui est pire qu'un test absent puisqu'il bloque des déploiements au hasard. On
    interroge donc jusqu'à ce que ce soit vrai, avec une borne franche.
    """
    import time
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(step_ms / 1000.0)
    return False


def _offline_queue(page):
    """La file hors-ligne du navigateur (`localStorage.offlineQueue`) — la seconde destination
    possible d'une note saisie. La lire, c'est la différence entre « le test a échoué » et
    « le test sait pourquoi »."""
    try:
        return page.evaluate(
            "() => { try { return JSON.parse(localStorage.getItem('offlineQueue') || '[]'); }"
            "        catch (e) { return []; } }"
        )
    except Exception:
        return []


def _pourquoi_absent(page, texte, console_errors):
    """Message d'échec qui NOMME la cause au lieu de constater l'absence.

    Trois issues possibles pour une note saisie, et elles ne se soignent pas pareil :
      · dans la file hors-ligne → l'app se croyait hors ligne (course d'état, pas de lenteur) ;
      · nulle part             → l'`Enter` n'a rien déclenché (handler non lié) ;
      · erreurs console        → la page a cassé, et c'est ça qu'il faut lire d'abord.
    Sans ce tri, la prochaine occurrence sera aussi aveugle que les trois précédentes.
    """
    file_ = _offline_queue(page)
    en_file = any(texte in (n.get("content", "") or "") for n in file_ if isinstance(n, dict))
    etat = page.evaluate("() => ({ online: navigator.onLine, offline_app: (typeof isOffline !== 'undefined') ? isOffline : 'inconnu' })")
    if en_file:
        cause = ("AVALÉE PAR LE REPLI HORS-LIGNE : la note est dans `localStorage.offlineQueue`, "
                 "donc le handler a pris sa branche `isOffline` — l'app se croyait hors ligne "
                 "au moment de l'Enter. Aucune requête n'est partie ; attendre plus n'y change rien.")
    elif not file_:
        cause = ("L'ENTER N'A RIEN DÉCLENCHÉ : ni en base, ni en file. Le handler de #memo-quick "
                 "n'était pas lié, ou la touche n'a pas atteint le champ.")
    else:
        cause = "La file contient autre chose que la note attendue : %r" % (file_,)
    return ("Le mémo saisi dans l'UI n'est pas arrivé en base.\n  cause probable : %s\n"
            "  état : %r\n  erreurs console : %s" % (cause, etat, console_errors or "aucune"))


# --- Socle ----------------------------------------------------------------

def test_api_version_reachable(live_server, page):
    resp = page.request.get(live_server + "/api/version")
    assert resp.ok
    assert resp.json()["export"] == 27


def test_root_page_renders(live_server, page):
    page.goto(live_server, wait_until="domcontentloaded")
    assert page.locator("body").count() == 1
    assert page.title() is not None


# --- Parcours 1 : la page owner démarre pour de bon ------------------------

def test_owner_page_boots_without_js_error(live_server, page, console_errors):
    """La sidebar n'est pas dans le HTML servi : elle est peinte par le JS. La voir, c'est la
    preuve que le script a tourné jusqu'au bout."""
    _boot(page, live_server)
    assert page.locator(".cat-item").count() > 0, "Aucune catégorie peinte : le JS n'a pas démarré."
    assert console_errors == [], "Erreurs JS au chargement de la page owner :\n%s" % console_errors


# --- Parcours 2 : navigation entre les vues --------------------------------

def test_navigate_between_views(live_server, page, console_errors):
    """Plan / Agenda / Mémos : les trois vues principales doivent s'ouvrir sans casse."""
    _boot(page, live_server)
    for label in ("Plan", "Agenda", "Mémos"):
        item = page.locator(".cat-item", has_text=label).first
        item.click()
        # On attend que la vue prenne, pas un délai arbitraire : l'entrée cliquée devient active.
        _wait_until(lambda i=item: "active" in (i.get_attribute("class") or ""), timeout_ms=5_000)
        assert page.locator("body").count() == 1
    assert console_errors == [], "Erreurs JS pendant la navigation :\n%s" % console_errors


# --- Parcours 3 : créer un mémo par l'UI, et le retrouver en base ----------

def test_create_memo_through_the_ui(live_server, page, console_errors):
    """Le parcours qui compte vraiment : on tape dans le champ de capture rapide, et le mémo
    doit exister côté serveur. Bout en bout — formulaire, requête, persistance.

    ⚠ On reste sur la vue d'accueil : passer en vue « Mémos » masque la colonne latérale
    (`#memo-panel` → `display: none`), le board central prenant le relais. Le champ existe
    alors toujours dans le DOM mais n'est plus atteignable — vérifié, pas supposé.

    ⚠ L'app doit être EN LIGNE au moment de l'`Enter` : sinon le handler range la note dans sa
    file hors-ligne et le mémo n'arrive jamais, silencieusement. C'est la cause établie des
    trois rougissements de CI ([E2E-FLAKY-FIX]) — d'où l'attente d'état avant d'agir, et le
    diagnostic en cas d'échec."""
    texte = "Mémo créé par le test e2e"
    _force_navigateur_en_ligne(page)      # précondition posée AVANT le chargement
    _boot(page, live_server)
    assert _wait_app_online(page), (
        "L'app se déclare hors ligne : dans cet état elle met la note en file locale sans "
        "jamais la poster. Ce n'est pas un échec du parcours, c'est un environnement où "
        "`navigator.onLine` reste faux."
    )

    quick = page.locator("#memo-quick")
    assert quick.is_visible(), "Le champ de capture rapide n'est pas visible sur l'accueil."
    quick.fill(texte)
    quick.press("Enter")

    def _arrived():
        memos = page.request.get(live_server + "/api/memos").json()
        rows = memos if isinstance(memos, list) else memos.get("memos", [])
        return any(texte in (m.get("content", "") + m.get("title", "")) for m in rows)

    assert _wait_until(_arrived), _pourquoi_absent(page, texte, console_errors)
    assert console_errors == [], "Erreurs JS pendant la création :\n%s" % console_errors


# --- Parcours 4 : la page invitée se rend aussi ----------------------------

def test_share_page_renders_for_a_guest(live_server, page, console_errors):
    """`share.html` est une page distincte, avec son propre JS : elle mérite son propre garde-fou
    (une collision de nom dans le partial peut tuer l'invité sans toucher l'owner)."""
    pid = page.request.post(live_server + "/api/projects",
                            data={"name": "Dossier e2e"}).json()["id"]
    page.request.post(live_server + "/api/memos",
                      data={"content": "Visible par l'invité", "project_id": pid})
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": pid}).json()

    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")   # même discipline : on juge une app au repos
    assert _wait_until(lambda: "Visible par l'invité" in page.content()), (
        "La page de partage n'affiche pas son mémo."
    )
    assert console_errors == [], "Erreurs JS sur la page invitée :\n%s" % console_errors


# --- Parcours 5 : pivoter une photo ET l'enregistrer ------------------------

def test_rotate_and_save_a_photo(live_server, page, console_errors):
    """[PHOTO-ROTATE-SAVE] Le geste complet dans un vrai navigateur : le bouton n'existe que
    côté propriétaire, n'apparaît qu'une fois l'angle changé, et le fichier ORIGINAL a bien
    pivoté après la sauvegarde.

    On ouvre la visionneuse en l'appelant directement plutôt qu'en cliquant le picto d'une
    carte : ce test porte sur `runImageViewer`, pas sur le chrome des cartes — le viser par
    l'UI rendait le test fragile sans rien prouver de plus (deux sélecteurs différents ont déjà
    expiré avant que je renonce à ce chemin).
    """
    import io as _io
    from PIL import Image as _Image

    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Photo de travers"}).json()
    buf = _io.BytesIO()
    _Image.new("RGB", (900, 500), (200, 40, 40)).save(buf, "JPEG")
    up = page.request.post(live_server + "/api/memos/%d/images" % memo["id"],
                           multipart={"image": {"name": "p.jpg", "mimeType": "image/jpeg",
                                                "buffer": buf.getvalue()}})
    assert up.ok, up.text()
    nom = up.json()["images"][-1]

    _boot(page, live_server)

    # ① gabarit INVITÉ : aucun `rotateUrl` → aucun bouton (non-régression du périmètre invité)
    page.evaluate("(n) => runImageViewer({ images:[n], startIndex:0, imageUrl:(x)=>'/uploads/'+x })", nom)
    page.wait_for_selector(".iv-bar", timeout=10_000)
    assert page.locator(".iv-bar button[title='Enregistrer la rotation']").count() == 0, (
        "un invité ne doit pas pouvoir réécrire l'original du propriétaire"
    )
    page.keyboard.press("Escape")

    # ② gabarit OWNER : `rotateUrl` fourni
    page.evaluate("(n) => runImageViewer({ images:[n], startIndex:0, imageUrl:(x)=>'/uploads/'+x,"
                  " rotateUrl:(x)=>'/api/images/'+x+'/rotate' })", nom)
    page.wait_for_selector(".iv-bar", timeout=10_000)
    save = page.locator(".iv-bar button[title='Enregistrer la rotation']")
    assert save.count() == 1
    # [PHOTO-ROTATE-POLISH] Le bouton n'est plus masqué/révélé : il reste là, GRISÉ. Le masquer
    # réélargissait la barre centrée et faisait sauter les flèches sous le doigt.
    assert save.is_visible(), "le bouton doit rester dans la barre (largeur constante)"
    assert save.is_disabled(), "désactivé tant qu'il n'y a rien à sauver"

    page.locator(".iv-bar button[title='Pivoter à droite']").click()
    assert save.is_enabled(), "il doit s'activer dès que l'angle change"

    # ⚠ On lit le fichier SUR LE DISQUE du live_server, plus par HTTP : depuis
    # [PHOTO-ROTATE-POLISH] les images sont servies en revalidation et le client de test peut
    # légitimement rendre un corps vide (304 amorti par son propre cache), ce qui faisait
    # échouer la lecture Pillow alors que RIEN n'était cassé. Le disque dit la vérité.
    import os as _os
    chemin = _os.path.join(_os.environ["E2E_DATA_DIR"], "uploads", nom)

    def _pivotee():
        try:
            with _Image.open(chemin) as im:
                return im.size == (500, 900)
        except Exception:
            return False

    save.click()
    # ⚠ On attend l'EFFET, pas l'état du bouton : le handler pose `disabled = true` dès la
    # première ligne (anti double-clic), donc guetter « le bouton est grisé » rendait la main
    # AVANT même que la requête parte — le test lisait le fichier d'origine et accusait le code.
    assert _wait_until(_pivotee, timeout_ms=10_000), (
        "l'original n'a pas pivoté sur le disque après le clic Enregistrer"
    )
    assert save.is_disabled(), (
        "une fois la sauvegarde passée, l'angle est revenu à zéro : le bouton doit retomber grisé"
    )

    assert console_errors == [], "Erreurs JS pendant la rotation :\n%s" % console_errors


def test_rotate_button_is_there_when_opening_from_a_card_thumbnail(live_server, page, console_errors):
    """[PHOTO-ROTATE-SAVE-FIX] Le garde-fou qui manquait, et qui aurait vu le trou.

    Le parcours précédent appelle `runImageViewer` directement : il prouve que la visionneuse
    sait afficher le bouton, pas qu'une PORTE le lui demande. Or la v1 ne câblait `rotateUrl`
    que sur deux entrées sur six — ouvrir une photo par la vignette d'une card ne proposait donc
    rien à enregistrer, et aucun test ne s'en apercevait.

    Celui-ci ouvre par le vrai DOM (`.tc-thumb`, la vignette posée par `applyCardThumb`).
    """
    import io as _io
    from PIL import Image as _Image

    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Card avec vignette"}).json()
    buf = _io.BytesIO()
    _Image.new("RGB", (900, 500), (40, 120, 200)).save(buf, "JPEG")
    up = page.request.post(live_server + "/api/memos/%d/images" % memo["id"],
                           multipart={"image": {"name": "p.jpg", "mimeType": "image/jpeg",
                                                "buffer": buf.getvalue()}})
    assert up.ok, up.text()

    _boot(page, live_server)
    # Les cards à vignette vivent sur le board « Mémos », pas sur l'accueil — constaté, pas
    # supposé : le premier jet cherchait `.tc-thumb` sur l'accueil et ne trouvait rien.
    page.locator(".cat-item", has_text="Mémos").first.click()
    vignette = page.locator(".tc-thumb").first
    assert _wait_until(lambda: vignette.count() > 0, timeout_ms=10_000), (
        "aucune vignette de card : la porte testée n'est pas là où on la cherche"
    )
    vignette.click()
    page.wait_for_selector(".iv-bar", timeout=10_000)

    save = page.locator(".iv-bar button[title='Enregistrer la rotation']")
    assert save.count() == 1, (
        "ouvrir par la vignette d'une card doit proposer d'enregistrer la rotation — "
        "c'est exactement la porte qui était débranchée"
    )
    assert save.is_visible() and save.is_disabled(), "présent mais grisé tant que l'angle est nul"

    # Preuve anti-décalage : la barre contient EXACTEMENT le même nombre de boutons avant et
    # après la rotation. C'est ce qui garantit que la rangée, centrée, ne se recentre pas sous
    # le doigt au moment où l'on clique sur les flèches.
    avant = page.locator(".iv-bar button").count()
    page.locator(".iv-bar button[title='Pivoter à droite']").click()
    assert save.is_enabled(), "il doit s'activer dès que l'angle change"
    assert page.locator(".iv-bar button").count() == avant, (
        "le nombre de boutons de la barre a changé : la rangée va se décaler"
    )

    assert console_errors == [], "Erreurs JS :\n%s" % console_errors


# --- Parcours 6 : le bouton Carte compte aussi les photos géolocalisées -----

def test_map_button_appears_for_photo_geo_only(live_server, page, console_errors):
    """[MAP-PHOTO-COUNT] La régression que le lot corrige, prise par la vraie barre.

    Un dossier dont un mémo porte une photo géolocalisée mais AUCUNE localisation manuelle
    n'avait pas de bouton Carte : le garde ne lisait que `memos.location`. On ne pouvait donc
    pas ouvrir la carte pour voir ces photos, alors que la donnée existait depuis l'upload.

    L'état est monté par l'API pour la partie normale (projet, mémo, upload réel), puis le seul
    bit qui manque — « cette photo a des coordonnées » — est posé en base : l'uploader vraiment
    géotaguée ferait géocoder chez Nominatim, et ce sous-processus n'est pas couvert par la
    garde zéro-réseau. On ouvre ensuite par la BARRE du dossier, pas en appelant `openMapDialog` :
    c'est la leçon du lot précédent, un test qui court-circuite la porte ne prouve rien sur elle.
    """
    import os as _os
    import sqlite3 as _sqlite3
    import io as _io
    from PIL import Image as _Image

    proj = page.request.post(live_server + "/api/projects",
                             data={"name": "Dossier photos situees"}).json()
    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Mémo sans localisation manuelle",
                                   "project_id": proj["id"]}).json()
    assert not memo.get("location"), "le mémo ne doit PAS avoir de localisation manuelle"

    buf = _io.BytesIO()
    _Image.new("RGB", (600, 400), (90, 120, 60)).save(buf, "JPEG")
    up = page.request.post(live_server + "/api/memos/%d/images" % memo["id"],
                           multipart={"image": {"name": "p.jpg", "mimeType": "image/jpeg",
                                                "buffer": buf.getvalue()}})
    assert up.ok, up.text()
    nom = up.json()["images"][-1]

    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        con.execute("UPDATE image_meta SET has_gps = 1, lat = ?, lng = ?, label = ? "
                    "WHERE filename = ?", (43.4832, -1.4666, "Bayonne", nom))
        con.commit()
    finally:
        con.close()

    _boot(page, live_server)
    page.locator(".cat-item", has_text="Dossier photos situees").first.click()

    # `.hdr-btn` = le bouton de la BARRE du dossier. Un `button:has-text("Carte")` trop large
    # attrapait un onglet caché d'une pop-in — le test échouait sur un élément invisible qui
    # n'avait rien à voir avec la fonctionnalité.
    carte = page.locator(".hdr-btn", has_text="Carte").first
    assert _wait_until(lambda: carte.count() > 0, timeout_ms=10_000), (
        "le bouton Carte doit apparaître alors que SEULE une photo est géolocalisée"
    )
    carte.click()

    assert _wait_until(lambda: page.locator(".leaflet-container").count() > 0, timeout_ms=10_000), (
        "la carte doit s'ouvrir sur le calque photo au lieu d'avorter sur « Aucun élément "
        "géolocalisé » — c'est le second volet du correctif"
    )
    assert console_errors == [], "Erreurs JS :\n%s" % console_errors


# --- Parcours 7 : la rotation survit à une réouverture SANS recharger la page ---

def _img_decodee(page, selecteur="dialog[open] img", timeout_ms=10_000):
    """Attend que l'image soit vraiment DÉCODÉE, pas seulement présente dans le DOM.

    Un `<img>` conserve l'ancien bitmap tant que le nouveau n'est pas décodé : lire
    `naturalWidth` trop tôt renvoie les dimensions de l'image PRÉCÉDENTE. C'est le piège qui
    m'a fait rapporter un faux « la réouverture montre l'ancienne image » lors du diagnostic —
    l'anomalie était réelle, mais pas au taux annoncé.
    """
    lire = ("(sel) => { const i = document.querySelector(sel);"
            " return i ? {w: i.naturalWidth, h: i.naturalHeight, complete: i.complete,"
            " src: i.getAttribute('src')} : null; }")
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        d = page.evaluate(lire, selecteur)
        if d and d["complete"] and d["w"] > 0:
            return d
        time.sleep(0.15)
    return page.evaluate(lire, selecteur)


def _img_versionnee(page, selecteur="dialog[open] img", timeout_ms=15_000):
    """Attend l'image d'APRÈS sauvegarde : `src` portant le jeton `&v=` ET décodée.

    ⚠ Ne jamais attendre `save.is_disabled()` pour ça : le handler pose `disabled = true` dès sa
    première ligne, en anti-double-clic, donc la condition est vraie AVANT même que la requête
    parte. Je m'y suis laissé prendre deux fois — dont une en écrivant ce test-ci.
    """
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        d = _img_decodee(page, selecteur, timeout_ms=1_000)
        if d and d["complete"] and d["w"] > 0 and "&v=" in (d["src"] or ""):
            return d
        time.sleep(0.15)
    return _img_decodee(page, selecteur)


def test_rotation_survives_reopening_without_a_page_reload(live_server, page, console_errors):
    """[PHOTO-ROTATE-MEMCACHE] Le défaut que la revalidation ETag ne pouvait pas corriger.

    En rouvrant la galerie sans recharger la page, le code réassigne `img.src` à une URL déjà
    chargée : Chromium sert alors depuis son cache MÉMOIRE — mesuré, aucune requête ne part, ni
    au réseau ni au service worker. Le `no-cache` du serveur n'a donc aucune prise, et la photo
    réapparaissait de travers juste après avoir été redressée.

    Le jeton de version par fichier (millisecondes) change l'URL, ce qui est la seule chose que
    ce cache-là respecte. On vérifie les DEUX chemins qui en dépendent : la visionneuse rouverte
    et la vignette de la card — l'un et l'autre sans jamais recharger la page.
    """
    import io as _io
    from PIL import Image as _Image

    memo = page.request.post(live_server + "/api/memos",
                             data={"content": "Photo à redresser sans rechargement"}).json()
    buf = _io.BytesIO()
    _Image.new("RGB", (900, 500), (30, 110, 170)).save(buf, "JPEG", quality=95)
    up = page.request.post(live_server + "/api/memos/%d/images" % memo["id"],
                           multipart={"image": {"name": "p.jpg", "mimeType": "image/jpeg",
                                                "buffer": buf.getvalue()}})
    assert up.ok, up.text()

    _boot(page, live_server)
    page.locator(".cat-item", has_text="Mémos").first.click()
    carte = page.locator(".task", has_text="Photo à redresser sans rechargement").first
    assert _wait_until(lambda: carte.count() > 0, timeout_ms=10_000), "card introuvable"
    carte.scroll_into_view_if_needed()

    # ── ouverture par la vignette (porte réelle), rotation, sauvegarde
    carte.locator(".tc-thumb").first.click()
    page.wait_for_selector(".iv-bar", timeout=10_000)
    depart = _img_decodee(page)
    assert depart["w"] > depart["h"], "l'image de départ doit être en paysage"

    page.locator(".iv-bar button[title='Pivoter à droite']").click()
    save = page.locator(".iv-bar button[title='Enregistrer la rotation']")
    assert save.is_enabled()
    save.click()
    apres = _img_versionnee(page)
    assert apres["h"] > apres["w"], (
        "la visionneuse doit montrer l'image redressée dès le clic (src=%s)" % apres["src"])
    assert save.is_disabled(), "l'angle est retombé à zéro : le bouton doit être grisé"

    # ── fermeture puis RÉOUVERTURE, SANS recharger la page : le cœur du test
    page.keyboard.press("Escape")
    # ⚠ Un <dialog> fermé garde ses enfants dans le DOM : compter `.iv-bar` ne dit rien.
    # C'est l'attribut `open` qui fait foi.
    assert _wait_until(lambda: page.locator("dialog[open]").count() == 0, timeout_ms=5_000), (
        "la visionneuse ne s'est pas fermée")
    carte.locator(".tc-thumb").first.click()
    page.wait_for_selector(".iv-bar", timeout=10_000)
    rouvert = _img_decodee(page)
    assert rouvert["h"] > rouvert["w"], (
        "la galerie rouverte montre l'ancienne image (%dx%d) : le cache mémoire n'a pas été "
        "défait — src=%s" % (rouvert["w"], rouvert["h"], rouvert["src"])
    )
    assert "&v=" in (rouvert["src"] or ""), (
        "l'URL doit porter le jeton de version, sinon rien ne distingue cette requête de la "
        "précédente pour le cache mémoire (src=%s)" % rouvert["src"]
    )
    page.keyboard.press("Escape")

    # ── la vignette de la card, elle aussi SANS rechargement
    # (on passe par le locator : `:has-text()` est une extension Playwright, pas un sélecteur CSS
    # valide pour `querySelector`.)
    vig = carte.locator(".tc-thumb img").first
    lire = "i => ({w: i.naturalWidth, h: i.naturalHeight, complete: i.complete, src: i.getAttribute('src')})"
    vignette = None
    fin = time.time() + 15
    while time.time() < fin:
        vignette = vig.evaluate(lire)
        if vignette["complete"] and vignette["w"] > 0 and "&v=" in (vignette["src"] or ""):
            break
        time.sleep(0.2)
    assert vignette and vignette["h"] > vignette["w"], (
        "la vignette de la card montre encore l'ancienne orientation (%r) — `onRotated` repeint "
        "les cards, mais sans jeton l'URL identique ressort du cache mémoire" % (vignette,)
    )

    assert console_errors == [], "Erreurs JS :\n%s" % console_errors
