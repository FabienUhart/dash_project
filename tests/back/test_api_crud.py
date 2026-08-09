"""
CRUD et validations d'entrée — le comportement quotidien des routes owner.

Deux familles ici : ce que l'app doit accepter (créer, modifier, réordonner) et surtout ce
qu'elle doit REFUSER. Les tests de refus valent plus cher que les autres : une validation qui
saute ne se voit pas à l'œil, elle se voit le jour où quelqu'un en profite.
"""
import io

import pytest

pytestmark = pytest.mark.unit


# --- Liens et catégories --------------------------------------------------

def test_create_link_and_list_it(client):
    r = client.post("/api/links", json={"name": "Zimaboard", "url": "http://192.168.1.50:8099"})
    assert r.status_code in (200, 201), r.data
    names = [l.get("name") for l in client.get("/api/links").get_json()]
    assert "Zimaboard" in names


def test_create_link_requires_a_name(client):
    r = client.post("/api/links", json={"url": "http://exemple.local"})
    assert r.status_code == 400, "Un lien sans nom a été accepté."


def test_create_category_and_list_it(client):
    r = client.post("/api/categories", json={"name": "Infra"})
    assert r.status_code in (200, 201), r.data
    names = [c.get("name") for c in client.get("/api/categories").get_json()]
    assert "Infra" in names


# --- Mémos : champs et validations ---------------------------------------

def test_memo_accepts_title_without_content(client):
    """« Titre OU contenu » : un mémo peut n'avoir qu'un titre (invariant 1, v14)."""
    r = client.post("/api/memos", json={"title": "Juste un titre"})
    assert r.status_code in (200, 201), r.data
    assert r.get_json().get("title") == "Juste un titre"


def test_memo_rejects_empty_payload(client):
    assert client.post("/api/memos", json={}).status_code == 400


def test_memo_subtasks_roundtrip(client):
    m = client.post("/api/memos", json={"content": "Avec étapes"}).get_json()
    subs = [{"content": "étape 1", "done": False}, {"content": "étape 2", "done": True}]
    r = client.put("/api/memos/%d" % m["id"], json={"subtasks": subs})
    assert r.status_code in (200, 204), r.data
    got = [x for x in client.get("/api/memos").get_json() if x["id"] == m["id"]][0]
    assert [s["content"] for s in got["subtasks"]] == ["étape 1", "étape 2"]
    assert [bool(s["done"]) for s in got["subtasks"]] == [False, True]


def test_memo_due_time_needs_a_date(client):
    """Invariant 1 (v18) : une heure sans date n'existe pas.

    ⚠ On exige explicitement le 200 : un test de refus qui n'inspecte que la valeur finale
    passe aussi quand la requête a échoué (405, 404…) et ne prouve alors plus rien. Piège
    rencontré en écrivant ce fichier — la route est en PUT, pas en PATCH."""
    m = client.post("/api/memos", json={"content": "Sans date"}).get_json()
    r = client.put("/api/memos/%d" % m["id"], json={"due_time": "18:30"})
    assert r.status_code == 200, r.data
    got = [x for x in client.get("/api/memos").get_json() if x["id"] == m["id"]][0]
    assert got.get("due_time", "") == "", "Une heure a été posée sans date de référence."


def test_memo_due_end_must_not_precede_due_date(client):
    """Invariant 1 (v24) : la fin de plage ne peut pas être avant le début."""
    m = client.post("/api/memos", json={"content": "Séjour"}).get_json()
    ok = client.put("/api/memos/%d" % m["id"], json={"due_date": "2026-11-06"})
    assert ok.status_code == 200, ok.data
    r = client.put("/api/memos/%d" % m["id"], json={"due_end": "2026-11-03"})
    assert r.status_code == 400, "Une fin de plage antérieure au début a été acceptée."
    got = [x for x in client.get("/api/memos").get_json() if x["id"] == m["id"]][0]
    assert got.get("due_end", "") == ""


def test_memo_marker_color_rejects_non_hex(client):
    """`_clean_hex_color` : `#rrggbb` strict, jamais de HTML qui traîne dans une couleur."""
    m = client.post("/api/memos", json={"content": "Couleur"}).get_json()
    r = client.put("/api/memos/%d" % m["id"], json={"marker_color": "<script>alert(1)</script>"})
    assert r.status_code == 200, r.data          # accepté, mais NETTOYÉ — voir ci-dessous
    got = [x for x in client.get("/api/memos").get_json() if x["id"] == m["id"]][0]
    assert got.get("marker_color", "") == "", "Une couleur non hexadécimale a été stockée."


# --- Upload d'image : la signature binaire fait foi (invariant 5) ---------

def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_image_upload_accepts_a_real_png(client):
    m = client.post("/api/memos", json={"content": "Avec photo"}).get_json()
    r = client.post("/api/memos/%d/images" % m["id"],
                    data={"image": (io.BytesIO(_png_bytes()), "photo.png")},
                    content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.data


def test_image_upload_refuses_a_fake_png(client):
    """Un fichier nommé .png mais qui n'en est pas doit être refusé : c'est la SIGNATURE
    binaire qui décide, pas l'extension — sinon on sert du HTML/JS depuis /uploads."""
    m = client.post("/api/memos", json={"content": "Faux fichier"}).get_json()
    payload = b"<html><script>alert('xss')</script></html>"
    r = client.post("/api/memos/%d/images" % m["id"],
                    data={"image": (io.BytesIO(payload), "piege.png")},
                    content_type="multipart/form-data")
    assert r.status_code >= 400, (
        "Un faux PNG (HTML déguisé) a été accepté : la vérification de signature a sauté."
    )
