# Makefile — dashboard. `make` ou `make help` liste les cibles.
#
# ⚠️ Indentation = TABULATIONS (obligatoire dans un Makefile).
#
# Venv-aware : `PY` vise le python du venv, donc `make test` tourne SANS activer le venv
# (fini le `command not found: pytest`). Repli sur `python3` quand le venv n'existe pas
# encore — sinon la moindre cible échouerait avant même `make install`, et en CI, où les
# dépendances sont posées à même le runner. Autre python : `make test PY=python3`.
.DEFAULT_GOAL := help
VENV ?= .venv
PY ?= $(shell [ -x $(VENV)/bin/python ] && echo $(VENV)/bin/python || echo python3)

.PHONY: help install venv test test-back test-front test-inv test-invariants test-cov build hooks

help:  ## Liste les cibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:  ## (interne) crée le venv s'il manque
	python3 -m venv $(VENV)

install: $(VENV)/bin/python  ## Crée le venv au besoin + deps de dev + navigateur headless
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m playwright install chromium

venv: install  ## Alias historique de `install`

test:  ## Tous les tests (back + front)
	$(PY) -m pytest

test-back:  ## Back rapides (unit + invariants, sans e2e)
	$(PY) -m pytest -m "not e2e"

test-front:  ## Front (pytest-playwright, headless)
	$(PY) -m pytest -m e2e

test-inv:  ## Batterie d'invariants seule
	$(PY) -m pytest -m invariant

test-invariants: test-inv  ## Alias verbeux de `test-inv`

# Couverture mesurée sur le BACK SEUL, et c'est volontaire : les tests back importent `app`
# dans le processus pytest, donc chaque ligne exécutée est vue. Les e2e, eux, tapent l'app via
# `live_server` — un SOUS-PROCESSUS que pytest-cov ne capte pas sans instrumentation dédiée.
# Les inclure donnerait un chiffre faussement bas (tout ce que le navigateur exerce compterait
# comme non couvert), et un mauvais chiffre oriente plus mal qu'aucun chiffre.
# Pas de `--cov-fail-under` : on mesure d'abord (décision Fabien), on fixera un plancher quand
# la suite aura mûri.
test-cov:  ## Couverture back (term-missing) + rapport HTML dans htmlcov/
	$(PY) -m pytest -m "not e2e" --cov=app --cov-report=term-missing --cov-report=html
	@echo "Rapport HTML : ouvre htmlcov/index.html"

build:  ## Rebuild local (docker compose)
	docker compose up -d --build

hooks:  ## Active le hook git pre-commit versionné (.githooks/)
	git config core.hooksPath .githooks
	@echo "Hook pre-commit actif : la suite complète tournera avant chaque commit."
