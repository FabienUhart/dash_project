# Brief CC — [PROCESS-DOC] : inscrire la doctrine TDD + « STOP = build ET tests verts » dans CLAUDE.md

> **But (Fabien)** : rendre le process de réalisation **rodé et portable**. Aujourd'hui la
> boucle TDD, le rôle des tests dans le « STOP », et les garde-fous ne sont **pas** dans
> `CLAUDE.md` — la section « Comment tester » est même restée sur l'ancienne méthode
> (py_compile + scénarios manuels). Or `.claude/hooks/` est gitignoré : le hook Stop révisé
> vit sur un seul Mac. La doctrine **écrite dans `CLAUDE.md`** (commitée) est ce qui suit le
> dépôt partout et tient entre les sessions.
>
> **Périmètre** : `CLAUDE.md` **uniquement** (documentation). Aucun changement applicatif,
> aucun test à écrire. Donc : édite `CLAUDE.md`, `make test` doit rester vert (il ne bouge
> pas), journal + handoff, **STOP**. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

Quatre éditions ciblées. Les textes ci-dessous sont prêts à coller ; intègre-les dans le
style du fichier.

---

## Édition 1 — Remplacer toute la section « ## Comment tester avant de commit »

Remplacer la section actuelle (le bloc ```bash py_compile / cp db / flask run / scénarios
critiques```, **y compris** le sous-titre « ### Scénarios de test spécifiques v19 ») par :

```markdown
## Tests (pytest) & méthode TDD

Depuis **V27.38.230** le projet a une **suite de tests** (`tests/`, lancée par `pytest`),
une **batterie d'invariants** et un barrage CI. Commande unique :

    make test            # toute la suite (back + front)
    make test-back       # back seul (unit + invariants), rapide, sans navigateur
    make test-front      # front seul (pytest-playwright, headless)
    make test-invariants # les garde-fous seuls
    make install         # crée .venv + deps de dev + Chromium (une fois)

**Sûreté** : les tests back tournent sur des **bases SQLite temporaires** (fixtures de
`tests/conftest.py`), **jamais** `data/dashboard.db` ; le front lance un `live_server` sur
une base temp dédiée. `make test` ne touche donc jamais les vraies données.

**Batterie d'invariants** (`-m invariant`) = les garde-fous non négociables, qui encodent
les invariants ci-dessus : round-trip export→import sans perte ni doublon, v1 importable,
import non destructif, uid stable, corbeille hors export, écriture invitée sous `/share/*`
uniquement, format d'export figé v27. **Un rouge sur un invariant = pas de deploy.**

**Méthode = TDD (rouge → vert)** :
- Toute **nouvelle feature back** et **tout bugfix** commencent par un **test qui échoue**
  (pour un bug : un test qui **reproduit** le bug), puis le code jusqu'au vert. Un test qui
  passe sur un bug déjà corrigé ne prouve rien — le prouver rouge d'abord.
- Le **legacy** n'est pas réécrit : il est couvert par la **batterie d'invariants**, pas par
  une couverture rétroactive ligne à ligne (doctrine hybride).
- Le **front** grossit par petits parcours e2e, chacun avec l'assertion « zéro erreur
  console ».
- Boucle : **Fabien donne l'idée → Cowork cadre (le brief liste d'abord les tests + les
  invariants touchés) → CC écrit les tests rouges puis le code → passe Cowork → GO Fabien.**

Exploration manuelle toujours possible sur une **copie** de la base (jamais la vraie) :
`cp data/dashboard.db /tmp/test.db && DB_PATH=/tmp/test.db flask --app app run -p 8099` —
mais `make test` est la source de vérité.
```

---

## Édition 2 — « ## Process de fin de réalisation », étape 1

Remplacer l'étape 1 actuelle :

> 1. **Tester** : `python3 -m py_compile app.py` + les scénarios critiques (voir « Comment tester »), toujours sur une **copie** de la base (`cp data/dashboard.db /tmp/test.db`), jamais sur `data/dashboard.db`.

par :

```markdown
1. **Tester** : `make test` **vert** (back + front ; bases temporaires, jamais `data/dashboard.db`). Un bugfix a d'abord eu son test rouge (cf. § Tests & TDD). Le `py_compile` reste couvert par la CI.
```

## Édition 3 — même section, étape 4

Remplacer l'étape 4 actuelle :

> 4. **Mettre à jour le journal et le handoff** : la ligne `✅` dans `.claude/session-log.md` et `.claude/handoff.json` (statut `ready`, pas `deployed`).

par :

```markdown
4. **Mettre à jour le journal et le handoff** : la ligne `✅` dans `.claude/session-log.md` et `.claude/handoff.json`. **`status: ready` ne vaut que si le build ET `pytest -m "not e2e"` sont verts** — le hook Stop l'impose (sinon `tests_failed`, ou `tests_skipped` si les deps dev manquent) ; jamais `deployed`.
```

---

## Édition 4 — Ajouter une sous-section « Les garde-fous » sous la règle de deploy

Juste **après** la section « ### ⛔ Règle permanente : CC ne déploie pas » (après le
paragraphe qui se termine par l'option « dure » du hook `Stop`), insérer :

```markdown
### Les garde-fous : qui teste où

Quatre acteurs, une même règle « pas de rouge » :

1. **Hook Stop** (après chaque réalisation, sur le M4) — `pytest -m "not e2e"` (back rapide)
   → `handoff.json` `ready` seulement si vert. Boucle courte.
2. **Pre-commit** (`.githooks/pre-commit`, activé une fois par `make hooks`, sur le M4) —
   **suite complète** (back + front) avant que le commit n'existe ; rouge = commit refusé
   (`git commit --no-verify` = secours d'urgence seulement).
3. **Passe Cowork** — revue d'**honnêteté** des tests (le rouge-avant-vert est-il prouvé ?
   aucun bug figé en « comportement attendu » ?), en plus de la validation Chrome des features.
4. **CI GitHub** — `deploy.yml` porte `deploy: needs [tests]` → **rouge = pas de deploy**.
   C'est la garantie **portable** : elle suit le dépôt. Les hooks locaux (Stop, pre-commit)
   vivent sur la machine — sur une machine neuve, les réarmer par `make install` + `make hooks`
   (le hook Stop, dans `.claude/` gitignoré, est à réappliquer à la main).

Le Zimaboard ne lance **jamais** de tests : uniquement l'étape de déploiement.
```

---

## Édition 5 — Mettre à jour le bullet « Automatisé » (section journal de session)

Remplacer :

> - **Automatisé** : le hook `Stop` (`.claude/hooks/post-stop-rebuild.sh`) appende lui-même la ligne `✅ rebuild local OK` (ou `⚠ rebuild local ECHOUE`) en même temps qu'il écrit `handoff.json`. […]

par :

```markdown
- **Automatisé** : le hook `Stop` (`.claude/hooks/post-stop-rebuild.sh`) rebuild le local **puis lance `pytest -m "not e2e"`** et écrit `handoff.json` avec le statut correspondant (`ready` = build + tests verts / `tests_failed` / `tests_skipped` si deps dev absentes / `build_failed`), en appendant la ligne `✅`/`⚠` au journal. Le `▶` et les `⚠`/`❓` restent **manuels** — c'est du jugement, pas de l'automatisme.
```

---

## Definition of Done

1. Les 5 éditions appliquées à `CLAUDE.md`, cohérentes avec le reste du fichier.
2. `make test` toujours vert (le fichier de doc ne touche pas au code).
3. Journal `.claude/session-log.md` + `handoff.json`, puis **STOP**.
4. Commit (`CLAUDE.md`, + ce brief `docs/briefs/PROCESS-DOC.md` déjà versé) après passe
   Cowork + GO Fabien. **Pas de tag ni de Deploy** (documentation pure).

> Note : la mise à jour de la **mémoire Cowork** (`dash-cc-handoff-hook.md` + une fiche
> `dash-test-harness`) est faite **par Cowork directement** (hors dépôt), pas par CC.
