# Brief CC — [TESTS-PORT-2] : surface d'expression invitée (commentaires, réactions) + validateur d'emoji

> **Suite de [TESTS-PORT vague 1]** (délégation `/share/*`). La couverture par fonction
> (`htmlcov/function_index.html`) confirme que le gros du risque **nu** reste la **surface
> publique invitée** `/share/*` (invariant 5). Cette vague prend le **cœur d'expression** :
> écrire un commentaire, y répondre, le supprimer, réagir — plus le **validateur d'emoji**
> (`_clean_reaction_emoji`, pur, invariant 6 : anti-injection).
>
> **Nature = caractérisation** (comme la vague 1). On fige le comportement correct actuel.
> **Un test qui tombe = bug réel** dans une route de sécurité → **arrête-toi, signale-le**,
> ne réécris jamais l'assertion pour matcher un comportement faux. Éprouve chaque garde par
> **mutation** (casse-la, vois tomber *exactement un* test, restaure `app.py`) — comme en vague 1.
>
> **Discipline** : fichier de test uniquement, **aucun changement applicatif**. `make test`
> vert → journal + handoff → **STOP**. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 1. Fichier : `tests/back/test_share_comments.py`

Marqueur `@pytest.mark.invariant`. Contrats relevés dans `app.py` (ne pas ré-explorer) :

- `POST /api/shares` `{kind:"project", target_id, role}` → `{token, pin, ...}`. **`role`** fixe
  le rôle du lien : `"viewer"` (lecture), `"commenter"`, `"editor"`. C'est le levier pour
  tester « a la capacité » vs « ne l'a pas ».
- `POST /share/<token>/register` `{name,email,pin}` → `{guest_token}` (invité approuvé).
- `POST /share/<token>/memo/<memo_id>/comments` `{body, parent_id?, priority?}` → **201** ;
  gardes en ordre : token 404 · non approuvé 403 (`_approved_or_403`) · mémo hors scope 404 ·
  capacité `comment` refusée 403 (`_role_gate`) · `body` vide 400. `/vote_choix a ; b` dans le
  body crée un scrutin **si** `sw_votes` actif, sinon **403** « Les votes sont désactivés ».
- `DELETE /share/<token>/comment/<comment_id>` → supprime **son propre** message (match e-mail,
  `can_edit` NON requis) ; message d'autrui → **403** ; tombale/absent → 404.
- `POST /share/<token>/comment/<comment_id>/react` `{emoji}` → réagit ; `can_edit` NON requis
  mais approuvé + capacité `react` (= commenter) + mémo du commentaire dans le scope ; emoji
  **hors palette → 400** ; re-poster le même emoji **bascule** (toggle).
- Fonction pure : `app._clean_reaction_emoji(raw)` → l'emoji si UN seul grapheme valide, sinon `""`.

### Helpers (réutilise l'esprit de la vague 1)

```python
import sqlite3, pytest
pytestmark = pytest.mark.invariant
H = lambda gt: {"X-Guest-Token": gt}

def _project(c, name):
    r = c.post("/api/projects", json={"name": name}); assert r.status_code == 201, r.data
    return r.get_json()["id"]

def _memo(c, pid, content):
    r = c.post("/api/memos", json={"content": content, "project_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]

def _share(c, pid, role="commenter"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    return r.get_json()                      # {token, pin, ...}

def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token, json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]

def _add_comment(c, token, memo_id, gt, body):
    return c.post("/share/%s/memo/%d/comments" % (token, memo_id), headers=H(gt), json={"body": body})
```

---

## 2. Les tests (la liste = la spec)

### A. `_clean_reaction_emoji` — pur, sans montage (invariant 6, anti-injection)

`import app` puis appeler `app._clean_reaction_emoji(...)` :

1. **`test_emoji_accepts_simple`** — `"👍"` → renvoyé.
2. **`test_emoji_accepts_zwj_sequence`** — famille `"👨‍👩‍👧"` → renvoyée (une seule base logique).
3. **`test_emoji_accepts_flag`** — `"🇫🇷"` (2 indicateurs régionaux) → renvoyé.
4. **`test_emoji_accepts_skin_tone`** — `"👍🏽"` → renvoyé.
5. **`test_emoji_rejects_text`** — `"hello"`, `"a"` → `""`.
6. **`test_emoji_rejects_html`** — `"<b>"`, `"<script>"`, `"&"` → `""`.
7. **`test_emoji_rejects_two_emojis`** — `"👍👎"` → `""`.
8. **`test_emoji_rejects_empty_and_space`** — `""`, `"   "` → `""`.
9. **`test_emoji_rejects_non_str`** — `None`, `123` → `""`.
10. **`test_emoji_rejects_overlong`** — chaîne de > 10 code points → `""`.

### B. `share_add_comment`

11. **`test_comment_anonymous_403`** — sans header → 403.
12. **`test_comment_memo_out_of_scope_404`** — mémo d'un dossier non partagé → 404.
13. **`test_viewer_cannot_comment_403`** — lien `role="viewer"`, invité approuvé → 403 (capacité `comment` refusée).
14. **`test_comment_empty_body_400`** — `body` vide/espaces → 400.
15. **`test_commenter_can_comment_201`** — lien `role="commenter"` → 201, le message apparaît (le refetch du fil le contient).
16. **`test_comment_reply_sets_parent`** — répondre avec `parent_id` → 201, la réponse est rattachée.
17. **`test_poll_command_blocked_when_votes_off`** — `body="/vote_choix a ; b"` sur un partage `sw_votes` **off** → 403 « Les votes sont désactivés ». *(Régler `sw_votes` via la route owner d'update de partage si besoin ; sinon documenter l'état par défaut et tester le chemin actif du défaut.)*

### C. `share_delete_comment`

18. **`test_delete_own_comment_ok`** — l'auteur invité supprime son message → 200/204 ; il disparaît du fil (tombale : corps vidé, cf. invariant 7 addendum) — vérifie qu'il n'est plus listé.
19. **`test_cannot_delete_others_comment_403`** — un autre invité (même lien) tente → 403.
20. **`test_delete_unknown_comment_404`** — id inexistant → 404.

### D. `share_react_comment` (+ palette)

21. **`test_react_anonymous_403`** — sans header → 403.
22. **`test_react_out_of_scope_404`** — commentaire d'un mémo hors scope → 404.
23. **`test_viewer_cannot_react_403`** — lien `role="viewer"` → 403.
24. **`test_react_off_palette_400`** — emoji absent de la palette (ex. un emoji rare non listé, ou `"x"`) → 400.
25. **`test_react_toggles`** — même (emoji, commentaire, votant) posté 2× → présent puis retiré (vérifie le compte dans la réponse `_react_result`).

> ~25 tests. La plupart doivent **passer d'emblée**. Tout rouge = signalement (cf. en-tête).

---

## 3. Definition of Done

1. `tests/back/test_share_comments.py` créé (~25 tests, marqueur `invariant`), gardes éprouvées par mutation.
2. `make test` **vert** (ou rouge **signalé** comme bug potentiel, jamais masqué).
3. `make test-cov` : `share_add_comment`, `share_delete_comment`, `share_react_comment`,
   `_clean_reaction_emoji` ne sont plus à nu (le % remonte).
4. `git status` : seul `tests/` bouge (aucun fichier applicatif).
5. Journal + handoff, **STOP**. Commit `tests/back/test_share_comments.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT-2.md`) après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 4. Rappel hors lot

Le micro-fix **docstring** de `share_admin_view` (vague 1) reste à faire, **à part** (c'est
une ligne dans `app.py`, pas un test) — ne pas le mêler à ce lot test-only.
