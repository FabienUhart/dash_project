"""[MAP-DIALOG-WIDE] — la pop-in Carte/Frise d'un voyage, lisible en desktop comme en mobile.

Mesures Cowork du 28 sept. 2026 (prod, « Voyage Japon », 48 points, 19 jours) :

- DESKTOP 2160 px : `#map-dialog` 920 px fixes ; la bande des jours `.map-days-band` (22 px,
  `nowrap`, `overflow:auto`) voyait sa barre de défilement recouvrir les boutons de 21 px, et
  « Jour 19 » était HORS du dialog — `elementFromPoint` rendait le dialog, pas le bouton ;
- MOBILE 421 px : le dialog s'ouvrait DÉJÀ défilé de 218 px — la barre Voix/Photos/Frise et les
  chips sous-projets étaient cachées au-dessus, 331 px de chips avant une carte de 480 px.

Ce que ces parcours PROTÈGENT :

- desktop : dialog large (≥ 1500 px sur 1920), carte haute, liste latérale élargie ; **chaque**
  bouton « Jour N » est dans le dialog, fait ≥ 32 px et reçoit le clic (bande en `flex-wrap`) ;
- mobile : ouverture à `scrollTop 0`, barre d'outils visible, sous-projets et groupes repliés
  derrière « Filtres (n) » (qui les déplie), carte ~45vh ;
- invariant 8 : aucune de ces mises en page ne passe par GSAP sur le `<dialog>`.
"""
import datetime as _dt

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1920, "height": 1080}
MOBILE = {"width": 412, "height": 915}
N_JOURS = 20
# Desktop : 32 jours. À 1700 px de large, 20 boutons tiennent sur UNE ligne — la mutation « nowrap
# remis » y survivait. 32 jours forcent la 2e ligne, donc prouvent le retour à la ligne.
N_JOURS_BUREAU = 32
VOYAGE = "Voyage MDW"

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


def _semer(live_server, n_jours=N_JOURS):
    """Un voyage de 20 jours qui ENGLOBE aujourd'hui (le recentrage « jour courant » joue),
    deux sous-dossiers géolocalisés (→ barre sous-projets) et des groupes (→ barre groupes)."""
    import requests
    s = requests.Session()

    def projet(nom, parent=None):
        r = s.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
        assert r.status_code in (200, 201), r.text
        nid = r.json()["id"]
        _PROJETS.append(nid)
        if parent:   # le parent se pose par PUT, pas à la création
            r = s.put(live_server + "/api/projects/%d" % nid, json={"parent_id": parent}, timeout=5)
            assert r.status_code == 200, r.text
        return nid

    pid = projet(VOYAGE)
    r = s.put(live_server + "/api/projects/%d" % pid, json={"is_trip": 1}, timeout=5)
    assert r.status_code == 200, r.text
    subs = [projet("Étape MDW %d" % i, pid) for i in (1, 2, 3)]
    debut = _dt.date.today() - _dt.timedelta(days=8)
    for i in range(n_jours):
        jour = debut + _dt.timedelta(days=i)
        corps = {
            "title": "MDW %02d" % (i + 1), "content": "étape",
            "project_id": subs[i % 3] if i % 4 == 0 else pid,
            "due_date": jour.isoformat(),
            "location": {"lat": 35.0 + i * 0.05, "lng": 135.0 + i * 0.05, "label": "p%d" % i},
            "map_groups": [["Resto", "Temples", "Onsen"][i % 3]],
        }
        r = s.post(live_server + "/api/memos", json=corps, timeout=5)
        assert r.status_code in (200, 201), r.text
        _MEMOS.append(r.json()["id"])
    return pid


def _ouvrir_carte(page, live_server, vp):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    # En mobile la sidebar vit dans un panneau replié : on attend l'élément, pas sa visibilité.
    page.wait_for_selector(".cat-item", state="attached", timeout=10_000)
    page.wait_for_load_state("networkidle")
    page.evaluate(
        "l => [...document.querySelectorAll('#sidebar .cat-item')]"
        "      .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === l).click()",
        VOYAGE,
    )
    page.wait_for_timeout(400)
    page.evaluate(
        "() => [...document.querySelectorAll('#memo-board button')]"
        "        .find(b => /Carte/.test(b.textContent) || /Carte/.test(b.getAttribute('aria-label') || '')).click()"
    )
    page.wait_for_selector("#map-dialog[open] .map-days-band", timeout=5_000)
    # Laisse jouer les recentrages différés (jour courant, fitBounds).
    page.wait_for_timeout(900)


# --------------------------------------------------------------------------- desktop


def test_desktop_dialog_large_et_tous_les_jours_cliquables(page, live_server, console_errors):
    _semer(live_server, N_JOURS_BUREAU)
    _ouvrir_carte(page, live_server, BUREAU)
    m = page.evaluate("""() => {
      const d = document.getElementById('map-dialog').getBoundingClientRect();
      const mapH = document.getElementById('map-el').getBoundingClientRect().height;
      const listW = document.getElementById('map-list').getBoundingClientRect().width;
      const jours = [...document.querySelectorAll('#map-dialog .map-days-band [data-day-iso]')].map(b => {
        const r = b.getBoundingClientRect();
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        const hit = document.elementFromPoint(x, y);
        return { t: b.textContent.trim(), h: r.height,
                 dedans: r.left >= d.left && r.right <= d.right && r.top >= d.top && r.bottom <= d.bottom,
                 clic: !!hit && (hit === b || b.contains(hit)) };
      });
      return { w: d.width, mapH, listW, jours, vh: innerHeight };
    }""")
    assert m["w"] >= 1500, m["w"]
    assert m["mapH"] >= 0.6 * m["vh"] - 1, m["mapH"]
    assert m["listW"] >= 300, m["listW"]
    assert len(m["jours"]) == N_JOURS_BUREAU, [j["t"] for j in m["jours"]]
    hors = [j["t"] for j in m["jours"] if not j["dedans"]]
    assert hors == [], "hors du dialog : %s" % hors
    muets = [j["t"] for j in m["jours"] if not j["clic"]]
    assert muets == [], "non cliquables (recouverts) : %s" % muets
    petits = [(j["t"], j["h"]) for j in m["jours"] if j["h"] < 32]
    assert petits == [], "boutons < 32 px : %s" % petits
    # Le clic réel sur le dernier jour aboutit (le filtre Jour s'active).
    page.locator("#map-dialog .map-days-band [data-day-iso]").last.click()
    page.wait_for_timeout(200)
    assert page.locator("#map-dialog .map-days-band [data-day-iso]").last.text_content().startswith("✓")
    assert console_errors == []


# --------------------------------------------------------------------------- mobile


def test_mobile_ouverture_en_haut_et_filtres_replies(page, live_server, console_errors):
    """Mesure Cowork : « le dialog s'ouvre DÉJÀ défilé de 218 px ». Cause trouvée : un <dialog>
    GARDE son scrollTop entre close() et showModal() — on reproduit donc l'usage réel : défiler
    dans la carte, la fermer, la rouvrir."""
    _semer(live_server)
    _ouvrir_carte(page, live_server, MOBILE)
    page.evaluate("() => { const d = document.getElementById('map-dialog'); d.scrollTop = d.scrollHeight; }")
    assert page.evaluate("() => document.getElementById('map-dialog').scrollTop") > 100
    page.locator("#map-close-top").click()
    page.wait_for_timeout(200)
    page.evaluate(
        "() => [...document.querySelectorAll('#memo-board button')]"
        "        .find(b => /Carte/.test(b.textContent) || /Carte/.test(b.getAttribute('aria-label') || '')).click()"
    )
    page.wait_for_selector("#map-dialog[open] .map-days-band", timeout=5_000)
    page.wait_for_timeout(900)
    m = page.evaluate("""() => {
      const dlg = document.getElementById('map-dialog');
      const d = dlg.getBoundingClientRect();
      const vis = id => { const e = document.getElementById(id); if (!e) return false;
        const r = e.getBoundingClientRect();
        return getComputedStyle(e).display !== 'none' && r.height > 0 && r.top >= d.top && r.bottom <= d.bottom; };
      const btn = document.getElementById('map-filters-btn');
      return { scrollTop: dlg.scrollTop, toolbar: vis('map-toolbar'),
               sub: vis('map-subbar'), grp: vis('map-groupbar'),
               btn: btn ? { vis: vis('map-filters-btn'), t: btn.textContent.trim() } : null,
               mapH: document.getElementById('map-el').getBoundingClientRect().height, vh: innerHeight };
    }""")
    assert m["scrollTop"] == 0, m
    assert m["toolbar"], m
    assert not m["sub"] and not m["grp"], m
    assert m["btn"] and m["btn"]["vis"], m
    assert "Filtres" in m["btn"]["t"], m
    assert m["mapH"] <= 0.5 * m["vh"], m
    # « Filtres » déplie les deux barres.
    page.locator("#map-filters-btn").click()
    page.wait_for_timeout(150)
    ouvert = page.evaluate("""() => ['map-subbar', 'map-groupbar'].map(id => {
      const e = document.getElementById(id);
      return getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; })""")
    assert ouvert == [True, True], ouvert
    assert console_errors == []


def test_desktop_filtres_toujours_visibles(page, live_server, console_errors):
    """Le repli « Filtres » est une affaire de MOBILE : en desktop, sous-projets et groupes
    restent affichés d'emblée et le bouton n'est pas montré."""
    _semer(live_server)
    _ouvrir_carte(page, live_server, BUREAU)
    m = page.evaluate("""() => {
      const on = id => { const e = document.getElementById(id);
        return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; };
      return { sub: on('map-subbar'), grp: on('map-groupbar'), btn: on('map-filters-btn') };
    }""")
    assert m == {"sub": True, "grp": True, "btn": False}, m
    assert console_errors == []
