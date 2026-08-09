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
    page.goto(live_server + path, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)   # la sidebar est peinte = le JS a tourné


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
        page.locator(".cat-item", has_text=label).first.click()
        page.wait_for_timeout(300)
        assert page.locator("body").count() == 1
    assert console_errors == [], "Erreurs JS pendant la navigation :\n%s" % console_errors


# --- Parcours 3 : créer un mémo par l'UI, et le retrouver en base ----------

def test_create_memo_through_the_ui(live_server, page, console_errors):
    """Le parcours qui compte vraiment : on tape dans le champ de capture rapide, et le mémo
    doit exister côté serveur. Bout en bout — formulaire, requête, persistance.

    ⚠ On reste sur la vue d'accueil : passer en vue « Mémos » masque la colonne latérale
    (`#memo-panel` → `display: none`), le board central prenant le relais. Le champ existe
    alors toujours dans le DOM mais n'est plus atteignable — vérifié, pas supposé."""
    _boot(page, live_server)

    quick = page.locator("#memo-quick")
    assert quick.is_visible(), "Le champ de capture rapide n'est pas visible sur l'accueil."
    quick.fill("Mémo créé par le test e2e")
    quick.press("Enter")
    page.wait_for_timeout(800)

    memos = page.request.get(live_server + "/api/memos").json()
    rows = memos if isinstance(memos, list) else memos.get("memos", [])
    contents = [m.get("content", "") + m.get("title", "") for m in rows]
    assert any("Mémo créé par le test e2e" in c for c in contents), (
        "Le mémo saisi dans l'UI n'est pas arrivé en base."
    )
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
    page.wait_for_timeout(1200)
    assert "Visible par l'invité" in page.content(), "La page de partage n'affiche pas son mémo."
    assert console_errors == [], "Erreurs JS sur la page invitée :\n%s" % console_errors
