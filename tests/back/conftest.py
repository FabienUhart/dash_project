"""Fixtures propres aux tests back.

[DASH-API] Le limiteur d'abus de l'API v1 vit en mémoire de processus (compteurs par jeton et
par IP, à la minute). Dans la suite, tous les tests tapent depuis la même « IP » du test_client :
sans remise à zéro, les tentatives sans jeton des tests d'authentification s'additionneraient
d'un test à l'autre et finiraient par faire 429 un test qui n'a rien demandé. Chaque test repart
donc avec des compteurs vides — ce que fait aussi un redémarrage du serveur.
"""
import pytest


@pytest.fixture(autouse=True)
def _api_rate_reset(app_module):
    reset = getattr(app_module, "_api_rate_reset", None)
    if reset:
        reset()
    yield
    if reset:
        reset()
