"""[TESTS-PORT vague 5] Les entrailles de l'import — invariants 1, 2 et 3.

C'est la douleur d'origine : `import_links` est l'endroit où [IMPORT-CONTENT-DEDUP-FIX]
avait perdu **12 mémos sur 51 en silence** (V27.36.228), et `_import_dry_run` n'avait
jamais été exécuté par un test. La batterie d'invariants tient la **crête** (round-trip
sans perte, v1 importable, non-destruction, uid stable) ; ce fichier descend dans les
**branches** : aperçu, « Importer ici », résolution des projets, remap des priorités,
dédup fine, résolutions de conflit.

Nature = **CARACTÉRISATION + mutation**. Un rouge ici est un bug de DONNÉES — la pire
espèce, parce qu'elle est silencieuse. Zéro réseau.

⚠ **Une sémantique à ne pas croire sur parole** : dans `resolutions`, seuls `overwrite` et
`duplicate` font quelque chose. Toute autre valeur — y compris le mot `"skip"` — retombe
sur le comportement par défaut, qui est **newer-wins**, PAS « ne rien faire ». Un fichier
plus récent met donc à jour un mémo marqué `"skip"`. C'est vérifié plus bas, et c'est
contre-intuitif : le nom promet l'inverse de ce que le code fait.
"""
import json
import sqlite3

import pytest

pytestmark = pytest.mark.invariant


# ─────────────────────────────────────────────────────────────── montage ────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _project(c, name, parent_id=None):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    pid = r.get_json()["id"]
    if parent_id is not None:
        assert c.put("/api/projects/%d" % pid, json={"parent_id": parent_id}).status_code == 200
    return pid


def _memo(c, content, project_id=None, **extra):
    body = {"content": content}
    if project_id is not None:
        body["project_id"] = project_id
    body.update(extra)
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _row(table, **where):
    cond = " AND ".join("%s = ?" % k for k in where)
    con = _db()
    try:
        return con.execute("SELECT * FROM %s WHERE %s" % (table, cond),
                           tuple(where.values())).fetchone()
    finally:
        con.close()


def _memo_uid(memo_id):
    return _row("memos", id=memo_id)["uid"]


def _memos_matching(content):
    con = _db()
    try:
        return con.execute(
            "SELECT * FROM memos WHERE content = ? AND COALESCE(deleted_at,'') = '' ORDER BY id",
            (content,)).fetchall()
    finally:
        con.close()


def _projects():
    con = _db()
    try:
        return {r["name"]: r for r in con.execute("SELECT * FROM projects").fetchall()}
    finally:
        con.close()


def _import(c, payload, **params):
    q = "&".join("%s=%s" % (k, v) for k, v in params.items())
    url = "/api/import" + ("?" + q if q else "")
    return c.post(url, json=payload)


def _dry(c, payload):
    r = _import(c, payload, dry_run=1)
    assert r.status_code == 200, r.data
    return r.get_json()


def _snapshot(c):
    """L'export, débarrassé de ce qui bouge tout seul — pour prouver qu'un dry-run n'écrit RIEN."""
    e = c.get("/api/export").get_json()
    return json.dumps({k: e.get(k) for k in ("memos", "projects", "categories", "links",
                                             "priorities")}, sort_keys=True, ensure_ascii=False)


# ══════════════ A. _import_dry_run — lecture pure (0 % avant ce lot) ══════════════

def test_dry_run_writes_nothing(client):
    """La promesse du mode aperçu : on regarde sans toucher. S'il écrivait, l'utilisateur
    aurait déjà importé au moment de décider s'il veut importer."""
    c = client
    pid = _project(c, "Dossier existant")
    _memo(c, "Mémo déjà là", project_id=pid)
    avant = _snapshot(c)

    rapport = _dry(c, {"memos": [{"content": "Un mémo tout neuf", "uid": "uid-neuf-1"},
                                 {"content": "Encore un", "uid": "uid-neuf-2"}],
                       "projects": [{"name": "Dossier jamais vu"}]})
    assert rapport["bilan"]["memos_new"] == 2
    assert rapport["bilan"]["projects_new"] == 1
    assert _snapshot(c) == avant, "le dry-run a écrit quelque chose"
    assert "Dossier jamais vu" not in _projects()


def test_dry_run_project_new_vs_merge(client):
    """`merge` se décide uid-D'ABORD : un dossier renommé localement mais réimporté sous le
    même uid est un MERGE, pas un nouveau — sinon chaque renommage créerait un doublon."""
    c = client
    pid = _project(c, "Voyage Japon")
    uid_local = _row("projects", id=pid)["uid"]

    rapport = _dry(c, {"memos": [], "projects": [
        {"name": "Voyage Japon 2026", "uid": uid_local},   # même uid, nom différent → merge
        {"name": "Voyage Japon"},                          # même nom, sans uid → merge
        {"name": "Voyage Corée"},                          # inconnu → new
    ]})
    par_nom = {p["name"]: p["status"] for p in rapport["projects"]}
    assert par_nom["Voyage Japon 2026"] == "merge"
    assert par_nom["Voyage Japon"] == "merge"
    assert par_nom["Voyage Corée"] == "new"
    assert rapport["bilan"]["projects_new"] == 1
    assert rapport["bilan"]["projects_merge"] == 2


def test_dry_run_memo_new_skip_conflict(client):
    """Les quatre états d'un mémo à l'aperçu. `skip` tient à la SIGNATURE (contenu/titre/
    done/date/heure), pas à `updated_at` : un mémo retouché puis remis à l'identique reste
    « rien à faire »."""
    c = client
    id_same = _memo(c, "Identique des deux côtés")
    id_diff = _memo(c, "Modifié localement")
    id_trash = _memo(c, "Parti à la corbeille")
    uid_same, uid_diff, uid_trash = (_memo_uid(i) for i in (id_same, id_diff, id_trash))
    assert c.delete("/api/memos/%d" % id_trash).status_code in (200, 204)

    rapport = _dry(c, {"memos": [
        {"content": "Identique des deux côtés", "uid": uid_same},
        {"content": "Modifié dans le fichier", "uid": uid_diff},
        {"content": "Parti à la corbeille", "uid": uid_trash},
        {"content": "Jamais vu", "uid": "uid-inconnu"},
    ]})
    par_uid = {m["uid"]: m for m in rapport["memos"]}
    assert par_uid[uid_same]["status"] == "skip"
    assert par_uid[uid_diff]["status"] == "conflict"
    assert par_uid[uid_diff]["conflict_kind"] == "active"
    assert par_uid[uid_trash]["status"] == "conflict"
    assert par_uid[uid_trash]["conflict_kind"] == "trashed"
    assert par_uid["uid-inconnu"]["status"] == "new"

    b = rapport["bilan"]
    assert (b["memos_new"], b["memos_skip"], b["conflicts_active"], b["conflicts_trashed"]) == (1, 1, 1, 1)


def test_dry_run_builds_the_project_tree(client):
    """L'arbre du rapport doit refléter la hiérarchie du FICHIER, y compris quand l'enfant y
    est listé avant son parent — c'est ce que l'utilisateur va lire pour décider."""
    rapport = _dry(client, {"memos": [], "projects": [
        {"name": "Restaurants", "parent": "Japon"},
        {"name": "Japon"},
    ]})
    assert [r["name"] for r in rapport["projects"]] == ["Japon"]
    assert [e["name"] for e in rapport["projects"][0]["children"]] == ["Restaurants"]


def test_dry_run_ignores_unusable_entries(client):
    """Une entrée sans contenu ni titre, ou qui n'est pas un objet, ne compte pas — et ne
    plante pas non plus (les vieux exports contiennent des chaînes brutes)."""
    rapport = _dry(client, {"memos": ["une chaîne v1", {"content": "   "}, {},
                                      {"content": "Valide", "uid": "u1"}],
                            "projects": ["pas un objet", {"name": "   "}]})
    assert rapport["bilan"]["memos_new"] == 1
    assert rapport["projects"] == []


# ══════════════ B. target_parent_id — « Importer ici » (invariant 2) ══════════════

def test_import_here_invalid_id_400(client):
    r = _import(client, {"memos": []}, target_parent_id="abc")
    assert r.status_code == 400, r.data
    assert r.get_json()["error"] == "target_parent_id invalide"


def test_import_here_unknown_folder_400(client):
    r = _import(client, {"memos": []}, target_parent_id=999999)
    assert r.status_code == 400, r.data
    assert "introuvable" in r.get_json()["error"]


def test_import_here_cycle_400(client):
    """Importer un dossier SOUS lui-même n'a pas de sens : refus explicite plutôt qu'un arbre
    replié sur lui-même."""
    c = client
    pid = _project(c, "Japon")
    r = _import(c, {"memos": [], "projects": [{"name": "Japon"}, {"name": "Restaurants",
                                                                 "parent": "Japon"}]},
                target_parent_id=pid)
    assert r.status_code == 400, r.data
    assert "cycle" in r.get_json()["error"]


def test_import_here_attaches_only_new_roots(client):
    """Le cœur de « Importer ici », et sa limite : seules les RACINES NOUVELLES du fichier
    atterrissent sous la cible. Un dossier existant n'est jamais déplacé (invariant 2 :
    l'import ajoute, il ne réorganise pas) et un sous-dossier reste sous SON parent."""
    c = client
    cible = _project(c, "Archives")
    deja = _project(c, "Dossier deja la")

    r = _import(c, {"memos": [], "projects": [
        {"name": "Voyage Coree"},                             # racine nouvelle → sous la cible
        {"name": "Restaurants", "parent": "Voyage Coree"},    # a son parent dans le fichier
        {"name": "Dossier deja la"},                          # existant → ne bouge pas
    ]}, target_parent_id=cible)
    assert r.status_code == 200, r.data

    p = _projects()
    assert p["Voyage Coree"]["parent_id"] == cible
    assert p["Restaurants"]["parent_id"] == p["Voyage Coree"]["id"]
    assert p["Dossier deja la"]["id"] == deja
    assert p["Dossier deja la"]["parent_id"] is None, "un dossier existant ne se fait pas déplacer"


def test_import_here_collision_stays_at_root(client):
    """Nom déjà pris sous la cible → le nouveau reste à la racine. Tolérant par choix : un
    import ne doit pas échouer en bloc pour une collision de nom (jamais de 409 ici)."""
    c = client
    cible = _project(c, "Archives")
    _project(c, "Voyage Japon", parent_id=cible)   # occupe la place sous la cible

    r = _import(c, {"memos": [], "projects": [{"name": "Voyage Japon", "uid": "uid-fichier-1"}]},
                target_parent_id=cible)
    assert r.status_code == 200, r.data

    con = _db()
    try:
        lignes = con.execute("SELECT parent_id FROM projects WHERE name = ? ORDER BY id",
                             ("Voyage Japon",)).fetchall()
    finally:
        con.close()
    assert len(lignes) == 2, "le dossier importé doit exister, pas être fondu dans l'occupant"
    assert sorted((r["parent_id"] or 0) for r in lignes) == [0, cible]


def test_import_here_is_inert_without_the_param(client):
    """Sans le paramètre, rien ne change du comportement historique : tout arrive à la racine."""
    c = client
    _project(c, "Archives")
    assert _import(c, {"memos": [], "projects": [{"name": "Voyage Coree"}]}).status_code == 200
    assert _projects()["Voyage Coree"]["parent_id"] is None


# ══════════════ C. Résolution projets / catégories / priorités ══════════════

def test_project_resolved_by_uid_even_if_renamed(client):
    """L'uid est l'identité (invariant 3). Un dossier renommé localement puis réimporté sous
    son uid d'origine se retrouve — et son nom LOCAL n'est pas écrasé : les projets n'ont pas
    d'`updated_at`, donc « newer-wins » serait indécidable ; on ne détruit pas un renommage."""
    c = client
    pid = _project(c, "Nom local retenu")
    uid = _row("projects", id=pid)["uid"]

    assert _import(c, {"memos": [], "projects": [
        {"name": "Nom du fichier", "uid": uid, "color": "#112233"}]}).status_code == 200

    p = _projects()
    assert "Nom du fichier" not in p, "un doublon a été créé au lieu d'un merge"
    apres = _row("projects", id=pid)
    assert apres["name"] == "Nom local retenu"
    assert apres["uid"] == uid, "l'uid ne se régénère jamais"
    assert apres["color"] == "#112233", "les champs VIDES, eux, s'enrichissent"


def test_projects_created_topologically(client):
    """Le fichier peut lister un enfant AVANT son parent : la création se fait dans l'ordre
    topologique, sinon tout atterrirait à la racine (le défaut corrigé en v25)."""
    assert _import(client, {"memos": [], "projects": [
        {"name": "Restaurants", "parent": "Japon"},
        {"name": "Japon"},
    ]}).status_code == 200
    p = _projects()
    assert p["Japon"]["parent_id"] is None
    assert p["Restaurants"]["parent_id"] == p["Japon"]["id"]


def test_same_name_allowed_under_two_parents(client):
    """[PROJECT-NAME-PER-FOLDER] v25 : « Restaurants » sous Japon ET sous Corée — l'unicité
    est par PARENT, plus globale. Sans ça, le second serait avalé par le premier."""
    assert _import(client, {"memos": [], "projects": [
        {"name": "Japon"}, {"name": "Coree"},
        {"name": "Restaurants", "parent": "Japon"},
        {"name": "Restaurants", "parent": "Coree"},
    ]}).status_code == 200

    con = _db()
    try:
        parents = sorted(r["parent_id"] for r in con.execute(
            "SELECT parent_id FROM projects WHERE name = 'Restaurants'").fetchall())
    finally:
        con.close()
    p = _projects()
    assert parents == sorted([p["Japon"]["id"], p["Coree"]["id"]])


def test_memo_project_resolved_by_uid_then_name(client):
    """Rattachement d'un mémo : `project_uid` d'abord, puis le nom ; un nom inconnu fait
    naître le dossier à la racine plutôt que de laisser le mémo orphelin."""
    c = client
    pid = _project(c, "Dossier cible")
    uid = _row("projects", id=pid)["uid"]

    assert _import(c, {"memos": [
        {"content": "Par uid", "uid": "m1", "project_uid": uid, "project": "Nom trompeur"},
        {"content": "Par nom", "uid": "m2", "project": "Dossier cible"},
        {"content": "Nom inconnu", "uid": "m3", "project": "Dossier inexistant"},
    ]}).status_code == 200

    assert _row("memos", uid="m1")["project_id"] == pid, "l'uid doit primer sur le nom"
    assert _row("memos", uid="m2")["project_id"] == pid
    cree = _projects()["Dossier inexistant"]
    assert _row("memos", uid="m3")["project_id"] == cree["id"]
    assert cree["parent_id"] is None


def test_category_enriches_but_never_overwrites(client):
    """Invariant 2 en miniature : l'import remplit les trous, il n'écrase pas ce qui est là."""
    c = client
    assert c.post("/api/categories", json={"name": "Vide", "color": ""}).status_code in (200, 201)
    assert c.post("/api/categories", json={"name": "Colorée", "color": "#aabbcc"}).status_code in (200, 201)

    assert _import(c, {"links": [], "categories": [
        {"name": "Vide", "color": "#123456", "emoji": "🌸"},
        {"name": "Colorée", "color": "#ffffff"},
    ]}).status_code == 200

    assert _row("categories", name="Vide")["color"] == "#123456"
    assert _row("categories", name="Vide")["emoji"] == "🌸"
    assert _row("categories", name="Colorée")["color"] == "#aabbcc", "couleur locale écrasée"


def test_priority_remapped_by_name_not_raw_id(client):
    """Invariant 1 (v10) : une priorité se rattache par NOM, jamais par l'id brut du fichier.
    Deux bases n'attribuent pas les mêmes ids — importer l'id tel quel donnerait à un mémo
    « Urgent » la couleur et le rang de « Plus tard »."""
    c = client
    # Base locale : on crée les priorités dans un ordre, le fichier en utilisera un autre.
    assert _import(c, {"memos": [], "priorities": [{"id": 1, "name": "Basse"},
                                                   {"id": 2, "name": "Haute"}]}).status_code == 200
    local_haute = _row("priorities", name="Haute")["id"]
    local_basse = _row("priorities", name="Basse")["id"]
    assert local_haute != local_basse

    # Fichier : « Haute » y porte l'id 77, et le mémo référence 77.
    assert _import(c, {"memos": [{"content": "Mémo prioritaire", "uid": "mp1", "priority": 77}],
                       "priorities": [{"id": 77, "name": "Haute"},
                                      {"id": 88, "name": "Basse"}]}).status_code == 200

    assert _row("memos", uid="mp1")["priority"] == local_haute
    con = _db()
    try:
        n = con.execute("SELECT COUNT(*) AS n FROM priorities WHERE name = 'Haute'").fetchone()["n"]
    finally:
        con.close()
    assert n == 1, "la priorité de même nom ne doit pas être dupliquée"


# ══════════════ D. Dédup mémo & résolutions — le cœur données ══════════════

def test_content_dedup_applies_only_without_uid(client):
    """LE bug de V27.36.228, des deux côtés. Sans uid (legacy v1), le contenu reste la seule
    identité disponible → anti-doublon. AVEC des uid distincts, deux mémos de même texte sont
    deux mémos — « J3 matin. » deux fois dans un voyage, c'est légitime. Confondre les deux a
    coûté 12 mémos sur 51, en silence."""
    c = client
    assert _import(c, {"memos": [
        {"content": "Texte répété"},                      # sans uid ─┐ un seul doit survivre
        {"content": "Texte répété"},                      # sans uid ─┘
        {"content": "Texte jumeau", "uid": "j1"},         # uid distincts ─┐ les deux survivent
        {"content": "Texte jumeau", "uid": "j2"},         #               ─┘
    ]}).status_code == 200

    assert len(_memos_matching("Texte répété")) == 1
    assert len(_memos_matching("Texte jumeau")) == 2


def test_content_dedup_also_guards_against_the_local_base(client):
    """L'anti-doublon legacy regarde aussi ce qui est DÉJÀ en base, pas seulement le lot."""
    c = client
    _memo(c, "Déjà présent")
    r = _import(c, {"memos": [{"content": "Déjà présent"}]})
    assert r.status_code == 200
    assert r.get_json()["skipped_memos"] >= 1
    assert len(_memos_matching("Déjà présent")) == 1


def test_reimport_of_an_export_adds_nothing(client):
    """Le garde-fou quotidien : ré-importer son propre export ne doit RIEN ajouter."""
    c = client
    pid = _project(c, "Voyage")
    _memo(c, "Un mémo", project_id=pid)
    _memo(c, "Un autre", project_id=pid)
    export = c.get("/api/export").get_json()

    avant = _snapshot(c)
    r = _import(c, export)
    assert r.status_code == 200, r.data
    bilan = r.get_json()
    assert bilan["imported_memos"] == 0, bilan
    assert bilan["skipped_memos"] == 2, bilan
    assert _snapshot(c) == avant


def test_resolution_overwrite_forces_and_restores(client):
    """`overwrite` = « écraser/restaurer » : il force la mise à jour MÊME si le fichier est
    plus ancien, et fait ressortir un mémo de la corbeille."""
    c = client
    mid = _memo(c, "Version locale")
    uid = _memo_uid(mid)
    assert c.delete("/api/memos/%d" % mid).status_code in (200, 204)
    assert (_row("memos", id=mid)["deleted_at"] or "") != ""

    assert _import(c, {"memos": [{"content": "Version du fichier", "uid": uid,
                                  "updated_at": "2000-01-01T00:00:00+00:00"}],
                       "resolutions": {uid: "overwrite"}}).status_code == 200

    apres = _row("memos", id=mid)
    assert apres["content"] == "Version du fichier"
    assert (apres["deleted_at"] or "") == "", "overwrite doit restaurer un mémo en corbeille"


def test_resolution_duplicate_creates_a_second_memo(client):
    """`duplicate` ne touche pas l'existant : il tombe vers l'INSERT avec un uid NEUF — et
    court-circuite l'anti-doublon par contenu, puisqu'on veut justement une copie."""
    c = client
    mid = _memo(c, "À dupliquer")
    uid = _memo_uid(mid)

    assert _import(c, {"memos": [{"content": "À dupliquer", "uid": uid}],
                       "resolutions": {uid: "duplicate"}}).status_code == 200

    copies = _memos_matching("À dupliquer")
    assert len(copies) == 2
    uids = {r["uid"] for r in copies}
    assert uid in uids and len(uids) == 2, "la copie doit porter un uid NEUF, pas celui d'origine"


def test_resolution_skip_is_not_what_its_name_says(client):
    """⚠ CARACTÉRISATION D'UN BUG CONNU — ce test fige le comportement ACTUEL, pas le bon.

    Seuls `overwrite` et `duplicate` sont interprétés ; tout le reste — y compris le mot
    `"skip"` — retombe sur le défaut, qui est **newer-wins**. Un fichier plus RÉCENT met donc
    à jour un mémo explicitement marqué `"skip"`.

    Et ce n'est pas qu'une question de nommage : l'écran « Importer ici » propose bien
    « Écraser / Dupliquer / **Ignorer** » conflit par conflit et envoie `"skip"` pour le
    dernier. Quelqu'un qui clique « Ignorer » attend « ne touche pas à mon mémo » et se le
    fait écraser quand même. Rien n'est perdu (les révisions gardent l'état d'avant), mais le
    résultat contredit un choix explicite de l'utilisateur.

    On fige le réel ici parce que c'est un lot de caractérisation. La correction a son lot :
    **[IMPORT-SKIP-FIX]** — ce test sera alors RETOURNÉ en rouge (assertion juste : `skip`
    laisse intact même si le fichier est plus récent) avant que `import_links` ne l'honore."""
    c = client
    mid = _memo(c, "Version locale")
    uid = _memo_uid(mid)

    # ① fichier PLUS ANCIEN → rien ne bouge (ce que « skip » laisse espérer)
    assert _import(c, {"memos": [{"content": "Vieille version", "uid": uid,
                                  "updated_at": "2000-01-01T00:00:00+00:00"}],
                       "resolutions": {uid: "skip"}}).status_code == 200
    assert _row("memos", id=mid)["content"] == "Version locale"

    # ② fichier PLUS RÉCENT → mis à jour MALGRÉ le « skip »
    assert _import(c, {"memos": [{"content": "Version du futur", "uid": uid,
                                  "updated_at": "2099-01-01T00:00:00+00:00"}],
                       "resolutions": {uid: "skip"}}).status_code == 200
    assert _row("memos", id=mid)["content"] == "Version du futur", (
        "comportement réel : « skip » n'est pas interprété, le défaut newer-wins s'applique"
    )


def test_absent_resolution_is_newer_wins(client):
    """Le défaut, sans aucune résolution : plus récent gagne, plus ancien est ignoré. C'est la
    non-destruction de l'invariant 2 — un vieux fichier ne rétrograde jamais la base."""
    c = client
    mid = _memo(c, "Version locale")
    uid = _memo_uid(mid)

    assert _import(c, {"memos": [{"content": "Trop vieux", "uid": uid,
                                  "updated_at": "2000-01-01T00:00:00+00:00"}]}).status_code == 200
    assert _row("memos", id=mid)["content"] == "Version locale"

    assert _import(c, {"memos": [{"content": "Plus récent", "uid": uid,
                                  "updated_at": "2099-01-01T00:00:00+00:00"}]}).status_code == 200
    assert _row("memos", id=mid)["content"] == "Plus récent"


# ══════════════ E. Import des LIENS — la fonctionnalité d'origine (v1) ══════════════

def _link(c, name, url_public="", **extra):
    body = {"name": name, "url_public": url_public}
    body.update(extra)
    r = c.post("/api/links", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def test_link_matched_by_uid_is_newer_wins(client):
    """Même doctrine que les mémos : l'uid porte l'identité, et seul un fichier plus récent
    met à jour. Un vieil export ne doit jamais rétrograder un lien retouché depuis."""
    c = client
    lid = _link(c, "Mon service", "https://exemple.test", descr="Description locale")
    uid = _row("links", id=lid)["uid"]

    assert _import(c, {"links": [{"name": "Renommé par un vieux fichier", "uid": uid,
                                  "url_public": "https://exemple.test",
                                  "updated_at": "2000-01-01T00:00:00+00:00"}]}).status_code == 200
    assert _row("links", id=lid)["name"] == "Mon service"

    r = _import(c, {"links": [{"name": "Renommé par un fichier récent", "uid": uid,
                               "url_public": "https://exemple.test",
                               "updated_at": "2099-01-01T00:00:00+00:00"}]})
    assert r.status_code == 200
    assert r.get_json()["updated"] == 1
    assert _row("links", id=lid)["name"] == "Renommé par un fichier récent"


def test_link_without_uid_enriches_empty_fields_only(client):
    """Invariant 2 dans sa forme la plus ancienne : sans uid, le lien est retrouvé par
    (nom, URLs) et l'import ne remplit que les trous — jamais par-dessus."""
    c = client
    lid = _link(c, "Service", "https://a.test", descr="Déjà décrit", memo="")

    assert _import(c, {"links": [{"name": "Service", "url_public": "https://a.test",
                                  "descr": "Autre description", "memo": "Mémo ajouté",
                                  "tags": "maison"}]}).status_code == 200

    apres = _row("links", id=lid)
    assert apres["descr"] == "Déjà décrit", "une description remplie ne doit pas être écrasée"
    assert apres["memo"] == "Mémo ajouté", "un champ vide, lui, s'enrichit"
    assert "maison" in (apres["tags"] or "")


def test_link_reimport_is_idempotent_and_nameless_ignored(client):
    """Ré-importer le même lien n'ajoute rien (dédup par nom+URLs), et une entrée sans nom
    est ignorée sans faire échouer le lot."""
    c = client
    _link(c, "Service", "https://a.test")

    r = _import(c, {"links": [{"name": "Service", "url_public": "https://a.test"},
                              {"name": "   ", "url_public": "https://b.test"},
                              {"name": "Nouveau", "url_public": "https://c.test"}]})
    assert r.status_code == 200, r.data
    bilan = r.get_json()
    assert bilan["imported"] == 1 and bilan["skipped"] == 1

    con = _db()
    try:
        noms = sorted(x["name"] for x in con.execute("SELECT name FROM links").fetchall())
    finally:
        con.close()
    assert noms == ["Nouveau", "Service"]


def test_import_accepts_a_projects_only_payload(client):
    """La porte d'entrée est VOLONTAIREMENT permissive : un fichier sans mémo ni lien passe et
    crée ses dossiers. `memos` absent devient `[]`, qui est une liste — la garde ne se ferme
    donc que sur un corps réellement malformé (test suivant). C'est cohérent avec l'invariant 1
    (accepter tous les formats depuis v1), mais ça surprend à la lecture du code."""
    r = client.post("/api/import", json={"projects": [{"name": "Dossier seul"}]})
    assert r.status_code == 200, r.data
    assert "Dossier seul" in _projects()


def test_import_rejects_a_malformed_payload(client):
    """En revanche un corps dont `links` ET `memos` ne sont pas des listes → 400 explicite,
    jamais un 500."""
    r = client.post("/api/import", json={"links": "pas une liste", "memos": "non plus"})
    assert r.status_code == 400, r.data
    assert "links" in r.get_json()["error"]
