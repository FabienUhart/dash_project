# [TEST-HARNESS] Raccourcis de test. Une commande courte pour chaque intention.
#
# `pytest` est cherché d'abord dans le venv du projet (.venv/, gitignoré, créé par
# `make venv`), sinon dans le PATH — c'est ce qui permet aux mêmes cibles de servir en
# local ET en CI, où les dépendances sont installées à même le runner.

PYTEST := $(shell [ -x .venv/bin/pytest ] && echo .venv/bin/pytest || echo pytest)

.PHONY: test test-back test-front test-invariants venv help

help:            ## Liste les cibles disponibles
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  make %-16s %s\n", $$1, $$2}'

test:            ## Toute la suite (back + front)
	$(PYTEST)

test-back:       ## Back seul — rapide, sans navigateur
	$(PYTEST) -m "not e2e"

test-front:      ## Front seul — parcours navigateur headless
	$(PYTEST) -m e2e

test-invariants: ## Les garde-fous seuls (un rouge ici = pas de deploy)
	$(PYTEST) -m invariant

venv:            ## Crée .venv et installe les dépendances de dev + Chromium
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/python -m playwright install chromium
