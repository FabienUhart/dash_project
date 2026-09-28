"""Garde « zéro réseau » côté NAVIGATEUR — le pendant e2e de celle de `tests/conftest.py`.

La garde du processus pytest ferme `requests`, `urlopen` et SMTP. Elle ne pouvait rien contre
les appels sortants faits par la **page** : la page propriétaire interroge open-meteo au
chargement, et les favicons retombent sur icons.duckduckgo.com. Nos e2e dépendaient donc
silencieusement d'internet.

Ça s'est vu au pire endroit : sur un runner GitHub, sans accès sortant, l'appel météo pend
jusqu'à `net::ERR_TIMED_OUT` — donc `wait_for_load_state("networkidle")` n'aboutit jamais dans
les 30 s, et quatre tests de la page propriétaire tombaient en cascade. En local ils étaient
verts pour une raison qui n'a rien à voir avec le code : la machine avait internet.

On coupe donc le navigateur du monde extérieur. Les appels externes échouent **immédiatement**
au lieu de pendre : le réseau retombe au repos tout de suite, sur n'importe quelle machine, et
la suite cesse de dépendre d'une connexion.
"""
import pytest

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """[E2E-SW-GUARD] Service worker BLOQUÉ dans les e2e.

    À la première visite d'un contexte neuf — donc à CHAQUE test — la page enregistre `/sw.js` au
    `load` ; le SW fait `clients.claim()`, la page reçoit `controllerchange` et se recharge
    (`location.reload()`, index.html, bloc [OFFLINE]). Ce rechargement tombe n'importe quand après
    le chargement : sur un runner lent il détruisait le contexte JS au milieu d'un `evaluate`
    (« Execution context was destroyed » — test_rotate_and_save_a_photo le 25/09, test_link_refs
    le 28/09, deploy bloqué). On teste l'app, pas le SW : il a son test dédié
    (`test_service_worker.py`), dans un contexte qui l'autorise explicitement.

    Bonus : Playwright ne voit pas passer les requêtes émises PAR un service worker — la garde
    « zéro réseau » ci-dessous n'est étanche que SW bloqué.

    Chaîné : un fichier qui surcharge encore `browser_context_args` (fuseau de
    test_search_dates) part de ce dictionnaire, donc hérite du blocage.
    """
    return {**browser_context_args, "service_workers": "block"}


# Ce que la page a le droit d'atteindre : elle-même, et rien d'autre.
_SCHEMES_LOCAUX = ("data:", "blob:", "about:", "chrome-error:")


def _est_local(url):
    return (url.startswith("http://127.0.0.1")
            or url.startswith("http://localhost")
            or url.startswith(_SCHEMES_LOCAUX))


@pytest.fixture(autouse=True)
def navigateur_hors_ligne(page):
    """Coupe tout appel sortant de la page, et retient ce qui a été bloqué.

    La liste est rendue au test : `console_errors` s'en sert pour distinguer une dégradation
    ATTENDUE (la météo qui n'arrive pas parce qu'on l'a coupée) d'une vraie erreur JS.
    """
    bloques = []

    def _routeur(route):
        url = route.request.url
        if _est_local(url):
            route.continue_()
        else:
            bloques.append(url)
            route.abort()

    page.route("**/*", _routeur)
    return bloques


# Signatures de la dégradation hors ligne — écartées UNIQUEMENT si un appel externe a
# effectivement été bloqué. Volontairement littérales : une liste large masquerait de vrais bugs.
_DEGRADATION_HORS_LIGNE = (
    "Failed to load resource: net::ERR_FAILED",
    "weather failed",
)


@pytest.fixture
def console_errors(page, navigateur_hors_ligne):
    """Collecte les erreurs JS de la page. Une page owner qui meurt au chargement laisse ici
    une `SyntaxError`/`ReferenceError` — le symptôme exact d'une collision de `const` entre le
    partial et la page, invisible pour une vérification de syntaxe fichier par fichier.

    ⚠ Deux messages sont écartés, et seulement ceux-là : ce sont les conséquences ATTENDUES
    d'avoir coupé le navigateur du réseau (voir `conftest.py` du dossier). La page appelle
    open-meteo au chargement ; privée de sortie, elle échoue et le dit — c'est précisément la
    dégradation gracieuse qu'on veut, pas un défaut. Le filtre est **conditionné** à un blocage
    réellement survenu, et reste volontairement étroit : toute autre erreur, y compris un autre
    « Failed to fetch », continue de faire rougir.
    """
    errors = []

    def _garder(txt):
        if navigateur_hors_ligne and any(sig in txt for sig in _DEGRADATION_HORS_LIGNE):
            return
        errors.append(txt)

    page.on("console", lambda m: _garder(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: _garder(str(e)))
    return errors
