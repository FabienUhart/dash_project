"""[FRISE-STEP-NOGPS] — un chip de frise sans position bascule le jour et invite à en ajouter une.

Constat Fabien du 30 sept. 2026 (carte Voyage Japon, prod) : sur Jour 5, cliquer le chip
« nol kyoto sanjo » (6 nov., mémo sans position dans un dossier sans position) ne fait rien —
`openPassageOnPorter` retournait AVANT la bascule de jour quand le porteur n'a pas de `ll`.

Ce que ces parcours PROTÈGENT (brief `docs/briefs/FRISE-STEP-NOGPS.md` § 4) :

1. clic chip sans position → jour basculé, chip sélectionné, bulle « Pas de position » ancrée
   sur le chip, carte immobile, glyphe « sans position » sur le chip, section « Sans position · 1 » ;
2. adresse + Entrée → `PUT` avec `location`, point ajouté, carte centrée, glyphe et section
   disparus, toast ;
3. géocodage vide → « Adresse introuvable », aucun PUT ;
4. chip géolocalisé d'un autre jour → bascule + `setView` (non-régression) ;
5. re-clic sur le chip sélectionné → bulle fermée, désélection, jour inchangé ;
6. share : éditeur = même parcours que 2 par les routes `/share/*` ; lecteur = bulle sans champ,
   aucun PUT ;
7. zéro erreur console, à chaque test.

Le géocodage est MOCKÉ (`page.route`) : Nominatim n'est jamais appelé. Le décor se supprime en
sortie (base e2e partagée).
"""
import json
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1600, "height": 1000}
J1, J2 = "2026-11-03", "2026-11-04"
KYOTO = {"lat": 35.0094, "lng": 135.7712, "label": "Kyoto Sanjo"}
_n = [0]
_CREES = []   # urls de suppression, dossiers en DERNIER


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _semer(page, live_server):
    """Voyage 2 jours : J1 « NOGPS A » géolocalisé ; J2 « NOGPS B » SANS position dans un
    sous-dossier SANS position (le cas du bug) + « NOGPS C » J2 géolocalisé."""
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)

    def dossier(nom, parent=None):
        p = page.request.post(live_server + "/api/projects", data={"name": nom}).json()
        _CREES.insert(0, "/api/projects/%d" % p["id"])
        if parent:
            r = page.request.put(live_server + "/api/projects/%d" % p["id"], data={"parent_id": parent})
            assert r.ok, r.text()
        return p

    def memo(titre, pid, **extra):
        r = page.request.post(live_server + "/api/memos", data={"title": titre, "content": "étape", "project_id": pid, **extra})
        assert r.ok, r.text()
        _CREES.append("/api/memos/%d" % r.json()["id"])
        return r.json()

    racine = dossier("NOGPS voyage %s" % k)
    sous = dossier("NOGPS sous %s" % k, racine["id"])
    a = memo("NOGPS A", racine["id"], due_date=J1, location={"lat": 35.0, "lng": 135.0, "label": "A"})
    b = memo("NOGPS B", sous["id"], due_date=J2)
    c = memo("NOGPS C", racine["id"], due_date=J2, location={"lat": 35.1, "lng": 135.1, "label": "C"})
    return {"k": k, "racine": racine, "sous": sous, "a": a, "b": b, "c": c}


def _mock_geocode(page, motif, results):
    page.route(motif, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"results": results})))


def _ouvrir_carte_owner(page, live_server, d):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", state="attached", timeout=10_000)
    page.wait_for_load_state("networkidle")
    page.evaluate(
        "l => [...document.querySelectorAll('#sidebar .cat-item')]"
        "      .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === l).click()",
        d["racine"]["name"],
    )
    page.wait_for_timeout(400)
    _cliquer_carte(page, "#memo-board button")


def _cliquer_carte(page, scope):
    page.evaluate(
        "s => [...document.querySelectorAll(s)]"
        "        .find(b => /Carte/.test(b.textContent) || /Carte/.test(b.getAttribute('aria-label') || '')).click()",
        scope,
    )
    page.wait_for_selector("#map-dialog[open] .map-days-band [data-day-iso]", state="attached", timeout=5_000)
    page.wait_for_timeout(900)


def _ouvrir_carte_share(page, live_server, d, role):
    _n[0] += 1
    email = "nogps%d@ex.com" % _n[0]
    sh = page.request.post(live_server + "/api/shares",
                           data={"kind": "project", "target_id": d["racine"]["id"], "role": role}).json()
    reg = page.request.post(live_server + "/share/%s/register" % sh["token"],
                            data={"name": "Gaspard", "email": email, "pin": sh["pin"]})
    assert reg.ok, reg.text()
    page.set_viewport_size(BUREAU)
    page.add_init_script("localStorage.setItem('dashguest:%s', '%s')" % (sh["token"], reg.json()["guest_token"]))
    page.goto(live_server + "/share/" + sh["token"], wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    _cliquer_carte(page, "button")
    return sh


def _jours(page):
    return page.evaluate("() => [...document.querySelectorAll('#map-dialog .map-days-band [data-day-iso]')].map(b => b.textContent.trim())")


def _jour_actif(page):
    """Index (1-based) du bouton « Jour n » coché, ou None."""
    for i, t in enumerate(_jours(page)):
        if t.startswith("✓"):
            return i + 1
    return None


def _vue(page):
    return page.evaluate("() => { const c = activeMap.getCenter(); return {lat: c.lat, lng: c.lng, z: activeMap.getZoom()}; }")


def _nb_points_titre(page):
    import re
    t = page.locator("#map-title").inner_text()
    m = re.search(r"\((\d+) points?\)", t)
    assert m, t
    return int(m.group(1))


def _chip(page, mid):
    return page.locator('#map-timeline [data-memo-id="%d"]' % mid)


def _memo(page, live_server, mid):
    """`/api/memos` n'a pas de GET unitaire : on lit la liste."""
    return next(m for m in page.request.get(live_server + "/api/memos").json() if m["id"] == mid)


def _erreurs(console_errors):
    return [e for e in console_errors if "status of 404" not in e]


# ------------------------------------------------------------------ owner


def test_chip_sans_position_bascule_le_jour_et_invite(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir_carte_owner(page, live_server, d)
    b = d["b"]["id"]
    # niveau 1 : glyphe « sans position » sur le chip, section « Sans position · 1 » à droite
    assert _chip(page, b).locator(".frise-nogps").count() == 1, "glyphe absent"
    assert _chip(page, d["c"]["id"]).locator(".frise-nogps").count() == 0
    sec = page.locator("#map-list [data-nogps-section]")
    assert sec.count() == 1 and "Sans position · 1" in sec.inner_text(), sec.inner_text() if sec.count() else "section absente"
    assert page.locator('#map-list [data-nogps-row="%d"]' % b).count() == 1
    # filtre Jour 1, puis clic sur le chip J2 sans position
    page.locator("#map-dialog .map-days-band [data-day-iso]").first.click()
    page.wait_for_timeout(300)
    assert _jour_actif(page) == 1
    avant = _vue(page)
    _chip(page, b).click()
    page.wait_for_timeout(500)
    assert _jour_actif(page) == 2, _jours(page)
    assert _chip(page, b).get_attribute("data-step-sel") == "1", "chip non sélectionné"
    bulle = page.locator("#frise-pos-bubble")
    assert bulle.count() == 1 and bulle.is_visible(), "bulle absente"
    assert "Pas de position" in bulle.inner_text()
    assert bulle.locator("#frise-pos-input").count() == 1
    # ancrée sur le chip (pas sur la carte) : son bord haut touche le bas du chip, à ±40 px
    r = page.evaluate("""id => { const c = document.querySelector('#map-timeline [data-memo-id="' + id + '"]').getBoundingClientRect();
      const b = document.getElementById('frise-pos-bubble').getBoundingClientRect();
      return {dy: b.top - c.bottom, dx: b.left - c.left, inMap: !!document.querySelector('#map-el #frise-pos-bubble')}; }""", b)
    assert -40 <= r["dy"] <= 40 and abs(r["dx"]) < 200 and not r["inMap"], r
    # La vue est celle du bouton « Jour 2 » (recadrage sur les points DU JOUR, `applyDay` inchangé —
    # ici C, seul point de J2) : ni flyTo vers un porteur, ni autoPan. Écart au brief assumé : « centre
    # inchangé » vaut quand le jour est déjà actif (voir test_reclic_…), pas quand on change de jour.
    apres = _vue(page)
    assert abs(apres["lat"] - 35.1) < 1e-3 and abs(apres["lng"] - 135.1) < 1e-3 and apres["z"] == 15, (avant, apres)
    assert _erreurs(console_errors) == []


def test_adresse_saisie_pose_la_position(page, live_server, console_errors):
    d = _semer(page, live_server)
    _mock_geocode(page, "**/api/geocode*", [KYOTO])
    _ouvrir_carte_owner(page, live_server, d)
    b = d["b"]["id"]
    n_avant = _nb_points_titre(page)
    _chip(page, b).click()
    page.wait_for_timeout(400)
    page.locator("#frise-pos-input").fill("Kyoto Sanjo")
    page.locator("#frise-pos-input").press("Enter")
    page.wait_for_timeout(900)
    m = _memo(page, live_server, b)
    assert m["location"] and abs(m["location"]["lat"] - KYOTO["lat"]) < 1e-6 and m["location"]["label"] == "Kyoto Sanjo", m.get("location")
    # Passe Cowork (a) : le titre « 🗺 … (n points) » suit l'ajout du point.
    assert _nb_points_titre(page) == n_avant + 1, page.locator("#map-title").inner_text()
    assert _chip(page, b).locator(".frise-nogps").count() == 0, "glyphe toujours là"
    assert page.locator("#map-list [data-nogps-section]").count() == 0, "section toujours là"
    assert page.locator("#frise-pos-bubble").count() == 0, "bulle toujours ouverte"
    v = _vue(page)
    assert abs(v["lat"] - KYOTO["lat"]) < 1e-3 and abs(v["lng"] - KYOTO["lng"]) < 1e-3, v
    assert page.locator("#map-list [data-map-row='memo:%d']" % b).count() == 1, "point absent de la liste"
    assert page.locator("#frise-pos-toast").count() == 1 and "Position ajoutée" in page.locator("#frise-pos-toast").inner_text()
    assert _erreurs(console_errors) == []


def test_adresse_introuvable_aucun_put(page, live_server, console_errors):
    d = _semer(page, live_server)
    _mock_geocode(page, "**/api/geocode*", [])
    puts = []
    page.on("request", lambda r: puts.append(r.url) if r.method == "PUT" and "/api/memos/" in r.url else None)
    _ouvrir_carte_owner(page, live_server, d)
    b = d["b"]["id"]
    _chip(page, b).click()
    page.wait_for_timeout(400)
    page.locator("#frise-pos-input").fill("nulle part xyz")
    page.locator("#frise-pos-input").press("Enter")
    page.wait_for_timeout(600)
    assert "Adresse introuvable" in page.locator("#frise-pos-bubble").inner_text()
    assert puts == [], puts
    assert _memo(page, live_server, b)["location"] in (None, "", {})
    assert _erreurs(console_errors) == []


def test_chip_geolocalise_autre_jour_bascule_et_centre(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir_carte_owner(page, live_server, d)
    page.locator("#map-dialog .map-days-band [data-day-iso]").first.click()
    page.wait_for_timeout(300)
    assert _jour_actif(page) == 1
    _chip(page, d["c"]["id"]).click()
    page.wait_for_timeout(600)
    assert _jour_actif(page) == 2
    v = _vue(page)
    assert abs(v["lat"] - 35.1) < 1e-3 and abs(v["lng"] - 135.1) < 1e-3 and v["z"] == 15, v
    assert page.locator("#frise-pos-bubble").count() == 0
    assert _erreurs(console_errors) == []


def test_reclic_ferme_la_bulle_et_deselectionne(page, live_server, console_errors):
    d = _semer(page, live_server)
    _ouvrir_carte_owner(page, live_server, d)
    b = d["b"]["id"]
    page.locator("#map-dialog .map-days-band [data-day-iso]").nth(1).click()
    page.wait_for_timeout(300)
    avant = _vue(page)
    _chip(page, b).click()
    page.wait_for_timeout(400)
    assert page.locator("#frise-pos-bubble").count() == 1
    apres = _vue(page)   # jour déjà actif : ouvrir la bulle ne déplace pas la carte
    assert abs(avant["lat"] - apres["lat"]) < 1e-6 and abs(avant["lng"] - apres["lng"]) < 1e-6 and avant["z"] == apres["z"], (avant, apres)
    _chip(page, b).click()
    page.wait_for_timeout(300)
    assert page.locator("#frise-pos-bubble").count() == 0
    assert _chip(page, b).get_attribute("data-step-sel") is None
    assert _jour_actif(page) == 2
    assert _erreurs(console_errors) == []


# ------------------------------------------------------------------ share


def test_share_editeur_pose_la_position(page, live_server, console_errors):
    d = _semer(page, live_server)
    _mock_geocode(page, "**/share/*/geocode*", [KYOTO])
    _ouvrir_carte_share(page, live_server, d, "editor")
    b = d["b"]["id"]
    assert _chip(page, b).locator(".frise-nogps").count() == 1
    _chip(page, b).click()
    page.wait_for_timeout(400)
    page.locator("#frise-pos-input").fill("Kyoto Sanjo")
    page.locator("#frise-pos-input").press("Enter")
    page.wait_for_timeout(900)
    m = _memo(page, live_server, b)
    assert m["location"] and abs(m["location"]["lat"] - KYOTO["lat"]) < 1e-6, m.get("location")
    assert _chip(page, b).locator(".frise-nogps").count() == 0
    assert page.locator("#frise-pos-bubble").count() == 0
    assert _erreurs(console_errors) == []


def test_share_lecteur_bulle_sans_champ(page, live_server, console_errors):
    d = _semer(page, live_server)
    puts = []
    page.on("request", lambda r: puts.append(r.url) if r.method == "PUT" else None)
    _ouvrir_carte_share(page, live_server, d, "viewer")
    b = d["b"]["id"]
    _chip(page, b).click()
    page.wait_for_timeout(400)
    bulle = page.locator("#frise-pos-bubble")
    assert bulle.count() == 1 and "Pas de position" in bulle.inner_text()
    assert bulle.locator("#frise-pos-input").count() == 0, "champ affiché au lecteur"
    assert bulle.locator("button").count() == 0, "bouton affiché au lecteur"
    assert puts == []
    assert _memo(page, live_server, b)["location"] in (None, "", {})
    assert _erreurs(console_errors) == []
