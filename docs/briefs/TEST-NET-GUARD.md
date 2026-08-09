# Brief CC — [TEST-NET-GUARD] : garde « zéro réseau » globale (hissée dans conftest)

> Suite directe de [TESTS-PORT vague 6], qui a montré que la suite tournait avec un **vrai SMTP
> Gmail** (`.env` + `load_dotenv`) et n'a évité d'envoyer un vrai mail que grâce à une garde
> **locale à un seul fichier**. On en fait un **dispositif global** : aucun test, où qu'il soit,
> ne doit pouvoir toucher le réseau ou SMTP.
>
> **Discipline** : infra de test uniquement (`tests/conftest.py` + retrait du doublon local),
> **aucun changement applicatif**. `make test` **entièrement vert, e2e compris** → journal +
> handoff → STOP. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 1. Le but

Monter la garde autouse de `tests/back/test_owner_utils.py` dans **`tests/conftest.py`** pour
qu'elle couvre **toute** la suite. Deux raffinements, appris à la dure en vague 6, sont
**obligatoires** :

### (a) Lever une `BaseException`, pas une `AssertionError`

Le code applicatif avale les exceptions ordinaires : `_fx_fetch_rates` enveloppe tout dans
`except Exception`. Une garde qui lève `AssertionError`/`Exception` serait donc **silencieusement
gobée** dans les fonctions mêmes qu'on veut protéger. La garde doit lever une **sous-classe de
`BaseException`** (que `except Exception` ne rattrape pas) :

```python
class _ReseauInterdit(BaseException):
    pass
```

> **À vérifier** : que pytest **rapporte bien un échec de test** quand un `_ReseauInterdit`
> remonte (une sous-classe custom de `BaseException` est reportée en erreur/échec — mais confirme-le
> par un test qui l'attend, cf. §3).

### (b) Autoriser `localhost` — sinon on casse `live_server`

Le fixture `live_server` (e2e) **sonde le serveur via `requests.get("http://127.0.0.1:…/api/version")`**
dans le processus de test. Une garde qui bloque tout `requests.get` **casserait l'e2e**. Donc :

- `app.requests.get` → **laisser passer** si l'URL vise `127.0.0.1` / `localhost`, **sinon** lever.
- `app.urllib.request.urlopen` → **toujours** lever (rien de légitime ne l'utilise vers localhost
  dans les tests — et c'est LA porte du FX, `_fx_fetch_rates`).
- `app.smtplib.SMTP` → **toujours** lever.

```python
import pytest

class _ReseauInterdit(BaseException):
    pass

@pytest.fixture(autouse=True)
def _interdire_le_reseau(monkeypatch):
    import app
    _vrai_get = app.requests.get

    def _get_garde(url, *a, **k):
        u = str(url)
        if u.startswith("http://127.0.0.1") or u.startswith("http://localhost"):
            return _vrai_get(url, *a, **k)      # sonde live_server autorisée
        raise _ReseauInterdit("réseau interdit dans les tests : " + u)

    def _boom(*a, **k):
        raise _ReseauInterdit("réseau/SMTP interdit dans les tests")

    monkeypatch.setattr(app.requests, "get", _get_garde, raising=False)
    monkeypatch.setattr(app.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(app.smtplib, "SMTP", _boom)
```

> Vérifie les **chemins d'attributs réels** (`app.requests`, `app.urllib.request`, `app.smtplib`
> sont importés au niveau module d'`app.py` — la vague 6 le confirme). Si `live_server` fait aussi
> des `urlopen` localhost (peu probable, il utilise `requests`), élargis l'exception localhost à
> `urlopen` de la même façon plutôt que de tout bloquer.

## 2. Retirer le doublon

Une fois la garde dans `conftest.py`, **retirer** la garde autouse locale de
`tests/back/test_owner_utils.py` (elle ferait double emploi). Garder en revanche les
**compteurs/assertions FX explicites** de ce fichier (le mutant de la vague 6 a montré qu'on ne
peut pas se reposer sur l'exception seule dans `_fx_fetch_rates`).

## 3. Prouver la garde (dans `tests/back/`)

Quelques tests qui **prouvent le dispositif**, pas juste sa présence :

1. `test_guard_blocks_urlopen` — `app.urllib.request.urlopen("https://exemple.test")` lève.
2. `test_guard_blocks_smtp` — `app.smtplib.SMTP("smtp.gmail.com")` lève.
3. `test_guard_blocks_external_requests` — `app.requests.get("https://exemple.test")` lève.
4. `test_guard_allows_localhost_requests` — un `app.requests.get("http://127.0.0.1:…")` **n'est
   pas** bloqué par la garde (le prouver sans dépendre d'un serveur : la garde doit tenter le
   vrai appel → une `ConnectionError`/timeout, PAS un `_ReseauInterdit`). C'est ce qui garantit
   que `live_server` survit.
5. `test_guard_survives_except_Exception` — appeler dans un `try/except Exception` un stub qui fait
   `app.smtplib.SMTP(...)` : l'`except Exception` **ne doit pas** l'avaler (le `_ReseauInterdit`
   traverse). C'est la régression exacte de la vague 6.

## 4. Le vrai risque du lot

Le seul danger réel, c'est de **casser l'e2e** : si la garde bloque la sonde `requests.get`
localhost de `live_server`, tous les tests `-m e2e` tombent. **`make test` doit être vert e2e
compris** — c'est le critère d'acceptation n°1. Lance-le explicitement et confirme au journal.

## 5. Definition of Done

1. Garde dans `tests/conftest.py` (BaseException + exception localhost), doublon retiré de
   `test_owner_utils.py`.
2. `make test` **entièrement vert (unit + invariant + e2e)** — l'e2e est le juge de paix.
3. Tests §3 présents et verts (dont « survit à `except Exception` » et « localhost autorisé »).
4. `git status` : seul `tests/` bouge.
5. Journal + handoff, **STOP**. Commit `tests/conftest.py` + `tests/back/test_owner_utils.py` +
   `tests/back/test_<garde>.py` (ou dans un fichier dédié) + `REALISATION.md` +
   `docs/briefs/TEST-NET-GUARD.md` après passe Cowork + GO. Pas de tag ni de Deploy.
