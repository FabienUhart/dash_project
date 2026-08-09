"""[TESTS-PORT vague 4] Le HUB invité (`/share/hub/*`) — invariant 5.

Toujours de la surface PUBLIQUE : le hub vit sous `/share/hub/<hub_token>`, couvert par le
même bypass Authelia que `/share/*`, protégé par le seul jeton (+ code PIN). `hub_data` est
le plus gros bloc resté nu du dépôt.

**La garde reine** : un `hub_token` n'expose QUE les partages de SA personne — jamais ceux
d'un autre. Un hub n'est pas un passe-partout, c'est l'agrégat d'un e-mail.

Nature = **CARACTÉRISATION + mutation**, comme les vagues 1 à 3. Un rouge ici est un bug dans
une route de sécurité, jamais une assertion à réaligner.

Zéro réseau : `hub_fx` (taux de change) et `hub_send_link` (e-mail) sont **hors de ce lot**.

Modèle, pour qui relira : un hub existe **par e-mail** (`guest_hubs`), créé automatiquement
au `register` d'un partage (`_ensure_hub`, idempotent). Deux jetons cohabitent donc, et il ne
faut pas les confondre : le `hub_token` (l'URL de l'agrégat) et le `guest_token` (l'accès à
UN partage). Le premier ne prouve rien à lui seul — il est dans l'URL.
"""
import sqlite3

import pytest

pytestmark = pytest.mark.invariant


H = lambda gt: {"X-Guest-Token": gt}

# `_hub_by_token` refuse tout jeton de moins de 16 caractères AVANT même de requêter la base :
# deux chemins distincts, donc deux jetons de test.
COURT = "trop-court"
LONG_INCONNU = "jeton-hub-inconnu-mais-assez-long-pour-passer-la-garde"


# ─────────────────────────────────────────────────────────────── montage ────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _project(c, name):
    r = c.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _memo(c, pid, content):
    r = c.post("/api/memos", json={"content": content, "project_id": pid})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _share(c, pid, role="viewer"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token,
               json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _hub(email):
    """(hub_token, pin) du hub de cet e-mail — le `register` l'a créé au passage."""
    con = _db()
    try:
        row = con.execute("SELECT hub_token, pin FROM guest_hubs WHERE email = ?",
                          (email.lower(),)).fetchone()
        return (row["hub_token"], row["pin"]) if row else (None, None)
    finally:
        con.close()


def _guest_row(email, share_id):
    con = _db()
    try:
        return con.execute("SELECT * FROM share_guests WHERE lower(email) = ? AND share_id = ?",
                           (email.lower(), share_id)).fetchone()
    finally:
        con.close()


def _statuses(email):
    con = _db()
    try:
        return sorted(r["status"] for r in con.execute(
            "SELECT status FROM share_guests WHERE lower(email) = ?", (email.lower(),)).fetchall())
    finally:
        con.close()


def _set_status_in_db(guest_id, status):
    """`pending` n'est plus posable par aucune route ([GUEST-AUTO-APPROVE] : le register
    approuve directement). On l'écrit donc en base pour éprouver la cascade d'approbation,
    qui existe précisément pour ces états-là."""
    con = _db()
    try:
        con.execute("UPDATE share_guests SET status = ? WHERE id = ?", (status, guest_id))
        con.commit()
    finally:
        con.close()


def _labels(body):
    return sorted(x["label"] for x in body["roots"])


def _folder_labels(body_or_folders):
    src = body_or_folders["folders"] if isinstance(body_or_folders, dict) else body_or_folders
    return sorted(x["label"] for x in src)


def _prove(c, hub_token, pin):
    """Bon PIN → le test_client détient le cookie de session, et peut lire /data ensuite."""
    r = c.post("/share/hub/%s/approve" % hub_token, json={"pin": pin})
    assert r.status_code == 200, r.data
    return r


def _session_token(hub_token):
    con = _db()
    try:
        row = con.execute("SELECT session_token FROM guest_hubs WHERE hub_token = ?",
                          (hub_token,)).fetchone()
        return row["session_token"] if row else None
    finally:
        con.close()


@pytest.fixture
def hubs(client):
    """Deux personnes, deux dossiers, deux liens distincts — le décor minimal pour que
    l'isolation ait quelque chose à isoler.

        FA (partagé à alice)   ← memo « Secret d'Alice »
        FB (partagé à bob)     ← memo « Secret de Bob »
    """
    c = client
    fa = _project(c, "Dossier Alice")
    fb = _project(c, "Dossier Bob")
    ma = _memo(c, fa, "Secret d'Alice")
    mb = _memo(c, fb, "Secret de Bob")

    sha = _share(c, fa, role="viewer")
    shb = _share(c, fb, role="editor")
    gta = _register(c, sha["token"], sha["pin"], "alice@ex.com", "Alice")
    gtb = _register(c, shb["token"], shb["pin"], "bob@ex.com", "Bob")

    hta, pina = _hub("alice@ex.com")
    htb, pinb = _hub("bob@ex.com")
    assert hta and htb and hta != htb

    return {
        "c": c, "fa": fa, "fb": fb, "ma": ma, "mb": mb,
        "sha": sha, "shb": shb, "gta": gta, "gtb": gtb,
        "hta": hta, "pina": pina, "htb": htb, "pinb": pinb,
    }


# ══════════════════════════ A. hub_page ══════════════════════════

def test_hub_page_unknown_token_404(hubs):
    assert hubs["c"].get("/share/hub/%s" % LONG_INCONNU).status_code == 404


def test_hub_page_short_token_404(hubs):
    """Un jeton trop court est refusé AVANT la base : pas de requête, pas de fuite de timing."""
    assert hubs["c"].get("/share/hub/%s" % COURT).status_code == 404


def test_hub_page_valid_token_200(hubs):
    """Le shell HTML se sert sans preuve — mais il ne contient AUCUNE donnée : la liste des
    dossiers ne vient qu'après le code (c'est tout le point d'un shell statique)."""
    r = hubs["c"].get("/share/hub/%s" % hubs["hta"])
    assert r.status_code == 200
    corps = r.data.decode("utf-8", "replace")
    assert "Dossier Alice" not in corps
    assert "Secret d'Alice" not in corps
    assert hubs["gta"] not in corps


def test_hub_is_created_per_email_and_is_stable(hubs):
    """Un hub par e-mail, créé au `register` et JAMAIS régénéré : s'inscrire à un second
    partage ne doit pas changer le lien que la personne a déjà reçu."""
    c = hubs["c"]
    fc = _project(c, "Troisieme dossier")
    sh = _share(c, fc)
    _register(c, sh["token"], sh["pin"], "alice@ex.com", "Alice")

    encore, pin_encore = _hub("alice@ex.com")
    assert encore == hubs["hta"] and pin_encore == hubs["pina"]

    con = _db()
    try:
        n = con.execute("SELECT COUNT(*) AS n FROM guest_hubs WHERE email = ?",
                        ("alice@ex.com",)).fetchone()["n"]
    finally:
        con.close()
    assert n == 1


# ═════════════ B. hub_data — preuve, puis ISOLATION PAR PERSONNE ═════════════

def test_hub_data_unknown_token_404(hubs):
    assert hubs["c"].get("/share/hub/%s/data" % LONG_INCONNU).status_code == 404


def test_hub_data_without_proof_403(hubs):
    """Le `hub_token` est dans l'URL : à lui seul il ne prouve rien. Sans cookie ni jeton
    d'invité, la lecture est refusée — c'est l'écran « code »."""
    r = hubs["c"].get("/share/hub/%s/data" % hubs["hta"])
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "code requis"


def test_hub_data_with_cookie_lists_own_folders(hubs):
    c = hubs["c"]
    _prove(c, hubs["hta"], hubs["pina"])

    r = c.get("/share/hub/%s/data" % hubs["hta"])
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["kind"] == "hub"
    assert "Dossier Alice" in _labels(body)
    assert "Dossier Alice" in _folder_labels(body)
    assert "Dossier Bob" not in _labels(body)


def test_hub_always_carries_the_personal_space(hubs):
    """[GUEST-HOME] Un invité approuvé a TOUJOURS un dossier de plus que ceux qu'on lui a
    partagés : son espace personnel « 🏠 », provisionné à l'approbation puis (paresseusement)
    à chaque chargement du hub. C'est voulu — on le fige ici pour que la prochaine lecture ne
    prenne pas ce second dossier pour une fuite."""
    c = hubs["c"]
    _prove(c, hubs["hta"], hubs["pina"])
    body = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()

    maison = [x for x in body["folders"] if x["emoji"] == "🏠"]
    assert len(maison) == 1, _folder_labels(body)
    assert maison[0]["label"] == "Alice"
    assert _folder_labels(body) == ["Alice", "Dossier Alice"]

    con = _db()
    try:
        row = con.execute("SELECT created_by FROM projects WHERE name = ? AND emoji = '🏠'",
                          ("Alice",)).fetchone()
    finally:
        con.close()
    assert "alice@ex.com" in (row["created_by"] or ""), \
        "l'espace perso appartient à l'invité (c'est ce qui fonde la dédup par e-mail)"


def test_hub_data_accepts_an_approved_guest_token_as_proof(hubs):
    """Repli documenté : le `guest_token` d'un accès APPROUVÉ dont l'e-mail est celui du hub."""
    r = hubs["c"].get("/share/hub/%s/data" % hubs["hta"], headers=H(hubs["gta"]))
    assert r.status_code == 200, r.data
    assert "Dossier Alice" in _labels(r.get_json())


def test_hub_data_refuses_a_guest_token_of_someone_else(hubs):
    """Le jeton d'invité de Bob ne prouve rien sur le hub d'Alice : la preuve est liée à
    l'E-MAIL du hub, pas au simple fait de détenir un jeton valide quelque part."""
    r = hubs["c"].get("/share/hub/%s/data" % hubs["hta"], headers=H(hubs["gtb"]))
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "code requis"


def test_hub_data_isolates_people(hubs):
    """LA garde du lot. Le hub d'Alice ne montre que ce qui est partagé à Alice — ni le
    dossier de Bob, ni ses mémos, ni son jeton de partage. Et réciproquement."""
    c = hubs["c"]
    _prove(c, hubs["hta"], hubs["pina"])
    a = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()

    assert "Dossier Alice" in _labels(a)
    assert "Dossier Bob" not in _labels(a)
    assert hubs["fb"] not in [x.get("root_id") for x in a["roots"]]
    assert hubs["mb"] not in [m["id"] for m in a["memos"]]
    assert hubs["fb"] not in [p["id"] for p in a["projects"]]
    brut = str(a)
    assert "Secret de Bob" not in brut
    assert hubs["shb"]["token"] not in brut, "le jeton du partage de Bob n'a rien à faire ici"
    assert hubs["gtb"] not in brut

    _prove(c, hubs["htb"], hubs["pinb"])
    b = c.get("/share/hub/%s/data" % hubs["htb"]).get_json()
    assert "Dossier Bob" in _labels(b)
    assert "Dossier Alice" not in _labels(b)
    assert "Secret d'Alice" not in str(b)
    assert hubs["sha"]["token"] not in str(b)


def test_a_hub_cookie_does_not_open_another_hub(hubs):
    """Le cookie est comparé au `session_token` de CE hub : présenté sur un autre (ce que le
    scope de chemin empêche déjà côté navigateur, mais qu'un attaquant ferait à la main), il
    ne vaut rien. La garde est côté serveur, pas seulement dans l'attribut `Path`."""
    import app
    c = hubs["c"]
    _prove(c, hubs["hta"], hubs["pina"])
    jeton_a = _session_token(hubs["hta"])
    assert jeton_a
    _prove(c, hubs["htb"], hubs["pinb"])   # B a aussi une session : les deux existent

    # Client NEUF, sans bocal à cookies : sinon celui que le client détient légitimement pour
    # le hub visé partirait avec la requête et le test passerait sans rien éprouver.
    chemin_b = "/share/hub/%s" % hubs["htb"]
    pirate = app.app.test_client()
    pirate.set_cookie("dashhubsession", jeton_a, path=chemin_b)   # jeton d'A, posé chez B

    r = pirate.get("%s/data" % chemin_b)
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "code requis"

    # …et le même client, muni du bon jeton, passe : c'est bien le RAPPROCHEMENT cookie ↔ hub
    # qui tranche, pas une incapacité du client de test à porter un cookie.
    temoin = app.app.test_client()
    temoin.set_cookie("dashhubsession", _session_token(hubs["htb"]), path=chemin_b)
    ok = temoin.get("%s/data" % chemin_b)
    assert ok.status_code == 200, ok.data


def test_hub_data_drops_a_revoked_access(hubs):
    """[E9] La révocation retire la LECTURE, pas seulement l'écriture : un accès `rejected`
    disparaît du hub — et son `guest_token` cesse d'être servi, alors qu'il l'était encore
    avant le correctif."""
    c = hubs["c"]
    _prove(c, hubs["hta"], hubs["pina"])
    assert c.get("/share/hub/%s/data" % hubs["hta"]).get_json()["roots"]

    gid = _guest_row("alice@ex.com", hubs["sha"]["id"])["id"]
    assert c.put("/api/guests/%d" % gid, json={"status": "rejected"}).status_code == 200

    body = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()
    assert "Dossier Alice" not in _labels(body)
    assert "Dossier Alice" not in _folder_labels(body)
    assert hubs["gta"] not in str(body), "un révoqué ne doit plus recevoir le jeton du partage"
    # …et son espace perso, lui, ne lui est pas retiré : révoquer un partage n'est pas
    # confisquer ce qui appartient à la personne.
    assert _folder_labels(body) == ["Alice"]


def test_hub_aggregates_a_memo_share_and_drops_it_once_trashed(hubs):
    """Le hub agrège aussi les partages de MÉMO — et une cible partie à la corbeille en
    disparaît (invariant 7 : le mémo quitte les vues sans être supprimé). Sans ce filtre, le
    hub afficherait une entrée qui n'ouvre plus rien."""
    c = hubs["c"]
    mid = _memo(c, hubs["fa"], "Réservation Hôtel Sakura")
    sh = c.post("/api/shares", json={"kind": "memo", "target_id": mid, "role": "commenter"})
    assert sh.status_code in (200, 201), sh.data
    sh = sh.get_json()
    _register(c, sh["token"], sh["pin"], "alice@ex.com", "Alice")
    _prove(c, hubs["hta"], hubs["pina"])

    body = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()
    memo_roots = [x for x in body["roots"] if x["kind"] == "memo"]
    assert len(memo_roots) == 1
    assert memo_roots[0]["memo_id"] == mid
    assert "Sakura" in memo_roots[0]["label"]

    assert c.delete("/api/memos/%d" % mid).status_code in (200, 204)
    apres = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()
    assert [x for x in apres["roots"] if x["kind"] == "memo"] == []
    assert "Sakura" not in str(apres["folders"])


def test_two_shares_on_the_same_folder_keep_the_highest_role(hubs):
    """Deux liens sur le même dossier : c'est le rôle le PLUS HAUT qui gagne. Sinon l'ordre
    des partages déciderait des droits — et un lien lecture posé après coup rétrograderait
    quelqu'un sans que personne l'ait voulu."""
    c = hubs["c"]
    second = _share(c, hubs["fa"], role="editor")     # le premier lien d'Alice est « viewer »
    _register(c, second["token"], second["pin"], "alice@ex.com", "Alice")
    _prove(c, hubs["hta"], hubs["pina"])

    body = c.get("/share/hub/%s/data" % hubs["hta"]).get_json()
    sur_fa = [x for x in body["roots"] if x.get("root_id") == hubs["fa"]]
    assert len(sur_fa) == 2, "les deux liens restent listés (deux portes vers le même dossier)"
    assert any(x["role"] == "editor" and x["can_edit"] for x in sur_fa)

    projet = [p for p in body["projects"] if p["id"] == hubs["fa"]]
    assert projet and projet[0].get("can_edit") is True, \
        "le dossier lui-même doit hériter du rôle le plus haut, pas du premier venu"


def test_hub_name_follows_the_latest_registration(hubs):
    """Le nom du hub est cosmétique et suit la dernière inscription ; le jeton et le code, eux,
    ne bougent jamais — c'est ce que la personne a reçu."""
    c = hubs["c"]
    fc = _project(c, "Encore un dossier")
    sh = _share(c, fc)
    _register(c, sh["token"], sh["pin"], "alice@ex.com", "Alice Martin")

    jeton, pin = _hub("alice@ex.com")
    assert (jeton, pin) == (hubs["hta"], hubs["pina"])
    r = _prove(c, hubs["hta"], hubs["pina"])
    assert r.get_json()["name"] == "Alice Martin"


# ═════════════ C. hub_approve — PIN, cascade et révocation ═════════════

def test_hub_approve_unknown_hub_403(hubs):
    """Hub inconnu et PIN faux répondent EXACTEMENT pareil : sans quoi le 404 dirait
    « ce hub existe », et le lien deviendrait énumérable."""
    r = hubs["c"].post("/share/hub/%s/approve" % LONG_INCONNU, json={"pin": "0000"})
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "code invalide"

    faux = hubs["c"].post("/share/hub/%s/approve" % hubs["hta"],
                          json={"pin": "9" if hubs["pina"] != "9" else "8"})
    assert faux.status_code == 403
    assert faux.get_json() == r.get_json(), "les deux refus doivent être indiscernables"


def test_hub_approve_wrong_pin_403(hubs):
    mauvais = "0000" if hubs["pina"] != "0000" else "1111"
    r = hubs["c"].post("/share/hub/%s/approve" % hubs["hta"], json={"pin": mauvais})
    assert r.status_code == 403, r.data
    assert _session_token(hubs["hta"]) in (None, "")


def test_hub_approve_empty_pin_403(hubs):
    for vide in ({}, {"pin": ""}, {"pin": "   "}):
        r = hubs["c"].post("/share/hub/%s/approve" % hubs["hta"], json=vide)
        assert r.status_code == 403, (vide, r.data)


def test_hub_approve_correct_pin_returns_folders_and_sets_cookie(hubs):
    r = hubs["c"].post("/share/hub/%s/approve" % hubs["hta"], json={"pin": hubs["pina"]})
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["name"] == "Alice"
    assert "Dossier Alice" in _folder_labels(body)

    cookies = r.headers.getlist("Set-Cookie")
    assert any("dashhubsession=" in ck for ck in cookies), cookies
    pose = [ck for ck in cookies if "dashhubsession=" in ck][0]
    assert "HttpOnly" in pose, "le cookie de session ne doit pas être lisible en JS"
    assert "Path=/share/hub/%s" % hubs["hta"] in pose, \
        "le cookie est scopé à CE hub — deux invités coexistent sur le même navigateur"


def test_hub_approve_cascade_approves_only_pending_of_this_email(hubs):
    """La cascade fait entrer les accès en attente de CETTE personne — et d'elle seule."""
    c = hubs["c"]
    fc = _project(c, "Dossier commun")
    sh = _share(c, fc)
    _register(c, sh["token"], sh["pin"], "alice@ex.com", "Alice")
    _register(c, sh["token"], sh["pin"], "bob@ex.com", "Bob")
    ga = _guest_row("alice@ex.com", sh["id"])["id"]
    gb = _guest_row("bob@ex.com", sh["id"])["id"]
    _set_status_in_db(ga, "pending")
    _set_status_in_db(gb, "pending")

    _prove(c, hubs["hta"], hubs["pina"])

    con = _db()
    try:
        assert con.execute("SELECT status FROM share_guests WHERE id = ?",
                           (ga,)).fetchone()["status"] == "approved"
        assert con.execute("SELECT status FROM share_guests WHERE id = ?",
                           (gb,)).fetchone()["status"] == "pending", \
            "le code d'Alice ne fait entrer personne d'autre"
    finally:
        con.close()


def test_hub_approve_does_not_revive_a_revoked_access(hubs):
    """[GUEST-ROLES V2 · T1 — E10] Le test qui compte : la cascade ramassait autrefois tout ce
    qui n'était pas `approved`, donc AUSSI les `rejected` — le code du hub annulait alors
    silencieusement une révocation owner. Seul l'owner réactive."""
    c = hubs["c"]
    gid = _guest_row("alice@ex.com", hubs["sha"]["id"])["id"]
    assert c.put("/api/guests/%d" % gid, json={"status": "rejected"}).status_code == 200

    r = c.post("/share/hub/%s/approve" % hubs["hta"], json={"pin": hubs["pina"]})
    assert r.status_code == 200, r.data     # le PIN est bon : on ne ment pas sur le code

    con = _db()
    try:
        etat = con.execute("SELECT status FROM share_guests WHERE id = ?",
                           (gid,)).fetchone()["status"]
    finally:
        con.close()
    assert etat == "rejected", "le PIN du hub ne doit jamais annuler une révocation"
    assert "Dossier Alice" not in _folder_labels(r.get_json())


def test_hub_approve_touches_only_this_email(hubs):
    """Rien de ce qui appartient à Bob ne bouge quand Alice saisit son code."""
    avant = _statuses("bob@ex.com")
    _prove(hubs["c"], hubs["hta"], hubs["pina"])
    assert _statuses("bob@ex.com") == avant


def test_hub_approve_is_throttled_after_repeated_failures(hubs):
    """Un PIN à 4 chiffres se force en 10 000 essais : la fenêtre glissante est ce qui rend
    l'énumération impraticable. Le throttle prend le pas même sur un code VALIDE — c'est
    voulu, sinon il suffirait d'intercaler le bon coup."""
    c = hubs["c"]
    mauvais = "0000" if hubs["pina"] != "0000" else "1111"
    vus = set()
    for _ in range(12):
        r = c.post("/share/hub/%s/approve" % hubs["hta"], json={"pin": mauvais})
        vus.add(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in vus, "aucun plafond n'a été atteint en 12 essais"

    bloque = c.post("/share/hub/%s/approve" % hubs["hta"], json={"pin": hubs["pina"]})
    assert bloque.status_code == 429, bloque.data
    assert _session_token(hubs["hta"]) in (None, "")
