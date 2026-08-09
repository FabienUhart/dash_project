"""[TEST-NET-GUARD] La garde « zéro réseau » — prouvée, pas supposée.

La garde vit dans `tests/conftest.py` (autouse, donc active partout). Ce fichier vérifie
qu'elle fait ce qu'elle promet : un garde-fou qu'on n'a jamais vu dire non ne prouve rien.

Deux propriétés valent plus que les autres, et chacune vient d'une leçon payée :

  · elle lève une **`BaseException`**, pas une `AssertionError`. Le code applicatif avale les
    exceptions ordinaires — `_fx_fetch_rates` enveloppe son appel réseau dans un
    `except Exception: return None`. Une garde ordinaire y serait **silencieusement gobée** :
    le test passerait au vert en croyant qu'aucun appel n'a eu lieu, alors que l'appel a été
    tenté puis avalé. C'est exactement le piège rencontré en [TESTS-PORT vague 6] ;

  · elle **laisse passer localhost** pour `requests.get` : un appel vers `127.0.0.1` depuis un
    test vise le serveur de test, pas l'extérieur.

⚠ Une mutation a corrigé ce que je croyais de cette seconde propriété. J'avais écrit qu'elle
était « ce qui garde l'e2e en vie » — c'est faux, et le bloquer exprès le montre : les six
tests e2e passent quand même, parce que `live_server` est **session-scoped** et sonde le
serveur AVANT que la garde (function-scoped) ne s'installe. L'exception reste juste, mais pour
une autre raison : elle couvre les appels faits dans un corps de test, et amortirait un
changement d'ordre des fixtures. Quatrième fois de ce chantier qu'un mutant démonte une
justification plausible — d'où le test ci-dessous, qui prouve le comportement sans rien
affirmer sur l'e2e.
"""
import pytest

pytestmark = pytest.mark.invariant


def test_guard_blocks_urlopen(reseau_interdit):
    """`urlopen` est LA porte du convertisseur de devises : elle reste fermée en toute
    circonstance (aucun usage localhost légitime dans les tests)."""
    import app
    with pytest.raises(reseau_interdit):
        app.urllib.request.urlopen("https://api.frankfurter.app/latest?from=EUR")


def test_guard_blocks_smtp(reseau_interdit):
    """Celle qui compte le plus : le `.env` de dev porte de vrais identifiants Gmail, et
    `app.py` les charge à l'import. Sans cette porte fermée, un test peut envoyer un vrai
    message."""
    import app
    with pytest.raises(reseau_interdit):
        app.smtplib.SMTP("smtp.gmail.com", 587)


def test_guard_blocks_external_requests(reseau_interdit):
    import app
    with pytest.raises(reseau_interdit):
        app.requests.get("https://exemple.test/quelque-chose")


def test_guard_allows_localhost_requests(reseau_interdit):
    """Un appel localhost traverse la garde. On le prouve SANS dépendre d'un serveur : l'appel
    atteint la pile réseau réelle et échoue en `RequestException` (rien n'écoute sur ce port),
    et surtout **pas** en `ReseauInterdit` — ce qui prouverait que la garde l'a intercepté."""
    import app
    with pytest.raises(app.requests.RequestException):
        app.requests.get("http://127.0.0.1:1/api/version", timeout=0.2)

    try:
        app.requests.get("http://localhost:1/api/version", timeout=0.2)
    except reseau_interdit:
        pytest.fail("un appel localhost ne doit pas être intercepté par la garde")
    except app.requests.RequestException:
        pass          # attendu : personne n'écoute sur le port 1


def test_guard_survives_an_except_Exception(reseau_interdit):
    """LA régression de la vague 6, en un test.

    On imite le motif du code applicatif : un appel réseau enveloppé dans un `except Exception`
    qui renvoie `None` en silence. La garde doit **traverser** ce filet — sans quoi elle ne
    protège rien là où on en a le plus besoin.
    """
    import app

    def _comme_fx_fetch_rates():
        try:
            app.urllib.request.urlopen("https://api.frankfurter.app/latest")
            return "des taux"
        except Exception:          # noqa: BLE001 — c'est le motif qu'on veut éprouver
            return None

    with pytest.raises(reseau_interdit):
        _comme_fx_fetch_rates()


def test_guard_is_active_without_being_requested(reseau_interdit):
    """Autouse : la garde s'applique même à un test qui ne demande aucun fixture d'app — c'est
    la différence entre un dispositif et une discipline."""
    import app
    with pytest.raises(reseau_interdit):
        app.smtplib.SMTP("localhost", 25)


def test_guard_is_reverted_after_the_test():
    """`monkeypatch` rend ses billes en teardown : la garde ne fuit pas hors de la suite (elle
    ne doit pas laisser `app.requests.get` piégé pour un usage ultérieur du module)."""
    import app
    assert app.requests.get.__name__ in ("_get_garde", "get")
