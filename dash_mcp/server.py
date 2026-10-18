"""[DASH-MCP] lot B — serveur MCP distant, FAÇADE de l'API v1 du dashboard.

Pourquoi : Claude (chat claude.ai, Claude Code) lit et écrit dans le dashboard sans passer par Chrome.
Le connecteur claude.ai appelle un serveur MCP distant en HTTPS et ne sait pas envoyer d'en-tête : le
jeton voyage donc DANS LE CHEMIN (`/mcp/<jeton>/`), ou en `Authorization: Bearer` pour Claude Code et le
CLI. Ce serveur ne contient AUCUNE règle métier et ne valide pas le jeton : chaque outil est un appel
HTTP à `/api/v1/…` (`require_token`, audit, quotas — invariant 10 par construction). Un 401 de l'API
devient l'erreur d'outil « jeton invalide ou révoqué ».

Hygiène : le chemin complet n'est JAMAIS journalisé (le jeton y est) — le middleware écrit `/mcp/***/`
et uvicorn est lancé avec `--no-access-log` (bin/start.sh). `Cache-Control: no-store` partout.

Paquet nommé `dash_mcp` (et non `mcp/` comme le brief) : un dossier `mcp/` à la racine du projet
masquerait le SDK officiel `mcp` sur `sys.path` et casserait `from mcp.server.fastmcp import FastMCP`.

Lancement : `uvicorn dash_mcp.server:app --host 0.0.0.0 --port 8100 --no-access-log --proxy-headers`.
Tests : `tests/back/test_mcp_server.py` branche `API_TRANSPORT` sur le Flask de test (zéro réseau).
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import anyio
import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

MCP_VERSION = "1.0.0"
API_BASE = os.environ.get("DASH_API_BASE", "http://127.0.0.1:8099")
API_TRANSPORT = None            # tests : httpx.WSGITransport(app=flask_app)
API_TIMEOUT = 30.0
CONTENT_MAX = 256 * 1024        # même plafond que l'API (413)
TOKEN_RE = re.compile(r"^dash_[A-Za-z0-9_-]{20,120}$")

log = logging.getLogger("dash.mcp")



# ───────────────────────── client HTTP vers l'API v1 ─────────────────────────

def _api_path(path):
    """Seul `/api/v1/*` est joignable depuis le MCP : une route owner (`/api/trash`, `/api/tokens`…) lève."""
    p = "/api/v1" + path if path.startswith("/") and not path.startswith("/api/") else path
    if not p.startswith("/api/v1/"):
        raise ValueError("le MCP ne parle qu'à /api/v1 : %s" % path)
    return p


def _client():
    return httpx.Client(base_url=API_BASE, transport=API_TRANSPORT, timeout=API_TIMEOUT)


def _token_of(ctx: Context) -> str:
    req = ctx.request_context.request
    tok = ""
    if req is not None:
        tok = (req.scope.get("state") or {}).get("dash_token", "") or ""
    if not tok:
        raise ToolError("jeton absent : appelle /mcp/<jeton>/ ou envoie Authorization: Bearer")
    return tok


def _client_label(ctx: Context) -> str:
    try:
        return (ctx.session.client_params.clientInfo.name or "unknown")[:60]
    except Exception:
        return "unknown"


def _call(ctx: Context, method: str, path: str, params=None, body=None):
    """Un appel API, synchrone (httpx) — exécuté hors de la boucle par `_acall`."""
    headers = {
        "Authorization": "Bearer " + _token_of(ctx),
        "X-Dash-Client": "mcp/%s (%s)" % (MCP_VERSION, _client_label(ctx)),
        "Accept": "application/json",
    }
    with _client() as c:
        r = c.request(method, _api_path(path), params=params, json=body, headers=headers)
    if r.status_code == 401:
        raise ToolError("jeton invalide ou révoqué : recrée un jeton dans Paramètres › Appareils connectés")
    if r.status_code == 403:
        raise ToolError("jeton en lecture seule : cette action demande les droits « lecture + écriture »")
    if r.status_code == 404:
        detail = ""
        try:
            detail = (r.json() or {}).get("error") or ""
        except Exception:
            pass
        if "dossier" in detail or "parent" in detail or "folder" in detail:
            raise ToolError("dossier introuvable")
        raise ToolError("mémo introuvable ou en corbeille")
    if r.status_code == 429:
        raise ToolError("quota dépassé, réessaie dans %s s" % (r.headers.get("Retry-After") or "60"))
    if r.status_code == 413:
        raise ToolError("contenu trop volumineux (256 Ko max)")
    if r.status_code >= 400:
        try:
            msg = (r.json() or {}).get("error") or r.text
        except Exception:
            msg = r.text
        raise ToolError("l'API a refusé (%d) : %s" % (r.status_code, str(msg)[:300]))
    if r.status_code == 204 or not r.content:
        return {"ok": True}
    return r.json()


async def _acall(ctx, method, path, params=None, body=None):
    return await anyio.to_thread.run_sync(lambda: _call(ctx, method, path, params, body))


def _check_size(*texts):
    for t in texts:
        if t and len(t.encode("utf-8")) > CONTENT_MAX:
            raise ToolError("contenu trop volumineux (256 Ko max)")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# ───────────────────────── outils — LECTURE ─────────────────────────

async def get_tree(ctx: Context) -> dict:
    return await _acall(ctx, "GET", "/tree")


async def list_memos(ctx: Context, filter: str | None = None, folder_id: int | None = None, subtree: bool = False,
                     sort: str | None = None, limit: int = 50, cursor: str | None = None) -> dict:
    params = _clean({"filter": filter, "folder": folder_id, "subtree": 1 if subtree else None, "sort": sort,
                     "limit": max(1, min(200, limit)), "cursor": cursor})
    return await _acall(ctx, "GET", "/memos", params=params)


async def get_memo(ctx: Context, id: int) -> dict:
    return await _acall(ctx, "GET", "/memos/%d" % id)


async def search_memos(ctx: Context, q: str, folder_id: int | None = None, tag: str | None = None,
                       due_from: str | None = None, due_to: str | None = None, limit: int = 50) -> dict:
    params = _clean({"q": q, "folder": folder_id, "tag": tag, "due_from": due_from, "due_to": due_to,
                     "limit": max(1, min(200, limit))})
    return await _acall(ctx, "GET", "/search", params=params)


async def get_counts(ctx: Context, folder_id: int | None = None) -> dict:
    params = _clean({"folder": folder_id, "subtree": 1 if folder_id else None})
    return await _acall(ctx, "GET", "/counts", params=params)


async def get_plan(ctx: Context) -> dict:
    return await _acall(ctx, "GET", "/plan")


async def whoami(ctx: Context) -> dict:
    return await _acall(ctx, "GET", "/me")


PARIS = ZoneInfo("Europe/Paris")


def _fmt_dt(iso: str) -> str:
    """Instant ISO (UTC en base) → « 18/10 14:43 » en heure de Paris ; brut si illisible."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PARIS).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(iso)[:16]


def _fmt_day(day: str) -> str:
    """Date « YYYY-MM-DD » (sans fuseau) → « 20/10/2026 » ; brut si illisible."""
    try:
        return datetime.strptime(str(day), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(day)


def _compact(m: dict, folders: dict) -> str:
    """Un mémo en 3-5 lignes de texte : l'outil `get_context` nourrit Claude, pas un écran."""
    lignes = []
    titre = (m.get("title") or (m.get("content_text") or "")[:60] or "(sans titre)").strip()
    dossier = folders.get(m.get("project_id"), "Inbox")
    etat = "✓ terminé" if m.get("done") else "en cours"
    lignes.append("#%d · %s · [%s] · %s" % (m.get("id"), titre, dossier, etat))
    dates = []
    if m.get("due_date"):
        dates.append("échéance %s%s" % (_fmt_day(m["due_date"]), (" → " + _fmt_day(m["due_end"])) if m.get("due_end") else ""))
    if m.get("updated_at"):
        dates.append("modifié %s" % _fmt_dt(m["updated_at"]))   # heure de Paris, pas l'UTC brut de la base
    elif m.get("created_at"):
        dates.append("créé %s" % _fmt_dt(m["created_at"]))
    if m.get("source"):
        dates.append("via %s" % m["source"])
    if dates:
        lignes.append("  " + " · ".join(dates))
    txt = (m.get("content_text") or "").strip()
    if txt:
        lignes.append("  " + (txt[:300] + ("…" if len(txt) > 300 else "")))
    subs = m.get("subtasks") or []
    if subs:
        lignes.append("  sous-tâches : " + " ; ".join(("☑ " if s.get("done") else "☐ ") + (s.get("content") or "") for s in subs[:8]))
    urls = m.get("urls") or []
    if urls:
        lignes.append("  liens : " + " ; ".join((u.get("label") or u.get("url") or "") for u in urls[:5]))
    return "\n".join(lignes)


async def get_context(ctx: Context, keywords: str, limit: int = 8) -> str:
    limit = max(1, min(30, limit))
    tree = await _acall(ctx, "GET", "/tree")
    folders = {f["id"]: f["name"] for f in tree.get("folders", [])}
    found = (await _acall(ctx, "GET", "/search", params={"q": keywords, "limit": limit})).get("items", []) if keywords.strip() else []
    recent = (await _acall(ctx, "GET", "/memos", params={"sort": "updated", "limit": limit})).get("items", [])
    today = (await _acall(ctx, "GET", "/memos", params={"filter": "today", "limit": limit})).get("items", [])
    vus, out = set(), []
    for bloc, items in (("Trouvés pour « %s »" % keywords.strip(), found), ("Modifiés récemment", recent), ("Aujourd'hui", today)):
        sel = [m for m in items if m.get("id") not in vus]
        if not sel:
            continue
        out.append("## " + bloc)
        for m in sel:
            if len(vus) >= limit:
                break
            vus.add(m["id"])
            out.append(_compact(m, folders))
        if len(vus) >= limit:
            break
    if not out:
        return "Aucun mémo ne correspond à « %s », et rien de récent." % keywords
    return "\n".join(out)


async def get_notifications(ctx: Context, level: str = "me", limit: int = 20) -> dict:
    params = _clean({"level": level if level in ("me", "activity") else "me", "limit": max(1, min(100, limit))})
    return await _acall(ctx, "GET", "/notifications", params=params)


# ───────────────────────── outils — ÉCRITURE ─────────────────────────

async def create_memo(ctx: Context, title: str, content_text: str | None = None, content_html: str | None = None,
                      folder_id: int | None = None, due_date: str | None = None, due_end: str | None = None,
                      due_time: str | None = None, priority: int | None = None, subtasks: list[str] | None = None,
                      tags: list[str] | None = None, urls: list[str] | None = None) -> dict:
    _check_size(content_text, content_html)
    body = _clean({
        "title": title, "content_text": content_text, "content": content_html, "folder_id": folder_id,
        "due_date": due_date, "due_end": due_end, "due_time": due_time, "priority": priority,
        "subtasks": [{"content": s, "done": False} for s in (subtasks or [])] or None,
        "tags": tags, "urls": [{"url": u, "label": ""} for u in (urls or [])] or None,
    })
    if folder_id is not None:
        body["folder_id"] = folder_id
    return await _acall(ctx, "POST", "/memos", body=body)


async def update_memo(ctx: Context, id: int, title: str | None = None, content_text: str | None = None,
                      content_html: str | None = None, folder_id: int | None = None, due_date: str | None = None,
                      due_end: str | None = None, due_time: str | None = None, priority: int | None = None) -> dict:
    _check_size(content_text, content_html)
    body = _clean({"title": title, "content_text": content_text, "content": content_html, "folder_id": folder_id,
                   "due_date": due_date, "due_end": due_end, "due_time": due_time, "priority": priority})
    if not body:
        raise ToolError("rien à modifier : donne au moins un champ")
    return await _acall(ctx, "PATCH", "/memos/%d" % id, body=body)


async def append_to_memo(ctx: Context, id: int, content_text: str) -> dict:
    _check_size(content_text)
    return await _acall(ctx, "POST", "/memos/%d/append" % id, body={"content_text": content_text})


async def move_memo(ctx: Context, id: int, folder_id: int | None) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/move" % id, body={"folder_id": folder_id})


async def complete_memo(ctx: Context, id: int) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/done" % id)


async def reopen_memo(ctx: Context, id: int) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/undone" % id)


async def add_subtask(ctx: Context, id: int, content: str) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/subtasks" % id, body={"content": content})


async def toggle_subtask(ctx: Context, id: int, index: int, done: bool) -> dict:
    return await _acall(ctx, "PATCH", "/memos/%d/subtasks/%d" % (id, index), body={"done": done})


async def add_url(ctx: Context, id: int, url: str, label: str | None = None) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/urls" % id, body={"url": url, "label": label or ""})


async def add_comment(ctx: Context, id: int, content: str) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/comments" % id, body={"content": content})


async def delete_memo(ctx: Context, id: int) -> dict:
    return await _acall(ctx, "DELETE", "/memos/%d" % id)


async def restore_memo(ctx: Context, id: int) -> dict:
    return await _acall(ctx, "POST", "/memos/%d/restore" % id)


async def create_folder(ctx: Context, name: str, parent_id: int | None = None, emoji: str | None = None,
                        color: str | None = None) -> dict:
    return await _acall(ctx, "POST", "/folders", body=_clean({"name": name, "parent_id": parent_id, "emoji": emoji, "color": color}))


# ───────────────────────── ASGI : jeton dans l'URL ou Bearer, chemin masqué ─────────────────────────

TOOL_DESCRIPTIONS = {
    "get_tree": "Rend l'arbre du dashboard : tous les dossiers (id, nom, emoji, parent, compteurs ouverts/terminés) et la liste des mémos sans leur contenu.",
    "list_memos": "Liste les mémos hors corbeille, filtrés comme les tuiles du tableau de bord (open, today, scheduled, overdue, done, history), triés et paginés ; `folder_id` restreint à un dossier (`subtree` inclut ses sous-dossiers).",
    "get_memo": "Rend un mémo complet par son id : contenu, texte brut, sous-tâches, liens attachés, commentaires, noms des fichiers et images.",
    "search_memos": "Cherche des mémos par mots-clés (accents et ordre des mots ignorés) dans le titre, le contenu, les sous-tâches, les personnes et les liens ; bornes optionnelles par dossier, #tag et dates d'échéance.",
    "get_counts": "Rend les six chiffres des tuiles du tableau de bord (en cours, en retard, aujourd'hui, planifiés, terminés, historique), pour tout le dashboard ou un dossier.",
    "get_plan": "Rend la vue Plan : les dossiers racines, leurs sous-dossiers et leurs mémos actifs, plus l'Inbox des mémos sans dossier.",
    "whoami": "Dit quel jeton parle : son nom, ses droits (lecture ou écriture), sa source et sa date d'expiration.",
    "get_notifications": "Rend les notifications du propriétaire : `level` = « me » (ce qu'on lui adresse : commentaires, mentions, réponses, votes, nouveaux invités, rôles) ou « activity » (ce que les invités et les clients API ont fait), avec le compteur de non-lues.",
    "get_context": "Donne en un appel le contexte utile sur un sujet : les mémos trouvés par mots-clés, puis les derniers modifiés et ceux du jour, dédoublonnés et résumés en texte compact (titre, dossier, dates, extrait, sous-tâches).",
    "create_memo": "Crée un mémo : titre, contenu en texte brut (`content_text`) ou HTML (`content_html`), dossier, dates d'échéance (début/fin, heure), priorité, sous-tâches, #tags et liens.",
    "update_memo": "Modifie un mémo existant, champ par champ : titre, contenu (texte brut ou HTML), dossier, dates, heure, priorité. Les champs omis ne bougent pas.",
    "append_to_memo": "Ajoute du texte à la fin d'un mémo (nouveaux paragraphes), sans toucher à l'existant.",
    "move_memo": "Déplace un mémo dans un dossier (`folder_id` null = Inbox, les mémos sans dossier).",
    "complete_memo": "Marque un mémo comme terminé (il passe dans l'historique ; un mémo récurrent est replanifié).",
    "reopen_memo": "Rouvre un mémo terminé (il quitte l'historique et redevient en cours).",
    "add_subtask": "Ajoute une sous-tâche (case à cocher) à la fin de la liste d'un mémo.",
    "toggle_subtask": "Coche ou décoche la sous-tâche d'un mémo par son index (0 = la première).",
    "add_url": "Attache un lien http(s) à un mémo, avec un libellé optionnel (doublon refusé).",
    "add_comment": "Ajoute un commentaire au fil d'un mémo, au nom du propriétaire.",
    "delete_memo": "Envoie un mémo à la corbeille (restaurable pendant la rétention ; jamais de suppression définitive depuis ici).",
    "restore_memo": "Sort un mémo de la corbeille et le remet en place.",
    "create_folder": "Crée un dossier (à la racine ou sous un dossier parent), avec un emoji et une couleur optionnels ; un nom déjà pris chez le même parent est refusé.",
}

_NO_STORE = [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]


async def _reply(send, status, body=b"{}"):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")] + _NO_STORE + [(b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def build_app():
    """Une instance FastMCP + son enveloppe ASGI. Fabrique (et non des globales) parce que le gestionnaire
    de sessions Streamable HTTP ne démarre qu'une fois par instance : les tests en construisent une par cas."""
    mcp = FastMCP(
        "dash",
        instructions=(
        "Dashboard perso de Fabien : dossiers (« folders ») et mémos (titre, contenu, dates, priorité, "
        "sous-tâches, liens). Commence par get_context(keywords) pour une question ouverte, get_counts pour "
        "l'état du jour, get_tree pour la structure. Les écritures passent par create_memo / update_memo / "
        "append_to_memo ; delete_memo envoie à la corbeille (jamais de suppression définitive)."
    ),
        stateless_http=True,
        json_response=True,
        # Le serveur vit DERRIÈRE Caddy : le Host est `dash.fabnode.dev`, pas localhost. La protection
        # DNS-rebinding de FastMCP (421 « Invalid Host header » sinon) vise des serveurs locaux appelés
        # par un navigateur ; ici la porte est le jeton (API, invariant 10) → désactivée explicitement.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for name, desc in TOOL_DESCRIPTIONS.items():
        mcp.add_tool(globals()[name], name=name, description=desc)
    inner = mcp.streamable_http_app()          # Starlette, route exacte `/mcp`

    async def app(scope, receive, send):
        """Lit le jeton (`/mcp/<jeton>/` ou `Authorization: Bearer`), le pose dans `scope.state`, réécrit le
        chemin en `/mcp` pour FastMCP, journalise le chemin MASQUÉ, force `no-store`."""
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        path = scope.get("path", "") or ""
        token = ""
        m = re.match(r"^/mcp/([^/]+)/?$", path)
        if m and TOKEN_RE.match(m.group(1)):
            token = m.group(1)
        elif m:
            token = ""    # un segment qui n'est pas un jeton : 401, on ne devine pas
        else:
            for k, v in scope.get("headers", []):
                if k == b"authorization" and v.lower().startswith(b"bearer "):
                    token = v[7:].decode("latin-1").strip()
        masked = re.sub(r"^/mcp/[^/]+(/?)$", r"/mcp/***\1", path) if m else path
        if not token or not TOKEN_RE.match(token):
            log.info("%s %s -> 401", scope.get("method", "?"), masked)
            return await _reply(send, 401)
        if not m and path.rstrip("/") != "/mcp":
            log.info("%s %s -> 404", scope.get("method", "?"), masked)
            return await _reply(send, 404, b'{"error":"not found"}')
        scope = dict(scope)
        scope["path"] = "/mcp"
        scope["raw_path"] = b"/mcp"
        scope["state"] = dict(scope.get("state") or {}, dash_token=token)
        scope["headers"] = [(k, v) for k, v in scope.get("headers", []) if k != b"authorization"]
        status = {"code": 0}

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                hdrs = [(k, v) for k, v in message.get("headers", []) if k.lower() not in (b"cache-control", b"x-content-type-options")]
                message = dict(message, headers=hdrs + _NO_STORE)
            await send(message)

        try:
            await inner(scope, receive, send_wrapped)
        finally:
            log.info("%s %s -> %s", scope.get("method", "?"), masked, status["code"] or "?")

    return mcp, app


mcp, app = build_app()
