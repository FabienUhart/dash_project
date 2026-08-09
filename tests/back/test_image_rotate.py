"""[PHOTO-ROTATE-SAVE] Pivoter une photo ET l'enregistrer — côté serveur.

Jusqu'ici la rotation de la visionneuse était de l'**affichage seul** (`transform` CSS, remis à
zéro à la fermeture). Cette route rend le geste durable : elle pivote l'ORIGINAL sur le disque
et régénère les dérivées.

Le piège du lot, et la raison d'être de la moitié de ces tests : ce que l'utilisateur voit dans
la visionneuse n'est pas l'original, c'est la dérivée — générée par `_gen_derived`, qui applique
déjà `ImageOps.exif_transpose`. Tourner les octets sans neutraliser le tag EXIF `Orientation`
ferait donc **tourner deux fois** au prochain rendu. Il faut cuire l'orientation dans les pixels
PUIS remettre `Orientation = 1`.

Owner uniquement en v1 : aucune route invitée (invariant 5), et un test le prouve.
"""
import io
import json
import os
import sqlite3

import pytest

pytestmark = pytest.mark.invariant

PIL = pytest.importorskip("PIL", reason="Pillow requis pour la rotation d'images")
from PIL import Image, ImageOps  # noqa: E402


# ───────────────────────────────────────── montage ─────────────────────────────────────────

def _db():
    import app
    con = sqlite3.connect(app.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _memo(c, contenu="Mémo à photos"):
    r = c.post("/api/memos", json={"content": contenu})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _jpeg(taille=(800, 400), exif=None, couleur_coin=(255, 0, 0)):
    """JPEG en mémoire. Un coin coloré sert de repère : après rotation il doit avoir bougé —
    c'est ce qui distingue « l'image a tourné » de « les dimensions ont changé »."""
    im = Image.new("RGB", taille, (20, 20, 20))
    im.putpixel((0, 0), couleur_coin)
    for x in range(0, min(40, taille[0])):
        for y in range(0, min(20, taille[1])):
            im.putpixel((x, y), couleur_coin)
    buf = io.BytesIO()
    if exif is not None:
        im.save(buf, "JPEG", quality=95, exif=exif)
    else:
        im.save(buf, "JPEG", quality=95)
    buf.seek(0)
    return buf


def _png(taille=(800, 400)):
    im = Image.new("RGB", taille, (10, 60, 120))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return buf


@pytest.fixture(autouse=True)
def _pas_de_geocodage(monkeypatch):
    """Uploader une photo GÉOTAGUÉE déclenche un géocodage inverse chez Nominatim
    ([PHOTO-MAP], appel documenté et voulu côté app). La garde zéro-réseau de `conftest.py`
    l'a intercepté dès le premier test à EXIF GPS — elle a fait exactement son travail. On
    neutralise donc le géocodeur : ce fichier teste la rotation, pas la carte."""
    import app
    monkeypatch.setattr(app, "_reverse_geocode", lambda lat, lng: "")


def _upload(c, memo_id, buf, nom="photo.jpg"):
    r = c.post("/api/memos/%d/images" % memo_id,
               data={"image": (buf, nom)}, content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    images = r.get_json()["images"]
    assert images, "l'upload doit renvoyer le mémo avec son image"
    return images[-1]


def _chemin(nom):
    import app
    return os.path.join(app.UPLOAD_DIR, nom)


def _derive(nom, taille="t"):
    import app
    return os.path.join(app.DERIVED_DIR, app._derived_name(taille, nom))


def _rotate(c, nom, angle):
    return c.post("/api/images/%s/rotate" % nom, json={"angle": angle})


def _exif_orientation(chemin):
    with Image.open(chemin) as im:
        return im.getexif().get(0x0112)


def _exif_avec_orientation(valeur=6, gps=True):
    """EXIF portant une Orientation ≠ 1 (6 = « tourner de 90° horaire à l'affichage »), plus
    des tags GPS/date que la carte du projet consomme."""
    exif = Image.Exif()
    exif[0x0112] = valeur                       # Orientation
    exif[0x0132] = "2026:08:09 12:00:00"        # DateTime
    if gps:
        # Rationnels simples : Pillow refuse d'empaqueter des tuples imbriqués ici.
        exif[0x8825] = {1: "N", 2: (43.0, 29.0, 0.0), 3: "W", 4: (1.0, 28.0, 0.0)}
    return exif.tobytes()


# ══════════════════════ le cœur : la rotation persiste et ne double pas ══════════════════════

def test_rotate_90_swaps_dimensions_and_persists(client):
    """Le geste de base : après un quart de tour, l'ORIGINAL sur le disque a ses dimensions
    échangées. « Persiste » veut dire : le fichier, pas seulement l'affichage."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))
    with Image.open(_chemin(nom)) as im:
        assert im.size == (800, 400)

    r = _rotate(c, nom, 90)
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["ok"] is True and body["name"] == nom
    assert body["rotated_at"], "le front en a besoin pour casser le cache"

    with Image.open(_chemin(nom)) as im:
        assert im.size == (400, 800), "l'original doit être physiquement pivoté"


def test_rotate_90_turns_clockwise(client):
    """Le SENS compte, et il est facile de l'inverser : `rotate(deg)` positif en CSS tourne dans
    le sens horaire, alors que `Image.rotate` de Pillow tourne dans l'autre. On vérifie donc où
    atterrit le repère : le coin haut-GAUCHE d'une image tournée d'un quart de tour horaire se
    retrouve en haut à DROITE."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400), couleur_coin=(255, 0, 0)))

    assert _rotate(c, nom, 90).status_code == 200
    with Image.open(_chemin(nom)) as im:
        larg, haut = im.size
        coin_hd = im.getpixel((larg - 5, 5))
        coin_hg = im.getpixel((5, 5))
    assert coin_hd[0] > 150 and coin_hd[1] < 90, (
        "le repère devrait être en haut à droite après un quart de tour horaire, trouvé %r" % (coin_hd,))
    assert coin_hg[0] < 90, "il ne devrait plus être en haut à gauche"


def test_rotate_normalizes_exif_no_double_rotation(client):
    """LA régression que ce lot doit empêcher.

    L'image porte `Orientation = 6`, donc la visionneuse l'affiche déjà redressée (les dérivées
    passent par `exif_transpose`). Si la route se contentait de tourner les octets en laissant
    le tag, `_gen_derived` re-tournerait par-dessus au rendu suivant : double rotation, et
    l'utilisateur voit son image partir de travers alors qu'il vient de la redresser.

    Après rotation, l'original doit donc porter `Orientation = 1` ET des pixels correspondant à
    « ce qu'on voyait, tourné du bon angle ».
    """
    c = client
    mid = _memo(c)
    source = _jpeg((800, 400), exif=_exif_avec_orientation(6))
    source.seek(0)
    attendu = ImageOps.exif_transpose(Image.open(io.BytesIO(source.getvalue()))).transpose(
        Image.ROTATE_270)          # 90° horaire, sans ré-échantillonnage
    source.seek(0)
    nom = _upload(c, mid, source)
    assert _exif_orientation(_chemin(nom)) == 6, "le montage doit bien poser un tag ≠ 1"

    assert _rotate(c, nom, 90).status_code == 200

    assert _exif_orientation(_chemin(nom)) == 1, (
        "l'orientation doit être NEUTRALISÉE, sinon exif_transpose re-tourne à la génération "
        "des dérivées → double rotation"
    )
    with Image.open(_chemin(nom)) as im:
        assert im.size == attendu.size, "pixels attendus = exif_transpose(source) puis rotation"


def test_rotate_preserves_gps_and_date_exif(client):
    """La rotation ne déplace pas la photo dans le temps ni dans l'espace : les tags GPS/date
    survivent. La carte du projet ([PHOTO-MAP]) les lit — les perdre ferait disparaître le point
    d'un simple geste de redressement."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400), exif=_exif_avec_orientation(1)))

    assert _rotate(c, nom, 180).status_code == 200

    with Image.open(_chemin(nom)) as im:
        exif = im.getexif()
    assert exif.get(0x0132) == "2026:08:09 12:00:00", "la date a été perdue"
    assert exif.get_ifd(0x8825), "les coordonnées GPS ont été perdues"


def test_rotate_regenerates_derivatives(client):
    """Les dérivées doivent être RECONSTRUITES, pas seulement purgées : la vignette de la grille
    est servie depuis `t_` et doit montrer l'image droite tout de suite."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))
    c.get("/uploads/%s?size=t" % nom)          # force la génération de la dérivée
    d = _derive(nom, "t")
    assert os.path.isfile(d), "la dérivée doit exister AVANT, sinon le test ne prouve rien"
    with Image.open(d) as im:
        avant = im.size
    assert avant[0] > avant[1], "vignette paysage au départ"

    assert _rotate(c, nom, 90).status_code == 200

    assert os.path.isfile(d), "la dérivée doit être régénérée, pas juste supprimée"
    with Image.open(d) as im:
        apres = im.size
    assert apres[1] > apres[0], "la vignette doit être portrait après le quart de tour"


def test_rotate_180_and_270_are_accepted(client):
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))

    assert _rotate(c, nom, 180).status_code == 200
    with Image.open(_chemin(nom)) as im:
        assert im.size == (800, 400), "un demi-tour conserve les dimensions"

    assert _rotate(c, nom, 270).status_code == 200
    with Image.open(_chemin(nom)) as im:
        assert im.size == (400, 800)


def test_rotate_works_on_png(client):
    """PNG : sans perte, et sans EXIF d'orientation en général — le chemin ne doit pas planter
    pour autant."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _png((800, 400)), nom="photo.png")

    assert _rotate(c, nom, 90).status_code == 200
    with Image.open(_chemin(nom)) as im:
        assert im.size == (400, 800)
        assert im.format == "PNG", "le format ne doit pas changer sous les pieds de l'utilisateur"


# ══════════════════════════════ les refus ══════════════════════════════

def test_rotate_rejects_non_multiple_of_90(client):
    """Un angle libre n'a pas de sens ici : la rotation par `transpose` est exacte et sans
    ré-échantillonnage justement parce qu'elle est bornée aux quarts de tour."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))

    for mauvais in (45, 91, -30, "beaucoup", None):
        r = _rotate(c, nom, mauvais)
        assert r.status_code == 400, (mauvais, r.data)
        with Image.open(_chemin(nom)) as im:
            assert im.size == (800, 400), "un refus ne doit RIEN changer au fichier"


def test_rotate_zero_is_refused_and_changes_nothing(client):
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))
    avant = os.path.getsize(_chemin(nom))

    r = _rotate(c, nom, 0)
    assert r.status_code == 400, r.data
    assert os.path.getsize(_chemin(nom)) == avant, "rien à faire = ne pas ré-encoder"


def test_rotate_rejects_gif(client):
    """Un GIF peut être animé : il n'a jamais de dérivée, et le ré-encoder détruirait
    l'animation. On refuse plutôt que de mutiler."""
    import app
    c = client
    nom = "%s.gif" % ("ab12" * 8)
    os.makedirs(app.UPLOAD_DIR, exist_ok=True)
    with open(_chemin(nom), "wb") as f:
        f.write(b"GIF89a" + b"\x00" * 32)
    avant = os.path.getsize(_chemin(nom))

    r = _rotate(c, nom, 90)
    assert r.status_code in (400, 415), r.data
    assert os.path.getsize(_chemin(nom)) == avant


def test_rotate_bad_name_400(client):
    """`SAFE_IMG_NAME` est la barrière entre un nom d'URL et le disque, et elle doit refuser
    AVANT d'aller voir sur le système de fichiers.

    ⚠ Ce test exigeait au départ « 400 ou 404 » — et une mutation a montré que ça ne prouvait
    rien : en retirant la garde, les noms mal formés retombaient simplement sur « fichier
    introuvable » (404) et le test restait vert. On exige donc **400** précisément : c'est la
    différence entre « ce nom est refusé » et « ce nom a été cherché sur le disque »."""
    for mauvais in ("pas-un-uuid.jpg", "abc.exe", "%s.jpg" % ("zz" * 16),
                    "%s.JPG" % ("ab12" * 8), "%s.jpg.exe" % ("ab12" * 8)):
        r = client.post("/api/images/%s/rotate" % mauvais, json={"angle": 90})
        assert r.status_code == 400, (mauvais, r.status_code, r.data)


def test_rotate_cannot_escape_the_upload_dir(client):
    """La conséquence concrète de la garde : aucun nom ne doit désigner un fichier HORS du
    dossier d'uploads. On pose un fichier témoin à côté et on vérifie qu'aucune tentative de
    traversée ne le touche."""
    import app
    os.makedirs(app.UPLOAD_DIR, exist_ok=True)
    voisin = os.path.join(os.path.dirname(app.UPLOAD_DIR), "temoin.jpg")
    _jpeg((800, 400)).seek(0)
    with open(voisin, "wb") as f:
        f.write(_jpeg((800, 400)).getvalue())
    avant = open(voisin, "rb").read()

    for tentative in ("../temoin.jpg", "..%2Ftemoin.jpg", "....//temoin.jpg",
                      "%2e%2e%2ftemoin.jpg"):
        r = client.post("/api/images/%s/rotate" % tentative, json={"angle": 90})
        assert r.status_code in (400, 404, 405), (tentative, r.status_code)

    assert open(voisin, "rb").read() == avant, "un fichier hors du dossier d'uploads a été modifié"


def test_rotate_unknown_image_404(client):
    """Nom valide mais aucun fichier : 404, pas un 500."""
    r = _rotate(client, "%s.jpg" % ("cd34" * 8), 90)
    assert r.status_code == 404, r.data


def test_no_guest_rotate_route(client):
    """Invariant 5, prouvé structurellement : pivoter est owner-only en v1. Aucune route sous
    `/share/*` ne doit l'offrir — un invité ne modifie pas le fichier original du propriétaire."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid, _jpeg((800, 400)))
    sh = c.post("/api/shares", json={"kind": "memo", "target_id": mid}).get_json()

    for chemin in ("/share/%s/images/%s/rotate" % (sh["token"], nom),
                   "/share/%s/image/%s/rotate" % (sh["token"], nom),
                   "/share/%s/memo/%d/images/%s/rotate" % (sh["token"], mid, nom)):
        r = c.post(chemin, json={"angle": 90})
        assert r.status_code == 404, (chemin, r.status_code)

    with Image.open(_chemin(nom)) as im:
        assert im.size == (800, 400), "aucun chemin invité n'a pu toucher l'original"
