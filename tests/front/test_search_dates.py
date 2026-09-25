"""[MEMO-SORT-DATES] — moitié DATES : chercher les mémos par échéance (`d#`) ou création (`c#`).

Brief : `docs/briefs/MEMO-SORT-DATES.md`. Front pur, owner seul, zéro route.

Ce que ces parcours PROTÈGENT :

- **`d#` est une INTERSECTION de plage, pas une égalité de date** (test 10) : un séjour du 6 au
  8 novembre doit sortir pour `d#2026-11-07`, un jour où il ne commence ni ne finit — c'est tout
  l'intérêt d'avoir `due_end` ([MEMO-DATE-RANGE], export v24) ;
- **`c#` compare le jour LOCAL, pas l'ISO UTC brut** (test 12) : un mémo créé le 30 septembre à
  23 h 30 à Paris est stocké en `…T21:30Z`, donc encore le 30 en UTC — mais un mémo créé le
  1er octobre à 00 h 30 est stocké en `…T22:30Z` le 30 septembre. Comparer les chaînes ISO le
  ferait basculer de mois ;
- **une forme non reconnue ne mange pas la recherche** (test 13) : `d#nimporte` cherche le texte
  tel quel et n'affiche pas de chip — jamais de liste vide silencieuse ;
- **les préfixes de date restent BORNÉS au dossier courant** (test 15, [SEARCH-IN-FOLDER]) :
  chercher une date depuis « Voyage Japon » ne doit pas ramener tout le dashboard.

Les formes relatives (`semaine`, `aujourd'hui`…) sont éprouvées sur le PARSEUR, avec une date
de référence fournie : un test qui dépendrait du jour réel serait vert ou rouge selon le
calendrier, ce qui ne prouve rien.
"""
import os as _os
import sqlite3 as _sqlite3
import time as _time
from datetime import date as _date

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1500, "height": 1000}

_MEMOS = []
_PROJETS = []


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Fuseau FIGÉ côté navigateur : `c#` compare des jours LOCAUX, un test qui hériterait du
    fuseau de la machine passerait à Paris et tomberait ailleurs. Le `live_server` pose déjà
    `TZ=Europe/Paris` côté serveur — les deux bouts parlent enfin la même heure."""
    return {**browser_context_args, "timezone_id": "Europe/Paris"}


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
    for pid in _PROJETS:
        try:
            requests.delete(live_server + "/api/projects/%d" % pid, timeout=5)
        except Exception:
            pass
    _MEMOS.clear(); _PROJETS.clear()


def _memo(live_server, titre, due="", end="", projet=None, contenu=""):
    import requests
    corps = {"title": titre, "content": contenu or (titre + " — décor de dates")}
    if due:
        corps["due_date"] = due
    if end:
        corps["due_end"] = end
    if projet:
        corps["project_id"] = projet
    r = requests.post(live_server + "/api/memos", json=corps, timeout=5)
    assert r.status_code in (200, 201), r.text
    _MEMOS.append(r.json()["id"])
    return r.json()["id"]


def _projet(live_server, nom):
    import requests
    r = requests.post(live_server + "/api/projects", json={"name": nom}, timeout=5)
    assert r.status_code in (200, 201), r.text
    _PROJETS.append(r.json()["id"])
    return r.json()["id"]


def _semer(live_server):
    """Le décor des dates d'échéance. « SD sejour » est la PLAGE qui fait tout l'intérêt de `d#`."""
    return {
        "avant": _memo(live_server, "SD avant", "2026-11-05"),
        "sejour": _memo(live_server, "SD sejour", "2026-11-06", "2026-11-08"),
        "apres": _memo(live_server, "SD apres", "2026-11-20"),
        "octobre": _memo(live_server, "SD octobre", "2026-10-30"),
        "kyoto": _memo(live_server, "SD kyoto", "2026-11-12"),
        "sansdate": _memo(live_server, "SD sansdate"),
    }


def _boot(page, live_server, projet=None):
    """Ouvre la vue MÉMOS — le board n'est rendu que là (en vue Liens, `#memo-board` est vide).

    Sans dossier, on passe par l'entrée « Mémos » de la sidebar : tous les mémos, toutes portées.
    """
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    if projet:
        page.locator(".cat-item", has_text=projet).first.click()
    else:
        page.evaluate(
            "() => [...document.querySelectorAll('#sidebar .cat-item')]"
            "       .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === 'Mémos').click()"
        )
    page.wait_for_timeout(300)
    page.wait_for_load_state("networkidle")


def _chercher(page, texte):
    page.fill("#search", texte)
    page.wait_for_timeout(350)


def _titres(page):
    """Les titres de NOS mémos dans le board, dans l'ordre affiché."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#memo-board .task')]"
        "       .map(t => (t.textContent.match(/SD [a-z]+/) || [''])[0]).filter(Boolean)"
    )


def _analyser(page, brut, aujourdhui):
    """Appelle le parseur PUR du partial avec une date de référence fournie."""
    return page.evaluate("([b, t]) => parseDatePrefix(b, t)", [brut, aujourdhui])


_BRUIT_404 = "the server responded with a status of 404"


@pytest.fixture
def urls_404(page):
    vues = []
    page.on("response", lambda r: vues.append(r.url) if r.status == 404 else None)
    return vues


def _erreurs_js(console_errors, urls_404):
    fautifs = [u for u in urls_404 if "/api/favicon/" not in u]
    assert fautifs == [], "404 inattendu(s) : %s" % fautifs
    return [e for e in console_errors if _BRUIT_404 not in e]


# -------------------------------------------------------------------------- 10


def test_d_prefixe_intersecte_la_plage(page, live_server, console_errors, urls_404):
    """`d#2026-11` prend tout novembre ; `d#2026-11-07` sort le séjour 6→8 SANS le 5 nov."""
    _semer(live_server)
    _boot(page, live_server)
    _chercher(page, "d#2026-11")
    assert sorted(_titres(page)) == ["SD apres", "SD avant", "SD kyoto", "SD sejour"]

    _chercher(page, "d#2026-11-07")
    vus = _titres(page)
    assert vus == ["SD sejour"], "le 7 nov. tombe DANS la plage 6→8, et seulement elle"
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 11


def test_formes_acceptees(page, live_server, console_errors, urls_404):
    """Toutes les écritures rendent le MÊME objet {from, to} — parseur pur, date de réf. fournie.

    Référence : mercredi 4 novembre 2026 (sa semaine ISO court du lundi 2 au dimanche 8).
    """
    _boot(page, live_server)
    REF = "2026-11-04"
    attendu = {
        "d#2026-11-07": ("due", "2026-11-07", "2026-11-07"),
        "d#2026-11": ("due", "2026-11-01", "2026-11-30"),
        "d#2026": ("due", "2026-01-01", "2026-12-31"),
        "d#2026-11-03..2026-11-09": ("due", "2026-11-03", "2026-11-09"),
        "d#07/11/2026": ("due", "2026-11-07", "2026-11-07"),
        "d#11/2026": ("due", "2026-11-01", "2026-11-30"),
        "d#aujourd'hui": ("due", REF, REF),
        "d#aujourdhui": ("due", REF, REF),
        "d#demain": ("due", "2026-11-05", "2026-11-05"),
        "d#hier": ("due", "2026-11-03", "2026-11-03"),
        "d#semaine": ("due", "2026-11-02", "2026-11-08"),
        "d#mois": ("due", "2026-11-01", "2026-11-30"),
        "c#2026-09": ("created", "2026-09-01", "2026-09-30"),
    }
    for brut, (kind, f, t) in attendu.items():
        got = _analyser(page, brut, REF)
        assert got, "forme non reconnue : " + brut
        assert (got["kind"], got["from"], got["to"]) == (kind, f, t), brut
    # février bissextile : le mois ne s'arrête pas au 28 par principe
    assert _analyser(page, "d#2028-02", REF)["to"] == "2028-02-29"
    assert _analyser(page, "d#nimporte", REF) is None
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 12


def test_c_prefixe_compare_le_jour_local(page, live_server, console_errors, urls_404):
    """`c#` filtre sur la date de CRÉATION, lue dans le fuseau local.

    Le mémo « SD tardif » est créé le 1er octobre à 00 h 30 à Paris — soit `2026-09-30T22:30Z`
    en base. Comparer l'ISO brut le rangerait en septembre ; il appartient à octobre.
    """
    ids = _semer(live_server)
    ancien = _memo(live_server, "SD aout")
    tardif = _memo(live_server, "SD tardif")
    con = _sqlite3.connect(_os.path.join(_os.environ["E2E_DATA_DIR"], "dashboard.db"))
    try:
        con.execute("UPDATE memos SET created_at = ? WHERE id = ?",
                    ("2026-08-15T10:00:00+00:00", ancien))
        con.execute("UPDATE memos SET created_at = ? WHERE id = ?",
                    ("2026-09-30T22:30:00+00:00", tardif))
        con.commit()
    finally:
        con.close()
    _boot(page, live_server)

    _chercher(page, "c#2026-08")
    assert _titres(page) == ["SD aout"]

    _chercher(page, "c#2026-10")
    vus = _titres(page)
    assert "SD tardif" in vus, "créé le 1er oct. à Paris : il appartient à octobre"
    assert "SD aout" not in vus
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 13


def test_combine_avec_du_texte_et_forme_invalide(page, live_server, console_errors, urls_404):
    """`d#2026-11 kyoto` = intervalle ET mots. `d#nimporte` = texte brut, sans chip."""
    _semer(live_server)
    _boot(page, live_server)
    _chercher(page, "d#2026-11 kyoto")
    assert _titres(page) == ["SD kyoto"]
    assert page.locator("#search-date-chip").is_visible()

    _chercher(page, "d#nimporte")
    assert page.locator("#search-date-chip").is_hidden(), "forme non reconnue → pas de chip"
    assert _titres(page) == [], "la recherche porte alors sur le TEXTE « d#nimporte »"
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 14


def test_chip_de_date(page, live_server, console_errors, urls_404):
    """Le chip nomme l'intervalle, et son ✕ retire le préfixe en GARDANT le texte libre."""
    _semer(live_server)
    _boot(page, live_server)
    _chercher(page, "d#2026-11 kyoto")
    chip = page.locator("#search-date-chip")
    assert chip.is_visible()
    txt = chip.inner_text()
    assert "échéance" in txt and "nov. 2026" in txt, txt

    _chercher(page, "c#2026-09")
    assert "créés" in page.locator("#search-date-chip").inner_text()

    _chercher(page, "d#2026-11 kyoto")
    page.locator("#search-date-chip .sc-x").click()
    page.wait_for_timeout(300)
    assert page.input_value("#search") == "kyoto"
    assert page.locator("#search-date-chip").is_hidden()
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 16


MOBILE = {"width": 412, "height": 900}


def test_feuille_mobile_comprend_les_dates(page, live_server, console_errors, urls_404):
    """La FEUILLE de recherche mobile doit rendre les mêmes mémos que le desktop.

    Renvoi de la passe Cowork du 25 sept. : en 412 px, entrer dans le champ ouvre la feuille —
    et `d#2026-11` y donnait « Aucun résultat » alors que le board desktop en listait 49. Le
    fournisseur de résultats du propriétaire s'arrêtait sur `if (!q) return []` : avec un préfixe
    de date, le texte EST vide, et une requête parfaitement valide passait pour une requête nulle.
    C'est le même défaut que celui rattrapé côté partage — deux fois la même leçon : une
    recherche ne se résume pas à ses mots.
    """
    _semer(live_server)
    page.set_viewport_size(MOBILE)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    # ⚠ Depuis [MOBILE-NAV] la sidebar est masquée sous 900 px : on attend le champ de recherche,
    # qui est justement la porte de la feuille, plutôt qu'un `.cat-item` devenu invisible.
    page.wait_for_selector("#search", timeout=10_000)
    page.wait_for_load_state("networkidle")

    page.locator("#search").click()
    page.wait_for_selector("#search-sheet[open]", timeout=5_000)
    page.fill("#search-sheet input[type=text]", "d#2026-11")
    page.wait_for_timeout(400)

    vus = page.evaluate(
        "() => [...document.querySelectorAll('#search-sheet .ss-item .ss-t')]"
        "       .map(e => (e.textContent.match(/SD [a-z]+/) || [''])[0]).filter(Boolean)"
    )
    assert sorted(set(vus)) == ["SD apres", "SD avant", "SD kyoto", "SD sejour"], \
        "la feuille doit voir la date, pas seulement les mots"
    assert page.locator("#search-sheet .ss-empty").count() == 0

    # …et un préfixe combiné au texte se comporte comme en desktop.
    page.fill("#search-sheet input[type=text]", "d#2026-11 kyoto")
    page.wait_for_timeout(400)
    vus = page.evaluate(
        "() => [...document.querySelectorAll('#search-sheet .ss-item .ss-t')]"
        "       .map(e => (e.textContent.match(/SD [a-z]+/) || [''])[0]).filter(Boolean)"
    )
    assert sorted(set(vus)) == ["SD kyoto"]

    # L'aide de la feuille annonce les deux préfixes (elle est la seule porte en mobile).
    page.fill("#search-sheet input[type=text]", "")
    page.wait_for_timeout(300)
    aide = page.locator("#search-sheet .ss-help").inner_text()
    assert "d#" in aide and "c#" in aide, aide
    assert _erreurs_js(console_errors, urls_404) == []


# -------------------------------------------------------------------------- 15


def test_date_bornee_au_dossier(page, live_server, console_errors, urls_404):
    """Depuis un dossier, `d#` reste borné à son sous-arbre — et « Chercher partout » élargit."""
    pid = _projet(live_server, "Voyage dates")
    _semer(live_server)
    _memo(live_server, "SD dedans", "2026-11-04", projet=pid)
    _boot(page, live_server, projet="Voyage dates")
    _chercher(page, "d#2026-11")
    assert _titres(page) == ["SD dedans"], "borné au dossier courant ([SEARCH-IN-FOLDER])"
    assert page.locator("#search-chip").is_visible(), "le chip « dans : … » reste affiché"

    page.locator("#search-chip .sc-x").click()
    page.wait_for_timeout(350)
    assert sorted(_titres(page)) == ["SD apres", "SD avant", "SD dedans", "SD kyoto", "SD sejour"]
    assert _erreurs_js(console_errors, urls_404) == []
