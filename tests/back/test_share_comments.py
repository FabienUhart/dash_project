"""[TESTS-PORT vague 2] Surface d'EXPRESSION invitée sous /share/* — invariants 5 et 6.

Écrire un message, y répondre, le retirer, réagir : le cœur de ce qu'un invité peut dire.
Plus le validateur d'emoji (`_clean_reaction_emoji`), qui est la porte anti-injection de la
palette de réactions (invariant 6 : Python pur, aucune lib, aucun CDN).

Même nature qu'en vague 1 : tests de **CARACTÉRISATION** du comportement correct actuel.
**Un rouge ici est un bug dans une route de sécurité**, pas une assertion à réaligner.

Deux doctrines du projet sont figées ici parce qu'elles se contredisent en apparence :
  · **la tombale** (invariant 7 addendum) — supprimer un commentaire ne fait pas de `DELETE` :
    la LIGNE survit pour que les réponses gardent leur contexte, mais le CORPS est vidé et
    toutes ses actions meurent (réactions purgées, plus de `can_delete`, plus de réaction
    possible). Un test qui exigerait la disparition de la ligne serait donc *faux* ;
  · **modérer ≠ posséder** — un Modérateur retire le message d'un invité, jamais celui du
    propriétaire.
"""
import sqlite3

import pytest

pytestmark = pytest.mark.invariant


H = lambda gt: {"X-Guest-Token": gt}


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


def _share(c, pid, role="commenter"):
    r = c.post("/api/shares", json={"kind": "project", "target_id": pid, "role": role})
    assert r.status_code in (200, 201), r.data
    return r.get_json()


def _register(c, token, pin, email, name="Inv"):
    r = c.post("/share/%s/register" % token,
               json={"name": name, "email": email, "pin": pin})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["guest_token"]


def _guest_id(email, share_id):
    con = _db()
    try:
        row = con.execute("SELECT id FROM share_guests WHERE email = ? AND share_id = ?",
                          (email.lower(), share_id)).fetchone()
        return row["id"] if row else None
    finally:
        con.close()


def _post(c, token, memo_id, gt, **payload):
    return c.post("/share/%s/memo/%d/comments" % (token, memo_id),
                  headers=(H(gt) if gt else {}), json=payload)


def _thread(c, token, gt, memo_id):
    """Le fil tel que l'invité le LIT (c'est `/share/<token>/data` qui le porte)."""
    r = c.get("/share/%s/data" % token, headers=(H(gt) if gt else {}))
    assert r.status_code == 200, r.data
    for m in r.get_json()["memos"]:
        if m["id"] == memo_id:
            return m.get("comments", [])
    raise AssertionError("mémo %d absent du payload invité" % memo_id)


@pytest.fixture
def room(client):
    """Un dossier partagé « commentateur », un mémo dedans, deux invités — plus un dossier
    HORS partage avec son mémo, pour éprouver le périmètre."""
    c = client
    pid = _project(c, "Dossier partage")
    mid = _memo(c, pid, "Le mémo qui porte le fil")
    out_pid = _project(c, "Dossier prive")
    out_mid = _memo(c, out_pid, "Hors perimetre")

    sh = _share(c, pid, role="commenter")
    gtA = _register(c, sh["token"], sh["pin"], "a@ex.com", "Alice")
    gtB = _register(c, sh["token"], sh["pin"], "b@ex.com", "Bob")
    return {
        "c": c, "pid": pid, "mid": mid, "out_mid": out_mid,
        "share_id": sh["id"], "token": sh["token"], "pin": sh["pin"],
        "gtA": gtA, "gtB": gtB,
        "idA": _guest_id("a@ex.com", sh["id"]), "idB": _guest_id("b@ex.com", sh["id"]),
    }


# ═══════════ A. _clean_reaction_emoji — pur, sans montage (invariant 6) ═══════════
# Python pur : plages Unicode + accessoires + garde de longueur. C'est la seule barrière
# entre un champ libre et la palette — d'où le soin mis aux REFUS.

def _clean(raw):
    import app
    return app._clean_reaction_emoji(raw)


def test_emoji_accepts_simple():
    assert _clean("👍") == "👍"
    assert _clean("🎉") == "🎉"


def test_emoji_accepts_zwj_sequence():
    """Une famille est UNE base logique, même si elle compte plusieurs pictogrammes reliés
    par des ZWJ — le compteur de bases ne doit pas la prendre pour trois emojis."""
    assert _clean("👨‍👩‍👧") == "👨‍👩‍👧"


def test_emoji_accepts_flag():
    """Un drapeau = exactement DEUX indicateurs régionaux, et rien d'autre."""
    assert _clean("🇫🇷") == "🇫🇷"
    assert _clean("🇯🇵") == "🇯🇵"


def test_emoji_accepts_skin_tone():
    assert _clean("👍🏽") == "👍🏽"


def test_emoji_accepts_variation_selector():
    """❤️ = cœur + sélecteur de variante : l'accessoire ne compte pas comme une base."""
    assert _clean("❤️") == "❤️"


def test_emoji_rejects_text():
    for bad in ("hello", "a", "0", "ok 👍"):
        assert _clean(bad) == "", bad


def test_emoji_rejects_html():
    """La raison d'être du validateur : rien de ce qui pourrait être rendu comme du balisage."""
    for bad in ("<b>", "<script>alert(1)</script>", "&", "&amp;", "<img src=x onerror=1>",
                "👍<b>", "\"👍\""):
        assert _clean(bad) == "", bad


def test_emoji_rejects_two_emojis():
    """Deux bases collées → refus : une réaction est UN grapheme, sinon la palette dérive."""
    assert _clean("👍👎") == ""
    assert _clean("🇫🇷🇯🇵") == ""      # quatre indicateurs régionaux = deux drapeaux


def test_emoji_rejects_empty_and_space():
    for bad in ("", "   ", "\t", "\n"):
        assert _clean(bad) == "", repr(bad)


def test_emoji_rejects_non_str():
    for bad in (None, 123, 1.5, [], {}, True):
        assert _clean(bad) == "", repr(bad)


def test_emoji_rejects_accessories_only():
    """Que des accessoires (ZWJ, sélecteur de variante) sans aucune base → refus."""
    assert _clean("‍") == ""
    assert _clean("️") == ""


def test_emoji_rejects_overlong():
    """Garde de longueur : une séquence ZWJ plausible plafonne vers 7-8 code points."""
    assert _clean("👍" * 11) == ""
    assert _clean("a" * 50) == ""


def test_default_palette_is_entirely_valid():
    """La palette de base doit passer son propre validateur — sinon un emoji livré serait
    proposé par l'UI et refusé par le serveur."""
    import app
    assert app.REACTION_EMOJIS
    for e in app.REACTION_EMOJIS:
        assert _clean(e) == e, e


# ══════════════════════ B. share_add_comment — prendre la parole ══════════════════════

def test_comment_unknown_token_404(room):
    r = _post(room["c"], "jeton-invente", room["mid"], room["gtA"], body="Coucou")
    assert r.status_code == 404, r.data


def test_comment_anonymous_403(room):
    """Le lien seul ne fait pas parler : il faut être approuvé (invariant 5)."""
    r = _post(room["c"], room["token"], room["mid"], None, body="Coucou")
    assert r.status_code == 403, r.data
    assert r.get_json()["status"] == "anonymous"


def test_comment_memo_out_of_scope_404(room):
    """Un mémo hors du partage n'existe pas pour ce jeton — 404, jamais 403 : on ne confirme
    pas l'existence d'un mémo qu'on ne partage pas."""
    r = _post(room["c"], room["token"], room["out_mid"], room["gtA"], body="Coucou")
    assert r.status_code == 404, r.data


def test_viewer_cannot_comment_403(room):
    """Approuvé sur un lien LECTURE : entrer ne donne pas la parole."""
    c = room["c"]
    sh = _share(c, room["pid"], role="viewer")
    gt = _register(c, sh["token"], sh["pin"], "v@ex.com", "Vera")
    r = _post(c, sh["token"], room["mid"], gt, body="Je peux ?")
    assert r.status_code == 403, r.data
    assert r.get_json()["error"] == "non autorisé"


def test_comment_empty_body_400(room):
    for bad in ("", "   ", None):
        r = _post(room["c"], room["token"], room["mid"], room["gtA"], body=bad)
        assert r.status_code == 400, (bad, r.data)
        assert r.get_json()["error"] == "body required"


def test_commenter_can_comment_201(room):
    """Le cas nominal, vérifié jusqu'au fil relu par l'invité."""
    r = _post(room["c"], room["token"], room["mid"], room["gtA"], body="Bonjour à tous")
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["body"] == "Bonjour à tous"
    assert body["guest"] is True
    assert "a@ex.com" in body["author"]
    assert body["can_delete"] is True         # son propre message

    fil = _thread(room["c"], room["token"], room["gtA"], room["mid"])
    assert [c["id"] for c in fil] == [body["id"]]


def test_comment_body_is_stripped_of_angle_brackets(room):
    """`_clean_comment_body` retire `<` et `>` : le message reste du texte, jamais du balisage."""
    r = _post(room["c"], room["token"], room["mid"], room["gtA"],
              body="<script>alert(1)</script>")
    assert r.status_code == 201, r.data
    got = r.get_json()["body"]
    assert "<" not in got and ">" not in got
    assert got == "scriptalert(1)/script"


def test_comment_reply_sets_parent(room):
    """Répondre rattache — c'est ce rattachement que la tombale protégera plus bas."""
    first = _post(room["c"], room["token"], room["mid"], room["gtA"], body="Question ?")
    assert first.status_code == 201, first.data
    pid = first.get_json()["id"]

    rep = _post(room["c"], room["token"], room["mid"], room["gtB"],
                body="Réponse", parent_id=pid)
    assert rep.status_code == 201, rep.data
    assert rep.get_json()["parent_id"] == pid


def test_reply_to_foreign_comment_is_not_attached(room):
    """Un `parent_id` qui n'appartient pas à CE mémo est NEUTRALISÉ, jamais accepté tel quel :
    sinon un invité rattacherait sa réponse à un fil qu'il ne voit pas. Le message retombe au
    premier niveau — même valeur de `parent_id` qu'un message racine (pas `None` : la couche de
    rendu émet `''` pour un parent absent, on fige la valeur réellement servie)."""
    c = room["c"]
    other = c.post("/api/memos/%d/comments" % room["out_mid"], json={"body": "Ailleurs"})
    assert other.status_code in (200, 201), other.data
    racine = _post(c, room["token"], room["mid"], room["gtA"], body="Message racine")
    neutre = racine.get_json()["parent_id"]          # ce que vaut « pas de parent »

    rep = _post(c, room["token"], room["mid"], room["gtA"],
                body="Réponse égarée", parent_id=other.get_json()["id"])
    assert rep.status_code == 201, rep.data
    assert rep.get_json()["parent_id"] == neutre
    assert not rep.get_json()["parent_id"]


def test_reply_to_a_reply_attaches_to_the_root(room):
    """Un seul niveau de profondeur : répondre à une réponse rattache au message RACINE,
    sinon le fil s'enfoncerait sans fin."""
    c = room["c"]
    root = _post(c, room["token"], room["mid"], room["gtA"], body="Racine").get_json()["id"]
    rep1 = _post(c, room["token"], room["mid"], room["gtB"],
                 body="Niveau 1", parent_id=root).get_json()
    assert rep1["parent_id"] == root

    rep2 = _post(c, room["token"], room["mid"], room["gtA"],
                 body="Niveau 2", parent_id=rep1["id"])
    assert rep2.status_code == 201, rep2.data
    assert rep2.get_json()["parent_id"] == root


def test_poll_command_works_by_default(room):
    """Les interrupteurs sont ON par défaut (absent/NULL = ON) : `/vote_choix` crée un scrutin,
    et créer un scrutin coûte `commenter` — aucune route nouvelle, donc aucun périmètre neuf."""
    r = _post(room["c"], room["token"], room["mid"], room["gtA"],
              body="/vote_choix Ramen ; Sushi")
    assert r.status_code == 201, r.data
    assert r.get_json()["poll"] is not None


def test_poll_command_blocked_when_votes_off(room):
    """Interrupteur « Votes » coupé → refus EXPLICITE : un refus muet ferait croire à une
    commande cassée alors que c'est un réglage du partage."""
    c = room["c"]
    up = c.put("/api/shares/%d" % room["share_id"], json={"sw_votes": False})
    assert up.status_code == 200, up.data
    assert up.get_json()["sw_votes"] is False

    r = _post(c, room["token"], room["mid"], room["gtA"], body="/vote_choix Ramen ; Sushi")
    assert r.status_code == 403, r.data
    assert "désactivés" in r.get_json()["error"]

    # …et le message ordinaire, lui, passe toujours : l'interrupteur coupe les votes, pas la parole.
    assert _post(c, room["token"], room["mid"], room["gtA"], body="Un mot").status_code == 201


def test_poll_command_needs_two_options(room):
    r = _post(room["c"], room["token"], room["mid"], room["gtA"], body="/vote_choix Ramen")
    assert r.status_code == 400, r.data
    assert "deux options" in r.get_json()["error"]


# ══════════════════ C. share_delete_comment — retirer ses propres mots ══════════════════

def test_delete_own_comment_leaves_a_tombstone(room):
    """Invariant 7 addendum : la LIGNE survit (les réponses gardent leur contexte) mais le
    CORPS est vidé et toutes les actions meurent. Exiger sa disparition serait un faux test."""
    c = room["c"]
    first = _post(c, room["token"], room["mid"], room["gtA"], body="Message à retirer")
    cid = first.get_json()["id"]
    rep = _post(c, room["token"], room["mid"], room["gtB"], body="Ma réponse", parent_id=cid)
    rid = rep.get_json()["id"]

    r = c.delete("/share/%s/comment/%d" % (room["token"], cid), headers=H(room["gtA"]))
    assert r.status_code in (200, 204), r.data

    fil = {x["id"]: x for x in _thread(c, room["token"], room["gtA"], room["mid"])}
    assert cid in fil, "la tombale doit RESTER, sinon la réponse perd son contexte"
    tomb = fil[cid]
    assert tomb["deleted"] is True
    assert tomb["body"] == ""
    assert tomb["can_delete"] is False
    assert tomb["reactions"] == []
    assert fil[rid]["parent_id"] == cid       # la réponse tient toujours au bon fil

    con = _db()
    try:
        row = con.execute("SELECT body, deleted_at FROM memo_comments WHERE id = ?",
                          (cid,)).fetchone()
    finally:
        con.close()
    assert row["body"] == "", "le corps doit être vidé EN BASE, pas seulement masqué au rendu"
    assert row["deleted_at"]


def test_tombstone_body_is_masked_even_if_it_survived_in_base(room):
    """Défense en PROFONDEUR, et il a fallu une mutation pour s'en rendre compte : vider le
    corps en base (`_soft_delete_comment`) et le masquer au rendu (`_comment_dict`) sont DEUX
    gardes, mais la première rend la seconde invisible aux tests — tant que le corps est déjà
    vide, casser le masquage ne fait rien tomber. On force donc le cas que la seconde garde
    existe pour couvrir : une ligne marquée supprimée dont le corps aurait survécu."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Mots à taire").get_json()["id"]
    con = _db()
    try:
        con.execute("UPDATE memo_comments SET deleted_at = ?, body = ? WHERE id = ?",
                    ("2026-01-01T00:00:00+00:00", "Mots à taire", cid))
        con.commit()
    finally:
        con.close()

    fil = {x["id"]: x for x in _thread(c, room["token"], room["gtA"], room["mid"])}
    assert fil[cid]["deleted"] is True
    assert fil[cid]["body"] == "", "un message marqué supprimé ne doit JAMAIS ressortir en clair"
    assert fil[cid]["reactions"] == [] and fil[cid]["can_delete"] is False


def test_cannot_delete_others_comment_403(room):
    """Un invité ordinaire ne retire que ses propres mots — le message d'un autre est à lui."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="À moi").get_json()["id"]

    r = c.delete("/share/%s/comment/%d" % (room["token"], cid), headers=H(room["gtB"]))
    assert r.status_code == 403, r.data
    assert "auteur" in r.get_json()["error"]

    fil = {x["id"]: x for x in _thread(c, room["token"], room["gtA"], room["mid"])}
    assert fil[cid]["deleted"] is False and fil[cid]["body"] == "À moi"


def test_delete_comment_anonymous_403(room):
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="À moi").get_json()["id"]
    assert c.delete("/share/%s/comment/%d" % (room["token"], cid)).status_code == 403


def test_delete_comment_unknown_token_404(room):
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="À moi").get_json()["id"]
    r = c.delete("/share/jeton-invente/comment/%d" % cid, headers=H(room["gtA"]))
    assert r.status_code == 404, r.data


def test_delete_unknown_comment_404(room):
    r = room["c"].delete("/share/%s/comment/999999" % room["token"], headers=H(room["gtA"]))
    assert r.status_code == 404, r.data


def test_delete_comment_out_of_scope_404(room):
    """Le commentaire d'un mémo hors partage n'est pas atteignable par ce jeton."""
    c = room["c"]
    other = c.post("/api/memos/%d/comments" % room["out_mid"], json={"body": "Ailleurs"})
    cid = other.get_json()["id"]
    r = c.delete("/share/%s/comment/%d" % (room["token"], cid), headers=H(room["gtA"]))
    assert r.status_code == 404, r.data


def test_moderator_can_delete_a_guest_message(room):
    """[GUEST-ROLES V2 · T4] `moderer` prend corps : un Modérateur pose la tombale sur le
    message d'un AUTRE invité. La doctrine ne bouge pas — c'est QUI peut la poser qui s'élargit."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Message d'Alice").get_json()["id"]
    assert c.put("/api/guests/%d/role" % room["idB"],
                 json={"project_id": room["pid"], "role": "moderator"}).status_code == 200

    r = c.delete("/share/%s/comment/%d" % (room["token"], cid), headers=H(room["gtB"]))
    assert r.status_code in (200, 204), r.data
    fil = {x["id"]: x for x in _thread(c, room["token"], room["gtA"], room["mid"])}
    assert fil[cid]["deleted"] is True


def test_moderator_cannot_delete_owner_message(room):
    """Modérer les invités n'est pas modérer le propriétaire : son message reste hors d'atteinte."""
    c = room["c"]
    own = c.post("/api/memos/%d/comments" % room["mid"], json={"body": "Mot du proprio"})
    assert own.status_code in (200, 201), own.data
    cid = own.get_json()["id"]
    assert c.put("/api/guests/%d/role" % room["idB"],
                 json={"project_id": room["pid"], "role": "moderator"}).status_code == 200

    r = c.delete("/share/%s/comment/%d" % (room["token"], cid), headers=H(room["gtB"]))
    assert r.status_code == 403, r.data

    con = _db()
    try:
        row = con.execute("SELECT body FROM memo_comments WHERE id = ?", (cid,)).fetchone()
    finally:
        con.close()
    assert row["body"] == "Mot du proprio"


# ══════════════════════ D. share_react_comment — réagir ══════════════════════

def _react(room, gt, comment_id, emoji, token=None):
    return room["c"].post("/share/%s/comment/%d/react" % (token or room["token"], comment_id),
                          headers=(H(gt) if gt else {}), json={"emoji": emoji})


def test_react_anonymous_403(room):
    cid = _post(room["c"], room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    r = _react(room, None, cid, "👍")
    assert r.status_code == 403, r.data


def test_react_out_of_scope_404(room):
    c = room["c"]
    other = c.post("/api/memos/%d/comments" % room["out_mid"], json={"body": "Ailleurs"})
    r = _react(room, room["gtA"], other.get_json()["id"], "👍")
    assert r.status_code == 404, r.data


def test_react_unknown_comment_404(room):
    assert _react(room, room["gtA"], 999999, "👍").status_code == 404


def test_react_unknown_token_404(room):
    cid = _post(room["c"], room["token"], room["mid"], room["gtA"],
                body="Salut").get_json()["id"]
    assert _react(room, room["gtA"], cid, "👍", token="jeton-invente").status_code == 404


def test_viewer_cannot_react_403(room):
    """Réagir n'exige PAS `can_edit` (réagir ≠ éditer) — mais exige la capacité de commenter."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    sh = _share(c, room["pid"], role="viewer")
    gt = _register(c, sh["token"], sh["pin"], "v@ex.com", "Vera")

    r = _react(room, gt, cid, "👍", token=sh["token"])
    assert r.status_code == 403, r.data


def test_react_off_palette_400(room):
    """La whitelist serveur tranche : un emoji valide mais absent de la palette est refusé
    tout autant qu'un texte — le validateur d'unicité ne remplace pas la palette."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    for bad in ("🦑", "x", "<b>", ""):
        r = _react(room, room["gtB"], cid, bad)
        assert r.status_code == 400, (bad, r.data)
        assert r.get_json()["error"] == "emoji hors palette"


def test_react_toggles(room):
    """Une réaction est un interrupteur par (commentaire, emoji, votant) — reposter retire."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]

    on = _react(room, room["gtB"], cid, "👍")
    assert on.status_code == 200, on.data
    reacts = {x["emoji"]: x for x in on.get_json()["reactions"]}
    assert reacts["👍"]["count"] == 1
    assert reacts["👍"]["mine"] is True
    assert reacts["👍"]["voters"] == ["Bob"]          # le NOM seul : l'e-mail reste owner-only

    off = _react(room, room["gtB"], cid, "👍")
    assert off.status_code == 200, off.data
    assert off.get_json()["reactions"] == []

    con = _db()
    try:
        n = con.execute("SELECT COUNT(*) AS n FROM comment_reactions WHERE comment_id = ?",
                        (cid,)).fetchone()["n"]
    finally:
        con.close()
    assert n == 0, "le toggle doit RETIRER la ligne, pas empiler une seconde réaction"


def test_react_two_guests_are_counted_separately(room):
    """Le toggle porte sur (commentaire, emoji, VOTANT) : deux personnes ne s'annulent pas."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    assert _react(room, room["gtA"], cid, "🎉").status_code == 200
    res = _react(room, room["gtB"], cid, "🎉")
    assert res.status_code == 200, res.data
    agg = {x["emoji"]: x for x in res.get_json()["reactions"]}["🎉"]
    assert agg["count"] == 2
    assert sorted(agg["voters"]) == ["Alice", "Bob"]


def test_configured_palette_replaces_the_default(room):
    """[REACTION-PALETTE] La whitelist est DATA-DRIVEN : l'owner ajoute et retire. Ce que le
    serveur accepte suit la config, pas la liste livrée — sinon la config ne servirait à rien."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    up = c.put("/api/settings", json={"reaction_emojis": ["🦑", "👍"]})
    assert up.status_code == 200, up.data
    assert up.get_json()["reaction_emojis"] == ["🦑", "👍"]

    assert _react(room, room["gtB"], cid, "🦑").status_code == 200   # ajouté → accepté
    assert _react(room, room["gtB"], cid, "🎉").status_code == 400   # retiré → refusé


def test_palette_config_rejects_invalid_emoji(room):
    """La config passe par le MÊME validateur que les réactions (invariant 6) : pas de porte
    dérobée par laquelle du texte ou du balisage entrerait dans la palette."""
    c = room["c"]
    for bad in (["<b>"], ["hello"], ["👍👎"], [""]):
        r = c.put("/api/settings", json={"reaction_emojis": bad})
        assert r.status_code == 400, (bad, r.data)
        assert r.get_json()["error"] == "emoji invalide"
    assert c.put("/api/settings", json={"reaction_emojis": "👍"}).status_code == 400
    # …et la palette n'a pas bougé sous ces refus.
    assert c.get("/api/settings").get_json()["reaction_emojis"] == list(_palette_default())


def _palette_default():
    import app
    return app.REACTION_EMOJIS


def test_corrupted_palette_config_falls_back_to_default(room):
    """Une config illisible en base (JSON cassé, ou pas une liste) retombe sur la palette de
    base — jamais un 500 : la réaction est un ornement, elle ne doit pas emporter la page."""
    import app
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    for garbage in ("{pas du json", '"une chaine"', "42"):
        con = _db()
        try:
            con.execute("INSERT INTO app_state (key, value) VALUES ('reaction_emojis', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (garbage,))
            con.commit()
        finally:
            con.close()
        assert c.get("/api/settings").get_json()["reaction_emojis"] == list(app.REACTION_EMOJIS)
        r = _react(room, room["gtB"], cid, "👍")
        assert r.status_code == 200, (garbage, r.data)
        _react(room, room["gtB"], cid, "👍")      # on repose l'interrupteur pour le tour suivant


def test_reaction_kept_after_its_emoji_leaves_the_palette(room):
    """Retirer un emoji de la palette ne DÉTRUIT pas les réactions déjà posées : elles restent
    affichées, rejetées en fin de liste. Non destructif à l'affichage — on ne réécrit pas le passé."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="Salut").get_json()["id"]
    assert _react(room, room["gtB"], cid, "🎉").status_code == 200
    assert c.put("/api/settings", json={"reaction_emojis": ["👍"]}).status_code == 200

    fil = {x["id"]: x for x in _thread(c, room["token"], room["gtA"], room["mid"])}
    emojis = [x["emoji"] for x in fil[cid]["reactions"]]
    assert emojis == ["🎉"], "la réaction posée doit survivre au retrait de son emoji"


def test_cannot_react_on_a_tombstone(room):
    """Une tombale n'a plus d'actions : le front ne montre pas la palette, le serveur le garantit."""
    c = room["c"]
    cid = _post(c, room["token"], room["mid"], room["gtA"], body="À retirer").get_json()["id"]
    assert _react(room, room["gtB"], cid, "👍").status_code == 200
    assert c.delete("/share/%s/comment/%d" % (room["token"], cid),
                    headers=H(room["gtA"])).status_code in (200, 204)

    assert _react(room, room["gtB"], cid, "👍").status_code == 404

    con = _db()
    try:
        n = con.execute("SELECT COUNT(*) AS n FROM comment_reactions WHERE comment_id = ?",
                        (cid,)).fetchone()["n"]
    finally:
        con.close()
    assert n == 0, "les réactions partent AVEC le message supprimé"
