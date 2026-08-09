"""
Fixtures partagées — back (test_client sur base temp) + front (live_server headless).

SÛRETÉ : aucun test ne touche la vraie base (prod/dev). `app.py` lit `DB_PATH` dans l'env
à l'import et en dérive `UPLOAD_DIR`/`BACKUP_DIR`/`DERIVED_DIR`. On force un `DB_PATH` temp
AVANT le premier import de `app`, puis on réoriente vers un `tmp_path` frais à chaque test
(revert auto via monkeypatch).

SÛRETÉ (2) : aucun test ne touche le RÉSEAU ni SMTP — voir la garde autouse plus bas. Elle
est ici, et pas dans un fichier de tests, parce qu'un dispositif qui ne protège qu'un fichier
n'est pas un dispositif : c'est de la chance.
"""
import os
import socket
import subprocess
import sys
import time

import pytest

# Racine du repo (parent de tests/) → pour `import app` et le cwd du live_server.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Filet : si `app` est importé avant toute fixture, il tape un scratch temp, jamais la
# vraie base. La base par test est posée par `new_base()`.
os.environ.setdefault("DB_PATH", os.path.join(REPO_ROOT, ".pytest-scratch", "dashboard.db"))
os.environ.setdefault("TZ", "Europe/Paris")


# ------------------------------------------------------- GARDE ZÉRO-RÉSEAU ----
# [TEST-NET-GUARD] Motif, découvert en [TESTS-PORT vague 6] : `app.py` appelle `load_dotenv()`
# à l'import, et un `.env` de dev porte de VRAIS identifiants SMTP. La suite tournait donc avec
# un SMTP fonctionnel, et n'a évité d'envoyer un vrai message que grâce à une garde locale à un
# seul fichier. On en fait un dispositif global.


class ReseauInterdit(BaseException):
    """Hérite de `BaseException`, PAS d'`Exception`, et c'est tout l'intérêt.

    Le code applicatif avale les exceptions ordinaires — `_fx_fetch_rates` enveloppe son appel
    réseau dans un `except Exception: return None`. Une garde levant `AssertionError` y serait
    silencieusement gobée : le test passerait au vert en croyant qu'aucun appel n'a eu lieu,
    alors que l'appel a bien été tenté puis avalé. Une `BaseException` traverse ces `except`.
    """


def _est_local(url):
    u = str(url)
    return u.startswith("http://127.0.0.1") or u.startswith("http://localhost")


@pytest.fixture(autouse=True)
def _interdire_le_reseau(monkeypatch):
    """Ferme les trois portes de sortie de l'app, pour TOUS les tests.

    `requests.get` garde une exception pour **localhost** : un appel vers `127.0.0.1` depuis un
    test vise le serveur de test, pas l'extérieur — le bloquer n'apporterait rien et casserait
    tout usage légitime.

    ⚠ Mesuré, pas supposé : cette exception n'est PAS ce qui garde l'e2e en vie. `live_server`
    est **session-scoped**, donc sa boucle de sonde tourne AVANT que cette garde (function-scoped)
    ne s'installe — vérifié en bloquant localhost exprès : les six tests e2e passent quand même.
    L'exception reste néanmoins juste : elle couvre les appels faits DANS un corps de test, et
    le jour où l'ordre des fixtures changerait, elle éviterait une panne franche (`live_server`
    rattrape `RequestException`, qu'une `BaseException` traverserait sans être amortie).

    `urlopen` et `smtplib.SMTP` sont bloqués sans exception : rien de légitime ne les emprunte
    dans les tests, et `urlopen` est précisément la porte du convertisseur de devises.
    """
    import app

    vrai_get = app.requests.get

    def _get_garde(url, *a, **k):
        if _est_local(url):
            return vrai_get(url, *a, **k)      # sonde live_server : autorisée
        raise ReseauInterdit("réseau interdit dans les tests : %s" % url)

    def _boom(*a, **k):
        cible = a[0] if a else ""
        raise ReseauInterdit("réseau/SMTP interdit dans les tests : %s" % (cible,))

    monkeypatch.setattr(app.requests, "get", _get_garde, raising=False)
    monkeypatch.setattr(app.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(app.smtplib, "SMTP", _boom)


@pytest.fixture
def reseau_interdit():
    """L'exception de la garde, pour les tests qui l'attendent explicitement."""
    return ReseauInterdit


# ------------------------------------------------------------------ BACK ----

@pytest.fixture
def app_module():
    """Le module `app` (importé une seule fois, caché par Python)."""
    import app  # import tardif : après le setdefault DB_PATH ci-dessus
    return app


@pytest.fixture
def new_base(app_module, monkeypatch, tmp_path_factory):
    """Fabrique : `new_base()` -> test_client Flask sur une base SQLite VIERGE.

    Appelable plusieurs fois dans un même test — c'est indispensable au round-trip, qui a
    besoin d'une base A (celle qu'on exporte) et d'une base B vierge (celle où l'on importe).
    Le dernier appel est la base active ; `monkeypatch` reverte tout en teardown, donc la
    vraie base n'est jamais touchée, même si un test échoue en cours de route.
    """
    app = app_module

    def _factory():
        d = tmp_path_factory.mktemp("base")
        monkeypatch.setattr(app, "DB_PATH", str(d / "dashboard.db"))
        monkeypatch.setattr(app, "UPLOAD_DIR", str(d / "uploads"))
        monkeypatch.setattr(app, "BACKUP_DIR", str(d / "backups"))
        monkeypatch.setattr(app, "DERIVED_DIR", str(d / "uploads" / "derived"))
        app.init_db()
        app.app.config.update(TESTING=True)
        return app.app.test_client()

    return _factory


@pytest.fixture
def client(new_base):
    """Client de test sur une base temp neuve (cas courant : une seule base)."""
    return new_base()


# ------------------------------------------------------------------ FRONT ---

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Lance l'app Flask réelle en sous-process (base temp dédiée, port libre).

    Rend l'URL de base. Utilisé par les tests `@pytest.mark.e2e` (pytest-playwright).
    """
    import requests  # local : n'impose rien aux tests back purs

    port = _free_port()
    data_dir = tmp_path_factory.mktemp("e2e_data")
    env = dict(os.environ)
    env["DB_PATH"] = str(data_dir / "dashboard.db")
    env["TZ"] = "Europe/Paris"

    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import app; app.init_db(); "
         "app.app.run(host='127.0.0.1', port=%d, use_reloader=False)" % port],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(60):
            if proc.poll() is not None:  # le process est mort au démarrage
                out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
                raise RuntimeError("live_server arrêté au démarrage :\n" + out)
            try:
                if requests.get(base + "/api/version", timeout=0.5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("live_server n'a pas répondu sur /api/version à temps")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
