"""
Parcours navigateur (headless).

Ce que le back ne peut pas dire : la page se rend-elle vraiment, le JS démarre-t-il, un
formulaire aboutit-il jusqu'en base ? Un `node --check` valide la syntaxe mais laisse passer
une `ReferenceError` qui tue la page au chargement — c'est précisément ce que ces tests
attrapent. D'où l'assertion « aucune erreur console » sur chaque parcours.
"""
import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
def console_errors(page):
    """Collecte les erreurs JS de la page. Une page owner qui meurt au chargement laisse ici
    une `SyntaxError`/`ReferenceError` — le symptôme exact d'une collision de `const` entre le
    partial et la page, invisible pour une vérification de syntaxe fichier par fichier."""
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return errors


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
