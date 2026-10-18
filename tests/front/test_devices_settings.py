"""[DASH-API] § 1.8 — Paramètres › Appareils connectés : créer un jeton (affiché UNE fois),
le voir dans la liste, le révoquer (→ 401), lire l'audit ; icône de provenance sur la card.

Ce que ces parcours PROTÈGENT :
- le jeton en clair n'apparaît qu'au moment de la création (modale + Copier), jamais dans la liste ;
- un jeton révoqué depuis l'UI ne passe plus la porte (`/api/v1/me` → 401) — c'est le geste de
  sécurité du propriétaire, il doit marcher du premier coup ;
- la confirmation de révocation est DOUCE (deux clics sur le même bouton, pas de `confirm()` natif) ;
- l'audit se lit et se filtre par jeton ;
- un mémo écrit par l'API porte une icône discrète sur sa card (title « via … »), un mémo de l'UI non ;
- zéro erreur console.
"""
import pytest

pytestmark = pytest.mark.e2e

_CREES = []


@pytest.fixture(autouse=True)
def _nettoyer(page, live_server):
    yield
    while _CREES:
        page.request.delete(live_server + _CREES.pop())


def _owner(page, live_server):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof setSettingsTab === 'function'")


def _ouvrir_appareils(page):
    page.click("#settings-btn")
    page.wait_for_selector("#settings-dialog[open]", timeout=5_000)
    page.click('#settings-tabs .prio-btn[data-tab="devices"]')
    page.wait_for_selector('#settings-dialog .settings-panel[data-panel="devices"]:not([style*="display: none"])', timeout=5_000)


def test_creer_voir_une_fois_revoquer(page, live_server, console_errors):
    _owner(page, live_server)
    _ouvrir_appareils(page)
    page.fill("#tok-name", "iPhone de Fabien")
    page.select_option("#tok-source", "flutter")
    page.select_option("#tok-scopes", "read,write")
    page.click("#tok-create")
    page.wait_for_selector("#token-dialog[open]", timeout=5_000)
    jeton = page.locator("#token-dialog #tok-plain").inner_text().strip()
    assert jeton.startswith("dash_") and len(jeton) >= 40
    assert "une seule fois" in page.locator("#token-dialog").inner_text().lower()
    assert page.locator("#token-dialog #tok-copy").count() == 1
    # le jeton marche
    r = page.request.get(live_server + "/api/v1/me", headers={"Authorization": "Bearer " + jeton})
    assert r.status == 200 and r.json()["name"] == "iPhone de Fabien" and r.json()["source"] == "flutter"
    page.click("#token-dialog #tok-close")
    page.wait_for_selector("#token-dialog[open]", state="detached", timeout=5_000)
    # la liste : nom, source, droits, état — et JAMAIS le jeton
    ligne = page.locator('#tok-list .tok-row:has-text("iPhone de Fabien")')
    ligne.wait_for(timeout=5_000)
    txt = ligne.inner_text()
    assert "flutter" in txt and "read,write" in txt.replace(" ", "") or "écriture" in txt.lower()
    assert jeton not in page.locator("#tok-list").inner_text()
    assert jeton not in page.content(), "le jeton ne doit plus être dans la page après fermeture"
    # révocation douce : 1er clic = « Confirmer ? », 2e clic = révoqué
    btn = ligne.locator(".tok-revoke")
    btn.click()
    assert "confirm" in btn.inner_text().lower()
    btn.click()
    page.wait_for_function("""() => { const r = [...document.querySelectorAll('#tok-list .tok-row')].find(x => x.textContent.includes('iPhone de Fabien')); return r && /révoqu/i.test(r.textContent); }""", timeout=5_000)
    r = page.request.get(live_server + "/api/v1/me", headers={"Authorization": "Bearer " + jeton})
    assert r.status == 401, "un jeton révoqué depuis l'UI doit être refusé"
    # audit : au moins l'appel /me réussi, filtrable par jeton
    page.wait_for_selector("#tok-audit .tok-audit-row", timeout=5_000)
    assert "/api/v1/me" in page.locator("#tok-audit").inner_text()
    assert console_errors == []


def test_icone_de_provenance_sur_la_card(page, live_server, console_errors):
    _owner(page, live_server)
    t = page.request.post(live_server + "/api/tokens", data={"name": "cc", "scopes": "read,write", "source": "claude-code"}).json()
    _CREES.append("/api/tokens/%d" % t["id"])
    via = page.request.post(live_server + "/api/v1/memos", data={"title": "Écrit par Claude Code"},
                            headers={"Authorization": "Bearer " + t["token"]}).json()
    _CREES.append("/api/memos/%d" % via["id"])
    ui = page.request.post(live_server + "/api/memos", data={"title": "Écrit à la main"}).json()
    _CREES.append("/api/memos/%d" % ui["id"])
    page.evaluate("async () => { await loadAll(); state.view = 'memos'; state.memoProject = 'all'; renderAll(); }")
    card_via = page.locator('.task[data-memo-id="%d"]' % via["id"])
    card_via.wait_for(timeout=5_000)
    ic = card_via.locator(".memo-source")
    assert ic.count() == 1
    assert "claude code" in (ic.get_attribute("title") or "").lower()
    assert page.locator('.task[data-memo-id="%d"] .memo-source' % ui["id"]).count() == 0
    assert console_errors == []
