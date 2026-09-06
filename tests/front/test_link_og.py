"""[LINK-OG] La card de lien enrichie — parcours navigateur (propriétaire).

Ce que le back garantit (colonnes peuplées, vignette cachée) ne dit rien de ce que Fabien voit.
Ces parcours mesurent le RENDU : la miniature réellement chargée depuis notre serveur, le
domaine, le titre de la page, et surtout les DEUX replis — pas d'aperçu, et fichier manquant.

Le fetch n'a pas lieu ici : la garde zéro-réseau du navigateur (`tests/front/conftest.py`) coupe
la page du monde, et l'état OG est posé DIRECTEMENT dans la base du `live_server` (même relais
`E2E_DATA_DIR` que [MAP-PHOTO-COUNT] : le sous-processus a sa propre base temporaire).
"""
import io
import os as _os
import sqlite3 as _sqlite3

import pytest

pytestmark = pytest.mark.e2e


def _boot(page, live_server, path="/"):
    page.goto(live_server + path, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    page.wait_for_load_state("networkidle")


def _data_dir():
    return _os.environ["E2E_DATA_DIR"]


def _db():
    con = _sqlite3.connect(_os.path.join(_data_dir(), "dashboard.db"))
    con.row_factory = _sqlite3.Row
    return con


_CREES = []


@pytest.fixture(autouse=True)
def _nettoyer_les_liens(live_server):
    """Les liens créés ici ne survivent PAS à leur test.

    Le `live_server` est session-scoped : sa base est partagée par toute la suite. Or ce fichier
    est le premier à créer des liens, et une card de lien demande son favicon — que le serveur,
    coupé du réseau, ne peut pas trouver. Sans ce ménage, chaque test suivant héritait d'une
    poignée de 404 dans sa console et rougissait sur son `console_errors == []` : un lot qui
    casse des tests qu'il ne touche pas, par le seul effet d'un état laissé derrière lui.
    """
    _CREES.clear()
    yield
    import requests
    for lid in _CREES:
        try:
            requests.delete(live_server + "/api/links/%d" % lid, timeout=5)
        except Exception:
            pass
    _CREES.clear()


def _creer_lien(live_server, **kw):
    import requests
    payload = {"name": "Meduse carte"}
    payload.update(kw)
    r = requests.post(live_server + "/api/links", json=payload, timeout=5)
    assert r.status_code == 201, r.text
    lien = r.json()
    _CREES.append(lien["id"])
    return lien


def _poser_og(link_id, *, titre, desc, domaine, image_nom, statut="ok"):
    con = _db()
    con.execute(
        "UPDATE links SET og_title=?, og_desc=?, og_domain=?, og_image=?, "
        "og_fetched_at='2026-09-06T12:00:00+00:00', og_status=? WHERE id=?",
        (titre, desc, domaine, image_nom, statut, link_id),
    )
    con.commit()
    con.close()


def _poser_vignette(uid, couleur=(30, 120, 200)):
    from PIL import Image
    dossier = _os.path.join(_data_dir(), "uploads", "og")
    _os.makedirs(dossier, exist_ok=True)
    chemin = _os.path.join(dossier, uid + ".jpg")
    Image.new("RGB", (600, 400), couleur).save(chemin, "JPEG", quality=82)
    return chemin


def _carte(page, nom):
    return page.locator("#links .card", has_text=nom).first


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    """Les URL qui ont répondu 404, pour pouvoir juger le bruit de console au lieu de le subir."""
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404, tolerees=("/api/favicon/",)):
    """Erreurs de console, débarrassées du SEUL 404 attendu ici.

    Une card de lien demande son favicon ; le navigateur est coupé du réseau (garde e2e) et le
    serveur ne peut pas davantage aller le chercher — `/api/favicon/<id>` répond donc 404 et
    l'emoji 🔗 prend le relais. C'est la dégradation prévue, pas un défaut.

    Le filtre reste HONNÊTE : la ligne de console ne dit pas quelle ressource a manqué, alors on
    ne la retire qu'après avoir vérifié, sur les réponses réelles, qu'aucun AUTRE 404 n'a eu
    lieu. Un 404 sur `/api/og-image/…` fait donc toujours rougir — c'est même précisément ce
    qu'on veut voir si la route casse.
    """
    fautifs = [u for u in urls_404 if not any(t in u for t in tolerees)]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# --------------------------------------------------------------------------- #

def test_link_card_shows_the_og_preview(page, live_server, console_errors, urls_404):
    """Le parcours qui porte le lot : une card de lien avec aperçu affiche la miniature SERVIE
    PAR NOTRE SERVEUR, le domaine et le titre de la page."""
    lien = _creer_lien(live_server, name="Meduse carte",
                       url_public="https://meduseo.com/fr/ville/Bilbao-1")
    _poser_vignette(lien["uid"])
    _poser_og(lien["id"], titre="Bilbao — méduses, marées et spots",
              desc="Le guide des plages et de la faune du littoral basque.",
              domaine="meduseo.com", image_nom=lien["uid"] + ".jpg")

    _boot(page, live_server)
    card = _carte(page, "Meduse carte")
    og = card.locator(".og")
    assert og.count() == 1, "aucun bloc d'aperçu rendu sur la card"
    # `inner_text` rend le texte AFFICHÉ : la maquette met le domaine en capitales (CSS
    # `text-transform`), on compare donc sans tenir compte de la casse.
    assert og.locator(".og-dom").inner_text().strip().lower() == "meduseo.com"
    assert "plages" in og.locator(".og-s").inner_text()
    # [LINK-OG retouche] Le nom saisi est déjà en tête de card : le titre OG ne doit PAS le
    # doubler d'une seconde ligne. Il ne s'affiche que si `name` est vide (cf. le test dédié
    # ci-dessous), exactement comme `descr || og_desc`.
    assert og.locator(".og-t").count() == 0, \
        "le titre OG double le nom saisi (« %s »)" % og.locator(".og-t").inner_text()
    assert "Meduse carte" in card.locator(".name").inner_text()

    # La miniature n'est pas seulement dans le DOM : elle est CHARGÉE. `naturalWidth > 0`
    # prouve que la route owner a bien servi l'octet — un <img> cassé passerait tout le reste.
    img = og.locator("img.og-img")
    assert img.count() == 1
    assert page.evaluate("el => el.complete && el.naturalWidth > 0", img.element_handle()), \
        "la vignette n'a pas été chargée (route /api/og-image cassée ?)"
    assert "/api/og-image/" in img.get_attribute("src")
    assert "?v=" in img.get_attribute("src"), "cache-bust og_fetched_at absent de l'URL"

    assert _erreurs_js(console_errors, urls_404) == []


def test_link_card_without_og_keeps_its_plain_look(page, live_server, console_errors, urls_404):
    """Repli n° 1 — aucun aperçu (jamais fetché, `none`, `failed` ou `pending`) : la card garde
    exactement son allure d'avant. Pas de trou, pas de cadre vide."""
    _creer_lien(live_server, name="NAS maison", descr="Le disque du salon",
                url_local="http://192.168.1.50:8080/")

    _boot(page, live_server)
    card = _carte(page, "NAS maison")
    assert card.locator(".og").count() == 0, "cadre d'aperçu rendu sans aperçu à montrer"
    assert "Le disque du salon" in card.inner_text()
    assert _erreurs_js(console_errors, urls_404) == []


def test_missing_thumbnail_falls_back_to_text_only(page, live_server, console_errors):
    """Repli n° 2, celui que Fabien a demandé : la vignette est référencée mais le FICHIER a
    disparu (purge, corruption). On veut le bloc en texte seul — jamais l'icône d'image cassée."""
    lien = _creer_lien(live_server, name="Lien sans vignette",
                       url_public="https://exemple.test/page")
    _poser_og(lien["id"], titre="Un titre qui reste", desc="Une description qui reste",
              domaine="exemple.test", image_nom=lien["uid"] + ".jpg")  # aucun fichier posé

    _boot(page, live_server)
    card = _carte(page, "Lien sans vignette")
    og = card.locator(".og")
    assert og.count() == 1, "le texte de l'aperçu doit survivre à l'image manquante"
    assert "Une description qui reste" in og.locator(".og-s").inner_text()

    # L'image a pu être tentée, mais elle ne doit plus être là après son `onerror`.
    assert og.locator("img.og-img").count() == 0 or not og.locator("img.og-img").is_visible(), \
        "une image cassée est restée affichée"
    assert og.evaluate("el => el.classList.contains('og-noimg')"), \
        "le bloc n'a pas basculé en texte seul"


def test_og_title_only_shows_when_the_name_is_empty(page, live_server):
    """La règle de repli, prise à la source. On appelle `ogBlockEl` directement plutôt que de
    passer par une card : `name` est OBLIGATOIRE côté API (400 si vide), donc le cas « nom vide »
    n'est pas atteignable par un parcours — et le laisser non testé en ferait du code mort dont
    personne ne saurait dire s'il marche. Ici, les deux branches sont exercées pour de bon.
    """
    _boot(page, live_server)
    rendu = page.evaluate("""() => {
      const base = { og_status: 'ok', og_domain: 'exemple.test', og_title: 'Titre de la page',
                     og_desc: 'Description de la page', og_image: '', url_public: 'https://exemple.test/' };
      const lire = (l) => {
        const b = ogBlockEl(l);
        return b ? {
          t: b.querySelector('.og-t') ? b.querySelector('.og-t').textContent : null,
          dom: b.querySelector('.og-dom') ? b.querySelector('.og-dom').textContent : null,
          s: b.querySelector('.og-s') ? b.querySelector('.og-s').textContent : null,
        } : null;
      };
      return {
        nomme: lire({ ...base, name: 'Mon nom soigné' }),
        anonyme: lire({ ...base, name: '' }),
        titreSeul: lire({ ...base, name: 'Nommé', og_domain: '', og_desc: '' }),
      };
    }""")

    assert rendu["nomme"]["t"] is None, "le titre OG s'affiche alors que le nom est rempli"
    assert rendu["nomme"]["dom"] == "exemple.test", "le domaine doit rester"
    assert rendu["nomme"]["s"] == "Description de la page", "la description doit rester"

    assert rendu["anonyme"]["t"] == "Titre de la page", \
        "sans nom saisi, le titre OG doit prendre le relais"

    # Garde-fou : un OG qui n'a QUE son titre ne doit pas faire disparaître le bloc entier sous
    # prétexte que ce titre est masqué — c'est le piège de juger la présence sur l'après-repli.
    assert rendu["titreSeul"] is not None, "le bloc a disparu alors que l'OG portait un titre"


def test_a_very_long_title_does_not_break_the_card(page, live_server):
    """Troncature : un domaine, un titre et une description à rallonge doivent être COUPÉS, pas
    repliés sur dix lignes.

    ⚠ Ce test a d'abord été écrit en comparant la largeur du bloc à celle de la card — et une
    mutation l'a démoli : en retirant `nowrap`, le texte revient simplement à la ligne, donc rien
    ne déborde jamais horizontalement et le test restait vert en croyant prouver la troncature.
    La vraie propriété est la HAUTEUR : un aperçu bavard doit occuper exactement la même place
    qu'un aperçu court. C'est ce qu'on mesure ici, avec le court comme étalon.
    """
    court = _creer_lien(live_server, name="Lien sobre", url_public="https://exemple.test/")
    _poser_vignette(court["uid"])
    _poser_og(court["id"], titre="Titre court", desc="Description courte",
              domaine="exemple.test", image_nom=court["uid"] + ".jpg")

    bavard = _creer_lien(live_server, name="Lien bavard", url_public="https://exemple.test/2")
    _poser_vignette(bavard["uid"])
    _poser_og(bavard["id"], titre="Titre " + ("interminable " * 40),
              desc="Description " + ("sans fin " * 60),
              domaine="sous.domaine." + ("tres-long-" * 12) + "exemple.test",
              image_nom=bavard["uid"] + ".jpg")

    _boot(page, live_server)
    haut_court = _carte(page, "Lien sobre").locator(".og").bounding_box()["height"]
    boite_bavard = _carte(page, "Lien bavard").locator(".og").bounding_box()
    largeur_card = _carte(page, "Lien bavard").bounding_box()["width"]

    assert abs(boite_bavard["height"] - haut_court) <= 2, (
        "l'aperçu bavard occupe %spx contre %spx pour le sobre : le texte n'est pas tronqué"
        % (boite_bavard["height"], haut_court))
    assert boite_bavard["width"] <= largeur_card + 1, "l'aperçu déborde de la card"
