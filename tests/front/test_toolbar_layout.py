"""[TOOLBAR-LAYOUT] UNE barre d'actions, une ligne de tri qui tient, des tuiles sans « 0 ».

Brief : `docs/briefs/TOOLBAR-LAYOUT.md` (§ 0 = deux captures prod du 4 oct. 2026 du même dossier :
barres empilées en sombre, écartées en clair ; « Tri » seul sur sa ligne ; `0` sur les tuiles ;
horloge Tokyo sur un seul navigateur). Front pur, export 29 inchangé. Cible V29.1.280.

Ce que ces parcours PROTÈGENT (numéros = § 2 du brief) :

1. **une seule** `.hdr-toolbar` par board (actions du dossier + dock dans le même cadre, une seule
   bascule « ‹ › ») — plus jamais deux colonnes de boutons ;
2. à 900 px la barre **ne s'empile pas** (≤ 72 px de haut) : elle défile, elle ne wrappe pas ;
3. plus de vignette chevron hors du cadre : « ▾ » dans le libellé seulement, rien en compact ;
4. la ligne de tri tient sur **une** ligne même à 412 px, sans label « Tri », et l'actif se voit
   dans les **deux thèmes** ;
5. l'aide des dates est **calculée** sur le mois courant (plus de `2026-11` figé) et discrète ;
6. aucun `0` sur les tuiles ; les compteurs suivent la recherche ;
7. l'horloge secondaire est un **réglage serveur** (`extra_tz`), avec migration douce du localStorage ;
8. zéro erreur console sur 1280 / 900 / 412.

La base du `live_server` est partagée par toute la session : décor et réglages sont remis en
état en sortie (fixture `_nettoyer`).
"""
import io
import os
import time

import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1280, "height": 800}
MOYEN = {"width": 900, "height": 800}
MOBILE = {"width": 412, "height": 900}
_BRUIT_404 = "the server responded with a status of 404"
_n = [0]
_CREES = []   # urls de suppression, dossiers en DERNIER


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())
    page.request.put(live_server + "/api/settings", data={"extra_tz": ""})   # réglage serveur remis à vide
    try:
        page.evaluate("() => { localStorage.removeItem('hdrToolbarCompact'); localStorage.removeItem('extraTZ'); }")
    except Exception:
        pass


def _erreurs_js(console_errors):
    return [e for e in console_errors if _BRUIT_404 not in e]


def _attendre(page, cond, timeout_ms=8_000):
    fin = time.time() + timeout_ms / 1000.0
    while time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return False


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 80, 40)).save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ décor


def _semer(page, live_server, avec_photo=True):
    """Dossier « TL k » : 2 mémos en cours (l'un avec photo → bascule Immersif), 1 planifié,
    aucun en retard, 1 terminé. Titres porteurs de `k` : aucun décor voisin ne peut matcher."""
    _n[0] += 1
    k = "%d%d" % (_n[0], int(time.time()) % 1000)
    p = page.request.post(live_server + "/api/projects", data={"name": "TL dossier %s" % k}).json()
    _CREES.insert(0, "/api/projects/%d" % p["id"])

    def memo(titre, **extra):
        r = page.request.post(live_server + "/api/memos", data={"title": "%s %s" % (titre, k), "content": "décor TL", "project_id": p["id"], **extra})
        assert r.ok, r.text()
        m = r.json()
        _CREES.append("/api/memos/%d" % m["id"])
        return m

    m1 = memo("TL photo")
    if avec_photo:
        r = page.request.post(live_server + "/api/memos/%d/images" % m1["id"],
                              multipart={"image": {"name": "tl.png", "mimeType": "image/png", "buffer": _png()}})
        assert r.ok, r.text()
    memo("TL en cours")
    memo("TL planifié", due_date="2099-01-01")
    memo("TL terminé", done=True)
    return {"k": k, "projet": p}


def _owner(page, live_server, pid, vp=BUREAU):
    page.set_viewport_size(vp)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof renderBoard === 'function' && state.memos")
    page.evaluate("pid => { state.view = 'memos'; state.memoProject = pid; state.memoFilter = 'all'; renderAll(); }", pid)
    page.wait_for_selector("#memo-board .hdr-toolbar", timeout=5_000)
    page.wait_for_timeout(300)


# --------------------------------------------------------------------------- 1


def test_une_seule_barre_actions_et_dock_fusionnes(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server, d["projet"]["id"])
    barres = page.locator("#memo-board .hdr-toolbar")
    assert barres.count() == 1, "deux barres d'actions (actions + dock) : c'est exactement ce que Fabien ne supporte plus"
    barre = barres.first
    assert barre.locator('[title^="Modifier ce projet"]').count() == 1, "les actions du dossier manquent dans la barre"
    assert barre.locator('[title^="Afficher/masquer la barre de création"]').count() == 1, "le dock n'est pas dans la MÊME barre"
    assert barre.locator(".hdr-toggle").count() == 1, "une barre = une seule bascule « ‹ › »"
    assert page.locator("#memo-board .hdr-toggle").count() == 1
    assert "bare" not in (barre.get_attribute("class") or "")

    # le dock garde son comportement : clic = bascule .on + aria-pressed
    dock = barre.locator('[title^="Afficher/masquer la barre de création"]')
    avant = dock.get_attribute("aria-pressed")
    dock.click()
    page.wait_for_timeout(300)
    dock = page.locator('#memo-board .hdr-toolbar [title^="Afficher/masquer la barre de création"]')
    assert dock.get_attribute("aria-pressed") != avant
    assert page.locator("#memo-board .hdr-toolbar").count() == 1

    # Tous les mémos / Inbox : pas de dock, et au plus une barre « nue »
    for vue in ("all", "inbox"):
        page.evaluate("v => { state.memoProject = v; renderAll(); }", vue)
        page.wait_for_timeout(300)
        n = page.locator("#memo-board .hdr-toolbar").count()
        assert n <= 1, vue
        if n == 1:
            assert "bare" in (page.locator("#memo-board .hdr-toolbar").get_attribute("class") or ""), vue
        assert page.locator('#memo-board [title^="Afficher/masquer la barre de création"]').count() == 0, vue
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 2


def test_a_900px_la_barre_ne_s_empile_pas(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server, d["projet"]["id"], vp=MOYEN)
    barre = page.locator("#memo-board .hdr-toolbar").first
    bb = barre.bounding_box()
    assert bb and bb["height"] <= 72, "la barre fait %r px de haut : elle s'est empilée" % (bb and bb["height"])
    # elle contient tout (actions + dock) ; déborder EN LARGEUR est permis (défilement), pas en hauteur
    assert barre.locator('[title^="Modifier ce projet"]').count() == 1
    assert barre.locator('[title^="Afficher/masquer la barre de création"]').count() == 1
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0, "la page déborde en largeur"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 3


def test_plus_de_chevron_hors_cadre(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server, d["projet"]["id"])
    assert page.locator(".hdr-menu").count() == 0, "la vignette chevron « ⌄ » existe encore"
    votes = page.locator('#memo-board .hdr-toolbar [title^="Créer et gérer des votes"]')
    assert votes.count() == 1
    lbl = votes.locator(".hdr-lbl").inner_text().strip()
    assert lbl.endswith("▾"), "le libellé du bouton à menu doit se terminer par « ▾ » : %r" % lbl
    assert "⌄" not in page.locator("#memo-board .hdr-toolbar").inner_text()

    page.locator("#memo-board .hdr-toolbar .hdr-toggle").click()
    page.wait_for_timeout(300)
    assert "compact" in (page.locator("#memo-board .hdr-toolbar").get_attribute("class") or "")
    visible = page.locator("#memo-board .hdr-toolbar").inner_text()
    assert "▾" not in visible and "⌄" not in visible, "en compact, aucun indicateur de menu ne doit être visible"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 4


def _bg(page, sel):
    return page.evaluate("s => getComputedStyle(document.querySelector(s)).backgroundColor", sel)


def test_ligne_de_tri_une_ligne_sans_label_actif_visible(page, live_server, console_errors):
    # SANS photo, exprès : le gabarit `.cover-seg` n'était injecté que par la bascule Immersif/Compact
    # (absente sans photo) — vu au smoke sur un vrai dossier, invisible avec un décor à photo.
    d = _semer(page, live_server, avec_photo=False)
    _owner(page, live_server, d["projet"]["id"])
    bar = page.locator("#memo-sort-bar")
    assert bar.count() == 1
    assert "Tri" not in bar.inner_text().split("Manuel")[0], "le label « Tri » doit disparaître (segment auto-porteur)"
    assert page.locator("#memo-sort-seg[aria-label]").count() == 1
    assert page.locator("#memo-sort-seg .cover-seg-btn.on").count() == 1

    for theme in ("dark", "light"):
        page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
        page.wait_for_timeout(100)
        actif = _bg(page, "#memo-sort-seg .cover-seg-btn.on")
        voisin = _bg(page, "#memo-sort-seg .cover-seg-btn:not(.on)")
        assert actif != voisin, "thème %s : le tri actif a le même fond que ses voisins (invisible)" % theme
        # et pas un fond transparent qui laisserait filtrer le panneau derrière
        assert actif not in ("rgba(0, 0, 0, 0)", "transparent"), theme
    page.evaluate("() => document.documentElement.removeAttribute('data-theme')")

    page.set_viewport_size(MOBILE)
    page.wait_for_timeout(400)
    bb = page.locator("#memo-sort-bar").bounding_box()
    assert bb and bb["height"] <= 40, "à 412 px la ligne de tri fait %r px : elle wrappe" % (bb and bb["height"])
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 5


def test_aide_des_dates_calculee_sur_le_mois_courant(page, live_server, console_errors):
    d = _semer(page, live_server)
    _owner(page, live_server, d["projet"]["id"])
    aide = page.locator("#memo-date-help")
    assert aide.count() == 1
    texte = aide.inner_text()
    mois = page.evaluate("() => { const n = new Date(); return n.getFullYear() + '-' + String(n.getMonth() + 1).padStart(2, '0'); }")
    assert ("d#" + mois) in texte, "l'aide ne parle pas du mois courant %s : %r" % (mois, texte)
    assert ("c#" + mois) in texte
    assert "d#semaine" in texte and texte.startswith("Dates")
    # la semaine courante : lundi..dimanche, dates LOCALES
    lundi, dimanche = page.evaluate("""() => {
      const n = new Date(); const j = n.getDay() || 7;
      const l = new Date(n); l.setDate(n.getDate() - (j - 1)); const d = new Date(l); d.setDate(l.getDate() + 6);
      const f = x => x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0');
      return [f(l), f(d)]; }""")
    semaine = "d#%s..%s" % (lundi, dimanche)
    assert semaine in texte, texte
    # Hors la semaine calculée (qui peut légitimement déborder sur novembre, ex. 26/10 → 01/11),
    # aucune trace du mois figé d'origine.
    if mois != "2026-11":
        assert "2026-11" not in texte.replace(semaine, ""), "texte figé sur novembre 2026 : %r" % texte
    fs_aide = page.evaluate("() => parseFloat(getComputedStyle(document.querySelector('#memo-date-help')).fontSize)")
    fs_tri = page.evaluate("() => parseFloat(getComputedStyle(document.querySelector('#memo-sort-seg button')).fontSize)")
    assert fs_aide < fs_tri, "l'aide doit être plus discrète que la ligne de tri (%s vs %s)" % (fs_aide, fs_tri)
    assert "cover-disp" not in (aide.get_attribute("class") or ""), "l'aide ne doit plus porter le gabarit de la ligne de tri"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 6


def test_tuiles_sans_zero(page, live_server, console_errors):
    d = _semer(page, live_server, avec_photo=False)
    _owner(page, live_server, d["projet"]["id"])
    assert page.locator("#memo-filters .f-overdue .mf-count").count() == 0, "« 0 » affiché sur En retard"
    # (les compteurs sont ANIMÉS au rendu — countUp GSAP — on attend la valeur finale)
    compte = lambda cls: page.locator("#memo-filters .%s .mf-count" % cls).inner_text().strip()
    assert _attendre(page, lambda: compte("f-inbox") == "3" and compte("f-done") == "1" and compte("f-scheduled") == "1"), \
        "compteurs attendus 3 / 1 / 1, vus %s / %s / %s" % (compte("f-inbox"), compte("f-done"), compte("f-scheduled"))
    assert "0" not in [c.strip() for c in page.locator("#memo-filters .mf-count").all_inner_texts()]
    # les six tuiles restent alignées : même hauteur de `.mf-top` avec ou sans compteur
    hauteurs = page.evaluate("() => [...document.querySelectorAll('#memo-filters .mf-top')].map(t => Math.round(t.getBoundingClientRect().height))")
    assert len(set(hauteurs)) == 1, "tuiles désalignées sans compteur : %r" % hauteurs

    # retouche post-passe : le compteur de la tuile ACTIVE doit se lire dans les DEUX thèmes (fond
    # sombre fixe → en clair il héritait de --text sombre : invisible, capture Opera du 4 oct.)
    for theme in ("dark", "light"):
        page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
        page.wait_for_timeout(100)
        ratio = page.evaluate("""() => {
          const el = document.querySelector('#memo-filters .mfilter.active .mf-count');
          const rgb = s => s.match(/[\\d.]+/g).slice(0, 3).map(Number);
          const lum = ([r, g, b]) => { const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
          let bg = null, n = el;
          while (n && !bg) { const c = getComputedStyle(n).backgroundColor; if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') bg = c; n = n.parentElement; }
          const l1 = lum(rgb(getComputedStyle(el).color)), l2 = lum(rgb(bg));
          return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        }""")
        assert ratio > 3, "thème %s : contraste du compteur de la tuile active = %.2f:1 (< 3:1, illisible)" % (theme, ratio)
    page.evaluate("() => document.documentElement.removeAttribute('data-theme')")

    # les compteurs suivent la recherche : rien ne matche → aucun compteur
    page.locator("#search").fill("m#zzzz-rien-%s" % d["k"])
    assert _attendre(page, lambda: page.locator("#memo-filters .mf-count").count() == 0), \
        "des compteurs à 0 subsistent quand la recherche ne trouve rien"
    page.locator("#search").fill("m#TL en cours %s" % d["k"])
    assert _attendre(page, lambda: page.locator("#memo-filters .f-inbox .mf-count").count() == 1
                     and compte("f-inbox") == "1")
    assert page.locator("#memo-filters .f-done .mf-count").count() == 0
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 7


def _contexte_vierge(browser, browser_context_args, init_script=None):
    ctx = browser.new_context(**browser_context_args)
    ctx.route("**/*", lambda r: r.continue_() if (r.request.url.startswith("http://127.0.0.1") or r.request.url.startswith("http://localhost")) else r.abort())
    if init_script:
        ctx.add_init_script(init_script)
    return ctx


def test_horloge_secondaire_est_un_reglage_serveur(page, live_server, browser, browser_context_args, console_errors):
    r = page.request.put(live_server + "/api/settings", data={"extra_tz": "Asia/Tokyo"})
    assert r.ok, r.text()
    assert page.request.get(live_server + "/api/settings").json().get("extra_tz") == "Asia/Tokyo"

    # un AUTRE navigateur (localStorage vierge) voit Tokyo : c'est le serveur qui porte le réglage
    ctx = _contexte_vierge(browser, browser_context_args)
    try:
        p2 = ctx.new_page()
        p2.goto(live_server + "/", wait_until="domcontentloaded")
        p2.wait_for_function("() => (document.getElementById('clock-extra') || {}).textContent.indexOf('Tokyo') >= 0", timeout=10_000)
        assert p2.evaluate("() => localStorage.getItem('extraTZ')") == "Asia/Tokyo", "le cache local doit refléter le serveur"
        # le sélecteur de Paramètres lit la même valeur
        assert p2.evaluate("() => document.getElementById('tz-select').value") == "Asia/Tokyo"
    finally:
        ctx.close()

    # migration douce : serveur vide + localStorage ancien → poussé UNE fois au serveur
    assert page.request.put(live_server + "/api/settings", data={"extra_tz": ""}).ok
    assert page.request.get(live_server + "/api/settings").json().get("extra_tz", "") == ""
    ctx = _contexte_vierge(browser, browser_context_args, "localStorage.setItem('extraTZ', 'Europe/London')")
    try:
        p3 = ctx.new_page()
        p3.goto(live_server + "/", wait_until="domcontentloaded")
        p3.wait_for_function("() => (document.getElementById('clock-extra') || {}).textContent.indexOf('Londres') >= 0", timeout=10_000)
        assert _attendre(page, lambda: page.request.get(live_server + "/api/settings").json().get("extra_tz") == "Europe/London"), \
            "le réglage du localStorage n'a pas été poussé au serveur (migration douce)"
    finally:
        ctx.close()

    # une valeur invalide est refusée, jamais stockée
    r = page.request.put(live_server + "/api/settings", data={"extra_tz": "<script>"})
    assert r.status == 400
    assert page.request.get(live_server + "/api/settings").json().get("extra_tz") == "Europe/London"
    assert _erreurs_js(console_errors) == []


# --------------------------------------------------------------------------- 8


@pytest.mark.parametrize("vp", [BUREAU, MOYEN, MOBILE], ids=["1280", "900", "412"])
def test_zero_erreur_console_et_pas_de_debord(page, live_server, console_errors, vp):
    d = _semer(page, live_server)
    _owner(page, live_server, d["projet"]["id"], vp=vp)
    assert page.locator("#memo-board .hdr-toolbar").count() == 1
    assert page.locator("#memo-sort-bar").count() == 1 and page.locator("#memo-date-help").count() == 1
    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0
    page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
    page.evaluate("() => renderAll()")
    page.wait_for_timeout(300)
    assert page.locator("#memo-board .hdr-toolbar").count() == 1
    page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
    assert _erreurs_js(console_errors) == []
