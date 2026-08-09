"""[TESTS-PORT vague 6] Utilitaires owner — sans jamais toucher le réseau.

Quatre zones restées nues, réunies par une contrainte commune : elles sortent de l'app.
Taux de change (HTTP), envoi de lien (SMTP), export ZIP (fichiers) et la branche vocale de
la suppression de commentaire (fichiers).

**La garde « zéro réseau » est structurelle, pas une intention** : un fixture autouse de
`tests/conftest.py` fait échouer bruyamment tout appel sortant, pour toute la suite
([TEST-NET-GUARD]). Un test qui touche le fil rougit.

⚠ Elle ferme bien `urllib.request.urlopen` et pas seulement `requests` : c'est par `urlopen`
que passe `_fx_fetch_rates`, la fonction même que ce fichier vise.

Nature = **CARACTÉRISATION + mutation**, comme les vagues précédentes.
"""
import io
import json
import os
import sqlite3
import zipfile

import pytest

pytestmark = pytest.mark.invariant


# La garde « zéro réseau » n'est plus ici : elle est HISSÉE dans `tests/conftest.py`
# ([TEST-NET-GUARD]) et couvre désormais toute la suite, avec une exception pour localhost
# (le fixture `live_server` en dépend). Les tests qui la prouvent vivent dans
# `tests/back/test_net_guard.py`.


# ───────────────────────────────────────── montage ─────────────────────────────────────────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _seed_fx_cache(rates, day, date="2026-08-09"):
    import app
    con = _db()
    try:
        con.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('fx_cache', ?)",
                    (json.dumps({"date": date, "base": "EUR", "rates": rates,
                                 "fetched_day": day}),))
        con.commit()
    finally:
        con.close()


def _aujourdhui():
    import app
    return app._fx_today()


def _project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _memo(c, content, project_id=None):
    body = {"content": content}
    if project_id is not None:
        body["project_id"] = project_id
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _share(c, pid, kind="project"):
    r = c.post("/api/shares", json={"kind": kind, "target_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _hub_of(c, pid):
    """Crée un hub en inscrivant un invité sur un partage — le seul chemin qui en fabrique un."""
    sh = _share(c, pid)
    r = c.post("/share/%s/register" % sh["token"],
               json={"name": "Alice", "email": "alice@ex.com", "pin": sh["pin"]})
    assert r.status_code in (200, 201), r.data
    con = _db()
    try:
        row = con.execute("SELECT * FROM guest_hubs WHERE email = 'alice@ex.com'").fetchone()
    finally:
        con.close()
    return dict(row), sh


def _upload(c, memo_id, nom, contenu=b"contenu du fichier", champ="file"):
    r = c.post("/api/memos/%d/attachments" % memo_id,
               data={champ: (io.BytesIO(contenu), nom)},
               content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    return r


def _noms_dans_zip(resp):
    return sorted(zipfile.ZipFile(io.BytesIO(resp.data)).namelist())


# ══════════════════ A.1 — _fx_rates : 1 appel/jour maximum, jamais de 500 ══════════════════

def test_fx_served_from_cache_without_any_fetch(client, monkeypatch):
    """Le chemin nominal, et la promesse de l'invariant 6 : **un appel par jour au maximum**.

    ⚠ Le compteur n'est pas décoratif, et une mutation me l'a appris : j'avais d'abord écrit
    que la garde réseau suffirait à faire rougir un fetch intempestif. C'est faux —
    `_fx_fetch_rates` enveloppe tout dans un `except Exception`, donc il aurait avalé
    l'exception de la garde et serait retombé sur le cache, l'air de rien. C'est d'ailleurs
    pour cela que la garde de [TEST-NET-GUARD] lève une `BaseException` ; mais même ainsi,
    seul un compteur explicite prouve qu'AUCUN appel n'a été TENTÉ."""
    import app
    appels = []
    monkeypatch.setattr(app, "_fx_fetch_rates", lambda: appels.append(1))
    _seed_fx_cache({"JPY": 161.5, "EUR": 1.0}, _aujourdhui())

    r = client.get("/api/fx")
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["rates"]["JPY"] == 161.5
    assert body["base"] == "EUR"
    assert appels == [], "cache du jour présent : aucun fetch ne doit être tenté"


def test_fx_fetches_once_then_caches(client, monkeypatch):
    """Cache périmé → un fetch, puis plus rien : le second appel du jour est servi de mémoire.
    C'est ce qui borne le trafic vers api.frankfurter.app à une requête quotidienne."""
    import app
    appels = []

    def _faux_fetch():
        appels.append(1)
        return {"date": "2026-08-09", "base": "EUR", "rates": {"JPY": 170.0, "EUR": 1.0}}

    monkeypatch.setattr(app, "_fx_fetch_rates", _faux_fetch)
    _seed_fx_cache({"JPY": 100.0, "EUR": 1.0}, "2000-01-01")   # cache d'hier

    assert client.get("/api/fx").get_json()["rates"]["JPY"] == 170.0
    assert len(appels) == 1
    assert client.get("/api/fx").get_json()["rates"]["JPY"] == 170.0
    assert len(appels) == 1, "le second appel du jour ne doit PAS refetcher"


def test_fx_falls_back_to_the_stale_cache_on_failure(client, monkeypatch):
    """Réseau en panne → on sert le dernier cache connu plutôt que rien. Un widget de change
    qui affiche des taux d'hier est utile ; un widget vide ne l'est pas."""
    import app
    monkeypatch.setattr(app, "_fx_fetch_rates", lambda: None)
    _seed_fx_cache({"JPY": 155.0, "EUR": 1.0}, "2000-01-01")

    r = client.get("/api/fx")
    assert r.status_code == 200
    assert r.get_json()["rates"]["JPY"] == 155.0


def test_fx_without_cache_nor_network_is_empty_not_500(client, monkeypatch):
    """Aucun cache ET pas de réseau : réponse vide mais valide. Le convertisseur est un
    ornement — il ne doit jamais emporter la page."""
    import app
    monkeypatch.setattr(app, "_fx_fetch_rates", lambda: None)
    r = client.get("/api/fx")
    assert r.status_code == 200, r.data
    assert r.get_json() == {"date": None, "base": "EUR", "rates": None}


def test_fx_ignores_a_corrupted_cache(client, monkeypatch):
    """Un `app_state.fx_cache` illisible ne fait pas planter : il est traité comme absent."""
    import app
    monkeypatch.setattr(app, "_fx_fetch_rates", lambda: None)
    con = _db()
    try:
        con.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('fx_cache', ?)",
                    ("{pas du json",))
        con.commit()
    finally:
        con.close()
    assert client.get("/api/fx").get_json()["rates"] is None


def test_fx_public_routes_revalidate_their_token(client):
    """Les taux sont publics (aucune approbation requise) mais les routes restent sous
    `/share/*` et revalident leur jeton — invariant 5 : pas de porte ouverte sans jeton."""
    c = client
    _seed_fx_cache({"JPY": 161.5, "EUR": 1.0}, _aujourdhui())
    pid = _project(c, "Dossier")
    hub, sh = _hub_of(c, pid)

    assert c.get("/share/%s/fx" % sh["token"]).get_json()["rates"]["JPY"] == 161.5
    assert c.get("/share/hub/%s/fx" % hub["hub_token"]).get_json()["rates"]["JPY"] == 161.5

    assert c.get("/share/jeton-invente/fx").status_code == 404
    assert c.get("/share/hub/jeton-hub-invente-assez-long-pour-passer/fx").status_code == 404


# ══════════════════ A.2 — hub_send_link : le destinataire n'est jamais celui du client ══════════════════

def test_send_link_requires_proof_403(client):
    """Sans preuve, rien ne part — et un hub inconnu répond PAREIL (403 générique), sinon le
    lien deviendrait énumérable."""
    c = client
    pid = _project(c, "Dossier")
    hub, _ = _hub_of(c, pid)

    sans_preuve = c.post("/share/hub/%s/send-link" % hub["hub_token"])
    assert sans_preuve.status_code == 403, sans_preuve.data
    inconnu = c.post("/share/hub/jeton-hub-invente-assez-long-pour-passer/send-link")
    assert inconnu.status_code == 403
    assert sans_preuve.get_json() == inconnu.get_json(), "les deux refus doivent être indiscernables"


def test_send_link_without_smtp_is_400(client, monkeypatch):
    """SMTP non configuré → refus explicite, et le bouton reste visible côté front pour dire
    quoi configurer.

    ⚠ `_smtp_config()` est monkeypatché à `None` À DESSEIN, et pas laissé « au défaut des
    tests » comme le supposait le brief : `app.py` appelle `load_dotenv()` à l'import, donc sur
    une machine dont le `.env` porte de vrais identifiants — c'est le cas de celle-ci — la
    configuration SMTP est BIEN présente pendant les tests. Sans ce monkeypatch, ce test
    partait vers un vrai serveur : c'est la garde autouse qui l'a arrêté (l'échec ressortait en
    502). Le sujet du test est « quand SMTP n'est pas configuré », pas « quand cette machine
    n'a pas de .env »."""
    import app
    c = client
    pid = _project(c, "Dossier")
    hub, _ = _hub_of(c, pid)
    assert c.post("/share/hub/%s/approve" % hub["hub_token"],
                  json={"pin": hub["pin"]}).status_code == 200
    monkeypatch.setattr(app, "_smtp_config", lambda: None)

    r = c.post("/share/hub/%s/send-link" % hub["hub_token"])
    assert r.status_code == 400, r.data
    assert "non disponible" in r.get_json()["error"]


def test_send_link_forces_the_hub_email_and_masks_it(client, monkeypatch):
    """LE point de sécurité de cette route : le destinataire est **forcé** à l'e-mail du hub,
    le corps de la requête est ignoré. Un invité ne se fait pas envoyer le lien de quelqu'un
    d'autre, et ne redirige pas le sien vers une adresse qu'il choisit."""
    import app
    c = client
    pid = _project(c, "Dossier")
    hub, _ = _hub_of(c, pid)
    assert c.post("/share/hub/%s/approve" % hub["hub_token"],
                  json={"pin": hub["pin"]}).status_code == 200

    envois = []
    monkeypatch.setattr(app, "_smtp_config",
                        lambda: {"host": "h", "port": 587, "user": "u", "pwd": "x", "from": "s@ex.com"})
    monkeypatch.setattr(app, "_send_hub_invite",
                        lambda cfg, to_email, name, hub_url, pin: envois.append(
                            {"to": to_email, "url": hub_url, "pin": pin}))

    r = c.post("/share/hub/%s/send-link" % hub["hub_token"],
               json={"email": "pirate@ailleurs.test", "to": "pirate@ailleurs.test"})
    assert r.status_code == 200, r.data

    assert len(envois) == 1
    assert envois[0]["to"] == "alice@ex.com", "le destinataire du CORPS ne doit jamais être suivi"
    assert "pirate@ailleurs.test" not in json.dumps(envois)

    body = r.get_json()
    assert body["ok"] is True
    assert body["sent_to"] == "a•••@e•••.com"
    brut = json.dumps(body, ensure_ascii=False)
    assert "alice@ex.com" not in brut, "l'adresse complète ne doit pas revenir dans un payload"
    assert hub["pin"] not in brut, "le code d'accès ne doit JAMAIS transiter dans la réponse"
    assert hub["hub_token"] not in brut


def test_send_link_is_throttled_after_two_sends(client, monkeypatch):
    """Deux envois par heure et par hub : le lien porte un code d'accès, il ne doit pas servir
    d'arrosoir. Le troisième est refusé sans rien envoyer."""
    import app
    c = client
    pid = _project(c, "Dossier")
    hub, _ = _hub_of(c, pid)
    assert c.post("/share/hub/%s/approve" % hub["hub_token"],
                  json={"pin": hub["pin"]}).status_code == 200

    envois = []
    monkeypatch.setattr(app, "_smtp_config",
                        lambda: {"host": "h", "port": 587, "user": "u", "pwd": "x", "from": "s@ex.com"})
    monkeypatch.setattr(app, "_send_hub_invite",
                        lambda *a, **k: envois.append(1))
    app._RESEND_SENT.pop(hub["id"], None)   # mémoire de processus : on part d'une ardoise propre

    assert c.post("/share/hub/%s/send-link" % hub["hub_token"]).status_code == 200
    assert c.post("/share/hub/%s/send-link" % hub["hub_token"]).status_code == 200
    trop = c.post("/share/hub/%s/send-link" % hub["hub_token"])
    assert trop.status_code == 429, trop.data
    assert len(envois) == 2, "le refus doit précéder l'envoi, pas le suivre"
    app._RESEND_SENT.pop(hub["id"], None)


def test_send_link_maps_an_smtp_failure_to_502_without_leaking(client, monkeypatch):
    """Un échec SMTP devient un 502 net : ni trace du serveur, ni du mot de passe, ni du code."""
    import app
    c = client
    pid = _project(c, "Dossier")
    hub, _ = _hub_of(c, pid)
    assert c.post("/share/hub/%s/approve" % hub["hub_token"],
                  json={"pin": hub["pin"]}).status_code == 200

    def _echoue(*a, **k):
        raise RuntimeError("535 auth failed motdepasse-secret")

    monkeypatch.setattr(app, "_smtp_config",
                        lambda: {"host": "h", "port": 587, "user": "u", "pwd": "motdepasse-secret",
                                 "from": "s@ex.com"})
    monkeypatch.setattr(app, "_send_hub_invite", _echoue)
    app._RESEND_SENT.pop(hub["id"], None)

    r = c.post("/share/hub/%s/send-link" % hub["hub_token"])
    assert r.status_code == 502, r.data
    brut = json.dumps(r.get_json(), ensure_ascii=False)
    assert "motdepasse-secret" not in brut and "535" not in brut


def test_mask_email_keeps_it_recognisable_without_exposing_it(client):
    """`_mask_email` doit permettre de RECONNAÎTRE son adresse sans la republier."""
    import app
    assert app._mask_email("fabien.uhart@gmail.com") == "f•••@g•••.com"
    assert app._mask_email("a@b.fr") == "a•••@b•••.fr"
    assert app._mask_email("pas-une-adresse") == "", "tolérant : pas de « @ » → chaîne vide"
    assert app._mask_email("") == ""


# ══════════════════ B.1 — export ZIP (fichiers locaux) ══════════════════

def test_memo_zip_without_any_file_is_404(client):
    """Rien à zipper → 404, pas une archive vide qui ferait croire à une perte."""
    c = client
    mid = _memo(c, "Mémo sans pièce jointe")
    assert c.get("/api/memos/%d/download.zip" % mid).status_code == 404


def test_memo_zip_defaults_to_photos_only(client):
    """⚠ Comportement qui surprend, donc figé : le zip par défaut ne contient QUE les photos.
    Il faut `?scope=all` pour emporter les autres fichiers. Un `.txt` seul donne donc un 404,
    pas une archive vide — je l'ai découvert en voyant ce test rougir."""
    c = client
    mid = _memo(c, "Mémo avec un fichier non-image")
    _upload(c, mid, "notes.txt", b"du texte")

    assert c.get("/api/memos/%d/download.zip" % mid).status_code == 404
    assert c.get("/api/memos/%d/download.zip?scope=all" % mid).status_code == 200


def test_memo_zip_contains_its_attachment(client):
    c = client
    mid = _memo(c, "Mémo avec fichier")
    _upload(c, mid, "notes.txt", b"du texte")

    r = c.get("/api/memos/%d/download.zip?scope=all" % mid)
    assert r.status_code == 200, r.data
    assert _noms_dans_zip(r) == ["notes.txt"]
    assert zipfile.ZipFile(io.BytesIO(r.data)).read("notes.txt") == b"du texte"


def test_zip_dedupes_colliding_names_instead_of_overwriting(client):
    """Deux fichiers de même nom : l'archive doit contenir les DEUX. Écraser silencieusement
    en perdrait un — le genre de perte qu'on ne remarque qu'en ayant besoin du fichier."""
    c = client
    mid = _memo(c, "Deux fois le même nom")
    _upload(c, mid, "photo.txt", b"premier")
    _upload(c, mid, "photo.txt", b"second")

    r = c.get("/api/memos/%d/download.zip?scope=all" % mid)
    assert r.status_code == 200, r.data
    noms = _noms_dans_zip(r)
    assert noms == ["photo (2).txt", "photo.txt"], noms
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert {z.read(n) for n in noms} == {b"premier", b"second"}


def test_memo_zip_of_a_trashed_memo_is_404(client):
    """Un mémo en corbeille n'a plus de vue, donc plus de téléchargement (invariant 7)."""
    c = client
    mid = _memo(c, "Mémo à jeter")
    _upload(c, mid, "notes.txt", b"du texte")
    assert c.delete("/api/memos/%d" % mid).status_code in (200, 204)
    assert c.get("/api/memos/%d/download.zip?scope=all" % mid).status_code == 404


def test_share_zip_stays_in_scope(client):
    """Variante invitée : le zip ne franchit pas le périmètre du partage (invariant 5)."""
    c = client
    dedans = _project(c, "Dossier partagé")
    dehors = _project(c, "Dossier privé")
    m_ok = _memo(c, "Dans le partage", project_id=dedans)
    m_ko = _memo(c, "Hors du partage", project_id=dehors)
    _upload(c, m_ok, "ok.txt", b"visible")
    _upload(c, m_ko, "secret.txt", b"invisible")
    sh = _share(c, dedans)

    r = c.get("/share/%s/memo/%d/download.zip?scope=all" % (sh["token"], m_ok))
    assert r.status_code == 200, r.data
    assert _noms_dans_zip(r) == ["ok.txt"]

    assert c.get("/share/%s/memo/%d/download.zip?scope=all"
                 % (sh["token"], m_ko)).status_code == 404
    assert c.get("/share/jeton-invente/memo/%d/download.zip?scope=all"
                 % m_ok).status_code == 404


# ══════════════════ B.2 — branche vocale de _soft_delete_comment ══════════════════

def _fichier_de(memo_id):
    con = _db()
    try:
        return con.execute("SELECT * FROM attachments WHERE memo_id = ? ORDER BY id DESC LIMIT 1",
                           (memo_id,)).fetchone()
    finally:
        con.close()


def _commentaires(memo_id):
    con = _db()
    try:
        return con.execute("SELECT * FROM memo_comments WHERE memo_id = ? ORDER BY id",
                           (memo_id,)).fetchall()
    finally:
        con.close()


def test_deleting_a_voice_comment_purges_file_and_system_line(client):
    """Un message vocal, c'est trois choses : un fichier, une ligne système « 📎 a ajouté … »
    qui l'annonce, et la bulle qui le porte. Le supprimer doit les emporter toutes les trois —
    sinon la ligne système réapparaîtrait, orpheline, à annoncer un fichier qui n'existe plus."""
    import app
    c = client
    mid = _memo(c, "Mémo porteur")
    _upload(c, mid, "vocal.m4a", b"\x00\x01du son")
    att = _fichier_de(mid)
    chemin = os.path.join(app.UPLOAD_DIR, att["filename"])
    assert os.path.isfile(chemin)

    lignes = _commentaires(mid)
    assert any(l["body"].startswith("📎") and "vocal.m4a" in l["body"] for l in lignes), \
        "l'upload doit avoir posé sa ligne système"

    bulle = c.post("/api/memos/%d/comments" % mid,
                   json={"body": "[audio:%s]" % att["filename"]})
    assert bulle.status_code in (200, 201), bulle.data
    cid = bulle.get_json()["id"]

    assert c.delete("/api/comments/%d" % cid).status_code in (200, 204)

    assert not os.path.exists(chemin), "le fichier vocal doit être PURGÉ du volume"
    assert _fichier_de(mid) is None, "la ligne attachments doit partir avec lui"
    restes = _commentaires(mid)
    assert not any(l["body"].startswith("📎") for l in restes), \
        "la ligne système annonçait un fichier qui n'existe plus : elle doit disparaître"
    tombale = [l for l in restes if l["id"] == cid][0]
    assert tombale["body"] == "" and (tombale["deleted_at"] or "") != ""


def test_soft_delete_is_idempotent(client):
    """Re-supprimer une tombale ne fait rien — et surtout ne relance pas la purge (le fichier
    d'un autre message pourrait porter le même nom d'origine)."""
    import app
    c = client
    mid = _memo(c, "Mémo porteur")
    cid = c.post("/api/memos/%d/comments" % mid, json={"body": "Un message"}).get_json()["id"]
    assert c.delete("/api/comments/%d" % cid).status_code in (200, 204)

    con = _db()
    try:
        avant = dict(con.execute("SELECT * FROM memo_comments WHERE id = ?", (cid,)).fetchone())
        ligne = con.execute("SELECT * FROM memo_comments WHERE id = ?", (cid,)).fetchone()
    finally:
        con.close()

    with app.app.app_context():
        db = app.get_db()
        app._soft_delete_comment(db, ligne)
        db.commit()

    con = _db()
    try:
        apres = dict(con.execute("SELECT * FROM memo_comments WHERE id = ?", (cid,)).fetchone())
    finally:
        con.close()
    assert apres == avant, "une seconde suppression ne doit rien changer, pas même l'horodatage"
