# Brief CC — [IMPORT-SKIP-FIX] : honorer « Ignorer » à l'import

> **Premier lot fonctionnel depuis le chantier tests** — il **touche `app.py`** (petit), et suit
> la doctrine TDD à la lettre : **rouge d'abord, vert ensuite**.
>
> **Prérequis** : [TESTS-PORT vague 5] (V27.38.241) commité — c'est là que vit le test à retourner.

---

## 1. Le bug (confirmé côté front + back)

Dans l'UI « Importer ici » (`templates/index.html`), chaque conflit propose **Écraser /
Dupliquer / Ignorer** ; les conflits sont mis à `'skip'` par défaut (l.3985) et le compteur
« résolus » exclut les `skip` (l.4042). L'utilisateur qui clique **« Ignorer »** demande donc
explicitement : *laisse ce mémo tel quel*.

Or dans `import_links` (`app.py`), le `resolutions` map n'interprète que `overwrite` et
`duplicate`. Pour un conflit marqué `"skip"`, on tombe dans la branche par défaut **newer-wins** :

```python
res = str(res_map.get(uid) or "").strip().lower() if uid else ""     # ~l.11181
if uid and uid in memos_by_uid and res != "duplicate":
    existing = memos_by_uid[uid]
    ... champs fusionnés ...
    if res == "overwrite":
        ... UPDATE forcé ...
    elif updated and updated > (existing["updated_at"] or ""):   # ← "skip" tombe ICI
        ... UPDATE newer-wins ...                                #    → écrase MALGRÉ « Ignorer »
    else:
        skipped_memos += 1
    _import_memo_attachments(...)
    continue
```

Conséquence : un fichier **plus récent** met à jour un mémo que l'utilisateur a explicitement
demandé d'**ignorer**. Pas une perte (les révisions gardent l'ancien), mais **le code contredit
un choix explicite de l'utilisateur**. C'est le défaut à corriger.

---

## 2. TDD — rouge d'abord

**Étape 1 (rouge).** Dans `tests/back/test_import_internals.py`, **retourner** le test de
caractérisation `test_resolution_skip_is_not_what_its_name_says` :

- le **renommer** (ex. `test_resolution_skip_leaves_the_memo_untouched`) ;
- réécrire sa docstring (ce n'est plus « nom trompeur » mais « `skip` = ne touche à rien ») ;
- changer l'assertion du cas ② (fichier **plus récent** + `resolutions={uid:"skip"}`) pour exiger
  que le mémo reste **inchangé** :
  ```python
  assert _row("memos", id=mid)["content"] == "Version locale", (
      "« Ignorer » doit laisser le mémo intact, même si le fichier est plus récent"
  )
  ```

Lancer `make test-back` → **ce test échoue** (le code fait encore newer-wins). C'est la preuve
que le test mord. Ne pas passer à l'étape 2 avant d'avoir **vu le rouge**.

## 3. Vert — le correctif (chirurgical)

Dans `import_links`, **juste après** la ligne `res = str(res_map.get(uid) ...)` (~l.11181),
court-circuiter `skip` — « ignorer » = ne rien faire pour cet uid :

```python
res = str(res_map.get(uid) or "").strip().lower() if uid else ""
if res == "skip":                    # [IMPORT-SKIP-FIX] « Ignorer » = laisser tel quel
    skipped_memos += 1               # (ni update, ni insertion, ni pièces jointes ajoutées)
    continue
```

Ce placement **avant** le bloc de conflit couvre les deux cas : un conflit marqué `skip` (le vrai
bug) **et** l'éventuel `skip` sur un uid non-conflit (cohérent : « ignorer » = ne pas importer).

> **Décision à assumer et à tester** : avec ce court-circuit, un mémo `skip` ne reçoit **pas** non
> plus ses pièces jointes (ignorer = ignorer entièrement). C'est le sens attendu de « Ignorer ».
> Si tu juges qu'il faut au contraire garder l'import additif des PJ pour un `skip`, l'alternative
> plus fine est de ne garder QUE la branche de contenu (`elif res != "skip" and updated and …`) —
> mais par défaut, prends le court-circuit complet, plus proche de l'intention utilisateur.

## 4. Vérifier

- Le test retourné passe **vert**.
- Les autres tests de résolution **ne régressent pas** : `overwrite` force/restaure toujours,
  `duplicate` crée toujours une copie (uid neuf), **résolution absente** = toujours newer-wins
  (`test_absent_resolution_is_newer_wins` reste vert — c'est important : on ne casse le newer-wins
  QUE pour le `skip` explicite, pas pour le défaut).
- `make test` **entièrement vert** (back + front).
- **Front** : aucun changement — il envoie déjà `skip` correctement, c'est le back qui s'aligne
  sur lui (et sur l'utilisateur).

## 5. Definition of Done

1. Test retourné (rouge prouvé **avant**, vert **après**), docstring à jour.
2. `import_links` corrigé (le court-circuit `skip`), **aucune autre logique touchée**.
3. `make test` vert ; rebuild local `docker compose up -d --build` (c'est un changement
   applicatif, pas un lot test-only).
4. Journal + `handoff.json`, puis **STOP**.
5. Commit `app.py` + `tests/back/test_import_internals.py` + `REALISATION.md` + brief après passe
   Cowork + GO. **Contrairement aux lots de tests, celui-ci est un vrai correctif fonctionnel** :
   un **tag + Deploy** est envisageable (décision Fabien) — la prod est encore sur V27.37.229.

---

## 6. Portée

Petit lot, une seule intention. Il **ne prétend pas** couvrir les 58 lignes nues restantes
d'`import_links` (mapping v1→v27, commentaires, réactions, PJ, liens) — celles-ci se traiteront au
fil des lots qui y touchent, comme convenu.
