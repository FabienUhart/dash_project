"""[LINK-REFS] Relier un LIEN à un mémo ou à un dossier — export v28.

Brief : `docs/briefs/LINK-REFS.md` (maquette validée par Fabien le 6 sept. 2026). Clôt son mémo
prod 257. **Ce lot bump le format d'export : X passe de 27 à 28.**

Ce que ces parcours PROTÈGENT :

- **la relation est symétrique** : posée d'un côté, elle se lit des deux — sinon « relié » voudrait
  dire deux choses selon l'écran où on se trouve ;
- **la projection invitée est STRICTE** (test 9) : un invité voit `{name, url_public, og_domain}`
  et RIEN d'autre. Pas d'`url_local` (un service LAN n'a rien à faire chez lui), pas la note
  `memo`, pas les tags, pas d'id — la table `links` reste hors de son périmètre (invariant 5) ;
- **l'export voyage par UID** (test 6) : un id n'a aucun sens dans une autre base, et l'import
  reste TOLÉRANT (uid inconnu → ref ignorée) et NON DESTRUCTIF (invariants 1 et 2) ;
- **un export v27 reste importable** (test 7) : la compat ascendante est l'invariant n° 1, et un
  bump de format est exactement le moment où on la casse par inadvertance ;
- **la corbeille masque sans détruire** (test 5) : restaurer un mémo doit lui rendre ses relations,
  comme pour les liens mémo↔mémo de v27 (invariant 7).
"""
import pytest


def _mk_link(c, name, url_public="", url_local=""):
    r = c.post("/api/links", json={"name": name, "url_public": url_public, "url_local": url_local})
    assert r.status_code == 201, r.data
    return r.get_json()


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


def _ref(c, link_id, kind, target_id):
    return c.post("/api/links/%d/refs" % link_id, json={"kind": kind, "target_id": target_id})


def _links(c):
    r = c.get("/api/links")
    assert r.status_code == 200, r.data
    return {l["name"]: l for l in r.get_json()}


def _memos(c):
    r = c.get("/api/memos")
    assert r.status_code == 200, r.data
    data = r.get_json()
    rows = data if isinstance(data, list) else data.get("memos", [])
    return {m["id"]: m for m in rows}


def _projects(c):
    r = c.get("/api/projects")
    assert r.status_code == 200, r.data
    return {p["name"]: p for p in r.get_json()}


# --------------------------------------------------------------------------- 1


def test_add_ref_memo_and_project_symmetric(client):
    """Posée d'un côté, la relation se lit des DEUX : c'est une relation, pas un champ."""
    lien = _mk_link(client, "Rentila", url_public="https://rentila.com")
    memo = _mk_memo(client, "Déclarer les loyers")
    proj = _mk_project(client, "Finance")

    assert _ref(client, lien["id"], "memo", memo["id"]).status_code == 201
    assert _ref(client, lien["id"], "project", proj["id"]).status_code == 201

    vu_lien = _links(client)["Rentila"]
    kinds = {(r["kind"], r["id"]) for r in vu_lien.get("refs", [])}
    assert ("memo", memo["id"]) in kinds and ("project", proj["id"]) in kinds

    cote_memo = _memos(client)[memo["id"]].get("link_refs", [])
    assert [r["name"] for r in cote_memo] == ["Rentila"]
    cote_proj = _projects(client)["Finance"].get("link_refs", [])
    assert [r["name"] for r in cote_proj] == ["Rentila"]

    # …et l'inverse : écrire depuis le mémo se lit depuis le lien.
    autre = _mk_link(client, "Impots", url_public="https://impots.gouv.fr")
    r = client.post("/api/memos/%d/link-refs" % memo["id"], json={"link_id": autre["id"]})
    assert r.status_code == 201, r.data
    assert {x["name"] for x in _memos(client)[memo["id"]]["link_refs"]} == {"Rentila", "Impots"}
    assert ("memo", memo["id"]) in {(x["kind"], x["id"]) for x in _links(client)["Impots"]["refs"]}


# --------------------------------------------------------------------------- 2


def test_ref_unique_pair_and_caps(client):
    """Reposer la même relation est idempotent ; au-delà du plafond, 400 explicite."""
    import app as app_module

    lien = _mk_link(client, "Actual", url_public="https://actualbudget.org")
    memo = _mk_memo(client, "Budget")
    assert _ref(client, lien["id"], "memo", memo["id"]).status_code == 201
    r2 = _ref(client, lien["id"], "memo", memo["id"])
    assert r2.status_code in (200, 201), r2.data
    assert len(_links(client)["Actual"]["refs"]) == 1, "doublon créé — la clé unique ne tient pas"

    plafond = app_module.LINK_REFS_MAX
    for i in range(plafond - 1):
        m = _mk_memo(client, "Budget %02d" % i)
        assert _ref(client, lien["id"], "memo", m["id"]).status_code == 201
    trop = _mk_memo(client, "Celui de trop")
    r = _ref(client, lien["id"], "memo", trop["id"])
    assert r.status_code == 400, "le plafond par lien n'est pas appliqué"
    assert "maximum" in (r.get_json() or {}).get("error", "").lower()


# --------------------------------------------------------------------------- 3


def test_ref_target_must_exist(client):
    """Une cible inconnue, ou en corbeille, n'est pas une cible : 404, jamais une ligne fantôme."""
    lien = _mk_link(client, "Navidrome", url_public="https://navidrome.org")
    assert _ref(client, lien["id"], "memo", 999_999).status_code == 404
    assert _ref(client, lien["id"], "project", 999_999).status_code == 404

    jete = _mk_memo(client, "Bientôt en corbeille")
    assert client.delete("/api/memos/%d" % jete["id"]).status_code in (200, 204)
    assert _ref(client, lien["id"], "memo", jete["id"]).status_code == 404

    assert _ref(client, lien["id"], "autre", 1).status_code == 400
    assert _links(client)["Navidrome"].get("refs", []) == []


# --------------------------------------------------------------------------- 4


def test_refs_cascade_on_delete(client):
    """Supprimer le porteur emporte ses relations : aucune ref orpheline ne survit."""
    import app as app_module

    lien = _mk_link(client, "Jellyfin", url_public="https://jellyfin.org")
    memo = _mk_memo(client, "Ranger les films")
    proj = _mk_project(client, "Media")
    for kind, tid in (("memo", memo["id"]), ("project", proj["id"])):
        assert _ref(client, lien["id"], kind, tid).status_code == 201

    def _compte():
        con = app_module.sqlite3.connect(app_module.DB_PATH)
        try:
            return con.execute("SELECT COUNT(*) FROM link_refs").fetchone()[0]
        finally:
            con.close()

    assert _compte() == 2
    assert client.delete("/api/links/%d" % lien["id"]).status_code in (200, 204)
    assert _compte() == 0, "les refs du lien supprimé survivent"

    # …et dans l'autre sens : purger le mémo, supprimer le dossier.
    lien2 = _mk_link(client, "Immich", url_public="https://immich.app")
    for kind, tid in (("memo", memo["id"]), ("project", proj["id"])):
        assert _ref(client, lien2["id"], kind, tid).status_code == 201
    assert _compte() == 2
    assert client.delete("/api/memos/%d" % memo["id"]).status_code in (200, 204)
    assert client.delete("/api/trash/%d" % memo["id"]).status_code in (200, 204)
    assert client.delete("/api/projects/%d" % proj["id"]).status_code in (200, 204)
    assert _compte() == 0, "les refs d'un mémo purgé ou d'un dossier supprimé survivent"


# --------------------------------------------------------------------------- 5


def test_trashed_memo_hides_refs_but_keeps_them(client):
    """Corbeille = masqué partout, conservé quand même — restaurer rend la relation (invariant 7)."""
    lien = _mk_link(client, "Paperless", url_public="https://paperless-ngx.com")
    memo = _mk_memo(client, "Scanner les factures")
    assert _ref(client, lien["id"], "memo", memo["id"]).status_code == 201

    assert client.delete("/api/memos/%d" % memo["id"]).status_code in (200, 204)
    assert _links(client)["Paperless"].get("refs", []) == [], "une ref vers la corbeille reste visible"

    r = client.post("/api/trash/%d/restore" % memo["id"])
    assert r.status_code in (200, 204), r.data
    assert [x["id"] for x in _links(client)["Paperless"]["refs"]] == [memo["id"]], \
        "la relation n'est pas revenue avec le mémo restauré"


# --------------------------------------------------------------------------- 6


def test_export_v28_link_refs_by_uid_and_roundtrip(client, new_base):
    """L'export porte `version: 28` et des relations par UID ; l'import les recrée, sans doublon."""
    lien = _mk_link(client, "Rentila", url_public="https://rentila.com")
    proj = _mk_project(client, "Finance")
    memo = _mk_memo(client, "Déclarer les loyers", pid=proj["id"])
    for kind, tid in (("memo", memo["id"]), ("project", proj["id"])):
        assert _ref(client, lien["id"], kind, tid).status_code == 201

    exp = client.get("/api/export").get_json()
    assert int(exp["version"]) == 28, "le bump de format n'est pas dans l'export"
    refs = exp.get("link_refs")
    assert refs and len(refs) == 2, refs
    for r in refs:
        assert set(r) == {"link_uid", "kind", "target_uid", "created_at", "created_by"}, r
        assert isinstance(r["link_uid"], str) and len(r["link_uid"]) > 10
        assert "id" not in r and "link_id" not in r and "target_id" not in r

    # … importé sur une base VIERGE, tout se retrouve.
    c2 = new_base()
    r = c2.post("/api/import", json=exp)
    assert r.status_code == 200, r.data
    vus = _links(c2)["Rentila"]["refs"]
    assert {v["kind"] for v in vus} == {"memo", "project"}

    # Ré-import : additif, donc zéro doublon.
    assert c2.post("/api/import", json=exp).status_code == 200
    assert len(_links(c2)["Rentila"]["refs"]) == 2, "le ré-import duplique les relations"

    # Un uid inconnu est IGNORÉ, jamais une erreur : un export partiel reste importable.
    bancal = dict(exp)
    bancal["link_refs"] = list(exp["link_refs"]) + [{
        "link_uid": "00000000-0000-4000-8000-000000000000", "kind": "memo",
        "target_uid": "11111111-1111-4111-8111-111111111111",
        "created_at": "2026-01-01T00:00:00+00:00", "created_by": "",
    }]
    c3 = new_base()
    r = c3.post("/api/import", json=bancal)
    assert r.status_code == 200, r.data
    assert len(_links(c3)["Rentila"]["refs"]) == 2


# --------------------------------------------------------------------------- 7


def test_v27_export_still_importable(client, new_base):
    """Un export v27 (sans `link_refs`) s'importe et rend la même chose — invariants 1 et 2."""
    lien = _mk_link(client, "Rentila", url_public="https://rentila.com")
    memo = _mk_memo(client, "Déclarer les loyers")
    assert _ref(client, lien["id"], "memo", memo["id"]).status_code == 201
    exp = client.get("/api/export").get_json()

    v27 = dict(exp)
    v27["version"] = 27
    v27.pop("link_refs", None)
    c2 = new_base()
    r = c2.post("/api/import", json=v27)
    assert r.status_code == 200, r.data
    assert "Rentila" in _links(c2)
    assert _links(c2)["Rentila"].get("refs", []) == [], \
        "un export sans relations ne doit pas en inventer"


# --------------------------------------------------------------------------- 8


def test_subtree_export_omits_out_of_scope_refs(client):
    """Export d'un sous-arbre : une relation vers un objet hors du sous-arbre est OMISE.

    Sinon l'export porterait un uid que rien, dans ce même fichier, ne permet de résoudre.
    """
    dedans = _mk_project(client, "Voyage")
    dehors = _mk_project(client, "Maison")
    m_dedans = _mk_memo(client, "Billets", pid=dedans["id"])
    m_dehors = _mk_memo(client, "Chaudière", pid=dehors["id"])
    lien = _mk_link(client, "SNCF", url_public="https://sncf-connect.com")
    assert _ref(client, lien["id"], "memo", m_dedans["id"]).status_code == 201
    assert _ref(client, lien["id"], "memo", m_dehors["id"]).status_code == 201

    exp = client.get("/api/export?project_id=%d" % dedans["id"]).get_json()
    uids = {m["uid"] for m in exp.get("memos", [])}
    refs = exp.get("link_refs") or []
    assert refs, "le sous-arbre doit porter la relation qui lui appartient"
    assert all(r["target_uid"] in uids for r in refs if r["kind"] == "memo"), \
        "une relation vers un mémo hors sous-arbre a fuité dans l'export"


# --------------------------------------------------------------------------- 9


_PROJECTION = {"name", "url_public", "og_domain"}


def test_guest_link_refs_strict_projection(client):
    """L'invité voit EXACTEMENT {name, url_public, og_domain}, et rien de plus (invariant 5).

    Le consentement du propriétaire porte sur la relation, pas sur la table `links` : `url_local`
    (un service du LAN), la note `memo`, les tags, l'id — rien de tout ça ne doit franchir
    `/share/`. Et un lien SANS `url_public` n'est pas exposé du tout : il n'existe que sur le
    réseau de Fabien.
    """
    proj = _mk_project(client, "Voyage")
    memo = _mk_memo(client, "Hôtel Kyoto", pid=proj["id"])
    hors = _mk_memo(client, "Hors scope")
    public = _mk_link(client, "Rentila", url_public="https://rentila.com",
                      url_local="http://192.168.1.39:8099")
    lan = _mk_link(client, "Navidrome", url_local="http://192.168.1.39:4533")
    assert _ref(client, public["id"], "memo", memo["id"]).status_code == 201
    assert _ref(client, lan["id"], "memo", memo["id"]).status_code == 201
    assert _ref(client, public["id"], "memo", hors["id"]).status_code == 201

    sh = client.post("/api/shares", json={"kind": "project", "target_id": proj["id"]}).get_json()
    data = client.get("/share/%s/data" % sh["token"]).get_json()
    vus = {m["content"]: m for m in data.get("memos", [])}
    assert "Hors scope" not in vus, "fuite hors scope"
    refs = vus["Hôtel Kyoto"].get("link_refs", [])
    assert len(refs) == 1, "le lien sans url_public ne doit pas être exposé : %r" % refs
    assert set(refs[0]) == _PROJECTION, "projection trop large : %r" % sorted(refs[0])
    assert refs[0]["url_public"] == "https://rentila.com"

    brut = client.get("/share/%s/data" % sh["token"]).data.decode()
    assert "192.168.1.39" not in brut, "une URL locale a fuité dans la charge invitée"
    assert "Navidrome" not in brut

    # Aucune route d'écriture invitée : relier est un acte du propriétaire (tranche C).
    r = client.post("/share/%s/link-refs" % sh["token"], json={"link_id": public["id"]})
    assert r.status_code in (404, 405), r.status_code


# -------------------------------------------------------------------------- 10


@pytest.mark.invariant
def test_link_refs_never_leak_ids_in_export(client):
    """Garde-fou de format : l'export ne porte QUE des uid pour les relations (invariant 1)."""
    lien = _mk_link(client, "Rentila", url_public="https://rentila.com")
    memo = _mk_memo(client, "Loyers")
    assert _ref(client, lien["id"], "memo", memo["id"]).status_code == 201
    exp = client.get("/api/export").get_json()
    for r in exp.get("link_refs") or []:
        assert not any(k.endswith("_id") for k in r), r
