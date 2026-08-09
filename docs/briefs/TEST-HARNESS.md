# Brief CC — [TEST-HARNESS] : socle de tests + `pytest` unique (back + front)

> **But (Fabien)** : une seule commande `pytest` en local lance à la fois les tests
> back (unitaires + invariants) et les tests front (pytest-playwright, headless).
> Premier chantier = la **batterie d'invariants** ; la vedette encode le bug de
> perte de données à l'import (dédup par contenu ignorant l'uid).
>
> **Discipline de deploy (rappel obligatoire)** : CC code → **rebuild local** →
> journal + handoff → **STOP**. Passe Cowork + GO Fabien **avant** tout
> commit/tag/push/Deploy. Ce lot ajoute des fichiers de test + modifie la CI :
> aucun commit tant que `pytest` n'est pas vert en local ET validé.

---

## 1. Arborescence à créer

```
dash_project/
├── pytest.ini                 # 1 seul `pytest` = back + front
├── requirements-dev.txt       # pytest + pytest-playwright (+ requirements.txt)
└── tests/
    ├── conftest.py            # fixtures : base temp (back) + live_server (front)
    ├── back/
    │   ├── test_invariants.py # LA batterie de garde-fous (flagship = round-trip)
    │   └── test_smoke_back.py # /api/version, / répond, création mémo basique
    └── front/
        └── test_smoke_front.py# pytest-playwright headless via live_server
```

Pas de `__init__.py` : on utilise `--import-mode=importlib` (voir `pytest.ini`).

---

## 2. `pytest.ini`

```ini
[pytest]
minversion = 8.0
testpaths = tests
python_files = test_*.py
addopts = -ra --import-mode=importlib
markers =
    unit: test unitaire pur, rapide, sans I/O réseau
    invariant: garde-fou non négociable (export v27, import non destructif, v1 importable, cascades sans orphelin, écriture guest sous /share/* uniquement)
    e2e: parcours navigateur headless (pytest-playwright, live_server)
```

Commandes :

- `pytest` → **tout** (back + front).
- `pytest -m "not e2e"` → back seul, rapide (= le job CI bloquant rapide).
- `pytest -m e2e` → front seul (= le job CI e2e).
- `pytest -m invariant` → uniquement les garde-fous.

---

## 3. `requirements-dev.txt`

```
-r requirements.txt
pytest==8.3.4
pytest-playwright==0.7.0
```

Installation locale :

```bash
pip install -r requirements-dev.txt
playwright install chromium   # navigateur headless pour les tests e2e
```

`requests` est déjà dans `requirements.txt` (2.32.3) → `live_server` peut l'importer
sans dépendance supplémentaire.

---

## 4. `tests/conftest.py`

Point-clé d'architecture (vérifié dans `app.py`) : `DB_PATH` est lu dans l'env **à
l'import** (l.89) et `UPLOAD_DIR`/`BACKUP_DIR`/`DERIVED_DIR` en sont dérivés (l.90-91,
106). `get_db` (l.390) et `init_db` (l.407) lisent le **global** `DB_PATH` au moment de
l'appel. → On importe `app` une fois, puis on réoriente `app.DB_PATH` + dossiers dérivés
vers un `tmp_path` **neuf par test** via `monkeypatch` (revert auto → jamais de fuite,
jamais la vraie base). `new_base()` peut être appelée plusieurs fois dans un même test
(indispensable au round-trip : base A d'export → base B vierge d'import).

```python
"""
Fixtures partagées — back (test_client sur base temp) + front (live_server headless).

SÛRETÉ : aucun test ne touche la vraie base (prod/dev). app.py lit DB_PATH dans l'env
à l'import (l.89) et en dérive UPLOAD_DIR/BACKUP_DIR/DERIVED_DIR (l.90-91, 106). On force
un DB_PATH temp AVANT le premier import de `app`, puis on réoriente vers un tmp_path frais
à chaque test (revert auto via monkeypatch).
"""
import os
import sys
import socket
import subprocess
import time

import pytest

# Racine du repo (parent de tests/) → pour `import app` et le cwd du live_server.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Filet : si `app` est importé avant toute fixture, il tape un scratch temp, jamais
# /app/data. La vraie base par test est posée par new_base().
os.environ.setdefault("DB_PATH", os.path.join(REPO_ROOT, ".pytest-scratch", "dashboard.db"))
os.environ.setdefault("TZ", "Europe/Paris")


# ------------------------------------------------------------------ BACK ----

@pytest.fixture
def app_module():
    """Le module `app` (importé une seule fois, caché par Python)."""
    import app  # import tardif : après le setdefault DB_PATH ci-dessus
    return app


@pytest.fixture
def new_base(app_module, monkeypatch, tmp_path_factory):
    """Fabrique : new_base() -> test_client Flask sur une base SQLite VIERGE.
    Appelable plusieurs fois (round-trip) ; le dernier appel est la base active.
    monkeypatch => revert auto en teardown (la vraie base n'est jamais touchée)."""
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
    Rend l'URL de base. Utilisé par les tests @pytest.mark.e2e (pytest-playwright)."""
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
```

---

## 5. `tests/back/test_invariants.py` — la batterie (flagship inclus)

Contrats confirmés dans `app.py` : `POST /api/projects {name}` → 201 `{id,...}` ;
`POST /api/memos {content, project_id, uid?}` → 201 (ou 200 si uid déjà présent) ;
`GET /api/export` → dict `{links, memos, categories, projects, ...}` ;
`POST /api/import` (même dict) → 200 ; `GET /api/version` → `{version, export:27}`.

```python
"""
Batterie d'INVARIANTS — garde-fous non négociables. Un rouge ici = pas de deploy.
Premier chantier TDD : ces tests encodent les règles qui ne doivent jamais casser.
"""
import pytest

pytestmark = pytest.mark.invariant


def _mk_project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _mk_memo(c, pid, content, uid=None):
    payload = {"content": content, "project_id": pid}
    if uid:
        payload["uid"] = uid
    r = c.post("/api/memos", json=payload)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _memos(c):
    # /api/export ne renvoie que les mémos non supprimés → parfait pour mesurer la perte.
    r = c.get("/api/export")
    assert r.status_code == 200, r.data
    return sorted(m.get("content", "") for m in r.get_json().get("memos", []))


# --- Format d'export figé v27 --------------------------------------------

def test_export_version_is_27(client):
    v = client.get("/api/version").get_json()
    assert v["export"] == 27, "Format d'export modifié sans bump de version majeure."


def test_export_has_stable_top_level_keys(client):
    exp = client.get("/api/export").get_json()
    for key in ("links", "memos", "categories", "projects"):
        assert key in exp, "Clé de haut niveau manquante dans l'export : %s" % key


# --- FLAGSHIP : l'import n'est JAMAIS destructif (round-trip sans perte) ---

def test_roundtrip_export_import_no_loss(new_base):
    """Export d'une base peuplée -> import dans une base VIERGE : aucun mémo perdu,
    aucun doublon. Encode directement le bug de perte de données à l'import."""
    a = new_base()
    pid = _mk_project(a, "Voyage Japon")
    _mk_memo(a, pid, "Reservation")       # doublon de contenu volontaire...
    _mk_memo(a, pid, "Reservation")       # ...uid serveur distinct -> DOIT survivre
    _mk_memo(a, pid, "Vol AF Tokyo")
    _mk_memo(a, pid, "Hotel Kyoto Sanjo")

    payload = a.get("/api/export").get_json()
    before = sorted(m["content"] for m in payload["memos"])
    assert before.count("Reservation") == 2

    b = new_base()                        # base vierge = le "fichier importé ailleurs"
    assert b.get("/api/export").get_json()["memos"] == []
    assert b.post("/api/import", json=payload).status_code == 200

    after = _memos(b)
    assert after == before, (
        "Round-trip export->import a perdu ou dupliqué des memos.\n"
        "avant=%r\napres=%r" % (before, after)
    )
    assert after.count("Reservation") == 2, (
        "Deux memos meme contenu / uid distinct : l'un a ete avale (regression "
        "du bug de dedup par contenu)."
    )


# --- Réimport idempotent (rejouer le même fichier n'ajoute rien) ----------

def test_reimport_same_file_is_idempotent(client):
    pid = _mk_project(client, "Idempotence")
    _mk_memo(client, pid, "A")
    _mk_memo(client, pid, "B")
    payload = client.get("/api/export").get_json()
    before = _memos(client)
    assert client.post("/api/import", json=payload).status_code == 200
    assert _memos(client) == before, "Reimport a l'identique a cree des doublons."


# --- v1 toujours importable (invariant 1) — squelette à compléter ---------

@pytest.mark.skip(reason="TODO CC : charger un fixture export v1 minimal et l'importer")
def test_v1_export_still_importable(client):
    import json, os
    p = os.path.join(os.path.dirname(__file__), "fixtures", "export_v1_min.json")
    with open(p, encoding="utf-8") as f:
        payload = json.load(f)
    assert client.post("/api/import", json=payload).status_code == 200
    assert len(_memos(client)) >= 1
```

> Les deux invariants encore ouverts (**cascades sans orphelin** : `DELETE /api/shares`
> purge `share_guests` ; **surface d'écriture guest** : toute écriture invité passe par
> `/share/*`) sont à ajouter par CC en rouge-vert dès qu'on attaque les lots concernés.
> Le fixture `export_v1_min.json` est à extraire d'un vrai vieux export.

---

## 6. `tests/back/test_smoke_back.py`

```python
import pytest

pytestmark = pytest.mark.unit


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.get_json()["export"] == 27


def test_create_memo_minimal(client):
    pid = client.post("/api/projects", json={"name": "Smoke"}).get_json()["id"]
    r = client.post("/api/memos", json={"content": "hello", "project_id": pid})
    assert r.status_code == 201, r.data
    assert r.get_json()["content"] == "hello"


def test_create_memo_requires_content_or_title(client):
    r = client.post("/api/memos", json={})
    assert r.status_code == 400
```

---

## 7. `tests/front/test_smoke_front.py` (pytest-playwright, headless)

```python
import pytest

pytestmark = pytest.mark.e2e


def test_api_version_reachable(live_server, page):
    resp = page.request.get(live_server + "/api/version")
    assert resp.ok
    assert resp.json()["export"] == 27


def test_root_page_renders(live_server, page):
    page.goto(live_server, wait_until="domcontentloaded")
    assert page.locator("body").count() == 1
    assert page.title() is not None
```

> Démarrage E2E minimal et robuste. CC enrichira avec un vrai parcours (ouvrir un
> dossier, créer un mémo, ouvrir la popin commentaires…) une fois le socle vert.

---

## 8. CI — rouge = pas de deploy (Fabien : « Oui, rouge = pas de deploy »)

### 8.1 `.github/workflows/ci.yml` — ajouter deux jobs de test

À ajouter après le job `build` existant (garder `py_compile` + check JS + docker build) :

```yaml
  tests-back:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Deps
        run: pip install -r requirements-dev.txt
      - name: Tests back (unit + invariants)
        run: pytest -m "not e2e"

  tests-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Deps
        run: pip install -r requirements-dev.txt
      - name: Navigateur headless
        run: playwright install --with-deps chromium
      - name: Tests e2e (front)
        run: pytest -m e2e
```

### 8.2 `.github/workflows/deploy.yml` — bloquer le deploy si rouge

Faire dépendre le job de déploiement d'un job de tests (mettre `needs: [tests]` sur
le job qui déploie, et ajouter en tête du workflow) :

```yaml
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-dev.txt
      - run: playwright install --with-deps chromium
      - run: pytest        # back + front ; un rouge stoppe le deploy
```

Ainsi un tag poussé sur une révision au rouge ne se déploie pas sur le Zimaboard.

---

## 9. Definition of Done du lot

1. Fichiers créés (§1–§7) ; `make install` (= deps dev + navigateur headless).
2. `pytest` (ou `make test`) **vert en local** (back + front) — c'est le rebuild/validation local.
3. CI mise à jour (§8) ; le deploy dépend des tests.
4. **Hook Stop révisé (§11)** : `handoff.json` passe à `ready` **seulement** si build OK **ET** `pytest -m "not e2e"` vert.
5. **`Makefile` (§12)** créé ; **hook git `pre-commit` (§13)** versionné dans `.githooks/`, exécutable, activé via `make hooks`.
6. Journal `.claude/session-log.md` + `handoff.json` mis à jour, puis **STOP**.
7. Commit/tag/push/Deploy **seulement après** passe Cowork + GO Fabien.

## 10. Doctrine TDD (rappel, hybride)

- Legacy sécurisé par la **batterie d'invariants** (pas de réécriture rétro-active).
- Tout **bugfix commence par un test rouge** reproduisant le bug, puis vert.
- Nouvelles features back : rouge → vert.
- Front : petit lot E2E-smoke, enrichi au fil des parcours réels.

---

## 11. Révision du hook Stop — « ready » = build **et** tests verts

Le hook actuel `.claude/hooks/post-stop-rebuild.sh` écrit `handoff.json` avec
`status: ready` **dès que `docker compose up -d --build` réussit**. Avec la suite de
tests, ça ne suffit plus : un build qui passe mais des tests rouges ne doit **pas**
déclencher ma passe ni ouvrir la voie au GO. On ajoute donc, après un build réussi, un
`pytest -m "not e2e"` (back + invariants — rapides, base temp, ne touchent **ni** le
conteneur **ni** la vraie base) qui **conditionne** le statut.

Trois statuts au lieu de deux : `ready` (build+tests OK), `tests_failed` (build OK,
tests rouges → **ne pas livrer**), `build_failed` (inchangé). L'e2e Playwright **reste
hors du hook** (lent, navigateur requis) — il tourne en CI et avant commit.

Deux modifications ciblées :

**(a)** Ajouter `requirements-dev.txt` et `tests` au hash de déclenchement (sinon un
changement de tests seul ne relance rien) :

```bash
NEW_HASH="$(find app.py requirements.txt requirements-dev.txt Dockerfile docker-compose.yml templates tests -type f \
  -exec shasum {} + 2>/dev/null | shasum | awk '{print $1}')"
```

**(b)** Remplacer le bloc « build réussi » par un build **puis** pytest gating. Le bloc
`if docker compose … then` devient :

```bash
  if docker compose up -d --build >> .claude/last_build.log 2>&1; then
    printf "%s" "'"$NEW_HASH"'" > .claude/.last_build_hash
    VER="$(grep -m1 -oE "\[V[0-9]+\.[0-9]+\.[0-9]+\]" REALISATION.md 2>/dev/null | head -n1 | tr -d "[]")"
    HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo n/a)"

    # --- NOUVEAU : garde-fou tests (back + invariants, hors e2e) ---
    # Préfère le python du venv (créé par `make install`) sinon python3 système.
    PYBIN="$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)"
    if ! "$PYBIN" -c "import pytest" >/dev/null 2>&1; then
      # deps dev absentes : on NE prétend PAS que c est vert
      cat > .claude/handoff.json <<EOF
{"status":"tests_skipped","at":"$(date -u +%FT%TZ)","version":"${VER:-?}","commit":"$HEAD","url":"http://localhost:8099/","note":"BUILD OK mais pytest indisponible (make install) - tests NON verifies"}
EOF
      printf -- "- %s [CC] ⚠ rebuild OK mais pytest indisponible — deps dev a installer (make install)\n" \
        "$(date +"%F %H:%M")" >> .claude/session-log.md
    else
      echo "[$(date)] $PYBIN -m pytest -m 'not e2e'..." >> .claude/last_build.log
      if "$PYBIN" -m pytest -m "not e2e" -q >> .claude/last_build.log 2>&1; then
        cat > .claude/handoff.json <<EOF
{"status":"ready","at":"$(date -u +%FT%TZ)","version":"${VER:-?}","commit":"$HEAD","url":"http://localhost:8099/","tests":"back+invariants verts","note":"rebuild local OK + tests verts - pret a tester"}
EOF
        printf -- "- %s [CC] ✅ rebuild + tests (back+invariants) VERTS — %s (%s) — pret a tester\n" \
          "$(date +"%F %H:%M")" "${VER:-?}" "$HEAD" >> .claude/session-log.md
      else
        cat > .claude/handoff.json <<EOF
{"status":"tests_failed","at":"$(date -u +%FT%TZ)","version":"${VER:-?}","commit":"$HEAD","url":"http://localhost:8099/","note":"BUILD OK mais pytest ROUGE - voir .claude/last_build.log - NE PAS livrer"}
EOF
        printf -- "- %s [CC] ⚠ rebuild OK mais TESTS ROUGES — voir .claude/last_build.log — NE PAS livrer\n" \
          "$(date +"%F %H:%M")" >> .claude/session-log.md
      fi
    fi
  else
    # … bloc build_failed inchangé …
```

> Le `pytest` du hook tourne sur l'hôte contre le repo (base temp via `conftest.py`),
> **pas** dans le conteneur — c'est voulu : feedback en quelques secondes. Si CC utilise
> un venv, adapter `python3` → le python du venv. Ma passe Cowork lira désormais
> `handoff.json` : `ready` = je valide ; `tests_failed`/`tests_skipped` = je renvoie à CC
> avant toute passe.

**Suites hors-repo à ajuster une fois le hook en place** (Fabien / Cowork) : la mémoire
`dash-cc-handoff-hook.md` et le `CLAUDE.md` du repo doivent redéfinir « STOP valide » =
« build OK **+** tests verts ».

---

## 12. `Makefile` — commandes centralisées

> ⚠️ **Indentation = TABULATIONS** (obligatoire dans un Makefile ; pas d'espaces).
>
> **Venv-aware** : `PY` pointe par défaut sur `.venv/bin/python`, donc `make test`
> tourne **sans activer le venv** (évite le `command not found: pytest`). `make install`
> crée le venv s'il manque. Pour utiliser un autre python : `make test PY=python3`.

```makefile
# Makefile — dashboard. `make` ou `make help` liste les cibles.
.DEFAULT_GOAL := help
VENV ?= .venv
PY ?= $(VENV)/bin/python

.PHONY: help install test test-back test-front test-inv build hooks

help:  ## Liste les cibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:  ## (interne) crée le venv s'il manque
	python3 -m venv $(VENV)

install: $(VENV)/bin/python  ## Crée le venv au besoin + deps de dev + navigateur headless
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m playwright install chromium

test:  ## Tous les tests (back + front)
	$(PY) -m pytest

test-back:  ## Back rapides (unit + invariants, sans e2e)
	$(PY) -m pytest -m "not e2e"

test-front:  ## Front (pytest-playwright, headless)
	$(PY) -m pytest -m e2e

test-inv:  ## Batterie d'invariants seule
	$(PY) -m pytest -m invariant

build:  ## Rebuild local (docker compose)
	docker compose up -d --build

hooks:  ## Active le hook git pre-commit versionné (.githooks/)
	git config core.hooksPath .githooks
	@echo "Hook pre-commit actif : les tests back tourneront avant chaque commit."
```

---

## 13. Hook git `pre-commit` — refuse le commit si les tests sont rouges

**Choix d'implémentation** : hook **versionné** dans `.githooks/` + `git config
core.hooksPath .githooks` (via `make hooks`), plutôt que le framework `pre-commit`
(pypi). Raison : zéro dépendance nouvelle, versionné avec le repo, activation en une
ligne — cohérent avec l'esprit « pas de build » du projet.

**Périmètre : la suite COMPLÈTE (back + front).** Le commit se fait sur la machine de
Fabien (M4), où `make test` tourne en ~6 s e2e comprise — donc on ne laisse **rien**
passer localement, back comme front. Le pre-commit tourne toujours là où l'on committe :
c'est le M4, jamais le Zimaboard. La CI reste le filet côté runner. *(Pour un pre-commit
rapide qui saute le navigateur : ajouter `-m "not e2e"` dans le script.)*

Pré-requis : `make venv` (ou `make install`) une fois — installe pytest, pytest-playwright
**et Chromium**, sans quoi les tests e2e du hook échoueront.

`.githooks/pre-commit` (à créer **exécutable** : `chmod +x .githooks/pre-commit`) :

```bash
#!/usr/bin/env bash
# Hook git pre-commit VERSIONNÉ : suite COMPLÈTE (back + front) avant tout commit.
# Tourne sur la machine qui committe (le M4). Activer une fois : `make hooks`.
# Contournement d'urgence : `git commit --no-verify`.
set -uo pipefail
# Préfère le pytest du venv (make venv) sinon celui du PATH.
PYTEST="$([ -x .venv/bin/pytest ] && echo .venv/bin/pytest || echo pytest)"
echo "→ pre-commit : $PYTEST (back + front)…"
if ! command -v "${PYTEST%% *}" >/dev/null 2>&1 && [ ! -x .venv/bin/pytest ]; then
  echo "⚠ pytest indisponible — lance 'make venv'. Commit refusé." >&2
  exit 1
fi
if "$PYTEST" -q; then
  echo "✅ suite complète verte — commit autorisé."
  exit 0
fi
echo "❌ tests ROUGES — commit refusé. Corrige, ou 'git commit --no-verify' en dernier recours." >&2
exit 1
```

> Belt-and-suspenders assumé : le hook **Stop** (§11) teste le back après chaque
> réalisation (boucle courte), le **pre-commit** re-teste **tout** au moment du commit
> (rare, après passe Cowork + GO) **sur le M4**, la **CI** teste tout côté runner et garde
> le deploy. Le Zimaboard ne lance jamais de tests. Quatre acteurs, une même règle.
