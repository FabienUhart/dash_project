"""[MAP-NO-AUTOPAN] — la carte ne bouge plus toute seule au survol d'un point.

Constat Fabien du 30 sept. 2026 (carte « Voyage Japon », 59 points) : « je regarde mes points et
la carte change toute seule pour aller sur ce point ». Cause : la bulle s'ouvre AU SURVOL
(`wireMarkerPopup`, 150 ms) et `bindPopup` sans option hérite de l'`autoPan: true` de Leaflet →
un point près d'un bord fait glisser la carte pour que sa bulle tienne dans le cadre.

Ce que ces parcours PROTÈGENT :

- survol d'un marqueur mémo au bord → bulle ouverte, centre et zoom INCHANGÉS ;
- clic sur la ligne de liste → recadrage volontaire conservé (`setView(ll, 16)`) ;
- clic sur une photo 📷 au bord (calque Photos) → la bulle photo s'ouvre, centre inchangé
  (les photos n'ont pas de bulle au survol : c'est au clic, sous la visionneuse, que la carte
  glissait).

`activeMap` est un `let` de premier niveau de la page : `page.evaluate` le lit directement.
Le calque photo est servi par `page.route` (une vraie photo exigerait un JPEG à EXIF GPS géocodé
à l'upload — hors sujet ici : seul le comportement de la bulle côté front est en cause).
"""
import json

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1600, "height": 1000}
DOSSIER = "Voyage NAP"
# 6 points ; le dernier est le coin NORD-EST : après fitBounds il tombe au bord haut-droit,
# sa bulle (qui s'ouvre au-dessus du point) ne peut pas tenir dans le cadre.
POINTS = [
    ("NAP 1", 35.00, 135.00),
    ("NAP 2", 35.05, 135.10),
    ("NAP 3", 35.10, 135.05),
    ("NAP 4", 35.15, 135.20),
    ("NAP 5", 35.20, 135.15),
    ("NAP bord", 35.40, 135.40),
]
BORD = POINTS[-1]
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")

_MEMOS = []
_PROJETS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    _MEMOS.clear(); _PROJETS.clear()
    yield
    import requests
    for mid in _MEMOS:
        try:
            requests.delete(live_server + "/api/memos/%d" % mid, timeout=5)
        except Exception:
            pass
    for pid in reversed(_PROJETS):
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    _MEMOS.clear(); _PROJETS.clear()


def _semer(live_server):
    import requests
    s = requests.Session()
    r = s.post(live_server + "/api/projects", json={"name": DOSSIER}, timeout=5)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    for titre, lat, lng in POINTS:
        r = s.post(live_server + "/api/memos", json={
            "title": titre, "content": "point", "project_id": pid,
            "location": {"lat": lat, "lng": lng, "label": titre},
        }, timeout=5)
        assert r.status_code in (200, 201), r.text
        _MEMOS.append(r.json()["id"])
    return pid


def _ouvrir_carte(page, live_server):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", state="attached", timeout=10_000)
    page.wait_for_load_state("networkidle")
    page.evaluate(
        "l => [...document.querySelectorAll('#sidebar .cat-item')]"
        "      .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === l).click()",
        DOSSIER,
    )
    page.wait_for_timeout(400)
    page.evaluate(
        "() => [...document.querySelectorAll('#memo-board button')]"
        "        .find(b => /Carte/.test(b.textContent) || /Carte/.test(b.getAttribute('aria-label') || '')).click()"
    )
    page.wait_for_selector("#map-dialog[open] #map-el .leaflet-map-pane", state="attached", timeout=5_000)
    page.wait_for_timeout(900)   # fitBounds différé
    # fitBounds arrondit le zoom : le point « bord » peut finir loin du cadre. On le pousse à
    # 25 px du coin haut-droit (pan instantané) — sa bulle, ouverte au-dessus, ne tient plus.
    page.evaluate("""([lat, lng]) => {
      const p = activeMap.latLngToContainerPoint([lat, lng]);
      const s = activeMap.getSize();
      activeMap.panBy([p.x - (s.x - 25), p.y - 25], {animate: false});
    }""", [BORD[1], BORD[2]])
    page.wait_for_timeout(200)


def _vue(page):
    return page.evaluate("() => { const c = activeMap.getCenter(); return {lat: c.lat, lng: c.lng, z: activeMap.getZoom()}; }")


def _survoler(page, lat, lng):
    """Amène la VRAIE souris sur le point (coordonnées écran calculées par Leaflet)."""
    xy = page.evaluate("""([lat, lng]) => {
      const p = activeMap.latLngToContainerPoint([lat, lng]);
      const r = document.getElementById('map-el').getBoundingClientRect();
      return {x: r.left + p.x, y: r.top + p.y, dansCadre: p.x > 0 && p.y > 0 && p.x < r.width && p.y < r.height};
    }""", [lat, lng])
    assert xy["dansCadre"], xy
    page.mouse.move(xy["x"] - 60, xy["y"] + 60)
    page.mouse.move(xy["x"], xy["y"], steps=5)
    page.wait_for_timeout(600)   # 150 ms d'anti-flicker + animation de pan éventuelle (250 ms)


def _meme_vue(a, b):
    return abs(a["lat"] - b["lat"]) < 1e-6 and abs(a["lng"] - b["lng"]) < 1e-6 and a["z"] == b["z"]


def test_survol_point_au_bord_ne_deplace_pas_la_carte(page, live_server, console_errors):
    _semer(live_server)
    _ouvrir_carte(page, live_server)
    avant = _vue(page)
    _survoler(page, BORD[1], BORD[2])
    assert page.locator("#map-el .leaflet-popup").count() == 1, "la bulle ne s'est pas ouverte au survol"
    assert "NAP bord" in page.locator("#map-el .leaflet-popup").inner_text()
    apres = _vue(page)
    assert _meme_vue(avant, apres), "la carte a bougé au survol : %s → %s" % (avant, apres)
    assert console_errors == []


def test_clic_ligne_liste_recadre_sur_le_point(page, live_server, console_errors):
    _semer(live_server)
    _ouvrir_carte(page, live_server)
    page.locator("#map-list button", has_text="NAP bord").first.click()
    page.wait_for_timeout(600)
    v = _vue(page)
    assert v["z"] == 16, v
    assert abs(v["lat"] - BORD[1]) < 1e-4 and abs(v["lng"] - BORD[2]) < 1e-4, v
    assert page.locator("#map-el .leaflet-popup").count() == 1
    assert console_errors == []


def test_clic_photo_au_bord_ne_deplace_pas_la_carte(page, live_server, console_errors):
    _semer(live_server)
    photo = [{
        "filename": "nap-bord.png", "memo_id": _MEMOS[-1], "project_id": _PROJETS[0],
        "lat": BORD[1], "lng": BORD[2], "label": "Photo du bord", "taken_at": "",
        "has_gps": True, "groups": [], "title": "NAP bord",
    }]
    page.route("**/api/projects/*/photos", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(photo)))
    # La visionneuse s'ouvre au clic : on lui sert une image et un EXIF vides (sinon 404 console).
    page.route("**/uploads/nap-bord.png*", lambda route: route.fulfill(
        status=200, content_type="image/png", body=_PNG_1PX))
    page.route("**/api/image-exif/**", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    _ouvrir_carte(page, live_server)
    page.locator("#map-toolbar button", has_text="Photos").first.click()
    page.wait_for_selector("#map-el .photo-pin", state="attached", timeout=5_000)
    page.wait_for_timeout(300)
    avant = _vue(page)
    # Clic par dispatch : la visionneuse (top-layer) recouvre la carte dès le mousedown suivant.
    page.evaluate("() => document.querySelector('#map-el .photo-pin').click()")
    page.wait_for_timeout(600)
    assert page.locator("#map-el .leaflet-popup", has_text="Photo du bord").count() == 1, \
        "la bulle photo ne s'est pas ouverte au clic"
    apres = _vue(page)
    assert _meme_vue(avant, apres), "la carte a bougé au clic photo : %s → %s" % (avant, apres)
    assert console_errors == []
