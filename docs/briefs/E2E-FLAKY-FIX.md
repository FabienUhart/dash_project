# Brief CC — [E2E-FLAKY-FIX] : tuer la course du test e2e de création de mémo

> **Priorité — passe devant [TESTS-PORT-5].** `test_create_memo_through_the_ui` a rougi la CI
> pour la **3e fois** (runs 231, puis intermittent, puis 239). C'est dans le **barrage de
> déploiement** (`deploy: needs [tests]`) : un faux rouge peut bloquer une vraie mise en prod —
> ce que le projet a lui-même qualifié de **pire qu'un test absent**. Un re-run vert ne clôt pas
> le sujet ; on établit la cause et on la supprime.
>
> **Discipline** : fichier de test uniquement (`tests/front/test_smoke_front.py`), **aucun
> changement applicatif**. `make test` vert → journal + handoff → **STOP**. Commit après passe
> Cowork + GO. Pas de tag ni de Deploy (test only).

---

## 1. Cause racine (diagnostic CC, validé)

Le correctif de 232 a rendu l'**assertion** patiente (`_wait_until` 10 s) mais l'**action** est
restée **avalable** : le handler de `#memo-quick` enveloppe le POST dans un `try/catch` qui, en
cas d'échec, range la note dans la **file hors-ligne locale** — **sans erreur console, sans ligne
en base**. Sur un runner lent, l'`Enter` part **avant que le handler soit lié** (ou avant que
l'app soit au repos) → le POST échoue ou ne part pas → repli offline silencieux → `_wait_until`
attend en vain, et `console_errors` reste vide **dans les deux cas** : le test ne peut même pas
dire *pourquoi*. En local il passe en ~1 s ; le mode de défaillance n'existe que sur machine lente.

Donc : **attendre plus longtemps ne corrige rien**. Il faut (a) agir seulement quand l'app est
vraiment prête, et (b) rendre l'échec **diagnostique**.

## 2. Le correctif (test-only)

1. **Agir sur une app au repos, handlers liés.** Après `_boot`, attendre
   `page.wait_for_load_state("networkidle")` **avant** de saisir/valider. Si un signal de « prêt »
   plus franc existe (un attribut/état posé quand l'app a fini son init, ou le binding effectif de
   `#memo-quick`), l'attendre explicitement — c'est plus sûr qu'un simple `networkidle`. **Ne
   presser `Enter` qu'ensuite.** C'est LE correctif : supprimer la course, pas l'attendre plus.

2. **Faire parler l'échec** (pour que ce test cesse d'être muet). En cas de non-arrivée, avant de
   `fail`, distinguer les causes et les **rapporter dans le message** :
   - erreurs console (déjà) ;
   - **inspecter la file hors-ligne** (via `page.evaluate(...)` sur l'état JS où elle vit — à
     localiser) : si la note y est → « avalée par le repli offline (app pas prête à l'`Enter`) » ;
     si elle n'y est ni en base ni dans la file → « handler pas lié / `Enter` sans effet ».
   Un test qui échoue doit nommer sa cause ; sinon la prochaine occurrence sera aussi aveugle.

3. **Ne pas se payer d'un re-run vert.** Le test passe toujours en local — donc « vert chez moi »
   ne prouve rien. Établir que le correctif **retire la course identifiée** : idéalement le
   reproduire d'abord (ralentir — CPU/`page.route` qui retarde les requêtes, ou une boucle de N
   exécutions) pour **voir rouge AVANT**, puis vert APRÈS le correctif. Si le repro fiable n'est
   pas atteignable, l'écrire noir sur blanc dans le journal (ce qu'on a prouvé, ce qu'on n'a pas
   pu prouver) plutôt que de déclarer victoire sur un seul vert.

## 3. Étendre la garde (tant qu'on y est)

Les autres parcours e2e (`test_navigate_between_views`, `test_share_page_renders_for_a_guest`)
peuvent porter la **même course** (agir avant que les handlers soient liés). Applique-leur la même
discipline `networkidle`/« app prête » de façon préventive — c'est la vraie racine, pas un cas isolé.

## 4. Definition of Done

1. `tests/front/test_smoke_front.py` corrigé : action après app au repos + échec diagnostique ;
   discipline étendue aux autres parcours e2e.
2. `make test` **vert**, et surtout : **la cause est établie** (repro-avant/après si possible, sinon
   consigné honnêtement). Pas de « victoire sur un re-run ».
3. `git status` : seul `tests/` bouge (aucun fichier applicatif).
4. Journal + handoff avec le verdict (cause + preuve du correctif), **STOP**. Commit
   `tests/front/test_smoke_front.py` (+ `REALISATION.md`, `docs/briefs/E2E-FLAKY-FIX.md`) après
   passe Cowork + GO. Pas de tag ni de Deploy.

## 5. Note (hors correctif, à ne PAS traiter ici)

Le repli offline qui avale un POST « en ligne mais app pas prête » est **du côté app** — pas un
bug de données (la file rejoue par uid, idempotent), mais un comportement à garder en tête. On ne
touche PAS `app.py` dans ce lot ; si ça mérite un examen, ce sera une graine séparée.
