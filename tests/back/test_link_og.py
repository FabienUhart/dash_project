"""[LINK-OG] Aperçu OpenGraph des cards de liens — back.

Doctrine du brief (docs/briefs/LINK-OG.md, v2) : le fetch est **owner-only**, ne vise que
`url_public`, se fait **hors du chemin de sauvegarde**, et les colonnes `og_*` sont **dérivées**
donc hors export. Les tests stubbent le fetcher : la garde zéro-réseau (`tests/conftest.py`)
reste verte de bout en bout, y compris pendant les enregistrements.

⚠ PÉRIMÈTRE INVITÉ — CORRECTION DE PRÉMISSE. Le brief prévoyait une sérialisation invitée et une
route `/share/<token>/og-image/<name>` « scopée au périmètre du token ». Mesuré dans le code :
la table `links` n'est exposée à AUCUNE surface invitée (`share_data` ne sérialise que mémos et
projets ; `share.html`/`hub.html` n'affichent aucun lien). Un lien n'est donc JAMAIS dans le
périmètre d'un jeton : la route scopée répondrait 404 en toute circonstance. On ne l'écrit pas —
une route publique morte n'est pas neutre, c'est de la surface d'attaque en plus (invariant 5).
Le test #9 du brief devient son contraire utile : `test_no_guest_og_surface`, qui verrouille
l'absence de cette route et l'absence de fuite de liens côté invité.
"""
import io
import json

import pytest

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ outils ---

def _jpeg(px=1200, color=(200, 60, 60)):
    """Un vrai JPEG en mémoire (signature valide), taille demandée."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (px, px), color).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _mk_link(c, **kw):
    payload = {"name": "Meduse carte"}
    payload.update(kw)
    r = c.post("/api/links", json=payload)
    assert r.status_code == 201, r.data
    return r.get_json()


def _get_link(c, lid):
    for l in c.get("/api/links").get_json():
        if l["id"] == lid:
            return l
    raise AssertionError("lien %s introuvable" % lid)


def _stub_fetch(app_module, monkeypatch, **og):
    """Stubbe `_fetch_og` et rend le compteur d'appels."""
    calls = []
    base = {"status": "ok", "title": "Bilbao — méduses, marées et spots",
            "desc": "Le guide des plages et de la faune du littoral basque.",
            "domain": "meduseo.com", "image_bytes": _jpeg()}
    base.update(og)

    def _fake(url):
        calls.append(url)
        return dict(base)

    monkeypatch.setattr(app_module, "_fetch_og", _fake)
    return calls


# --- #1 · le refresh peuple les colonnes ET cache une vignette ---------------

def test_refresh_fetches_og_and_caches_thumbnail(client, app_module, monkeypatch):
    """#1 du brief, à la sémantique v2 : ce n'est pas la création qui fetch (cf. #10) mais le
    refresh. `_fetch_og` stubbé → colonnes `og_*` peuplées, image téléchargée ET vignette
    présente dans le cache local."""
    import os
    calls = _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, url_public="https://meduseo.com/fr/ville/Bilbao-1")

    r = client.post("/api/links/%d/og-refresh" % link["id"])
    assert r.status_code == 200, r.data
    out = r.get_json()

    assert calls == ["https://meduseo.com/fr/ville/Bilbao-1"]
    assert out["og_status"] == "ok"
    assert out["og_title"] == "Bilbao — méduses, marées et spots"
    assert out["og_desc"].startswith("Le guide des plages")
    assert out["og_domain"] == "meduseo.com"
    assert out["og_image"] == link["uid"] + ".jpg"
    assert out["og_fetched_at"], "horodatage manquant (sert de cache-bust)"

    cached = os.path.join(app_module._og_dir(), out["og_image"])
    assert os.path.isfile(cached), "vignette non écrite dans le cache local"

    # servie par la route owner, avec revalidation (pas de cache figé)
    img = client.get("/api/og-image/" + out["og_image"])
    assert img.status_code == 200
    assert img.data[:3] == b"\xff\xd8\xff", "la vignette servie n'est pas un JPEG"


# --- #2 · le texte de Fabien n'est JAMAIS muté -------------------------------

def test_og_does_not_overwrite_user_text(client, app_module, monkeypatch):
    """#2 : `name`/`descr` saisis restent intacts après un fetch ; le repli d'affichage
    (`name || og_title`) n'existe QUE côté rendu — la base ne perd rien."""
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, name="Meduse carte", descr="Ma description à moi",
                    url_public="https://meduseo.com/")

    client.post("/api/links/%d/og-refresh" % link["id"])
    out = _get_link(client, link["id"])

    assert out["name"] == "Meduse carte", "le nom saisi a été écrasé par l'OG"
    assert out["descr"] == "Ma description à moi", "la description saisie a été écrasée"
    # l'OG est là, à côté, disponible pour le repli d'affichage
    assert out["og_title"] == "Bilbao — méduses, marées et spots"
    assert out["og_desc"].startswith("Le guide des plages")


def test_og_fills_the_gap_when_user_text_is_empty(client, app_module, monkeypatch):
    """Seconde moitié de #2 : à champs vides, l'affichage retombe sur l'OG. Le repli est une
    règle de rendu — on vérifie ici que la matière est bien exposée pour l'appliquer."""
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, name="Sans titre", descr="", url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])
    out = _get_link(client, link["id"])

    assert out["descr"] == "", "la description vide a été REMPLIE en base (interdit)"
    assert out["og_desc"], "rien à quoi retomber pour l'affichage"


# --- #3 · SSRF : les plages privées sont refusées AVANT tout appel -----------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://localhost:8099/",
    "http://192.168.1.42/",
    "http://10.0.0.7/",
    "http://172.16.3.1/",
    "http://169.254.169.254/latest/meta-data/",   # endpoint métadonnée cloud
    "http://[::1]/",
    "http://0.0.0.0/",
    "ftp://meduseo.com/",                          # schéma hors http/https
    "file:///etc/passwd",
])
def test_og_ssrf_blocks_private(app_module, monkeypatch, url):
    """#3 : refus AVANT tout appel — prouvé par un compteur, pas par l'absence de trace."""
    appels = []
    monkeypatch.setattr(app_module, "_og_http_get",
                        lambda *a, **k: appels.append(a) or None)

    out = app_module._fetch_og(url)

    assert out["status"] == "failed", "%s aurait dû être refusée" % url
    assert appels == [], "un appel réseau a été tenté vers %s" % url


def test_og_ssrf_revalidates_every_redirect(app_module, monkeypatch):
    """La redirection est le trou classique : l'hôte de départ est public, la cible ne l'est
    pas. Chaque saut est re-validé — sinon `http://public/` mène à `169.254.169.254`."""
    monkeypatch.setattr(app_module, "_og_resolve",
                        lambda host: [__import__("ipaddress").ip_address("93.184.216.34")]
                        if host == "meduseo.com" else
                        [__import__("ipaddress").ip_address("169.254.169.254")])

    vus = []

    class _Resp:
        status_code = 302
        headers = {"Location": "http://metadata.evil/latest/meta-data/"}
        def iter_content(self, n): return iter(())
        def close(self): pass

    def _fake_get(url, **k):
        vus.append(url)
        return _Resp()

    monkeypatch.setattr(app_module.requests, "get", _fake_get, raising=False)

    assert app_module._og_http_get("https://meduseo.com/", 1000) is None
    assert vus == ["https://meduseo.com/"], "la redirection privée a été suivie"


def test_og_public_host_is_allowed(app_module, monkeypatch):
    """Contre-épreuve : la garde ne refuse pas tout. Sans elle, #3 passerait au vert pour la
    mauvaise raison (un `return failed` inconditionnel)."""
    import ipaddress
    monkeypatch.setattr(app_module, "_og_resolve",
                        lambda host: [ipaddress.ip_address("93.184.216.34")])
    assert app_module._og_url_allowed("https://meduseo.com/page") is True


# --- #4 · url_local n'est JAMAIS passé au fetcher ---------------------------

def test_url_local_never_fetched(client, app_module, monkeypatch):
    """#4 : le LAN ne sort jamais. Seul `url_public` atteint le fetcher, même quand le lien
    porte une URL locale (et surtout quand il n'a QUE ça)."""
    calls = _stub_fetch(app_module, monkeypatch)

    deux = _mk_link(client, url_public="https://meduseo.com/", url_local="http://192.168.1.50:8080/")
    client.post("/api/links/%d/og-refresh" % deux["id"])
    assert calls == ["https://meduseo.com/"], "url_local a fuité vers le fetcher"

    calls.clear()
    lan = _mk_link(client, name="NAS", url_local="http://192.168.1.50:8080/")
    r = client.post("/api/links/%d/og-refresh" % lan["id"])
    assert r.status_code == 200, r.data
    assert calls == [], "un lien sans url_public a déclenché un fetch"
    assert _get_link(client, lan["id"])["og_status"] == ""


# --- #5 · page sans balises → 'none' ----------------------------------------

def test_no_og_tags_fallback(client, app_module, monkeypatch):
    """#5 : une page sans balise OG ni <title> → `og_status='none'`, la card reste en repli."""
    _stub_fetch(app_module, monkeypatch, status="none", title="", desc="",
                domain="meduseo.com", image_bytes=b"")
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])

    out = _get_link(client, link["id"])
    assert out["og_status"] == "none"
    assert out["og_title"] == "" and out["og_image"] == ""
    assert out["og_fetched_at"], "un 'none' doit être horodaté (sinon re-fetch en boucle)"


def test_og_parses_tags_with_title_fallback(app_module):
    """Le parseur, en direct : OG d'abord, repli `<title>`/`<meta name=description>` ensuite."""
    plein = app_module._og_parse(
        '<html><head><meta property="og:title" content="Titre OG">'
        '<meta property="og:description" content="Desc OG">'
        '<meta property="og:image" content="/img/cover.jpg">'
        '<title>Titre HTML</title></head></html>', "https://meduseo.com/a/b")
    assert plein["title"] == "Titre OG"
    assert plein["desc"] == "Desc OG"
    assert plein["image_url"] == "https://meduseo.com/img/cover.jpg", "URL image non absolutisée"

    maigre = app_module._og_parse(
        '<html><head><title>Titre HTML</title>'
        '<meta name="description" content="Desc HTML"></head></html>', "https://meduseo.com/")
    assert maigre["title"] == "Titre HTML"
    assert maigre["desc"] == "Desc HTML"
    assert maigre["image_url"] == ""

    vide = app_module._og_parse("<html><head></head><body>rien</body></html>", "https://meduseo.com/")
    assert vide["title"] == "" and vide["desc"] == "" and vide["image_url"] == ""


# --- #6 · la route de refresh est owner-only --------------------------------

def test_refresh_route_owner_only(client, app_module):
    """#6 : `POST /api/links/<id>/og-refresh` existe côté owner ; AUCUNE route de refresh sous
    `/share/*` (invariant 5 : rien de public ne déclenche un appel sortant)."""
    regles = [str(r) for r in app_module.app.url_map.iter_rules()]
    assert "/api/links/<int:link_id>/og-refresh" in regles

    fautives = [r for r in regles if r.startswith("/share/") and "og" in r.lower()]
    assert fautives == [], "surface invitée OG interdite : %s" % fautives


def test_refresh_unknown_link_is_404(client):
    r = client.post("/api/links/999999/og-refresh")
    assert r.status_code == 404


# --- #7 / #9 · aucune surface invitée, aucun fetch invité -------------------

def test_no_guest_og_surface(client, app_module):
    """#7+#9 réunis, à la prémisse corrigée (cf. l'en-tête du fichier) : les liens ne sont
    exposés à aucun invité, donc rien n'est à scoper — et rien ne doit apparaître. On verrouille
    les deux moitiés : pas de route OG publique, pas de liens dans la charge invitée."""
    _mk_link(client, url_public="https://meduseo.com/")
    pid = client.post("/api/projects", json={"name": "Voyage eclipse"}).get_json()["id"]
    client.post("/api/memos", json={"content": "Reservation", "project_id": pid})
    r = client.post("/api/shares", json={"kind": "project", "target_id": pid})
    assert r.status_code in (200, 201), r.data
    token = r.get_json()["token"]

    data = client.get("/share/%s/data" % token)
    assert data.status_code == 200, data.data
    brut = data.get_data(as_text=True)
    assert "meduseo.com" not in brut, "une URL de lien a fuité côté invité"
    assert "og_image" not in brut and "og_title" not in brut

    regles = [str(r) for r in app_module.app.url_map.iter_rules()]
    assert [r for r in regles if r.startswith("/share/") and "og" in r.lower()] == []


# --- #8 · image bornée au téléchargement ET rangée en vignette --------------

def test_og_image_is_thumbnailed_not_stored_raw(client, app_module, monkeypatch):
    """#8, moitié « vignette » : une source 1200 px est rangée en JPEG ≤ 600 px. On ne stocke
    QUE la vignette — le brut est jeté."""
    import os
    from PIL import Image
    gros = _jpeg(1200)
    _stub_fetch(app_module, monkeypatch, image_bytes=gros)
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])

    chemin = os.path.join(app_module._og_dir(), link["uid"] + ".jpg")
    assert os.path.isfile(chemin)
    with Image.open(chemin) as im:
        assert im.format == "JPEG"
        assert max(im.size) <= app_module.OG_THUMB_PX, "vignette non bornée : %s" % (im.size,)
    assert os.path.getsize(chemin) < len(gros), "le fichier stocké n'est pas plus léger que la source"


def test_og_download_is_capped(app_module, monkeypatch):
    """#8, moitié « plafond » : le téléchargement est COUPÉ au-delà de la borne. Un serveur
    hostile qui envoie un flux sans fin ne doit pas remplir le disque ni la RAM."""
    import ipaddress
    monkeypatch.setattr(app_module, "_og_resolve",
                        lambda host: [ipaddress.ip_address("93.184.216.34")])

    class _Flux:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}
        def iter_content(self, n):
            while True:            # robinet ouvert : c'est l'appelant qui doit fermer
                yield b"\x00" * n
        def close(self): pass

    monkeypatch.setattr(app_module.requests, "get", lambda url, **k: _Flux(), raising=False)

    got = app_module._og_http_get("https://meduseo.com/img.jpg", 4096)
    assert got is not None
    assert len(got["body"]) <= 4096, "flux non coupé au plafond (%d octets)" % len(got["body"])


def test_og_rejects_a_non_image_payload(client, app_module, monkeypatch):
    """Une « image » qui n'en est pas une (signature absente) n'est pas rangée : le reste de
    l'OG reste utilisable, seul `og_image` reste vide."""
    _stub_fetch(app_module, monkeypatch, image_bytes=b"<html>pas une image</html>")
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])

    out = _get_link(client, link["id"])
    assert out["og_image"] == "", "un non-image a été rangé dans le cache"
    assert out["og_status"] == "ok" and out["og_title"], "l'échec image a emporté tout l'OG"


# --- #10 · l'enregistrement ne touche pas le réseau -------------------------

def test_save_does_not_fetch_inline(client, app_module):
    """#10 : create/update posent `og_status='pending'` et NE TOUCHENT PAS au réseau. Ici, rien
    n'est stubbé : la garde zéro-réseau de `conftest.py` est le juge. Si l'enregistrement
    fetchait, elle lèverait (BaseException, non avalable)."""
    link = _mk_link(client, url_public="https://meduseo.com/")
    assert link["og_status"] == "pending"
    assert link["og_fetched_at"] == ""

    r = client.put("/api/links/%d" % link["id"], json={"url_public": "https://autre.example/"})
    assert r.status_code == 200, r.data
    assert r.get_json()["og_status"] == "pending"


def test_update_marks_pending_only_when_the_public_url_changes(client, app_module, monkeypatch):
    """Corollaire de #10, et garde anti-régression du refresh : un `PUT` qui ne touche pas à
    `url_public` (renommage, étiquettes…) ne doit PAS jeter l'OG déjà en cache."""
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])
    avant = _get_link(client, link["id"])
    assert avant["og_status"] == "ok"

    client.put("/api/links/%d" % link["id"], json={"name": "Meduse carte (2)"})
    apres = _get_link(client, link["id"])
    assert apres["og_status"] == "ok", "un renommage a invalidé l'OG"
    assert apres["og_title"] == avant["og_title"]
    assert apres["og_fetched_at"] == avant["og_fetched_at"]


def test_clearing_the_public_url_clears_the_og(client, app_module, monkeypatch):
    """Vider `url_public` vide l'OG et purge la vignette : pas de fiche fantôme, pas de fichier
    orphelin sur le volume."""
    import os
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])
    chemin = os.path.join(app_module._og_dir(), link["uid"] + ".jpg")
    assert os.path.isfile(chemin)

    client.put("/api/links/%d" % link["id"], json={"url_public": ""})
    out = _get_link(client, link["id"])
    assert out["og_status"] == "" and out["og_image"] == "" and out["og_title"] == ""
    assert not os.path.isfile(chemin), "vignette orpheline laissée sur le volume"


def test_deleting_a_link_purges_its_cached_thumbnail(client, app_module, monkeypatch):
    import os
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])
    chemin = os.path.join(app_module._og_dir(), link["uid"] + ".jpg")
    assert os.path.isfile(chemin)

    assert client.delete("/api/links/%d" % link["id"]).status_code == 204
    assert not os.path.isfile(chemin), "vignette orpheline après suppression du lien"


# --- sweep / backfill --------------------------------------------------------

def test_sweep_picks_up_pending_and_failed_but_skips_ok(client, app_module, monkeypatch):
    """Le sweep est **relançable sans danger** : il ramasse les `pending` et RETENTE les
    `failed` (échec temporaire), mais SAUTE les `ok` — sinon chaque passage re-taperait tous
    les sites du dashboard."""
    calls = _stub_fetch(app_module, monkeypatch)
    a = _mk_link(client, name="A pending", url_public="https://a.example/")
    b = _mk_link(client, name="B failed", url_public="https://b.example/")
    c = _mk_link(client, name="C ok", url_public="https://c.example/")
    d = _mk_link(client, name="D sans url")

    client.post("/api/links/%d/og-refresh" % c["id"])          # C passe à ok
    calls.clear()
    db = app_module.sqlite3.connect(app_module.DB_PATH)
    db.execute("UPDATE links SET og_status='failed', og_fetched_at='2026-01-01' WHERE id=?", (b["id"],))
    db.commit(); db.close()

    app_module._og_sweep()

    assert sorted(calls) == ["https://a.example/", "https://b.example/"], \
        "le sweep n'a pas ramassé exactement pending+failed : %s" % calls

    # relancé, il est idempotent : plus rien à faire
    calls.clear()
    app_module._og_sweep()
    assert calls == [], "second passage non idempotent : %s" % calls


def test_sweep_is_safe_with_two_workers(client, app_module, monkeypatch):
    """Le sweep tourne dans un thread lancé AU CHARGEMENT DU MODULE — donc une fois PAR WORKER
    gunicorn, et le Dockerfile en démarre deux. Sans précaution, les deux partent chercher les
    MÊMES liens : requêtes sortantes en double, et surtout deux processus qui écrivent la même
    vignette au même instant (JPEG déchiré). Le `_backup_loop` du projet est explicitement
    « idempotent par fichier-du-jour (multi-workers OK) » — même exigence ici.

    La course est reproduite pour de bon, pas approximée : le second sweep est déclenché DEPUIS
    l'intérieur du premier fetch, c'est-à-dire exactement à la fenêtre où le lien est encore
    marqué `pending` alors qu'un worker s'en occupe déjà.
    """
    appels = []
    entre = {"fait": False}
    vrai_ok = {"status": "ok", "title": "T", "desc": "D", "domain": "a.example", "image_bytes": b""}

    def _fake(url):
        appels.append(url)
        if not entre["fait"]:
            entre["fait"] = True
            app_module._og_sweep()          # « worker B » arrive pendant que A télécharge
        return dict(vrai_ok)

    monkeypatch.setattr(app_module, "_fetch_og", _fake)
    _mk_link(client, name="A", url_public="https://a.example/")

    app_module._og_sweep()

    assert appels == ["https://a.example/"], \
        "le lien a été cherché %d fois : les deux workers se marchent dessus (%s)" % (
            len(appels), appels)


def test_a_sweep_interrupted_leaves_no_link_stranded(client, app_module, monkeypatch):
    """Corollaire du claim : réserver une ligne ne doit pas pouvoir l'enterrer. Si le worker
    meurt en plein fetch (ici : une exception), la ligne garde son `pending` et le passage
    suivant la reprend — pas de lien condamné à ne jamais avoir d'aperçu."""
    def _boom(url):
        raise RuntimeError("worker abattu en plein vol")

    monkeypatch.setattr(app_module, "_fetch_og", _boom)
    lien = _mk_link(client, name="A", url_public="https://a.example/")
    app_module._og_sweep()

    assert _get_link(client, lien["id"])["og_status"] == "pending", \
        "la ligne a perdu son 'pending' : plus aucun sweep ne la reprendra"

    # La reprise est volontairement DIFFÉRÉE de `OG_CLAIM_TTL` : c'est ce délai qui distingue
    # « un autre worker s'en occupe à l'instant » de « personne ne s'en occupe plus ». On le met
    # à zéro pour observer la reprise tout de suite au lieu d'attendre deux minutes.
    monkeypatch.setattr(app_module, "OG_CLAIM_TTL", 0)
    calls = _stub_fetch(app_module, monkeypatch)
    app_module._og_sweep()
    assert calls == ["https://a.example/"], "le passage suivant n'a pas repris le lien"


# --- invariant 1 · les colonnes og_* sont DÉRIVÉES, hors export --------------

@pytest.mark.invariant
def test_og_columns_are_never_exported(client, app_module, monkeypatch):
    """Invariant 1 : `og_*` est de la donnée DÉRIVÉE (re-calculable depuis `url_public`), donc
    JAMAIS dans l'export — et `APP_VERSION` reste 27."""
    _stub_fetch(app_module, monkeypatch)
    link = _mk_link(client, url_public="https://meduseo.com/")
    client.post("/api/links/%d/og-refresh" % link["id"])

    exp = client.get("/api/export").get_json()
    assert exp["version"] == 27, "le format d'export a bougé sans bump documenté"
    assert exp["links"], "aucun lien exporté, le test ne prouve rien"
    for l in exp["links"]:
        fuites = [k for k in l if k.startswith("og_")]
        assert fuites == [], "champ dérivé exporté : %s" % fuites
    assert "meduseo" not in json.dumps(exp).replace('"url_public": "https://meduseo.com/"', ""), \
        "une trace d'OG a fuité ailleurs dans l'export"


@pytest.mark.invariant
def test_import_ignores_incoming_og_fields(client):
    """Symétrique : un fichier bricolé qui porterait des `og_*` ne doit rien injecter — la
    donnée dérivée se recalcule, elle ne s'importe pas."""
    payload = {"version": 27, "links": [{
        "name": "Bricolé", "url_public": "https://meduseo.com/", "uid": "u-og-1",
        "og_title": "INJECTÉ", "og_image": "../../etc/passwd", "og_status": "ok",
        "og_fetched_at": "2026-01-01", "og_desc": "INJECTÉ", "og_domain": "evil",
    }]}
    r = client.post("/api/import", json=payload)
    assert r.status_code in (200, 201), r.data

    out = [l for l in client.get("/api/links").get_json() if l["name"] == "Bricolé"][0]
    assert out["og_title"] == "" and out["og_image"] == "" and out["og_desc"] == ""
    assert out["og_status"] in ("", "pending"), out["og_status"]


# --- la route image owner ne sert que des noms légitimes --------------------

@pytest.mark.parametrize("nom", ["../../app.py", "..%2f..%2fapp.py", "pasunuid.jpg",
                                 "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.png"])
def test_og_image_route_rejects_bogus_names(client, nom):
    """Traversée de chemin et extensions exotiques : refusées. Le cache OG ne sert que des
    `<uid>.jpg`."""
    r = client.get("/api/og-image/" + nom)
    assert r.status_code in (404, 308), (nom, r.status_code)
