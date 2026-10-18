"""[NOTIF-CENTER] — la cloche devient un vrai centre de notifications, owner ET invités.

Brief : `docs/briefs/NOTIF-CENTER.md` § 4 (13 scénarios back). Doctrine : une ligne de notification
est ÉCRITE au moment de l'événement (fan-out par destinataire), jamais recalculée à la volée — c'est la
seule façon d'avoir un « non lu » par personne. Table `notifications` volatile, HORS export.

Ce que ces tests PROTÈGENT :
 1. commentaire d'un invité → `me/comment` pour l'owner seulement ; l'auteur ne se notifie jamais ;
 2. mention `@Nom` → `me/mention` pour la personne visée seulement ; une mention dans une réponse ne
    produit PAS en plus une ligne `reply` (anti-doublon) ;
 3. réponse (parent_id) à un commentaire de l'owner → `me/reply` owner ;
 4. nouvel invité auto-approuvé → `me/guest_new` owner ; une 2e visite n'en refait pas ;
 5. demande de rôle → `me/role_request` owner ; accord par un délégué → `me/role_granted` pour l'invité
    ET pour l'owner ; un rôle réglé par l'owner → `role_granted` pour l'invité seulement ;
 6. révision par un invité → `activity/edit` pour l'owner ET les autres invités du partage, pas l'auteur ;
 7. écriture via `/api/v1` → `activity/api_write` owner, `actor` = client_name, AUCUNE ligne invité ;
 8. invariant 5 : la route invité ne rend jamais une ligne d'un autre partage (double ceinture
    recipient + share_id) ; `read` d'un id d'un autre partage → 404, rien modifié ;
 9. `unread_me` ignore `activity` ; « tout lu » sur `me` ne touche pas `activity` ;
10. mémo en corbeille → masqué et exclu du compteur ; purge définitive → lignes supprimées ;
11. export v30 sans `notifications` ; un import n'en crée aucune ;
12. invariant 10 : `/api/v1/notifications` sans jeton → 401 `{}`, cookie seul → 401 ; avec jeton → 200 ;
13. purge quotidienne : lue > 90 j supprimée, non lue < 365 j conservée, non lue > 365 j supprimée.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

H = lambda gt: {"X-Guest-Token": gt}


def _db(app_module):
    con = sqlite3.connect(app_module.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _rows(app_module, where="1=1", args=()):
    con = _db(app_module)
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM notifications WHERE " + where + " ORDER BY id", args).fetchall()]
    finally:
        con.close()


def _project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _memo(c, pid, title, **kw):
    r = c.post("/api/memos", json=dict(title=title, project_id=pid, **kw))
    assert r.status_code == 201, r.data
    return r.get_json()


def _share(c, pid, role="commenter"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    d = r.get_json()
    d["share_id"] = d.get("share_id") or d["id"]
    return d


def _register(c, sh, email, name):
    r = c.post("/share/%s/register" % sh["token"], json={"name": name, "email": email, "pin": sh["pin"]})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _guest_id(app_module, share_id, email):
    con = _db(app_module)
    try:
        return con.execute("SELECT id FROM share_guests WHERE share_id = ? AND lower(email) = ?",
                           (share_id, email.lower())).fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def world(client, app_module):
    """Owner « Fabien », un dossier partagé en « éditeur » (pour pouvoir éditer ET commenter), un mémo
    de l'owner dedans, deux invités approuvés : Alice et Bob."""
    c = client
    assert c.put("/api/settings", json={"owner_name": "Fabien"}).status_code in (200, 204)
    pid = _project(c, "Dossier partagé")
    m = _memo(c, pid, "Le mémo de Fabien", content="<p>texte</p>")
    sh = _share(c, pid, role="editor")
    gtA = _register(c, sh, "alice@ex.com", "Alice")
    gtB = _register(c, sh, "bob@ex.com", "Bob")
    return {
        "c": c, "pid": pid, "mid": m["id"], "memo": m, "sh": sh, "token": sh["token"], "sid": sh["share_id"],
        "gtA": gtA, "gtB": gtB,
        "idA": _guest_id(app_module, sh["share_id"], "alice@ex.com"),
        "idB": _guest_id(app_module, sh["share_id"], "bob@ex.com"),
    }


def _comment(w, gt, body, parent_id=None):
    payload = {"body": body}
    if parent_id:
        payload["parent_id"] = parent_id
    r = w["c"].post("/share/%s/memo/%d/comments" % (w["token"], w["mid"]), json=payload, headers=H(gt))
    assert r.status_code == 201, r.data
    return r.get_json()


def _owner_comment(w, body, parent_id=None):
    payload = {"body": body}
    if parent_id:
        payload["parent_id"] = parent_id
    r = w["c"].post("/api/memos/%d/comments" % w["mid"], json=payload)
    assert r.status_code == 201, r.data
    return r.get_json()


# ------------------------------------------------------------------ 1


def test_commentaire_invite_notifie_l_owner_pas_l_auteur(world, app_module):
    w = world
    # le décor (inscriptions) a déjà produit des guest_new : on ne regarde que les commentaires
    c = _comment(w, w["gtA"], "Bonjour Fabien")
    rows = _rows(app_module, "kind = 'comment'")
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["recipient"] == "" and r["level"] == "me" and r["actor"] == "Alice" and r["actor_kind"] == "guest"
    assert r["memo_id"] == w["mid"] and r["share_id"] == w["sid"] and r["project_id"] == w["pid"]
    assert r["comment_id"] == c["id"] and r["title"] == "Le mémo de Fabien" and r["excerpt"] == "Bonjour Fabien"
    assert r["read_at"] is None and r["uid"]
    assert _rows(app_module, "recipient = ?", ("g:%d" % w["idA"],)) == [], "l'auteur ne se notifie jamais"
    assert _rows(app_module, "recipient = ? AND kind = 'comment'", ("g:%d" % w["idB"],)) == [], \
        "Bob n'a ni créé, ni été assigné, ni commenté : rien pour lui"


# ------------------------------------------------------------------ 2


def test_mention_vise_la_personne_seule_et_pas_de_reply_en_plus(world, app_module):
    w = world
    c1 = _owner_comment(w, "@Bob tu peux regarder ?")
    assert _rows(app_module, "kind = 'mention'") and all(r["recipient"] == "g:%d" % w["idB"] for r in _rows(app_module, "kind = 'mention'"))
    assert _rows(app_module, "kind = 'mention' AND recipient = ?", ("g:%d" % w["idA"],)) == []
    assert _rows(app_module, "kind = 'mention' AND recipient = ''") == []
    # Bob RÉPOND à l'owner en le mentionnant : UNE ligne pour l'owner, de kind `mention` (pas `reply`)
    c2 = _comment(w, w["gtB"], "@Fabien oui je regarde", parent_id=c1["id"])
    pour_owner = _rows(app_module, "recipient = '' AND comment_id = ?", (c2["id"],))
    assert len(pour_owner) == 1, pour_owner
    assert pour_owner[0]["kind"] == "mention" and pour_owner[0]["actor"] == "Bob"


# ------------------------------------------------------------------ 3


def test_reponse_a_l_owner_est_un_reply(world, app_module):
    w = world
    c1 = _owner_comment(w, "Première remarque")
    c2 = _comment(w, w["gtA"], "Je réponds", parent_id=c1["id"])
    pour_owner = _rows(app_module, "recipient = '' AND comment_id = ?", (c2["id"],))
    assert len(pour_owner) == 1 and pour_owner[0]["kind"] == "reply" and pour_owner[0]["actor"] == "Alice"
    assert pour_owner[0]["excerpt"] == "Je réponds"


# ------------------------------------------------------------------ 4


def test_nouvel_invite_une_seule_fois(world, app_module):
    w = world
    avant = _rows(app_module, "kind = 'guest_new'")
    assert sorted(r["actor"] for r in avant) == ["Alice", "Bob"] and all(r["recipient"] == "" for r in avant)
    _register(w["c"], w["sh"], "alice@ex.com", "Alice")      # 2e visite
    assert len(_rows(app_module, "kind = 'guest_new'")) == 2, "une ré-inscription n'est pas un nouvel invité"
    _register(w["c"], w["sh"], "carla@ex.com", "Carla")
    rows = _rows(app_module, "kind = 'guest_new'")
    assert len(rows) == 3 and rows[-1]["actor"] == "Carla" and rows[-1]["level"] == "me" and rows[-1]["share_id"] == w["sid"]


# ------------------------------------------------------------------ 5


def test_demande_de_role_et_accord_par_delegue(world, app_module):
    w = world
    r = w["c"].post("/share/%s/role-request" % w["token"], json={"role": "editor"}, headers=H(w["gtB"]))
    assert r.status_code in (200, 201), r.data
    rr = _rows(app_module, "kind = 'role_request'")
    assert len(rr) == 1 and rr[0]["recipient"] == "" and rr[0]["actor"] == "Bob" and "editor" in rr[0]["excerpt"].lower() or "éditeur" in rr[0]["excerpt"].lower()
    # l'owner nomme Alice admin → role_granted pour Alice seulement (l'owner ne s'écrit pas à lui-même)
    assert w["c"].put("/api/guests/%d/role" % w["idA"], json={"role": "admin", "project_id": w["pid"]}).status_code == 200
    g = _rows(app_module, "kind = 'role_granted'")
    assert [x["recipient"] for x in g] == ["g:%d" % w["idA"]] and g[0]["actor_kind"] == "owner"
    # Alice (déléguée) accorde la demande de Bob → role_granted pour Bob ET pour l'owner, actor = Alice
    con = _db(app_module)
    try:
        req = con.execute("SELECT id FROM role_requests WHERE guest_id = ?", (w["idB"],)).fetchone()[0]
    finally:
        con.close()
    r = w["c"].post("/share/%s/role-request/%d" % (w["token"], req), json={"decision": "grant"}, headers=H(w["gtA"]))
    assert r.status_code == 200, r.data
    g2 = [x for x in _rows(app_module, "kind = 'role_granted'") if x["actor"] == "Alice"]
    assert sorted(x["recipient"] for x in g2) == ["", "g:%d" % w["idB"]], g2
    assert all(x["actor_kind"] == "guest" and x["level"] == "me" for x in g2)


# ------------------------------------------------------------------ 6


def test_revision_invite_activity_pour_owner_et_autres_invites(world, app_module):
    w = world
    r = w["c"].put("/share/%s/memo/%d" % (w["token"], w["mid"]), json={"title": "Titre changé par Alice"}, headers=H(w["gtA"]))
    assert r.status_code == 200, r.data
    rows = _rows(app_module, "kind = 'edit'")
    assert sorted(x["recipient"] for x in rows) == ["", "g:%d" % w["idB"]], rows
    assert all(x["level"] == "activity" and x["actor"] == "Alice" and x["memo_id"] == w["mid"] for x in rows)
    assert rows[0]["title"] == "Titre changé par Alice"
    # l'excerpt dit la NATURE de la modification, pas le titre (retouche Cowork)
    assert rows[0]["excerpt"] == "titre modifié", rows[0]["excerpt"]
    # cocher une sous-tâche → « sous-tâche cochée » ; texte + dates → libellés joints
    assert w["c"].put("/api/memos/%d" % w["mid"], json={"subtasks": [{"content": "a", "done": False}]}).status_code == 200
    r = w["c"].put("/share/%s/memo/%d" % (w["token"], w["mid"]), json={"subtasks": [{"content": "a", "done": True}]}, headers=H(w["gtA"]))
    assert r.status_code == 200, r.data
    r = w["c"].put("/share/%s/memo/%d" % (w["token"], w["mid"]), json={"content": "<p>neuf</p>", "due_date": "2026-12-01"}, headers=H(w["gtA"]))
    assert r.status_code == 200, r.data
    ex = [x["excerpt"] for x in _rows(app_module, "kind = 'edit' AND recipient = ''")]
    assert ex[1] == "sous-tâche cochée", ex
    assert ex[2] == "texte modifié · dates modifiées", ex


# ------------------------------------------------------------------ 7


def test_ecriture_api_activity_owner_seulement(world, app_module):
    w = world
    t = w["c"].post("/api/tokens", json={"name": "Claude chat", "scopes": "read,write", "source": "claude-chat"}).get_json()
    h = {"Authorization": "Bearer " + t["token"], "X-Dash-Client": "mcp/1.0.0 (claude-ai)"}
    r = w["c"].post("/api/v1/memos", json={"title": "Créé par Claude", "folder_id": w["pid"]}, headers=h)
    assert r.status_code == 201, r.data
    mid = r.get_json()["id"]
    assert w["c"].post("/api/v1/memos/%d/done" % mid, headers=h).status_code == 200
    rows = _rows(app_module, "kind = 'api_write'")
    assert len(rows) >= 2 and all(x["recipient"] == "" and x["level"] == "activity" for x in rows), rows
    assert rows[0]["actor"] == "mcp" and rows[0]["actor_kind"] == "api" and rows[0]["memo_id"] == mid
    assert rows[0]["title"] == "Créé par Claude"
    assert _rows(app_module, "recipient LIKE 'g:%' AND kind = 'api_write'") == [], "jamais côté invité"
    # et dans le payload owner, l'activité porte le libellé de l'action
    items = w["c"].get("/api/notifications?level=activity").get_json()["items"]
    assert any(i["kind"] == "api_write" and i["memo_id"] == mid for i in items)


# ------------------------------------------------------------------ 8


def test_invariant5_jamais_une_ligne_d_un_autre_partage(world, app_module):
    w = world
    c = w["c"]
    # Alice est aussi sur un SECOND partage (dossier B) ; Bob2 y commente un mémo créé par Alice
    pid2 = _project(c, "Dossier B")
    sh2 = _share(c, pid2, role="editor")
    gtA2 = _register(c, sh2, "alice@ex.com", "Alice")
    gtB2 = _register(c, sh2, "bob@ex.com", "Bob")
    r = c.post("/share/%s/memos" % sh2["token"], json={"title": "Mémo d'Alice dans B"}, headers=H(gtA2))
    assert r.status_code == 201, r.data
    mid2 = r.get_json()["id"]
    r = c.post("/share/%s/memo/%d/comments" % (sh2["token"], mid2), json={"body": "coucou"}, headers=H(gtB2))
    assert r.status_code == 201, r.data
    idA2 = _guest_id(app_module, sh2["share_id"], "alice@ex.com")
    # Alice a bien une notification `comment` sur B
    b = c.get("/share/%s/notifications?level=me" % sh2["token"], headers=H(gtA2)).get_json()
    assert any(i["memo_id"] == mid2 and i["kind"] == "comment" for i in b["items"]), b
    # … et RIEN de B ne sort par le partage A, même si une ligne B portait son recipient A (double ceinture)
    con = _db(app_module)
    try:
        con.execute("INSERT INTO notifications (uid, recipient, level, kind, actor, actor_kind, share_id, project_id, memo_id, "
                    "title, excerpt, created_at) VALUES ('x', ?, 'me', 'comment', 'Bob', 'guest', ?, ?, ?, 'piège', 'piège', ?)",
                    ("g:%d" % w["idA"], sh2["share_id"], pid2, mid2, datetime.now(timezone.utc).isoformat()))
        con.commit()
        piege = con.execute("SELECT id FROM notifications WHERE uid = 'x'").fetchone()[0]
    finally:
        con.close()
    a = c.get("/share/%s/notifications?level=me" % w["token"], headers=H(w["gtA"])).get_json()
    assert all(i["share_id"] == w["sid"] for i in a["items"]), a
    assert not any(i["id"] == piege or i["memo_id"] == mid2 for i in a["items"])
    r = c.post("/share/%s/notifications/read" % w["token"], json={"ids": [piege]}, headers=H(w["gtA"]))
    assert r.status_code == 404
    assert _rows(app_module, "id = ?", (piege,))[0]["read_at"] is None, "rien modifié"
    # sans jeton invité → 403 ; jeton inconnu → 403 ; aucun paramètre ne désigne le destinataire
    assert c.get("/share/%s/notifications" % w["token"]).status_code == 403
    assert c.get("/share/%s/notifications?recipient=" % w["token"], headers=H("bidon")).status_code == 403


# ------------------------------------------------------------------ 9


def test_compteurs_me_et_activity_separes(world, app_module):
    w = world
    _comment(w, w["gtA"], "un")                                  # me/comment owner
    _comment(w, w["gtB"], "deux")                                # me/comment owner
    assert w["c"].put("/share/%s/memo/%d" % (w["token"], w["mid"]), json={"title": "edit"}, headers=H(w["gtA"])).status_code == 200  # activity/edit owner
    me = w["c"].get("/api/notifications?level=me").get_json()
    act = w["c"].get("/api/notifications?level=activity").get_json()
    assert me["unread_me"] == 4, me   # 2 commentaires + 2 guest_new du décor
    assert act["unread_me"] == 4
    assert all(i["level"] == "me" for i in me["items"]) and all(i["level"] == "activity" for i in act["items"])
    assert len(act["items"]) == 1 and act["items"][0]["kind"] == "edit"
    r = w["c"].post("/api/notifications/read", json={"level": "me", "all": True})
    assert r.status_code == 200 and r.get_json()["unread_me"] == 0
    assert _rows(app_module, "level = 'activity' AND read_at IS NULL"), "« tout lu » sur me ne touche pas activity"
    # lecture unitaire par ids
    aid = act["items"][0]["id"]
    assert w["c"].post("/api/notifications/read", json={"ids": [aid]}).status_code == 200
    assert _rows(app_module, "id = ?", (aid,))[0]["read_at"]
    # /api/activity : unread_me exposé, unseen = même valeur (compat)
    a = w["c"].get("/api/activity").get_json()
    assert a["unread_me"] == 0 and a["unseen"] == a["unread_me"]


# ------------------------------------------------------------------ 10


def test_corbeille_masque_puis_purge_supprime(world, app_module):
    w = world
    _comment(w, w["gtA"], "avant la corbeille")
    assert w["c"].get("/api/notifications?level=me").get_json()["unread_me"] == 3   # 2 guest_new + 1
    assert w["c"].delete("/api/memos/%d" % w["mid"]).status_code == 204
    me = w["c"].get("/api/notifications?level=me").get_json()
    assert me["unread_me"] == 2 and not any(i["memo_id"] == w["mid"] for i in me["items"]), me
    assert _rows(app_module, "memo_id = ?", (w["mid"],)), "conservée en base tant que le mémo est en corbeille"
    assert w["c"].post("/api/trash/%d/restore" % w["mid"]).status_code == 200
    assert w["c"].get("/api/notifications?level=me").get_json()["unread_me"] == 3
    assert w["c"].delete("/api/memos/%d" % w["mid"]).status_code == 204
    assert w["c"].delete("/api/trash/%d" % w["mid"]).status_code == 204   # purge définitive
    assert _rows(app_module, "memo_id = ?", (w["mid"],)) == []


# ------------------------------------------------------------------ 11


def test_export_sans_notifications_et_import_n_en_cree_pas(world, app_module):
    w = world
    _comment(w, w["gtA"], "exportée ?")
    exp = w["c"].get("/api/export").get_json()
    assert exp["version"] == 30 and "notifications" not in exp
    assert "notifications" not in w["c"].get("/api/export").get_data(as_text=True)
    n = len(_rows(app_module))
    assert w["c"].post("/api/import", json=exp).status_code == 200
    assert len(_rows(app_module)) == n


# ------------------------------------------------------------------ 12


def test_invariant10_api_v1_notifications(world, app_module):
    w = world
    assert w["c"].get("/api/v1/notifications").status_code == 401
    assert w["c"].get("/api/v1/notifications").get_json() == {}
    assert w["c"].get("/api/v1/notifications", headers={"Cookie": "authelia_session=abc"}).status_code == 401
    t = w["c"].post("/api/tokens", json={"name": "lecteur", "scopes": "read", "source": "cli"}).get_json()
    h = {"Authorization": "Bearer " + t["token"]}
    _comment(w, w["gtA"], "pour l'API")
    r = w["c"].get("/api/v1/notifications?level=me", headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body["unread_me"] >= 1 and any(i["kind"] == "comment" for i in body["items"])
    assert w["c"].post("/api/v1/notifications/read", json={"level": "me", "all": True}, headers=h).status_code == 403, "read exige write"
    rules = [r.rule for r in app_module.app.url_map.iter_rules() if "notifications" in r.rule]
    assert "/api/v1/notifications" in rules and "/api/v1/notifications/read" in rules
    for rule in app_module.app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1"):
            assert getattr(app_module.app.view_functions[rule.endpoint], "_requires_token", None) in ("read", "write"), rule.rule


# ------------------------------------------------------------------ 13


def test_purge_quotidienne(world, app_module):
    w = world
    now = datetime.now(timezone.utc)
    con = _db(app_module)
    try:
        def ins(uid, created, read):
            con.execute("INSERT INTO notifications (uid, recipient, level, kind, actor, actor_kind, title, excerpt, created_at, read_at) "
                        "VALUES (?, '', 'me', 'comment', 'X', 'guest', 't', 'e', ?, ?)", (uid, created, read))
        ins("lue-vieille", (now - timedelta(days=100)).isoformat(), (now - timedelta(days=95)).isoformat())
        ins("lue-recente", (now - timedelta(days=100)).isoformat(), (now - timedelta(days=10)).isoformat())
        ins("nonlue-moyenne", (now - timedelta(days=200)).isoformat(), None)
        ins("nonlue-tres-vieille", (now - timedelta(days=400)).isoformat(), None)
        con.commit()
    finally:
        con.close()
    app_module._purge_notifications()
    uids = {r["uid"] for r in _rows(app_module)}
    assert "lue-vieille" not in uids and "nonlue-tres-vieille" not in uids
    assert "lue-recente" in uids and "nonlue-moyenne" in uids
    assert app_module.NOTIF_KEEP_DAYS == (90, 365)
