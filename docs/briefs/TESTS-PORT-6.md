# Brief CC — [TESTS-PORT-6] : utilitaires owner, **sans jamais toucher le réseau**

> Dernier gros lot du chantier [TESTS-PORT]. Cibles : `_fx_rates`/`hub_fx` (taux de change,
> **fetch réseau**), `hub_send_link` (**SMTP**), l'export **ZIP** (`_send_zip` & co, local), et la
> branche **vocale** de `_soft_delete_comment` (fichiers, local).
>
> **La contrainte du lot** : aucun test ne doit toucher le réseau ni SMTP. La stratégie est fixée
> ci-dessous (garde autouse + monkeypatch + chemin cache) — c'est ce qui rend le lot faisable.
>
> **Nature = caractérisation + mutation.** Un test qui tombe = bug réel → signale. **Discipline** :
> fichier de test only, aucun changement applicatif. `make test` vert → journal + handoff → **STOP**.
> Commit après passe Cowork + GO. Pas de tag ni de Deploy.
>
> **Découpe** : ce lot a deux moitiés naturelles. **A = réseau neutralisé (FX + SMTP)** — le cœur,
> la raison d'être du lot. **B = fichiers locaux (ZIP + vocal)**. Si A+B est indigeste, **livre A**
> et note **B en `[TESTS-PORT-6b]`**.

---

## 0. La garde « zéro réseau » (à mettre en tête du fichier — non négociable)

Un fixture **autouse** qui fait **échouer bruyamment** tout appel réseau/SMTP réel. C'est ce qui
transforme « on fait attention » en garantie structurelle : un test qui touche le fil rougit.

```python
import json, sqlite3, zipfile, io, pytest
pytestmark = pytest.mark.invariant

@pytest.fixture(autouse=True)
def _interdire_le_reseau(monkeypatch):
    import app
    def _boom(*a, **k):
        raise AssertionError("réseau/SMTP interdit dans les tests [TESTS-PORT-6]")
    monkeypatch.setattr(app.requests, "get", _boom, raising=False)
    monkeypatch.setattr(app.smtplib, "SMTP", _boom, raising=False)
```

Helper pour semer le cache FX **sans réseau** (le chemin nominal du widget) :

```python
def _seed_fx_cache(rates, day):
    import app
    con = sqlite3.connect(app.DB_PATH)
    try:
        payload = {"date": "2026-08-09", "base": "EUR", "rates": rates, "fetched_day": day}
        con.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('fx_cache', ?)",
                    (json.dumps(payload),))
        con.commit()
    finally:
        con.close()
```

---

## Partie A — FX + SMTP (réseau neutralisé)

### A.1 `_fx_rates` / `hub_fx` (contrats relevés)

`_fx_rates(db)` : si le cache `app_state.fx_cache` a `fetched_day == aujourd'hui` (Paris) → le
sert **sans appeler `_fx_fetch_rates`**. Sinon fetch ; échec → dernier cache ; aucun cache →
`{date:None, base:"EUR", rates:None}` (jamais de 500). Routes : `/api/fx` (owner), `/share/<token>/fx`
(404 token invalide), `/share/hub/<hub_token>/fx` (404 hub invalide) — publiques, sans approbation.

1. **`test_fx_served_from_cache_without_fetch`** — `_seed_fx_cache({...}, aujourd'hui)` → `GET /api/fx`
   renvoie ces taux **et** la garde réseau n'a pas sauté (aucun fetch). C'est le chemin nominal.
2. **`test_fx_fetches_and_caches_when_stale`** — cache absent (ou `fetched_day` d'hier) +
   `monkeypatch.setattr(app, "_fx_fetch_rates", lambda: {"date":"…","base":"EUR","rates":{"JPY":160.0}})`
   → `GET /api/fx` renvoie le frais, et il est **mis en cache** (2e appel sans re-fetch : compter les
   appels au stub).
3. **`test_fx_falls_back_to_stale_cache_on_failure`** — cache d'hier + `_fx_fetch_rates` monkeypatché
   à `lambda: None` (échec réseau simulé) → sert le **dernier cache**, pas de crash.
4. **`test_fx_no_cache_no_network_is_empty_not_500`** — aucun cache + `_fx_fetch_rates → None` →
   `{date:None, rates:None}`, HTTP 200.
5. **`test_fx_routes_guard_tokens`** — `/share/<token>/fx` et `/share/hub/<token>/fx` : token bidon
   → 404 ; token valide (cache semé) → 200 avec les taux.

### A.2 `hub_send_link` (SMTP) — contrats

`POST /share/hub/<hub_token>/send-link` : **preuve requise** (`_hub_proof`) sinon **403** générique
(hub inconnu ≡ preuve absente) ; `_smtp_config()` `None` → **400** « non disponible » ; throttle
~2/h → **429** ; **destinataire FORCÉ = e-mail du hub** (le corps de la requête est **ignoré**) ;
succès → 200 `{ok:true, sent_to: <e-mail MASQUÉ>}` ; échec SMTP → 502. Le PIN/secret n'apparaît
jamais dans la réponse.

6. **`test_send_link_requires_proof_403`** — sans preuve → 403.
7. **`test_send_link_smtp_disabled_400`** — SMTP non configuré (défaut des tests : pas d'env
   `SMTP_PASS`) → 400 « non disponible », **aucun envoi** (la garde réseau le confirmerait sinon).
8. **`test_send_link_sends_to_hub_email_only`** — chemin activé **simulé** :
   `monkeypatch.setattr(app, "_smtp_config", lambda: {"host":"h","port":587,"user":"u","sender":"s"})`
   **et** `monkeypatch.setattr(app, "_send_hub_invite", enregistreur)` (un stub qui capture ses
   arguments). Preuve OK + corps contenant une **autre** adresse → 200, et l'enregistreur a reçu
   **le destinataire = e-mail du hub**, jamais celui du corps.
9. **`test_send_link_masks_recipient_and_hides_secret`** — la réponse `sent_to` est **masquée**
   (`f•••@…`), et le payload complet ne contient ni l'e-mail en clair ni le PIN.
10. **`test_send_link_throttled_429`** *(si montable)* — au-delà de ~2 envois/h → 429.

> Vérifie le **nom exact** de la fonction d'envoi à monkeypatcher (`_send_hub_invite` vs `_smtp_send`) —
> monkeypatche celle que `hub_send_link` appelle, pour capturer le destinataire sans SMTP réel.

---

## Partie B — ZIP + vocal (fichiers locaux, pas de réseau)

### B.1 Export ZIP (`_send_zip` & routes `download.zip`)

`_send_zip(entries, base)` : `entries` vide → **404** ; sinon zip streamé (dédup des noms d'arc en
collision : `nom (2).ext`). Routes : `/api/memos/<id>/download.zip`, `/api/projects/<id>/download.zip`,
et les variantes invité `/share/<token>/memo|project/<id>/download.zip`.

11. **`test_memo_zip_empty_is_404`** — mémo **sans** fichier → 404.
12. **`test_memo_zip_contains_its_files`** — mémo avec une pièce jointe (upload via l'API
    d'attachements) → `GET …/download.zip` = 200, et `zipfile.ZipFile(io.BytesIO(resp.data))`
    contient bien le fichier.
13. **`test_zip_dedupes_colliding_arc_names`** — deux fichiers de même nom → l'archive contient
    `nom` **et** `nom (2)` (aucune écrasée).
14. **`test_share_zip_scope_guard`** — variante invité : mémo hors scope / token invalide → 404 ;
    dans le scope → l'archive attendue.

### B.2 Branche vocale de `_soft_delete_comment`

Supprimer un commentaire **vocal** doit : **purger le fichier** de la pièce jointe référencée dans le
corps (`VOICE_BODY_RE`), supprimer sa ligne `attachments`, **retirer la ligne système** `📎 … <orig>`
qui l'annonçait, puis vider le corps + poser `deleted_at` (idempotent).

15. **`test_deleting_a_voice_comment_purges_file_and_system_line`** — monte l'état (commentaire
    vocal + attachement + ligne système `📎`, forgés en base comme les tombales de la vague 2, ou
    créés par les vraies routes si plus simple), supprime → le **fichier n'existe plus**, la ligne
    `attachments` est partie, la **ligne système `📎` a disparu**, le corps est vidé, `deleted_at` posé.
16. **`test_soft_delete_is_idempotent`** — re-supprimer une tombale ne fait rien (aucune erreur).

> La B.2 est la plus touffue (comprendre `VOICE_BODY_RE` + la forme d'un commentaire vocal). Si le
> montage résiste, **forge l'état en base** plutôt que de passer par l'UI, et **signale** si un
> comportement réel diffère du brief.

---

## Definition of Done

1. `tests/back/test_owner_utils.py` créé (marqueur `invariant`), **garde autouse zéro-réseau** en tête.
2. `make test` **vert** ; **aucun** test ne touche le réseau/SMTP (la garde le prouve structurellement).
3. `make test-cov` : `_fx_rates`, `hub_send_link`, `_send_zip`/`_memo_zip_files`/`_project_zip_entries`,
   et la branche vocale de `_soft_delete_comment` remontent.
4. `git status` : seul `tests/` bouge.
5. Journal + handoff, **STOP**. Commit `tests/back/test_owner_utils.py` (+ `REALISATION.md`,
   `docs/briefs/TESTS-PORT-6.md`) après passe Cowork + GO. Pas de tag ni de Deploy.
6. Si découpe : A livré, **B noté `[TESTS-PORT-6b]`** dans la file — pas de lot indigeste.

---

## Après ce lot

Le chantier [TESTS-PORT] est **clos** : surface publique invitée + données (import) + utilitaires
owner sous garde durable, couverture bien au-delà de 50 %. On pourra alors reprendre la file
produit : `[GUEST-PROFILE]`, `[GUEST-WELCOME]` (7/10), `[DEBUG-RECORDER]`, et cadrer `[MEMO-HANDLE]`
/ `[CUSTOM-COMMANDS]` quand tu voudras.
