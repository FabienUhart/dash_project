"""[DASH-API] OpenAPI 3.1 de l'API v1, écrite À LA MAIN (dict Python, zéro lib — invariant 6).

Servie par `GET /api/v1/openapi.json`. `tests/back/test_api_v1_read.py::test_openapi_decrit_chaque_route`
vérifie par introspection de `app.url_map` que CHAQUE route enregistrée sous /api/v1 figure ici
avec ses méthodes : ajouter une route sans la décrire fait rougir la suite.

Lot A : sécurité + lecture + écriture hors fichiers. Les fichiers (A2) et MCP (B) viendront avec
leurs briefs.
"""

_BEARER = [{"bearer": []}]
_JSON = "application/json"


def _resp(desc, schema=None):
    r = {"description": desc}
    if schema is not None:
        r["content"] = {_JSON: {"schema": schema}}
    return r


def _ref(name):
    return {"$ref": "#/components/schemas/" + name}


_ERRS = {
    "401": _resp("Jeton absent, inconnu, révoqué ou expiré — corps `{}` sans indice."),
    "403": _resp("Scope insuffisant (un jeton `read` sur une écriture)."),
    "429": _resp("Quota dépassé (120 lectures/min, 30 écritures/min par jeton) — en-tête `Retry-After`."),
}

_MEMO_ID = {"name": "memo_id", "in": "path", "required": True, "schema": {"type": "integer"}}
_FOLDER_Q = {"name": "folder", "in": "query", "schema": {"type": "string"},
             "description": "id de dossier, ou `inbox` (mémos sans dossier). Absent = tout."}
_SUBTREE_Q = {"name": "subtree", "in": "query", "schema": {"type": "integer", "enum": [0, 1]},
              "description": "1 = inclure les sous-dossiers du dossier visé."}
_TODAY_Q = {"name": "today", "in": "query", "schema": {"type": "string", "format": "date"},
            "description": "Aujourd'hui du CLIENT (YYYY-MM-DD) pour les tuiles ; défaut = date du serveur."}


def _op(summary, scope="read", params=None, body=None, responses=None, tags=None):
    op = {"summary": summary, "security": _BEARER, "tags": tags or ["memos"],
          "x-scope": scope, "responses": dict(_ERRS)}
    if params:
        op["parameters"] = params
    if body is not None:
        op["requestBody"] = {"required": True, "content": {_JSON: {"schema": body}}}
    op["responses"].update(responses or {})
    return op


MEMO_WRITE = {
    "type": "object",
    "description": "Mêmes validations que l'UI. `content_text` = texte brut → paragraphes échappés ; "
                   "`content` = HTML passé par le nettoyeur (script/on*/javascript: retirés).",
    "properties": {
        "title": {"type": "string", "maxLength": 200},
        "content": {"type": "string"},
        "content_text": {"type": "string"},
        "folder_id": {"type": ["integer", "null"], "description": "null = Inbox"},
        "due_date": {"type": "string", "format": "date"},
        "due_end": {"type": ["string", "null"], "format": "date"},
        "due_time": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
        "priority": {"type": "integer"},
        "subtasks": {"type": "array", "items": _ref("Subtask")},
        "assignees": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "ajoutés au corps en #hashtags"},
        "urls": {"type": "array", "items": {"type": "object", "properties": {"url": {"type": "string"}, "label": {"type": "string"}}}},
        "position": {"type": "integer"},
    },
}

OPENAPI = {
    "openapi": "3.1.0",
    "info": {
        "title": "Dashboard — API v1",
        "version": "1.0.0",
        "description": "API du dashboard perso pour Claude (chat, Claude Code), un CLI et l'appli mobile. "
                       "Un seul utilisateur : le propriétaire. Auth = `Authorization: Bearer dash_…` "
                       "(jetons créés dans Paramètres › Appareils connectés). Jamais de cookie. "
                       "Les mémos en corbeille ne sont jamais renvoyés (404). Hors périmètre : partages, "
                       "invités, jetons, réglages, import, purge.",
    },
    "servers": [{"url": "/api/v1"}],
    "components": {
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "dash_<40 car.>"}},
        "schemas": {
            "Subtask": {"type": "object", "properties": {"content": {"type": "string"}, "done": {"type": "boolean"}}},
            "Memo": {"type": "object", "description": "Mémo complet (= payload /api/memos de l'UI) + `content_text` (HTML déshabillé) + `source` "
                                                    "('' = UI, sinon la source du jeton qui l'a écrit en dernier).",
                     "properties": {"id": {"type": "integer"}, "uid": {"type": "string"}, "title": {"type": "string"},
                                    "content": {"type": "string"}, "content_text": {"type": "string"},
                                    "done": {"type": "boolean"}, "due_date": {"type": "string"}, "due_end": {"type": "string"},
                                    "due_time": {"type": "string"}, "priority": {"type": "integer"}, "project_id": {"type": ["integer", "null"]},
                                    "subtasks": {"type": "array", "items": _ref("Subtask")},
                                    "assignees": {"type": "array", "items": {"type": "string"}},
                                    "urls": {"type": "array", "items": {"type": "object"}},
                                    "attachments": {"type": "array", "items": {"type": "object"}},
                                    "images": {"type": "array", "items": {"type": "string"}},
                                    "source": {"type": "string"}, "created_at": {"type": "string"}, "updated_at": {"type": "string"}}},
            "MemoLite": {"type": "object", "properties": {"id": {"type": "integer"}, "uid": {"type": "string"}, "title": {"type": "string"},
                                                          "done": {"type": "boolean"}, "due_date": {"type": "string"}, "due_end": {"type": "string"},
                                                          "priority": {"type": "integer"}, "project_id": {"type": ["integer", "null"]}}},
            "Folder": {"type": "object", "properties": {"id": {"type": "integer"}, "uid": {"type": "string"}, "name": {"type": "string"},
                                                        "emoji": {"type": "string"}, "color": {"type": "string"}, "parent_id": {"type": ["integer", "null"]},
                                                        "position": {"type": "integer"}, "counts": {"type": "object", "properties": {"open": {"type": "integer"}, "done": {"type": "integer"}}}}},
            "Counts": {"type": "object", "properties": {k: {"type": "integer"} for k in ("all", "overdue", "today", "scheduled", "done", "history")}},
            "Page": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object"}}, "next_cursor": {"type": ["string", "null"]}}},
            "PlanNode": {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}, "emoji": {"type": "string"},
                                                          "color": {"type": "string"}, "count": {"type": "integer", "description": "mémos non terminés du sous-arbre"},
                                                          "memos": {"type": "array", "items": {"type": "object"}},
                                                          "children": {"type": "array", "items": {"type": "object"}}}},
            "Error": {"type": "object", "properties": {"error": {"type": "string"}}},
        },
    },
    "paths": {
        "/me": {"get": _op("Le jeton qui parle : nom, scopes, source, expiration.", tags=["auth"],
                           responses={"200": _resp("ok", {"type": "object", "properties": {"name": {"type": "string"}, "scopes": {"type": "array", "items": {"type": "string"}}, "source": {"type": "string"}, "expires_at": {"type": "string"}}})})},
        "/tree": {"get": _op("Dossiers (avec compteurs) + mémos SANS contenu.", tags=["lecture"],
                             responses={"200": _resp("ok", {"type": "object", "properties": {"folders": {"type": "array", "items": _ref("Folder")}, "memos": {"type": "array", "items": _ref("MemoLite")}}})})},
        "/memos": {
            "get": _op("Liste des mémos (hors corbeille), filtrée comme les six tuiles, triée, paginée.", tags=["lecture"],
                       params=[_FOLDER_Q, _SUBTREE_Q, _TODAY_Q,
                               {"name": "filter", "in": "query", "schema": {"type": "string", "enum": ["open", "today", "scheduled", "overdue", "done", "history"]},
                                "description": "Exactement les règles des tuiles. `history` rend les lignes de l'historique (memo_uid, content, project, done_at)."},
                               {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["manual", "newest", "updated", "due"]}},
                               {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 200, "default": 50}},
                               {"name": "cursor", "in": "query", "schema": {"type": "string"}, "description": "`next_cursor` de la page précédente"},
                               {"name": "since", "in": "query", "schema": {"type": "string", "format": "date-time"}, "description": "ne rend que les mémos dont `updated_at` > since"}],
                       responses={"200": _resp("ok", _ref("Page")), "400": _resp("paramètre invalide", _ref("Error")), "404": _resp("dossier inconnu")}),
            "post": _op("Crée un mémo (201). `source` = la source du jeton.", scope="write", body=MEMO_WRITE,
                        responses={"201": _resp("créé", _ref("Memo")), "400": _resp("invalide", _ref("Error")), "404": _resp("dossier inconnu"), "413": _resp("corps > 256 Ko")}),
        },
        "/memos/{memo_id}": {
            "get": _op("Mémo complet + `comments` + `urls` + noms des `attachments`/`images`.", tags=["lecture"], params=[_MEMO_ID],
                       responses={"200": _resp("ok", _ref("Memo")), "404": _resp("inconnu ou en corbeille")}),
            "patch": _op("Modification partielle (mêmes règles que l'UI) ; pose `source`.", scope="write", params=[_MEMO_ID], body=MEMO_WRITE,
                         responses={"200": _resp("ok", _ref("Memo")), "400": _resp("invalide", _ref("Error")), "404": _resp("inconnu ou en corbeille")}),
            "delete": _op("Envoie le mémo à la CORBEILLE (jamais de suppression définitive).", scope="write", params=[_MEMO_ID],
                          responses={"204": _resp("en corbeille"), "404": _resp("inconnu ou déjà en corbeille")}),
        },
        "/memos/{memo_id}/append": {"post": _op("Ajoute du contenu À LA FIN (`content` ou `content_text`).", scope="write", params=[_MEMO_ID],
                                                body={"type": "object", "properties": {"content": {"type": "string"}, "content_text": {"type": "string"}}},
                                                responses={"200": _resp("ok", _ref("Memo")), "400": _resp("vide"), "404": _resp("inconnu")})},
        "/memos/{memo_id}/move": {"post": _op("Déplace dans un dossier (`folder_id` null = Inbox).", scope="write", params=[_MEMO_ID],
                                              body={"type": "object", "properties": {"folder_id": {"type": ["integer", "null"]}}},
                                              responses={"200": _resp("ok", _ref("Memo")), "404": _resp("mémo ou dossier inconnu")})},
        "/memos/{memo_id}/done": {"post": _op("Termine (écrit l'historique, replanifie si récurrent).", scope="write", params=[_MEMO_ID],
                                              responses={"200": _resp("ok", _ref("Memo")), "404": _resp("inconnu")})},
        "/memos/{memo_id}/undone": {"post": _op("Rouvre (retire la dernière ligne d'historique).", scope="write", params=[_MEMO_ID],
                                                responses={"200": _resp("ok", _ref("Memo")), "404": _resp("inconnu")})},
        "/memos/{memo_id}/restore": {"post": _op("Sort le mémo de la corbeille.", scope="write", params=[_MEMO_ID],
                                                 responses={"200": _resp("ok", _ref("Memo")), "404": _resp("pas en corbeille")})},
        "/memos/{memo_id}/subtasks": {"post": _op("Ajoute une sous-tâche (201).", scope="write", params=[_MEMO_ID],
                                                  body={"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}},
                                                  responses={"201": _resp("ok", _ref("Memo")), "400": _resp("vide"), "404": _resp("inconnu")})},
        "/memos/{memo_id}/subtasks/{n}": {"patch": _op("Modifie la sous-tâche d'index n (`done`, `content`).", scope="write",
                                                       params=[_MEMO_ID, {"name": "n", "in": "path", "required": True, "schema": {"type": "integer"}}],
                                                       body={"type": "object", "properties": {"done": {"type": "boolean"}, "content": {"type": "string"}}},
                                                       responses={"200": _resp("ok", _ref("Memo")), "404": _resp("mémo ou index inconnu")})},
        "/memos/{memo_id}/urls": {"post": _op("Attache une URL http(s) (réutilise [MEMO-URLS]).", scope="write", params=[_MEMO_ID],
                                              body={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "label": {"type": "string"}}},
                                              responses={"201": _resp("ok"), "400": _resp("invalide / plafond"), "404": _resp("inconnu"), "409": _resp("doublon")})},
        "/memos/{memo_id}/urls/{url_id}": {"delete": _op("Retire le lien.", scope="write",
                                                         params=[_MEMO_ID, {"name": "url_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                                                         responses={"204": _resp("retiré"), "404": _resp("inconnu")})},
        "/memos/{memo_id}/comments": {"post": _op("Commentaire au nom du propriétaire (201).", scope="write", params=[_MEMO_ID],
                                                  body={"type": "object", "required": ["content"], "properties": {"content": {"type": "string", "maxLength": 2000}}},
                                                  responses={"201": _resp("ok"), "400": _resp("vide"), "404": _resp("inconnu")})},
        "/counts": {"get": _op("Les six chiffres des tuiles (all, overdue, today, scheduled, done, history).", tags=["lecture"],
                               params=[_FOLDER_Q, _SUBTREE_Q, _TODAY_Q], responses={"200": _resp("ok", _ref("Counts")), "404": _resp("dossier inconnu")})},
        "/search": {"get": _op("Recherche pliée (accents, casse, ordre des mots) sur titre, contenu, sous-tâches, assignés, libellés/URL.", tags=["lecture"],
                               params=[{"name": "q", "in": "query", "schema": {"type": "string"}}, {"name": "folder", "in": "query", "schema": {"type": "integer"}, "description": "sous-arbre inclus"},
                                       {"name": "tag", "in": "query", "schema": {"type": "string"}, "description": "#tag du corps (borne stricte)"},
                                       {"name": "due_from", "in": "query", "schema": {"type": "string", "format": "date"}}, {"name": "due_to", "in": "query", "schema": {"type": "string", "format": "date"}},
                                       {"name": "created_from", "in": "query", "schema": {"type": "string", "format": "date"}}, {"name": "created_to", "in": "query", "schema": {"type": "string", "format": "date"}},
                                       {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 200, "default": 50}}],
                               responses={"200": _resp("ok", _ref("Page")), "400": _resp("q ou tag requis, ou date invalide", _ref("Error"))})},
        "/plan": {"get": _op("La vue Plan : dossiers racines → sous-dossiers + mémos actifs (terminés compris), Inbox à part.", tags=["lecture"],
                             responses={"200": _resp("ok", {"type": "object", "properties": {"roots": {"type": "array", "items": _ref("PlanNode")}, "inbox": {"type": "object"}}})})},
        "/export": {"get": _op("L'export JSON complet (même fonction que Paramètres › Sauvegardes), version 30.", tags=["lecture"],
                               responses={"200": _resp("ok", {"type": "object"})})},
        "/openapi.json": {"get": _op("Ce document.", tags=["auth"], responses={"200": _resp("ok", {"type": "object"})})},
        "/client-versions": {"get": _op("Versions courantes des clients officiels (`mcp`, `cli`, `extension` ; null = pas encore livré) — un client se compare à elles. [DASH-MCP]", tags=["auth"],
                                        responses={"200": _resp("ok", {"type": "object", "properties": {"mcp": {"type": ["string", "null"]}, "cli": {"type": ["string", "null"]}, "extension": {"type": ["string", "null"]}}})})},
        "/folders": {"post": _op("Crée un dossier (201) ; 409 si le nom est pris chez le même parent.", scope="write", tags=["dossiers"],
                                 body={"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "parent_id": {"type": ["integer", "null"]}, "emoji": {"type": "string"}, "color": {"type": "string"}}},
                                 responses={"201": _resp("créé", _ref("Folder")), "400": _resp("invalide"), "404": _resp("parent inconnu"), "409": _resp("nom pris")})},
        "/folders/{folder_id}": {"patch": _op("Renomme / déplace / change emoji et couleur ; 409 si le nom est pris chez le parent visé.", scope="write", tags=["dossiers"],
                                              params=[{"name": "folder_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                                              body={"type": "object", "properties": {"name": {"type": "string"}, "parent_id": {"type": ["integer", "null"]}, "emoji": {"type": "string"}, "color": {"type": "string"}}},
                                              responses={"200": _resp("ok", _ref("Folder")), "400": _resp("invalide"), "404": _resp("inconnu"), "409": _resp("nom pris")})},
    },
}
