"""[MAP-PHOTO-COUNT] Le bouton Carte doit compter aussi les photos géolocalisées.

Angle mort d'origine : le bouton Carte d'un dossier ne dépendait que de la localisation
MANUELLE des mémos (`memos.location`). Un dossier plein de photos géotaguées n'avait donc pas
de bouton — on ne pouvait même pas ouvrir la carte pour les voir, alors que la donnée existait
depuis l'upload (`image_meta`, peuplée par `_record_image_meta`).

Ce fichier garde le maillon serveur : `GET /api/memos` expose `geo_photo_count` par mémo, avec
**exactement** le filtre du calque photo (`has_gps = 1`, hors corbeille image). Les deux doivent
rester alignés : un compteur qui annonce un point que le calque n'affiche pas est pire que pas
de compteur.

Zéro réseau : `_image_exif` est monkeypatché. Ça évite d'un coup le géocodage Nominatim (que la
garde de `conftest.py` bloquerait) et le forgeage d'un EXIF GPS dans le fichier de test.
"""
import io
import sqlite3

import pytest

pytestmark = pytest.mark.invariant

pytest.importorskip("PIL", reason="Pillow requis pour fabriquer une image de test")
from PIL import Image  # noqa: E402


# ───────────────────────────────────────── montage ─────────────────────────────────────────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _project(c, nom="Voyage"):
    r = c.post("/api/projects", json={"name": nom})
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _memo(c, contenu, project_id=None):
    body = {"content": contenu}
    if project_id is not None:
        body["project_id"] = project_id
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (90, 120, 60)).save(buf, "JPEG")
    buf.seek(0)
    return buf


def _upload(c, memo_id, nom="photo.jpg"):
    r = c.post("/api/memos/%d/images" % memo_id,
               data={"image": (_jpeg(), nom)}, content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    return r.get_json()["images"][-1]


@pytest.fixture
def geo(monkeypatch):
    """Fait passer toute image uploadée pour géotaguée, SANS réseau ni EXIF forgé.

    `_record_image_meta` appelle `_image_exif`, qui géocode via Nominatim : la garde
    zéro-réseau de `conftest.py` l'intercepterait. On stubbe donc la lecture EXIF elle-même —
    c'est aussi ce qui rend le test lisible : la photo est géolocalisée parce qu'on le dit,
    pas parce qu'on a réussi à empaqueter des rationnels GPS."""
    import app
    monkeypatch.setattr(app, "_image_exif", lambda name: {
        "lat": 43.4832, "lng": -1.4666, "label": "Bayonne", "datetime": "2026:08:09 12:00:00",
    })


@pytest.fixture
def sans_geo(monkeypatch):
    """L'inverse : une photo sans coordonnées (le cas le plus courant d'une capture d'écran)."""
    import app
    monkeypatch.setattr(app, "_image_exif", lambda name: {"datetime": "2026:08:09 12:00:00"})


def _meta(nom):
    con = _db()
    try:
        return con.execute("SELECT * FROM image_meta WHERE filename = ?", (nom,)).fetchone()
    finally:
        con.close()


def _memo_dict(c, memo_id):
    for m in c.get("/api/memos").get_json():
        if m["id"] == memo_id:
            return m
    raise AssertionError("mémo %d absent de /api/memos" % memo_id)


# ══════════════════════ la donnée source : image_meta ══════════════════════

def test_upload_geotagged_photo_records_has_gps(client, geo):
    """Le maillon d'amont, gardé pour que le reste du fichier ne repose pas sur une supposition :
    uploader une photo géotaguée pose bien `has_gps = 1` et ses coordonnées."""
    c = client
    mid = _memo(c, "Mémo à photos")
    nom = _upload(c, mid)

    row = _meta(nom)
    assert row is not None, "l'upload doit enregistrer la métadonnée d'image"
    assert row["has_gps"] == 1
    assert row["memo_id"] == mid
    assert abs(row["lat"] - 43.4832) < 1e-6 and abs(row["lng"] - (-1.4666)) < 1e-6


def test_photo_without_gps_is_recorded_but_not_geolocated(client, sans_geo):
    c = client
    mid = _memo(c, "Capture d'écran")
    nom = _upload(c, mid)

    row = _meta(nom)
    assert row is not None and row["has_gps"] == 0
    assert row["lat"] is None


# ══════════════════════ le champ exposé : geo_photo_count ══════════════════════

def test_memos_expose_geo_photo_count(client, geo):
    """Le champ qui manquait au front pour décider d'afficher le bouton Carte."""
    c = client
    pid = _project(c)
    avec = _memo(c, "Mémo avec photos géo", project_id=pid)
    sans = _memo(c, "Mémo sans photo", project_id=pid)
    _upload(c, avec, "a.jpg")
    _upload(c, avec, "b.jpg")

    assert _memo_dict(c, avec)["geo_photo_count"] == 2
    assert _memo_dict(c, sans)["geo_photo_count"] == 0, (
        "un mémo sans photo doit exposer 0, pas un champ absent — le front somme sans garde"
    )


def test_photo_without_gps_is_not_counted(client, sans_geo):
    """Une photo sans coordonnées ne met aucun point sur la carte : elle ne doit donc pas
    faire apparaître le bouton. Compter les photos plutôt que les photos GÉOLOCALISÉES
    ouvrirait une carte vide."""
    c = client
    pid = _project(c)
    mid = _memo(c, "Que des captures d'écran", project_id=pid)
    _upload(c, mid)

    assert _memo_dict(c, mid)["geo_photo_count"] == 0


def test_geo_photo_count_excludes_a_trashed_image(client, geo):
    """[IMAGE-TRASH] Une photo en corbeille quitte le calque photo (`_project_photos` la
    filtre) : le compteur doit la lâcher au même instant, sinon le badge annoncerait un point
    que la carte n'affiche pas."""
    c = client
    pid = _project(c)
    mid = _memo(c, "Mémo à photos", project_id=pid)
    a = _upload(c, mid, "a.jpg")
    _upload(c, mid, "b.jpg")
    assert _memo_dict(c, mid)["geo_photo_count"] == 2

    assert c.delete("/api/memos/%d/images/%s" % (mid, a)).status_code == 200

    assert _memo_dict(c, mid)["geo_photo_count"] == 1, (
        "la photo mise en corbeille ne doit plus compter"
    )


def test_counter_and_photo_layer_agree(client, geo):
    """Le vrai invariant du lot : le compteur et le calque comptent la MÊME chose. On les
    compare sur le même périmètre plutôt que de vérifier deux fois la même requête à la main."""
    import app
    c = client
    pid = _project(c)
    m1 = _memo(c, "Un", project_id=pid)
    m2 = _memo(c, "Deux", project_id=pid)
    _upload(c, m1, "a.jpg")
    _upload(c, m1, "b.jpg")
    nom = _upload(c, m2, "c.jpg")
    assert c.delete("/api/memos/%d/images/%s" % (m2, nom)).status_code == 200

    total = sum(m["geo_photo_count"] for m in c.get("/api/memos").get_json()
                if m.get("project_id") == pid)

    with app.app.app_context():
        db = app.get_db()
        calque = [p for p in app._project_photos(db, [m1, m2]) if p.get("has_gps")]
    assert total == len(calque) == 2


def test_geo_photo_count_is_not_exported(client, geo):
    """Donnée dérivée : elle n'entre pas dans l'export (invariant 1, `APP_VERSION` reste 27)."""
    c = client
    mid = _memo(c, "Mémo à photos")
    _upload(c, mid)

    export = c.get("/api/export").get_json()
    assert export["version"] == 27
    for m in export["memos"]:
        assert "geo_photo_count" not in m, "un compteur dérivé n'a rien à faire dans l'export"
