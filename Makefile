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

.PHONY: help install venv test test-back test-front test-inv test-invariants build hooks

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

build:  ## Rebuild local (docker compose)
	docker compose up -d --build

hooks:  ## Active le hook git pre-commit versionné (.githooks/)
	git config core.hooksPath .githooks
	@echo "Hook pre-commit actif : la suite complète tournera avant chaque commit."
