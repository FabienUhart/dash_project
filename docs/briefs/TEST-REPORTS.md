# Brief CC — [TEST-REPORTS] : couverture en local + JUnit en CI

> **But (Fabien)** : voir **où** manque la couverture sur `app.py` (pour prioriser les
> prochains tests), et obtenir un **résumé propre des tests en CI**. Pas de seuil bloquant
> pour l'instant — on mesure d'abord, on décidera d'un plancher plus tard.
>
> **Discipline** : test/infra/doc uniquement, **aucun changement applicatif**. CC code →
> `make test` + `make test-cov` verts en local → journal + handoff → **STOP**. Passe
> Cowork + GO Fabien avant commit. Pas de tag ni de Deploy (rien ne change côté prod).
>
> **Ordre** : pousser d'abord **V27.38.232** (il porte le correctif e2e qui remet `main`
> au vert), *puis* faire ce lot par-dessus, pour ne pas mélanger les deux dans l'arbre.

---

## 1. Dépendance de dev

`requirements-dev.txt` — ajouter **`pytest-cov`** (vérifie la version courante compatible
pytest 8, ex. `pytest-cov==5.0.0`, et épingle-la comme les autres) :

```
-r requirements.txt
pytest==8.3.4
pytest-playwright==0.7.0
pytest-cov==5.0.0
```

Le **JUnit XML est intégré à pytest** (`--junitxml=…`) : aucune dépendance à ajouter pour ça.

---

## 2. Makefile — cible `test-cov`

À ajouter (mêmes conventions que l'existant : **tabulations**, `$(PY)` venv-aware) :

```makefile
test-cov:  ## Couverture back (term-missing) + rapport HTML dans htmlcov/
	$(PY) -m pytest -m "not e2e" --cov=app --cov-report=term-missing --cov-report=html
	@echo "Rapport HTML : ouvre htmlcov/index.html"
```

Et l'ajouter à la liste `.PHONY`.

> **Pourquoi la couverture est mesurée sur le back seul (`-m "not e2e"`)** : les tests back
> importent `app` **dans le processus pytest** → `pytest-cov` voit chaque ligne exécutée.
> Les tests e2e, eux, tapent l'app via `live_server`, un **sous-processus séparé** que
> `pytest-cov` ne capte pas sans instrumentation dédiée (`COVERAGE_PROCESS_START`…). Les
> inclure donnerait un chiffre **faussement bas** (tout le code exercé par le navigateur
> compterait comme non couvert). On mesure donc ce qu'on mesure honnêtement : la couverture
> par les tests back. (Instrumenter le sous-processus est possible, mais hors de ce lot.)

`--cov=app` cible `app.py`. Le JS des templates n'est pas mesuré par `pytest-cov` (c'est le
rôle des tests e2e « zéro erreur console », pas de la couverture Python).

---

## 3. `.gitignore`

Ajouter les artefacts de couverture (jetables, jamais versionnés) :

```
htmlcov/
.coverage
```

---

## 4. CI — JUnit XML + artefact téléchargeable

Dans `.github/workflows/ci.yml`, faire produire à chaque job de test son rapport JUnit et
l'uploader. `if: always()` est **essentiel** : on veut le rapport **surtout quand c'est
rouge**, pour voir ce qui a cassé.

**Job `tests-back`** — remplacer l'étape de test par :

```yaml
      - name: Tests back (unit + invariants)
        run: pytest -m "not e2e" --junitxml=junit-back.xml
      - name: Rapport JUnit back (artefact)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-back
          path: junit-back.xml
```

**Job `tests-e2e`** — de même :

```yaml
      - name: Tests e2e (front)
        run: pytest -m e2e --junitxml=junit-e2e.xml
      - name: Rapport JUnit e2e (artefact)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-e2e
          path: junit-e2e.xml
```

> **Optionnel, pour plus tard** (pas dans ce lot) : une action comme
> `EnricoMi/publish-unit-test-result-action` lit ces XML et affiche un **résumé inline**
> dans l'onglet Checks + annote les lignes en échec sur les PR. À ajouter si le simple
> artefact ne suffit pas. On ne touche pas `deploy.yml` : son job `tests` est un barrage,
> pas un tableau de bord.

---

## 5. Pas de seuil bloquant (décision Fabien)

**Aucun `--cov-fail-under`** pour l'instant. Sur un `app.py` largement legacy, un gate
« échoue sous X % » bloquerait tout de suite sans rien apprendre. On mesure d'abord ; quand
la suite aura mûri, on fixera un plancher **et on interdira de le faire baisser** — mais
c'est une décision séparée, pas ce lot.

---

## 6. Definition of Done

1. `pytest-cov` dans `requirements-dev.txt` ; `make install` le pose.
2. `make test-cov` **vert en local** : affiche le `term-missing` (lignes non couvertes) **et**
   écrit `htmlcov/index.html` navigable.
3. `htmlcov/` + `.coverage` au `.gitignore` (jamais commités).
4. CI : les deux jobs produisent `junit-back.xml` / `junit-e2e.xml` et les uploadent
   (`if: always()`).
5. `make test` reste vert (aucune régression). Journal + `handoff.json`, puis **STOP**.
6. Commit (Makefile, requirements-dev.txt, .gitignore, ci.yml) **après** passe Cowork + GO.
   Pas de tag ni de Deploy — rien de fonctionnel ne change.

## 7. Ce que ça t'apporte concrètement

Après ce lot, `make test-cov` te donne la carte des trous de `app.py` : c'est **lui** qui
dira quelles routes/logiques back méritent le prochain lot de tests, au lieu de deviner. Et
la CI garde une trace consultable de chaque run, verte comme rouge.
