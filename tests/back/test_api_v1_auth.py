"""[DASH-API] § 1 — la porte de l'API v1 : un Bearer valide, rien d'autre.

Brief : `docs/briefs/DASH-API.md` § 1 (1.1 → 1.4, 1.7). C'est la partie à écrire EN PREMIER :
l'API est exposée hors Authelia (règle bypass `/api/v1/*`), donc le jeton est la SEULE porte.

Ce que ces tests PROTÈGENT :

- sans jeton, avec le seul cookie de session, avec un jeton inconnu, révoqué ou expiré → **401**
  et un corps `{}` qui ne dit rien (ni « expiré » ni « révoqué » : pas d'indice pour deviner) ;
- un jeton `read` qui écrit → **403** ; un jeton `read,write` écrit ;
- un jeton valide met `last_used_at` à jour ;
- quotas : 120 lectures/min, 30 écritures/min par jeton → **429** + `Retry-After` ; 20 tentatives/min
  sans jeton par IP → 429 ;
- en-têtes `Cache-Control: no-store` + `X-Content-Type-Options: nosniff` sur toute réponse v1 ;
- corps > 256 Ko → **413** ;
- le jeton en clair n'apparaît ni dans l'export, ni dans `api_audit` ; l'export ne porte pas de
  table `api_tokens` ; le jeton n'est stocké qu'en empreinte sha256 ;
- l'audit enregistre lectures ET écritures, sans jamais le contenu du mémo.

Les jetons se créent par les routes OWNER `/api/tokens` (derrière Authelia en prod) — c'est ce que
fera l'onglet Paramètres › Appareils connectés.
"""
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit


def _mk_token(client, name="Claude Code", scopes="read,write", source="claude-code", expires_at=""):
    r = client.post("/api/tokens", json={"name": name, "scopes": scopes, "source": source,
                                         "expires_at": expires_at})
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["token"].startswith("dash_") and len(body["token"]) >= 40
    return body


def _bearer(tok):
    return {"Authorization": "Bearer " + tok}


def _db(app_module):
    con = sqlite3.connect(app_module.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------------ 401 / 403


def test_sans_jeton_401_corps_vide(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.get_json() == {}


def test_le_cookie_de_session_ne_vaut_rien(client):
    """Invariant 10 : l'API ne lit JAMAIS le cookie — un navigateur connecté à Authelia qui tape
    `/api/v1/…` sans Bearer reçoit 401, exactement comme un inconnu."""
    r = client.get("/api/v1/me", headers={"Cookie": "authelia_session=abcdef0123456789"})
    assert r.status_code == 401 and r.get_json() == {}


def test_jeton_inconnu_401(client):
    r = client.get("/api/v1/me", headers=_bearer("dash_" + "x" * 40))
    assert r.status_code == 401 and r.get_json() == {}


def test_jeton_valide_me(client):
    t = _mk_token(client, name="Mon Mac", scopes="read", source="cli")
    r = client.get("/api/v1/me", headers=_bearer(t["token"]))
    assert r.status_code == 200
    me = r.get_json()
    assert me["name"] == "Mon Mac" and me["scopes"] == ["read"] and me["source"] == "cli"
    assert "expires_at" in me
    assert "token" not in me and "token_hash" not in me


def test_jeton_revoque_401_sans_indice(client):
    t = _mk_token(client)
    assert client.get("/api/v1/me", headers=_bearer(t["token"])).status_code == 200
    assert client.delete("/api/tokens/%d" % t["id"]).status_code == 204
    r = client.get("/api/v1/me", headers=_bearer(t["token"]))
    assert r.status_code == 401 and r.get_json() == {}


def test_jeton_expire_401_sans_indice(client):
    passe = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    t = _mk_token(client, expires_at=passe)
    r = client.get("/api/v1/me", headers=_bearer(t["token"]))
    assert r.status_code == 401 and r.get_json() == {}


def test_jeton_futur_ok(client):
    futur = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    t = _mk_token(client, expires_at=futur)
    assert client.get("/api/v1/me", headers=_bearer(t["token"])).status_code == 200


def test_scope_read_ne_peut_pas_ecrire_403(client):
    t = _mk_token(client, scopes="read")
    r = client.post("/api/v1/memos", json={"title": "interdit"}, headers=_bearer(t["token"]))
    assert r.status_code == 403
    assert client.get("/api/memos").get_json() == []


def test_scope_write_ecrit(client):
    t = _mk_token(client, scopes="read,write")
    r = client.post("/api/v1/memos", json={"title": "permis"}, headers=_bearer(t["token"]))
    assert r.status_code == 201, r.data


def test_mauvais_schema_authorization_401(client):
    t = _mk_token(client)
    r = client.get("/api/v1/me", headers={"Authorization": "Basic " + t["token"]})
    assert r.status_code == 401 and r.get_json() == {}


# ------------------------------------------------------------------ hygiène


def test_entetes_no_store_nosniff(client):
    t = _mk_token(client)
    for r in (client.get("/api/v1/me", headers=_bearer(t["token"])), client.get("/api/v1/me")):
        assert r.headers.get("Cache-Control") == "no-store", dict(r.headers)
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("Content-Type", "").startswith("application/json")


def test_last_used_at_mis_a_jour(client, app_module):
    t = _mk_token(client)
    con = _db(app_module)
    try:
        avant = con.execute("SELECT last_used_at FROM api_tokens WHERE id = ?", (t["id"],)).fetchone()[0]
        assert not avant
        client.get("/api/v1/me", headers=_bearer(t["token"]))
        apres = con.execute("SELECT last_used_at FROM api_tokens WHERE id = ?", (t["id"],)).fetchone()[0]
    finally:
        con.close()
    assert apres and apres[:4] == str(datetime.now(timezone.utc).year)
    liste = client.get("/api/tokens").get_json()
    moi = [x for x in liste if x["id"] == t["id"]][0]
    assert moi["last_used_at"] == apres
    assert "token" not in moi and "token_hash" not in moi


def test_seule_l_empreinte_est_stockee(client, app_module):
    t = _mk_token(client)
    con = _db(app_module)
    try:
        row = con.execute("SELECT * FROM api_tokens WHERE id = ?", (t["id"],)).fetchone()
        assert row["token_hash"] == hashlib.sha256(t["token"].encode()).hexdigest()
        assert t["token"] not in " ".join(str(v) for v in dict(row).values())
    finally:
        con.close()


def test_le_jeton_n_est_ni_dans_l_export_ni_dans_l_audit(client, app_module):
    t = _mk_token(client)
    client.get("/api/v1/me", headers=_bearer(t["token"]))
    client.post("/api/v1/memos", json={"title": "secret", "content_text": "corps à ne pas tracer"},
                headers=_bearer(t["token"]))
    exp = client.get("/api/export")
    assert exp.status_code == 200
    brut = exp.get_data(as_text=True)
    assert t["token"] not in brut
    assert hashlib.sha256(t["token"].encode()).hexdigest() not in brut
    assert "api_tokens" not in exp.get_json() and "api_audit" not in exp.get_json()
    con = _db(app_module)
    try:
        rows = con.execute("SELECT * FROM api_audit").fetchall()
    finally:
        con.close()
    assert rows, "l'audit doit tracer les appels"
    tout = " ".join(" ".join(str(v) for v in dict(r).values()) for r in rows)
    assert t["token"] not in tout
    assert "corps à ne pas tracer" not in tout, "l'audit ne porte JAMAIS le contenu"
    assert "secret" not in tout, "ni le titre"


def test_audit_trace_lecture_et_ecriture(client, app_module):
    t = _mk_token(client)
    m = client.post("/api/v1/memos", json={"title": "tracé"}, headers=_bearer(t["token"])).get_json()
    client.get("/api/v1/memos/%d" % m["id"], headers=_bearer(t["token"]))
    con = _db(app_module)
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM api_audit ORDER BY id").fetchall()]
    finally:
        con.close()
    methods = [(r["method"], r["route"], r["status"], r["token_id"], r["memo_id"]) for r in rows]
    assert ("POST", "/api/v1/memos", 201, t["id"], m["id"]) in methods
    assert ("GET", "/api/v1/memos/<memo_id>", 200, t["id"], m["id"]) in methods
    for r in rows:
        assert len(r["args_summary"] or "") <= 200
        assert r["ip"]
    # l'audit se lit aussi côté owner (Paramètres), filtrable par jeton
    a = client.get("/api/tokens/audit?token_id=%d&limit=50" % t["id"])
    assert a.status_code == 200 and len(a.get_json()) >= 2


def test_un_401_est_aussi_trace_sans_jeton(client, app_module):
    client.get("/api/v1/me", headers=_bearer("dash_" + "y" * 40))
    con = _db(app_module)
    try:
        rows = con.execute("SELECT token_id, status FROM api_audit").fetchall()
    finally:
        con.close()
    assert (None, 401) in [tuple(r) for r in rows]


# ------------------------------------------------------------------ quotas


def test_quota_lecture_120_par_minute(client):
    t = _mk_token(client)
    h = _bearer(t["token"])
    for i in range(120):
        assert client.get("/api/v1/me", headers=h).status_code == 200, "appel %d" % i
    r = client.get("/api/v1/me", headers=h)
    assert r.status_code == 429
    assert r.headers.get("Retry-After"), "Retry-After attendu"


def test_quota_ecriture_30_par_minute(client):
    t = _mk_token(client)
    h = _bearer(t["token"])
    for i in range(30):
        assert client.post("/api/v1/memos", json={"title": "m%d" % i}, headers=h).status_code == 201
    r = client.post("/api/v1/memos", json={"title": "trop"}, headers=h)
    assert r.status_code == 429 and r.headers.get("Retry-After")
    # le quota de lecture est distinct : lire marche encore
    assert client.get("/api/v1/me", headers=h).status_code == 200


def test_quota_ip_sans_jeton_20_par_minute(client):
    for i in range(20):
        assert client.get("/api/v1/me").status_code == 401, "tentative %d" % i
    r = client.get("/api/v1/me")
    assert r.status_code == 429 and r.headers.get("Retry-After")


def test_corps_trop_gros_413(client):
    t = _mk_token(client)
    gros = "x" * (256 * 1024 + 10)
    r = client.post("/api/v1/memos", json={"title": "gros", "content_text": gros}, headers=_bearer(t["token"]))
    assert r.status_code == 413


# ------------------------------------------------------------------ gestion owner


def test_creation_valide_les_champs(client):
    assert client.post("/api/tokens", json={"name": "", "scopes": "read", "source": "cli"}).status_code == 400
    assert client.post("/api/tokens", json={"name": "x", "scopes": "admin", "source": "cli"}).status_code == 400
    assert client.post("/api/tokens", json={"name": "x", "scopes": "read", "source": "martien"}).status_code == 400
    assert client.post("/api/tokens", json={"name": "x", "scopes": "read", "source": "cli",
                                            "expires_at": "pas-une-date"}).status_code == 400


def test_la_liste_owner_ne_montre_jamais_le_jeton(client):
    t = _mk_token(client)
    liste = client.get("/api/tokens").get_json()
    brut = str(liste)
    assert t["token"] not in brut and "token_hash" not in brut
    assert [x["name"] for x in liste] == ["Claude Code"]
    assert liste[0]["revoked_at"] == "" and liste[0]["scopes"] == "read,write"


def test_les_routes_tokens_ne_sont_pas_sous_api_v1(app_module):
    """La gestion des jetons est un acte du PROPRIÉTAIRE (derrière Authelia) : l'API ne gère pas
    les jetons (§ 1.6), sinon un jeton volé en fabriquerait d'autres."""
    rules = [r.rule for r in app_module.app.url_map.iter_rules()]
    assert "/api/tokens" in rules
    assert not any(r.startswith("/api/v1/tokens") for r in rules)
