"""[PHOTO-ROTATE-POLISH] Les images doivent être REVALIDÉES, pas mises en cache aveuglément.

Le nom d'un fichier ne change pas quand on pivote la photo : seul son contenu change. Servi
avec un cache fort de 24 h sans revalidation, le navigateur resservait donc l'ANCIENNE image
après une rotation. Le front compensait avec un `?v=<secondes>` — insuffisant par construction :
deux sauvegardes dans la même seconde produisent la même URL. L'utilisateur croyait que rien
n'avait pris, recliquait, et **chaque clic re-pivotait pour de vrai** (90 → 180 → 270).

La revalidation par ETag corrige la visionneuse, la vignette et la réouverture d'un seul geste :
tant que l'image ne bouge pas, le serveur répond 304 (bon marché) ; dès qu'elle bouge, l'ETag
change et le navigateur récupère la bonne.
"""
import io
import os

import pytest

pytestmark = pytest.mark.invariant

pytest.importorskip("PIL", reason="Pillow requis pour fabriquer une image de test")
from PIL import Image  # noqa: E402


# ───────────────────────────────────────── montage ─────────────────────────────────────────

def _memo(c, contenu="Mémo à photos"):
    r = c.post("/api/memos", json={"content": contenu})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _jpeg(taille=(900, 500)):
    buf = io.BytesIO()
    Image.new("RGB", taille, (120, 80, 40)).save(buf, "JPEG")
    buf.seek(0)
    return buf


def _upload(c, memo_id, nom="photo.jpg"):
    r = c.post("/api/memos/%d/images" % memo_id,
               data={"image": (_jpeg(), nom)}, content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    return r.get_json()["images"][-1]


def _revalide(cache_control):
    """La règle du lot : le navigateur ne doit JAMAIS servir l'image depuis son cache sans
    demander au serveur. `no-cache` (revalidation obligatoire) ou un `max-age` très court
    conviennent ; un `max-age=86400` non."""
    cc = (cache_control or "").lower()
    if "no-cache" in cc or "no-store" in cc or "must-revalidate" in cc:
        return True
    for part in cc.split(","):
        part = part.strip()
        if part.startswith("max-age="):
            try:
                return int(part.split("=", 1)[1]) <= 60
            except ValueError:
                return False
    return False


# ══════════════════════ la revalidation elle-même ══════════════════════

@pytest.mark.parametrize("url_suffixe", ["", "?size=t", "?size=s"])
def test_images_are_served_with_revalidation(client, url_suffixe):
    """Original ET dérivées : un ETag, et un `Cache-Control` qui oblige à le vérifier."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid)

    r = c.get("/uploads/%s%s" % (nom, url_suffixe))
    assert r.status_code == 200, r.data
    assert r.headers.get("ETag"), "sans ETag, aucune revalidation possible"
    assert _revalide(r.headers.get("Cache-Control")), (
        "Cache-Control=%r laisse le navigateur resservir l'ancienne image sans rien demander"
        % r.headers.get("Cache-Control")
    )


def test_unchanged_image_answers_304(client):
    """Le contrepoids : revalider ne doit pas coûter le transfert. Tant que l'image ne change
    pas, la requête conditionnelle répond 304 sans corps."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid)

    premier = c.get("/uploads/%s?size=t" % nom)
    etag = premier.headers.get("ETag")
    assert etag

    second = c.get("/uploads/%s?size=t" % nom, headers={"If-None-Match": etag})
    assert second.status_code == 304, "une image inchangée doit répondre 304, pas la renvoyer"
    assert not second.data


def test_etag_changes_after_a_rotation(client):
    """LE test du lot : après rotation, l'ETag doit changer — c'est ce qui fait que le
    navigateur va chercher la nouvelle image au lieu de resservir l'ancienne, et donc ce qui
    évite les clics répétés qui sur-pivotaient la photo."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid)

    avant = c.get("/uploads/%s?size=t" % nom)
    etag_avant = avant.headers.get("ETag")
    assert etag_avant

    assert c.post("/api/images/%s/rotate" % nom, json={"angle": 90}).status_code == 200

    apres = c.get("/uploads/%s?size=t" % nom)
    assert apres.headers.get("ETag") != etag_avant, (
        "même ETag après rotation : le navigateur resservirait l'image d'avant"
    )
    # …et l'ancien ETag ne vaut plus rien : la requête conditionnelle rapporte la NOUVELLE image.
    conditionnelle = c.get("/uploads/%s?size=t" % nom, headers={"If-None-Match": etag_avant})
    assert conditionnelle.status_code == 200, "l'ancien ETag ne doit plus donner un 304"


def test_original_etag_changes_after_a_rotation(client):
    """Même exigence sur l'ORIGINAL : c'est lui que sert le ⬇ et les images sous 400 px, pour
    lesquelles aucune dérivée n'est générée."""
    c = client
    mid = _memo(c)
    nom = _upload(c, mid)

    etag_avant = c.get("/uploads/%s" % nom).headers.get("ETag")
    assert etag_avant
    assert c.post("/api/images/%s/rotate" % nom, json={"angle": 180}).status_code == 200
    assert c.get("/uploads/%s" % nom).headers.get("ETag") != etag_avant


def test_revalidation_does_not_break_the_derivative_fallback(client):
    """Garde-fou de non-régression : une image plus petite que la cible n'a pas de dérivée —
    la route doit toujours servir l'original (jamais de 404), en-têtes compris."""
    c = client
    mid = _memo(c)
    r = c.post("/api/memos/%d/images" % mid,
               data={"image": (_jpeg((120, 80)), "petite.jpg")},
               content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data
    nom = r.get_json()["images"][-1]

    rep = c.get("/uploads/%s?size=t" % nom)
    assert rep.status_code == 200, "pas de dérivée ≠ pas d'image"
    assert rep.headers.get("ETag")
    assert _revalide(rep.headers.get("Cache-Control"))
