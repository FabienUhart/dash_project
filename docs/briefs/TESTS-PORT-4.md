# Brief CC — [TESTS-PORT-4] : le HUB (`/share/hub/*`), jamais testé

> **Toujours de la surface PUBLIQUE** (invariant 5) : le hub vit sous `/share/hub/<hub_token>`,
> le même bypass Authelia que `/share/*`, protégé par le seul `hub_token` (+ PIN). `hub_data`
> est le plus gros bloc nu du dépôt (**138 lignes**). La garde reine, comme partout ici : **un
> `hub_token` n'expose QUE les partages de SA personne (son e-mail), jamais ceux d'un autre**
> (`_hub_approved_shares` : « UNIQUEMENT cet e-mail »).
>
> **Nature = caractérisation + mutation** (même moule que les vagues 1-3). Un test qui tombe =
> bug réel → arrête-toi, signale. Éprouve chaque garde par mutation (casse-la, vois tomber
> exactement un test, restaure `app.py`).
>
> **⚠ Zéro réseau.** `hub_fx` (taux de change) et `hub_send_link` (e-mail) **sont hors de ce
> lot** — ils touchent réseau/SMTP et iront au lot utilitaire. Ici : `hub_data`, `hub_approve`,
> `hub_page` uniquement.
>
> **Discipline** : fichier de test only, aucun changement applicatif. `make test` vert → journal
> + handoff → **STOP**. Commit après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 1. Fichier : `tests/back/test_hub.py` (marqueur `invariant`)

### Modèle & contrats (relevés dans `app.py`)

- **Un hub par e-mail** : table `guest_hubs (email, name, hub_token, pin, session_token, …)`.
  `_ensure_hub(db, email, name)` le crée **au register d'un partage** (idempotent). Donc :
  inscrire un invité sur un partage crée son hub.
- `GET /share/hub/<hub_token>` (`hub_page`) → **404** si token inconnu, sinon 200 (shell HTML).
- `GET /share/hub/<hub_token>/data` (`hub_data`) → **404** token inconnu · **403** « code requis »
  sans preuve (`_hub_proof` : cookie de session **ou** guest_token approuvé de cet e-mail) ·
  sinon 200 avec `projects`/`memos`/… **agrégés pour ce seul e-mail**.
- `POST /share/hub/<hub_token>/approve` (`hub_approve`) `{pin}` → **403** « code invalide »
  (hub inconnu **≡** PIN faux, indiscernable, anti-énumération) · **429** si throttlé · sinon
  **200** `{name, folders}` **+ pose un cookie de session** ; la cascade passe à `approved`
  **uniquement** les `share_guests` de cet e-mail **qui ne sont pas déjà approved/rejected**
  (un accès **révoqué reste révoqué** — E10).

### Montage (helpers)

Le chemin de preuve le plus simple pour `hub_data` : **approuver d'abord** (le test_client garde
le cookie), puis lire `/data`.

```python
import sqlite3, pytest
pytestmark = pytest.mark.invariant

def _project(c, name):
    r = c.post("/api/projects", json={"name": name}); assert r.status_code == 201, r.data
    return r.get_json()["id"]

def _memo(c, pid, content):
    r = c.post("/api/memos", json={"content": content, "project_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]

def _share(c, pid, role="viewer"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    return r.get_json()

def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token, json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]

def _hub(email):
    """(hub_token, pin) du hub de cet e-mail, lus dans la base temp du test."""
    import app
    con = sqlite3.connect(app.DB_PATH)
    try:
        row = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?",
                          (email.lower(),)).fetchone()
        return (row[0], row[1]) if row else (None, None)
    finally:
        con.close()

def _prove(c, hub_token, pin):
    """Approuve (bon PIN) → le client détient le cookie de session pour lire /data ensuite."""
    r = c.post("/share/hub/%s/approve" % hub_token, json={"pin": pin})
    assert r.status_code == 200, r.data
    return r
```

> **À VÉRIFIER puis figer** : (a) que le cookie posé par `/approve` suffit bien comme preuve pour
> `/data` sur le **même** `test_client` (sinon, utilise l'`X-Guest-Token` de l'invité approuvé — le
> docstring de `hub_data` l'accepte). (b) le levier pour marquer un accès **`rejected`** (route
> owner `PUT /api/guests/<id>` avec un statut, sinon écriture directe en base temp, comme les
> tombales de la vague 2).

---

## 2. Les tests (la liste = la spec)

### A. `hub_page`

1. **`test_hub_page_unknown_token_404`** — token bidon → 404.
2. **`test_hub_page_valid_token_200`** — hub réel → 200.

### B. `hub_data` — preuve + **isolation par personne** (le cœur)

3. **`test_hub_data_unknown_token_404`**.
4. **`test_hub_data_without_proof_403`** — hub réel, aucune preuve → 403 « code requis ».
5. **`test_hub_data_with_proof_lists_own_folders`** — après `_prove`, `/data` → 200 et contient le dossier partagé à cette personne.
6. **`test_hub_data_isolates_people`** — **LA garde** : e-mail A (partage du dossier FA) et e-mail B (partage du dossier FB, autre lien). Le `/data` du hub de A (preuve A) contient FA et **jamais** FB ; réciproquement pour B. Un `hub_token` n'est pas un passe vers les partages d'autrui (invariant 5).

### C. `hub_approve` — PIN + révocation

7. **`test_hub_approve_unknown_hub_403`** — token bidon → 403 (indiscernable d'un PIN faux).
8. **`test_hub_approve_wrong_pin_403`** — hub réel, mauvais PIN → 403.
9. **`test_hub_approve_correct_pin_returns_folders_and_sets_cookie`** — bon PIN → 200, `folders` non vide, **`Set-Cookie`** présent dans la réponse.
10. **`test_hub_approve_does_not_revive_a_revoked_access`** — **E10, le test qui compte** : un
    `share_guest` de cet e-mail passé à `rejected`, puis `/approve` bon PIN → l'accès **reste
    `rejected`** (le PIN du hub n'annule pas une révocation owner). Vérifie en base.
11. **`test_hub_approve_touches_only_this_email`** — le bon PIN du hub de A ne fait rien passer
    à `approved` chez B : les accès de B restent en l'état (monte un accès B *pending* si le
    montage le permet, sinon vérifie qu'aucune ligne de B n'est modifiée).

> ~11 tests. `hub_data` étant énorme (138 lignes), la vague en couvre les **gardes** et
> l'**isolation** ; l'agrégation fine (union projets/mémos, share gagnant) pourra être creusée
> plus tard si la couverture le réclame — ne bloque pas le lot dessus.

---

## 3. Definition of Done

1. `tests/back/test_hub.py` créé (marqueur `invariant`), gardes éprouvées par mutation
   (au minimum l'isolation par personne #6 et l'E10 #10).
2. `make test` **vert** (ou rouge **signalé**, jamais masqué).
3. `make test-cov` : `hub_data`, `hub_approve`, `hub_page` remontent (surtout leurs gardes).
4. `git status` : seul `tests/` bouge.
5. Journal + handoff, **STOP**. Commit `tests/back/test_hub.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT-4.md`) après passe Cowork + GO. Pas de tag ni de Deploy.

---

## 4. Après ce lot

La surface **publique** invitée sera entièrement sous garde (partages + hub). Restera, par ordre
de risque : `[TESTS-PORT-5]` entrailles de l'import (`import_links` 157, `_import_dry_run` 46 —
données, la douleur d'origine), puis `[TESTS-PORT-6]` utilitaires owner (**ZIP**, **`_fx_rates`
et `hub_fx` sans réseau**, `hub_send_link`, branches vocales de `_soft_delete_comment`).
