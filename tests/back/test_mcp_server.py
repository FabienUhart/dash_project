"""[DASH-MCP] lot B — le serveur MCP est une FAÇADE de l'API v1 : aucune règle métier, tout passe par
`require_token`, l'audit et les quotas de l'API (invariant 10 par construction).

Brief : `docs/briefs/DASH-MCP.md` § 3. Montage : le Flask de test (fixture `client` = base vierge) est
branché DERRIÈRE le MCP par `httpx.WSGITransport` (le MCP ne sort pas sur le réseau), et le vrai client
MCP du SDK parle au serveur en ASGI par `httpx.ASGITransport` — le protocole Streamable HTTP complet
(initialize → tools/list → tools/call), pas des JSON-RPC bricolés.

Ce que ces tests PROTÈGENT :
1. `/mcp/` sans jeton (ni dans l'URL ni en Bearer) → 401 avant tout ;
2. un jeton RÉVOQUÉ dans l'URL → l'outil répond l'erreur « jeton invalide ou révoqué » (c'est l'API qui
   tranche, le MCP ne valide rien) ;
3. `tools/list` = les 21 outils du brief + `get_notifications` ([NOTIF-CENTER]), chacun avec une description française non vide ;
4. `get_counts` rend exactement `/counts` ;
5. `create_memo` écrit en base avec la `source` du jeton et laisse une ligne d'audit API ;
6. `delete_memo` = CORBEILLE (jamais une purge), `get_memo` ensuite → erreur « introuvable ou en corbeille » ;
7. jeton `read` → `create_memo` renvoie l'erreur « lecture seule » (403 de l'API) ;
8. `get_context("ipad")` contient le titre attendu, UNE seule fois (dédoublonnage) ;
9. `X-Dash-Client` reçu par l'API → `client_name` / `last_seen_version` posés sur le jeton ;
10. le journal du MCP ne contient JAMAIS le jeton (chemin masqué `/mcp/***/`) ;
11. `GET /api/v1/client-versions` répond la constante, protégé par jeton ;
12. le MCP n'appelle QUE `/api/v1/*` (garde du client HTTP) et Flask n'a aucune route `/mcp`.
"""
import json
import logging
import sqlite3

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mk_token(client, scopes="read,write", source="claude-chat", name="Claude chat"):
    r = client.post("/api/tokens", json={"name": name, "scopes": scopes, "source": source})
    assert r.status_code == 201, r.data
    return r.get_json()


class _Ns:
    pass


@pytest.fixture
def mcp_app(app_module, monkeypatch):
    """Une instance FRAÎCHE du serveur MCP (`build_app`), son client HTTP rebranché sur le Flask de test
    (WSGI, zéro réseau). Le gestionnaire de sessions Streamable HTTP est démarré par `_Session` (lifespan)."""
    import dash_mcp.server as srv
    monkeypatch.setattr(srv, "API_BASE", "http://api.test")
    monkeypatch.setattr(srv, "API_TRANSPORT", httpx.WSGITransport(app=app_module.app))
    ns = _Ns()
    ns.mcp, ns.app = srv.build_app()
    ns.MCP_VERSION = srv.MCP_VERSION
    ns._api_path = srv._api_path
    return ns


def _http_client_for(mcp_app, headers=None):
    """Le client httpx que `streamable_http_client` (API courante du SDK 1.30, non dépréciée) utilise :
    branché en ASGI sur notre serveur, pas sur le réseau."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app.app), base_url="http://mcp.test",
                             headers=headers, timeout=30.0, follow_redirects=True)


class _Session:
    """Petit contexte : ouvre une session MCP (streamable HTTP) sur `url`."""

    def __init__(self, mcp_app, url, headers=None):
        self.mcp_app, self.url, self.headers = mcp_app, url, headers

    async def __aenter__(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        self._life = self.mcp_app.mcp.session_manager.run()   # lifespan : ASGITransport ne le joue pas
        await self._life.__aenter__()
        self._http = _http_client_for(self.mcp_app, self.headers)
        await self._http.__aenter__()
        self._cm = streamable_http_client(self.url, http_client=self._http)
        read, write, _ = await self._cm.__aenter__()
        self._sess = ClientSession(read, write)
        await self._sess.__aenter__()
        await self._sess.initialize()
        return self._sess

    async def __aexit__(self, *exc):
        await self._sess.__aexit__(*exc)
        await self._cm.__aexit__(*exc)
        await self._http.__aexit__(*exc)
        await self._life.__aexit__(*exc)


def _text(result):
    return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def _json(result):
    return json.loads(_text(result))


def _db(app_module):
    con = sqlite3.connect(app_module.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


TOOLS = {
    "get_tree", "list_memos", "get_memo", "search_memos", "get_counts", "get_plan", "whoami", "get_context", "get_notifications",
    "create_memo", "update_memo", "append_to_memo", "move_memo", "complete_memo", "reopen_memo", "add_subtask",
    "toggle_subtask", "add_url", "add_comment", "delete_memo", "restore_memo", "create_folder",
}


# ------------------------------------------------------------------ 1


@pytest.mark.anyio
async def test_sans_jeton_401_avant_tout(client, mcp_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app.app), base_url="http://mcp.test") as c:
        for path in ("/mcp/", "/mcp"):
            r = await c.post(path, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                             headers={"Accept": "application/json, text/event-stream"})
            assert r.status_code == 401, (path, r.status_code, r.text)
            assert r.json() == {}
            assert r.headers.get("cache-control") == "no-store"
        r = await c.post("/mcp/pas-un-jeton/", json={}, headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 401


# ------------------------------------------------------------------ 2


@pytest.mark.anyio
async def test_jeton_revoque_erreur_lisible(client, mcp_app):
    t = _mk_token(client)
    assert client.delete("/api/tokens/%d" % t["id"]).status_code == 204
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("get_counts", {})
        assert res.isError, _text(res)
        assert "jeton invalide ou révoqué" in _text(res).lower()


# ------------------------------------------------------------------ 3


@pytest.mark.anyio
async def test_tools_list_21_outils_decrits(client, mcp_app):
    t = _mk_token(client)
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        tools = (await s.list_tools()).tools
    names = {x.name for x in tools}
    assert names == TOOLS, names ^ TOOLS
    assert len(tools) == 22   # [NOTIF-CENTER] + get_notifications
    for x in tools:
        assert x.description and len(x.description.strip()) > 15, x.name
        assert "é" in x.description or "è" in x.description or " le " in x.description or " un " in x.description or " la " in x.description, \
            "description en français attendue : %s" % x.name
    # arguments typés : create_memo exige title, toggle_subtask exige id/index/done
    cm = [x for x in tools if x.name == "create_memo"][0]
    assert "title" in cm.inputSchema["properties"] and "content_text" in cm.inputSchema["properties"]
    ts = [x for x in tools if x.name == "toggle_subtask"][0]
    assert set(ts.inputSchema.get("required", [])) >= {"id", "index", "done"}


# ------------------------------------------------------------------ 4


@pytest.mark.anyio
async def test_get_counts_egale_l_api(client, mcp_app):
    t = _mk_token(client)
    client.post("/api/memos", json={"title": "a", "due_date": "2000-01-01"})
    client.post("/api/memos", json={"title": "b"})
    attendu = client.get("/api/v1/counts", headers={"Authorization": "Bearer " + t["token"]}).get_json()
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("get_counts", {})
    assert not res.isError, _text(res)
    assert _json(res) == attendu and attendu["all"] == 2 and attendu["overdue"] == 1


# ------------------------------------------------------------------ 5


@pytest.mark.anyio
async def test_create_memo_source_et_audit(client, mcp_app, app_module):
    t = _mk_token(client, source="claude-chat")
    f = client.post("/api/projects", json={"name": "Dash"}).get_json()
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("create_memo", {"title": "Depuis Claude", "content_text": "ligne 1\n\nligne 2 & fin",
                                                "folder_id": f["id"], "due_date": "2026-11-01", "tags": ["mcp"]})
    assert not res.isError, _text(res)
    m = _json(res)
    assert m["title"] == "Depuis Claude" and m["source"] == "claude-chat" and m["project_id"] == f["id"]
    assert m["content"] == "<p>ligne 1</p><p>ligne 2 &amp; fin</p><p>#mcp</p>"
    con = _db(app_module)
    try:
        row = con.execute("SELECT source, title FROM memos WHERE id = ?", (m["id"],)).fetchone()
        audit = con.execute("SELECT method, route, status, token_id FROM api_audit WHERE memo_id = ?", (m["id"],)).fetchall()
    finally:
        con.close()
    assert row["source"] == "claude-chat"
    assert ("POST", "/api/v1/memos", 201, t["id"]) in [tuple(a) for a in audit], [tuple(a) for a in audit]


# ------------------------------------------------------------------ 6


@pytest.mark.anyio
async def test_delete_memo_est_une_corbeille(client, mcp_app):
    t = _mk_token(client)
    m = client.post("/api/memos", json={"title": "à jeter"}).get_json()
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("delete_memo", {"id": m["id"]})
        assert not res.isError, _text(res)
        res2 = await s.call_tool("get_memo", {"id": m["id"]})
    assert res2.isError
    assert "introuvable ou en corbeille" in _text(res2).lower()
    assert m["id"] in [x["id"] for x in client.get("/api/trash").get_json()], "le mémo doit être EN CORBEILLE, pas purgé"


# ------------------------------------------------------------------ 7


@pytest.mark.anyio
async def test_jeton_lecture_seule_403_lisible(client, mcp_app):
    t = _mk_token(client, scopes="read")
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("create_memo", {"title": "interdit"})
        ok = await s.call_tool("get_counts", {})
    assert res.isError and "lecture seule" in _text(res).lower()
    assert not ok.isError
    assert client.get("/api/memos").get_json() == []


# ------------------------------------------------------------------ 8


@pytest.mark.anyio
async def test_get_context_trouve_et_dedoublonne(client, mcp_app):
    t = _mk_token(client)
    f = client.post("/api/projects", json={"name": "Apple"}).get_json()
    cible = client.post("/api/memos", json={"title": "Réparation iPad", "content": "<p>suivi UPS</p>",
                                           "project_id": f["id"], "due_date": "2026-10-18",
                                           "subtasks": [{"content": "appeler", "done": False}]}).get_json()
    client.post("/api/memos", json={"title": "Courses"})
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("get_context", {"keywords": "ipad"})
    assert not res.isError, _text(res)
    txt = _text(res)
    assert "Réparation iPad" in txt
    # le mémo est à la fois « trouvé », « récent » et « daté » : il ne doit sortir qu'UNE fois
    assert txt.count("Réparation iPad") == 1, txt
    assert "Apple" in txt and "appeler" in txt and "suivi UPS" in txt
    assert "Courses" in txt, "les derniers mémos modifiés font partie du contexte"
    assert "#%d" % cible["id"] in txt
    # Dates en heure de PARIS, lisibles — pas l'ISO UTC brut de la base (« 2026-10-18T12:43:10+00:00 »)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    attendu = datetime.fromisoformat(cible["updated_at"]).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
    assert "modifié " + attendu in txt, (attendu, txt)
    assert "échéance 18/10/2026" in txt
    assert "T" + cible["updated_at"][11:16] not in txt and "+00:00" not in txt, "ISO UTC brut dans le contexte"


# ------------------------------------------------------------------ 9


@pytest.mark.anyio
async def test_x_dash_client_pose_la_version_sur_le_jeton(client, mcp_app, app_module):
    t = _mk_token(client)
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        res = await s.call_tool("whoami", {})
    assert not res.isError, _text(res)
    con = _db(app_module)
    try:
        row = con.execute("SELECT client_name, client_version, last_seen_version FROM api_tokens WHERE id = ?", (t["id"],)).fetchone()
    finally:
        con.close()
    assert row["client_name"] == "mcp"
    assert row["last_seen_version"] == mcp_app.MCP_VERSION and row["client_version"] == mcp_app.MCP_VERSION
    liste = client.get("/api/tokens").get_json()
    moi = [x for x in liste if x["id"] == t["id"]][0]
    assert moi["client_name"] == "mcp" and moi["last_seen_version"] == mcp_app.MCP_VERSION
    # et l'export ne porte pas ces colonnes (non exportées, comme le reste de api_tokens)
    assert "api_tokens" not in client.get("/api/export").get_json()


# ------------------------------------------------------------------ 10


@pytest.mark.anyio
async def test_le_journal_ne_contient_jamais_le_jeton(client, mcp_app, caplog):
    t = _mk_token(client)
    caplog.set_level(logging.DEBUG)
    async with _Session(mcp_app, "http://mcp.test/mcp/%s/" % t["token"]) as s:
        await s.call_tool("get_counts", {})
    import dash_mcp.server as srv
    m2, app2 = srv.build_app()   # 2e instance : un gestionnaire de sessions ne démarre qu'une fois
    async with m2.session_manager.run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://mcp.test") as c:
            r = await c.post("/mcp/", headers={"Authorization": "Bearer " + t["token"], "Accept": "application/json, text/event-stream"},
                             json={"jsonrpc": "2.0", "id": 9, "method": "ping"})
            assert r.status_code < 500, r.text
    # Seuls les loggers SERVEUR comptent : le client SDK du test (`mcp.client.*`, httpx) loggue l'URL
    # en DEBUG, mais il tourne chez Claude, pas chez nous — ce que ce test fige, c'est que NOTRE serveur
    # (dash.mcp, mcp.server.*, uvicorn, starlette) n'écrit jamais le jeton.
    serveur = "\n".join(r.getMessage() for r in caplog.records
                        if not r.name.startswith(("mcp.client", "httpx", "httpcore", "anyio")))
    assert t["token"] not in serveur, "le jeton est apparu dans un log serveur"
    assert t["token"][5:] not in serveur
    lignes = [r.getMessage() for r in caplog.records if r.name == "dash.mcp"]
    assert lignes, "le MCP doit journaliser ses accès (chemin masqué)"
    assert any("/mcp/***/" in l for l in lignes), lignes


# ------------------------------------------------------------------ 11


def test_client_versions_protege_et_constant(client, app_module):
    assert client.get("/api/v1/client-versions").status_code == 401
    t = _mk_token(client)
    r = client.get("/api/v1/client-versions", headers={"Authorization": "Bearer " + t["token"]})
    assert r.status_code == 200
    body = r.get_json()
    assert body == app_module.CLIENT_VERSIONS
    assert set(body.keys()) == {"mcp", "cli", "extension"} and body["mcp"]
    import dash_mcp.server as srv
    assert body["mcp"] == srv.MCP_VERSION, "la constante de l'API et la version du MCP doivent être la même"


# ------------------------------------------------------------------ 12


def test_le_mcp_n_appelle_que_api_v1_et_flask_n_a_pas_de_route_mcp(app_module):
    import dash_mcp.server as srv
    with pytest.raises(ValueError):
        srv._api_path("/api/trash/1")
    with pytest.raises(ValueError):
        srv._api_path("/api/tokens")
    assert srv._api_path("/memos/1") == "/api/v1/memos/1"
    assert not [r.rule for r in app_module.app.url_map.iter_rules() if r.rule.startswith("/mcp")]
