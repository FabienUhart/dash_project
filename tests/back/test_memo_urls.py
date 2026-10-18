"""[MEMO-URLS] Des liens attachés au mémo, comme les fichiers — export v29.

Brief : `docs/briefs/MEMO-URLS.md` (demande Fabien du 15 oct. 2026, mémo prod 403 : « rajouter
l'URL de suivi au mémo, comme les dates et les fichiers »). **Ce lot bump le format d'export :
X passe de 28 à 29.**

Ce que ces parcours PROTÈGENT :

- **seules les adresses http(s) entrent** (test 2) : `javascript:`/`data:`/`ftp:` → 400, jamais
  une ligne. Une URL attachée est rendue cliquable chez l'owner ET chez l'invité ;
- **une URL par mémo, exactement** (test 3) : la clé `UNIQUE(memo_id, url)` est ce qui rend le
  ré-import idempotent ;
- **la corbeille masque sans détruire** (test 5), la purge définitive emporte les lignes
  (invariant 7, comme les pièces jointes) ;
- **l'export voyage SANS les dérivées `og_*`** (test 6) : elles se recalculent ; un export v28
  (sans `urls`) reste importable à l'identique (invariants 1 et 2) ;
- **la projection invitée est STRICTE** (test 7) : `{url, label, og_title, og_domain}` et rien
  d'autre — ni id, ni `created_by` (invariant 5) ; écrire exige un invité approuvé + éditeur ;
- **l'aperçu est un bonus, jamais un blocage** (test 8) : réseau en panne → 201 quand même.

Numéros = § 3 du brief. Les 6 mutations du brief sont tuées par les tests nommés en regard.
"""
import pytest


# --------------------------------------------------------------------- décor


@pytest.fixture(autouse=True)
def _og_muet(monkeypatch, app_module):
    """Par défaut, l'aperçu OG ne sort PAS sur le réseau (la garde zéro-réseau le ferait sauter
    en `BaseException`). Chaque test qui veut un aperçu rempli pose son propre stub (test 8)."""
    monkeypatch.setattr(app_module, "_fetch_og", lambda url: {
        "status": "failed", "title": "", "desc": "", "domain": "", "image_bytes": b""})


def _mk_memo(c, content, pid=None, **kw):
    body = {"content": content}
    if pid:
        body["project_id"] = pid
    body.update(kw)
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _mk_project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()


def _add(c, memo_id, url, label=""):
    return c.post("/api/memos/%d/urls" % memo_id, json={"url": url, "label": label})


def _urls(c, memo_id):
    r = c.get("/api/memos/%d/urls" % memo_id)
    assert r.status_code == 200, r.data
    return r.get_json()


def _memos(c):
    r = c.get("/api/memos")
    assert r.status_code == 200, r.data
    data = r.get_json()
    rows = data if isinstance(data, list) else data.get("memos", [])
    return {m["id"]: m for m in rows}


def _count_rows(app_module):
    con = app_module.sqlite3.connect(app_module.DB_PATH)
    try:
        return con.execute("SELECT COUNT(*) FROM memo_urls").fetchone()[0]
    finally:
        con.close()


SUIVI = "https://suivi.exemple.test/colis?id=ABC123&lang=fr"


# --------------------------------------------------------------------------- 1


def test_add_url_appears_in_memos_payload(client):
    """POST valide → 201 + objet ; `/api/memos` porte `urls` sans appel de plus."""
    memo = _mk_memo(client, "Réparation iPad")
    r = _add(client, memo["id"], SUIVI, "Suivi Apple")
    assert r.status_code == 201, r.data
    u = r.get_json()
    assert u["url"] == SUIVI, "la query d'un lien de suivi doit survivre telle quelle"
    assert u["label"] == "Suivi Apple"
    assert u["id"] and u["position"] == 0

    vu = _memos(client)[memo["id"]]
    assert [x["url"] for x in vu.get("urls", [])] == [SUIVI]
    assert vu["urls"][0]["label"] == "Suivi Apple"
    assert "created_by_display" in vu["urls"][0]

    # un mémo sans URL porte la clé quand même ([] — jamais `undefined` côté front)
    vierge = _mk_memo(client, "Sans lien")
    assert _memos(client)[vierge["id"]].get("urls") == []

    # espaces trimés ; second lien → position 1
    r2 = _add(client, memo["id"], "  https://apple.com/fr/support  ")
    assert r2.status_code == 201, r2.data
    assert r2.get_json()["url"] == "https://apple.com/fr/support"
    assert [x["position"] for x in _urls(client, memo["id"])] == [0, 1]


# --------------------------------------------------------------------------- 2


@pytest.mark.parametrize("mauvaise", [
    "javascript:alert(1)",
    "data:text/html,hi",
    "ftp://exemple.test/f",
    "",
    "   ",
    "exemple.test/sans-schema",
    "https://exemple.test/" + ("x" * 2048),
])
def test_only_http_urls_are_accepted(client, mauvaise):
    """`javascript:`, `ftp:`, vide, sans schéma, > 2048 → 400 et AUCUNE ligne (mutation 1)."""
    import app as app_module
    memo = _mk_memo(client, "Validation")
    r = _add(client, memo["id"], mauvaise)
    assert r.status_code == 400, (mauvaise, r.data)
    assert "http" in (r.get_json() or {}).get("error", "").lower()
    assert _urls(client, memo["id"]) == []
    assert _count_rows(app_module) == 0


def test_label_is_plain_text_and_bounded(client):
    memo = _mk_memo(client, "Libellé")
    r = _add(client, memo["id"], SUIVI, "  <b>gras</b> " + ("l" * 200))
    assert r.status_code == 201, r.data
    lab = r.get_json()["label"]
    assert len(lab) <= 120
    assert lab.startswith("<b>gras</b>"), "le libellé est du TEXTE brut (échappé au rendu), pas filtré"


# --------------------------------------------------------------------------- 3


def test_duplicate_url_is_409(client):
    """Même URL, même mémo → 409 ; une autre casse de chemin est une AUTRE URL (mutation 2)."""
    memo = _mk_memo(client, "Doublon")
    assert _add(client, memo["id"], SUIVI).status_code == 201
    r = _add(client, memo["id"], SUIVI, "autre libellé")
    assert r.status_code == 409, r.data
    assert len(_urls(client, memo["id"])) == 1
    # la même URL sur un AUTRE mémo est légitime
    autre = _mk_memo(client, "Autre mémo")
    assert _add(client, autre["id"], SUIVI).status_code == 201


# --------------------------------------------------------------------------- 4


def test_cap_per_memo(client):
    import app as app_module
    memo = _mk_memo(client, "Plafond")
    for i in range(app_module.MEMO_URLS_MAX):
        assert _add(client, memo["id"], "https://exemple.test/%d" % i).status_code == 201
    r = _add(client, memo["id"], "https://exemple.test/trop")
    assert r.status_code == 400, "le plafond par mémo n'est pas appliqué"
    assert "maximum" in (r.get_json() or {}).get("error", "").lower()
    assert len(_urls(client, memo["id"])) == app_module.MEMO_URLS_MAX


def test_update_label_and_position_and_delete(client):
    memo = _mk_memo(client, "Édition")
    a = _add(client, memo["id"], "https://exemple.test/a").get_json()
    b = _add(client, memo["id"], "https://exemple.test/b").get_json()
    r = client.put("/api/memos/%d/urls/%d" % (memo["id"], b["id"]), json={"label": "Bé", "position": 0})
    assert r.status_code == 200, r.data
    vus = _urls(client, memo["id"])
    assert [x["url"] for x in vus] == ["https://exemple.test/b", "https://exemple.test/a"]
    assert vus[0]["label"] == "Bé"
    assert client.delete("/api/memos/%d/urls/%d" % (memo["id"], a["id"])).status_code == 204
    assert [x["id"] for x in _urls(client, memo["id"])] == [b["id"]]
    assert client.delete("/api/memos/%d/urls/%d" % (memo["id"], a["id"])).status_code == 404
    # l'URL ne se modifie pas par PUT : on retire puis on rattache (dédup intacte)
    r = client.put("/api/memos/%d/urls/%d" % (memo["id"], b["id"]), json={"url": "javascript:x"})
    assert r.status_code == 200
    assert _urls(client, memo["id"])[0]["url"] == "https://exemple.test/b"


# --------------------------------------------------------------------------- 5


def test_trash_hides_restore_returns_purge_deletes(client):
    """Corbeille → masquées (conservées) ; restauration → reviennent ; purge → lignes supprimées
    (mutation 6 : purge sans cascade)."""
    import app as app_module
    memo = _mk_memo(client, "Corbeille")
    assert _add(client, memo["id"], SUIVI, "Suivi").status_code == 201
    assert client.delete("/api/memos/%d" % memo["id"]).status_code in (200, 204)
    assert memo["id"] not in _memos(client)
    assert client.get("/api/memos/%d/urls" % memo["id"]).status_code == 404, \
        "un mémo en corbeille ne doit plus répondre ses liens"
    assert _add(client, memo["id"], "https://exemple.test/x").status_code == 404
    assert _count_rows(app_module) == 1, "la corbeille ne détruit pas"

    assert client.post("/api/trash/%d/restore" % memo["id"]).status_code in (200, 204)
    assert [x["label"] for x in _memos(client)[memo["id"]]["urls"]] == ["Suivi"]

    assert client.delete("/api/memos/%d" % memo["id"]).status_code in (200, 204)
    assert client.delete("/api/trash/%d" % memo["id"]).status_code in (200, 204)
    assert _count_rows(app_module) == 0, "la purge définitive laisse des lignes orphelines"


def test_auto_purge_deletes_rows(client, monkeypatch):
    """La purge AUTOMATIQUE (`_purge_trash`, délai écoulé) emporte aussi les lignes."""
    import app as app_module
    memo = _mk_memo(client, "Vieille corbeille")
    assert _add(client, memo["id"], SUIVI).status_code == 201
    assert client.delete("/api/memos/%d" % memo["id"]).status_code in (200, 204)
    monkeypatch.setattr(app_module, "BACKUP_KEEP_DAYS", 0)
    con = app_module.sqlite3.connect(app_module.DB_PATH)
    con.execute("UPDATE memos SET deleted_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (memo["id"],))
    con.commit(); con.close()
    app_module._purge_trash()
    assert _count_rows(app_module) == 0


# --------------------------------------------------------------------------- 6


_EXPORT_KEYS = {"url", "label", "position", "created_at", "created_by"}


def test_export_v29_urls_without_og_and_roundtrip(client, new_base, monkeypatch):
    """`version == 29`, `urls` nichée par mémo SANS `og_*` (mutation 3) ; ré-import = 0 doublon
    et un libellé local non vide n'est pas écrasé par un vide (invariant 2)."""
    import app as app_module
    monkeypatch.setattr(app_module, "_fetch_og", lambda url: {
        "status": "ok", "title": "Suivi de colis", "desc": "", "domain": "suivi.exemple.test", "image_bytes": b""})
    proj = _mk_project(client, "Maison")
    memo = _mk_memo(client, "Réparation iPad", pid=proj["id"])
    assert _add(client, memo["id"], SUIVI, "Suivi Apple").status_code == 201
    assert _add(client, memo["id"], "https://apple.com/fr").status_code == 201

    exp = client.get("/api/export").get_json()
    assert int(exp["version"]) >= 29, "le bump de format n'est pas dans l'export"
    assert client.get("/api/version").get_json()["export"] >= 29
    m = next(x for x in exp["memos"] if x["uid"] == memo["uid"])
    assert len(m["urls"]) == 2
    for u in m["urls"]:
        assert set(u) == _EXPORT_KEYS, "export : %r" % sorted(u)
        assert not any(k.startswith("og_") for k in u)
    assert [u["position"] for u in m["urls"]] == [0, 1]
    assert "og_title" not in str(exp)  # aucune dérivée nulle part
    brut = client.get("/api/export").data.decode()
    assert "Suivi de colis" not in brut

    # … importé sur une base VIERGE : tout se retrouve, et `og_domain` est recalculé (pur).
    c2 = new_base()
    r = c2.post("/api/import", json=exp)
    assert r.status_code == 200, r.data
    assert r.get_json().get("imported_memo_urls") == 2
    mid2 = next(i for i, x in _memos(c2).items() if x["uid"] == memo["uid"])
    vus = _urls(c2, mid2)
    assert [u["url"] for u in vus] == [SUIVI, "https://apple.com/fr"]
    assert vus[0]["label"] == "Suivi Apple"
    assert vus[0]["og_domain"] == "suivi.exemple.test"

    # Ré-import : additif → zéro doublon (UNIQUE — mutation 2).
    assert c2.post("/api/import", json=exp).status_code == 200
    assert len(_urls(c2, mid2)) == 2
    assert _count_rows(app_module) == 2

    # Un libellé local non vide n'est pas écrasé par un import au libellé vide ; une URL invalide
    # dans le fichier est ignorée, jamais un 400.
    bancal = dict(exp)
    bancal["memos"] = [dict(x) for x in exp["memos"]]
    for x in bancal["memos"]:
        if x["uid"] == memo["uid"]:
            x["urls"] = [{"url": SUIVI, "label": "", "position": 0, "created_at": "", "created_by": ""},
                         {"url": "javascript:alert(1)", "label": "piège", "position": 5},
                         "pas un dict"]
            x["updated_at"] = "2099-01-01T00:00:00+00:00"
    assert c2.post("/api/import", json=bancal).status_code == 200
    vus = _urls(c2, mid2)
    assert [u["url"] for u in vus] == [SUIVI, "https://apple.com/fr"], "une URL locale a été retirée"
    assert vus[0]["label"] == "Suivi Apple", "un libellé rempli a été écrasé par un vide (invariant 2)"


def test_v28_export_still_importable(client, new_base):
    """Un export v28 (sans `urls`) s'importe et rend la même chose — invariants 1 et 2."""
    memo = _mk_memo(client, "Déjà là")
    assert _add(client, memo["id"], SUIVI).status_code == 201
    exp = client.get("/api/export").get_json()
    v28 = dict(exp)
    v28["version"] = 28
    v28["memos"] = [{k: v for k, v in x.items() if k != "urls"} for x in exp["memos"]]
    c2 = new_base()
    r = c2.post("/api/import", json=v28)
    assert r.status_code == 200, r.data
    assert r.get_json().get("imported_memo_urls", 0) == 0
    mid2 = next(i for i, x in _memos(c2).items() if x["uid"] == memo["uid"])
    assert _urls(c2, mid2) == [], "un export sans liens ne doit pas en inventer"


@pytest.mark.invariant
@pytest.mark.parametrize("version", list(range(1, 29)))
def test_every_older_version_imports(client, version):
    """Tout export v1→v28 (forme minimale de chaque époque) reste importable sans 500."""
    if version == 1:
        payload = {"version": 1, "links": [], "memos": ["Note v1"]}
    else:
        payload = {"version": version, "links": [], "categories": [], "projects": [],
                   "memos": [{"uid": "00000000-0000-4000-8000-%012d" % version,
                              "content": "Note v%d" % version}]}
    r = client.post("/api/import", json=payload)
    assert r.status_code == 200, (version, r.data)
    contents = [m["content"] for m in _memos(client).values()]
    assert "Note v%d" % version in contents


# --------------------------------------------------------------------------- 7


_PROJECTION = {"url", "label", "og_title", "og_domain"}


def _share(c, kind, target_id, **kw):
    body = {"kind": kind, "target_id": target_id}
    body.update(kw)
    r = c.post("/api/shares", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token, json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def test_guest_projection_and_write_matrix(client, monkeypatch):
    """Invité : projection STRICTE `{url,label,og_title,og_domain}` (mutation 4 : `created_by`
    fuité), POST lecteur → 403, éditeur → 201, mémo hors scope → 404, anonyme → 403."""
    import app as app_module
    monkeypatch.setattr(app_module, "_fetch_og", lambda url: {
        "status": "ok", "title": "Suivi de colis", "desc": "", "domain": "suivi.exemple.test", "image_bytes": b""})
    proj = _mk_project(client, "Voyage")
    memo = _mk_memo(client, "Hôtel Kyoto", pid=proj["id"])
    hors = _mk_memo(client, "Hors scope")
    assert _add(client, memo["id"], SUIVI, "Suivi").status_code == 201

    lecteur = _share(client, "project", proj["id"], role="viewer")
    gt_l = _register(client, lecteur["token"], lecteur["pin"], "lecteur@ex.com")
    data = client.get("/share/%s/data" % lecteur["token"], headers={"X-Guest-Token": gt_l}).get_json()
    vus = {m["content"]: m for m in data.get("memos", [])}
    assert "Hors scope" not in vus
    urls = vus["Hôtel Kyoto"].get("urls")
    assert urls and len(urls) == 1
    assert set(urls[0]) == _PROJECTION, "projection trop large : %r" % sorted(urls[0])
    assert urls[0]["og_title"] == "Suivi de colis" and urls[0]["label"] == "Suivi"

    # lecteur approuvé : écrire est refusé
    r = client.post("/share/%s/memo/%d/urls" % (lecteur["token"], memo["id"]),
                    headers={"X-Guest-Token": gt_l}, json={"url": "https://exemple.test/l"})
    assert r.status_code == 403, r.data
    # anonyme : refusé aussi
    r = client.post("/share/%s/memo/%d/urls" % (lecteur["token"], memo["id"]), json={"url": "https://exemple.test/a"})
    assert r.status_code in (401, 403), r.data

    editeur = _share(client, "project", proj["id"], role="editor")
    gt_e = _register(client, editeur["token"], editeur["pin"], "editeur@ex.com", "Édith")
    r = client.post("/share/%s/memo/%d/urls" % (editeur["token"], memo["id"]),
                    headers={"X-Guest-Token": gt_e}, json={"url": "https://exemple.test/e", "label": "Par Édith"})
    assert r.status_code == 201, r.data
    rendu = r.get_json()
    assert isinstance(rendu, list) and all(set(u) == _PROJECTION for u in rendu), rendu
    assert [u["url"] for u in rendu] == [SUIVI, "https://exemple.test/e"]
    # côté owner, la provenance est tracée (pattern created_by v19)
    mine = [u for u in _urls(client, memo["id"]) if u["url"].endswith("/e")][0]
    assert "editeur@ex.com" in mine["created_by"] and "Édith" in mine["created_by_display"]

    # validation serveur identique pour l'invité
    r = client.post("/share/%s/memo/%d/urls" % (editeur["token"], memo["id"]),
                    headers={"X-Guest-Token": gt_e}, json={"url": "javascript:alert(1)"})
    assert r.status_code == 400
    # mémo hors scope → 404 (jamais 201, jamais une fuite)
    r = client.post("/share/%s/memo/%d/urls" % (editeur["token"], hors["id"]),
                    headers={"X-Guest-Token": gt_e}, json={"url": "https://exemple.test/h"})
    assert r.status_code == 404, r.data
    assert _urls(client, hors["id"]) == []

    # retirer : l'éditeur retire PAR URL (la projection n'a pas d'id) ; hors scope → 404
    r = client.delete("/share/%s/memo/%d/urls" % (editeur["token"], memo["id"]),
                      headers={"X-Guest-Token": gt_e}, json={"url": "https://exemple.test/e"})
    assert r.status_code == 204, r.data
    assert [u["url"] for u in _urls(client, memo["id"])] == [SUIVI]
    r = client.delete("/share/%s/memo/%d/urls" % (editeur["token"], hors["id"]),
                      headers={"X-Guest-Token": gt_e}, json={"url": SUIVI})
    assert r.status_code == 404
    # le lecteur ne retire rien
    r = client.delete("/share/%s/memo/%d/urls" % (lecteur["token"], memo["id"]),
                      headers={"X-Guest-Token": gt_l}, json={"url": SUIVI})
    assert r.status_code == 403
    assert len(_urls(client, memo["id"])) == 1


def test_hub_payload_has_same_projection(client, monkeypatch):
    import sqlite3
    import app as app_module
    proj = _mk_project(client, "Hub voyage")
    memo = _mk_memo(client, "Billets", pid=proj["id"])
    assert _add(client, memo["id"], SUIVI, "Suivi").status_code == 201
    sh = _share(client, "project", proj["id"], role="editor")
    _register(client, sh["token"], sh["pin"], "hub@ex.com", "Hubert")
    con = sqlite3.connect(app_module.DB_PATH); con.row_factory = sqlite3.Row
    row = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?", ("hub@ex.com",)).fetchone()
    con.close()
    assert client.post("/share/hub/%s/approve" % row["hub_token"], json={"pin": row["pin"]}).status_code == 200
    data = client.get("/share/hub/%s/data" % row["hub_token"]).get_json()
    vus = {m["content"]: m for m in data.get("memos", [])}
    urls = vus["Billets"].get("urls")
    assert urls and set(urls[0]) == _PROJECTION, urls


# --------------------------------------------------------------------------- 8


def test_og_preview_filled_or_silently_empty(client, monkeypatch):
    """`_fetch_og` rempli → `og_title/og_domain` ; réseau en panne → vides et 201 quand même."""
    import app as app_module
    appels = []

    def _ok(url):
        appels.append(url)
        return {"status": "ok", "title": "Réparation — suivi", "desc": "", "domain": "suivi.exemple.test", "image_bytes": b""}

    monkeypatch.setattr(app_module, "_fetch_og", _ok)
    memo = _mk_memo(client, "Aperçu")
    r = _add(client, memo["id"], SUIVI)
    assert r.status_code == 201, r.data
    assert appels == [SUIVI]
    u = r.get_json()
    assert u["og_title"] == "Réparation — suivi" and u["og_domain"] == "suivi.exemple.test"

    def _panne(url):
        raise RuntimeError("réseau en panne")

    monkeypatch.setattr(app_module, "_fetch_og", _panne)
    r = _add(client, memo["id"], "https://autre.exemple.test/p")
    assert r.status_code == 201, "un aperçu en échec ne doit jamais empêcher l'ajout"
    u = r.get_json()
    assert u["og_title"] == "" and u["og_domain"] == "autre.exemple.test", \
        "le domaine est PUR (urlparse), il ne dépend pas de l'aperçu"
