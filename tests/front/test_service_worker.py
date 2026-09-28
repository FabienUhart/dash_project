"""[E2E-SW-GUARD] — le service worker, testé À PART, et seulement ici.

Les e2e tournent SW bloqué (`browser_context_args` de `tests/front/conftest.py`) : sa prise de
contrôle recharge la page à un instant quelconque, ce qui cassait au hasard un `evaluate` en CI.
Ce fichier garde les deux bouts :

1. **la garde tient** : dans le contexte standard des e2e, aucun SW ne s'enregistre et la page ne
   se recharge pas toute seule (si le blocage saute, c'est ce test qui le dit, pas un flake) ;
2. **le SW marche** : dans un contexte qui l'AUTORISE, la première visite enregistre `/sw.js`,
   il prend le contrôle, la page se recharge UNE fois (`controllerchange`), puis reste stable et
   pilotable — on attend ce rechargement AVANT toute assertion sur le DOM.
"""
import time as _time

import pytest

pytestmark = pytest.mark.e2e


def _compter_chargements(page):
    """Compte les chargements du document principal (le premier + chaque rechargement)."""
    n = {"v": 0}
    page.on("load", lambda: n.__setitem__("v", n["v"] + 1))
    return n


def _attendre(page, cond, delai=10.0):
    """⚠ Attendre via `page.wait_for_timeout`, pas `time.sleep` : l'API sync de Playwright ne
    distribue ses événements (ici `load`) que pendant ses propres appels."""
    fin = _time.time() + delai
    while _time.time() < fin:
        if cond():
            return True
        page.wait_for_timeout(100)
    return cond()


def test_sw_bloque_dans_les_e2e(page, live_server, console_errors):
    """Contexte standard des e2e : pas de SW, pas de rechargement spontané."""
    n = _compter_chargements(page)
    page.goto(live_server + "/", wait_until="load")
    page.wait_for_selector(".cat-item", state="attached", timeout=10_000)
    # Laisse au SW le temps qu'il lui faut d'habitude pour s'installer et prendre la main.
    page.wait_for_timeout(2500)
    etat = page.evaluate("""async () => ({
      controller: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
      regs: navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0,
    })""")
    assert n["v"] == 1, "la page s'est rechargée %d fois (SW : %s)" % (n["v"] - 1, etat)
    assert etat == {"controller": False, "regs": 0}, etat
    assert console_errors == []


def test_sw_actif_prend_le_controle_et_recharge_une_fois(browser, live_server):
    """Contexte AVEC service worker : enregistrement, prise de contrôle, UN rechargement, puis
    une page stable. Aucune assertion DOM avant la fin du rechargement."""
    ctx = browser.new_context(service_workers="allow", viewport={"width": 1500, "height": 1000})
    try:
        page = ctx.new_page()
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        n = _compter_chargements(page)
        page.goto(live_server + "/", wait_until="load")
        assert _attendre(page, lambda: n["v"] >= 2), "pas de rechargement à la prise de contrôle du SW"
        page.wait_for_load_state("load")
        page.wait_for_selector(".cat-item", state="attached", timeout=10_000)
        etat = page.evaluate("""async () => {
          const reg = await navigator.serviceWorker.ready;
          return { controller: !!navigator.serviceWorker.controller,
                   script: reg.active ? new URL(reg.active.scriptURL).pathname : null };
        }""")
        assert etat == {"controller": True, "script": "/sw.js"}, etat
        # Stable : le rechargement ne se répète pas (garde `swRefreshing`).
        page.wait_for_timeout(1500)
        assert n["v"] == 2, "rechargements : %d" % (n["v"] - 1)
        assert page.evaluate("() => document.querySelectorAll('.cat-item').length") > 0
        assert erreurs == []
    finally:
        ctx.close()
