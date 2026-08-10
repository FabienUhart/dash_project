"""Le banc d'essai lui-même : le `live_server` ne doit pas s'étouffer dans ses propres logs.

Ce test ne vise pas l'application mais le harnais. Le serveur de développement journalise une
ligne par requête sur sa sortie standard, branchée sur un tube (`subprocess.PIPE`). Tant que
personne ne vide ce tube, le noyau l'accumule — et au bout de son tampon (64 Ko sur macOS) le
serveur **bloque en écriture** : il cesse de répondre, sans erreur, sans trace, au milieu de la
suite. Le symptôme observé était un `page.goto` qui pendait trente secondes alors qu'une requête
servie l'instant d'avant allait très bien, et qui se déplaçait de test en test au gré du volume.

On force donc le débordement : assez de requêtes pour dépasser largement le tampon, puis on
vérifie que le serveur répond encore. Sans le fil qui draine la sortie, ce test pend et rougit.
"""
import pytest

pytestmark = pytest.mark.e2e


def test_live_server_survives_more_logs_than_its_pipe_buffer(live_server, page):
    """Assez de requêtes pour saturer le tube — le serveur doit rester vivant après."""
    # Chaque requête servie vaut ~90 octets de journal ; 1200 dépassent confortablement les
    # 64 Ko du tampon, marge comprise.
    for i in range(1200):
        r = page.request.get(live_server + "/api/version", timeout=5_000)
        assert r.ok, "le serveur a cessé de répondre après %d requêtes : %s" % (i, r.status)

    # La preuve qui compte : une page HTML complète, pas seulement une réponse JSON minuscule.
    page.goto(live_server, wait_until="domcontentloaded", timeout=15_000)
    page.wait_for_selector(".cat-item", timeout=15_000)


# ─────────────────────── Le navigateur non plus ne sort pas ───────────────────────
# La garde « zéro réseau » de `tests/conftest.py` ferme le processus pytest. Le NAVIGATEUR,
# lui, restait libre : la page propriétaire appelle open-meteo au chargement, donc nos e2e
# dépendaient d'internet sans le dire. Ça s'est payé sur un runner GitHub, sans accès sortant :
# l'appel météo pendait jusqu'à `ERR_TIMED_OUT`, `networkidle` n'aboutissait jamais, et quatre
# tests de la page propriétaire tombaient — verts en local pour la seule raison que la machine
# avait une connexion.

def test_the_browser_cannot_reach_the_outside(live_server, page):
    """Un `fetch` vers l'extérieur doit échouer, et échouer VITE."""
    page.goto(live_server, wait_until="domcontentloaded")
    verdict = page.evaluate("""async () => {
      try { await fetch('https://api.open-meteo.com/v1/forecast'); return 'ATTEINT'; }
      catch (e) { return 'BLOQUE'; }
    }""")
    assert verdict == "BLOQUE", (
        "la page a joint un hôte externe : la suite dépend alors d'internet, et rougit sur "
        "une machine qui n'en a pas")

    # Et l'app, elle, doit rester joignable — bloquer l'extérieur ne doit pas la couper d'elle-même.
    interne = page.evaluate("""async () => {
      const r = await fetch('/api/version'); return r.ok ? 'OK' : ('HTTP ' + r.status);
    }""")
    assert interne == "OK", "l'app doit rester joignable depuis la page (vu : %s)" % interne


def test_the_offline_filter_stays_narrow(live_server, page, console_errors):
    """Le filtre de `console_errors` écarte la dégradation hors ligne, RIEN d'autre.

    ⚠ Première version de ce test : verte pour la mauvaise raison. Elle écoutait sa PROPRE
    liste — jamais filtrée — et comparait les signatures à la main. Élargir le filtre à un
    simple « Failed » la laissait passer sans broncher. On exerce donc la vraie fixture, avec
    un message qu'un filtre trop large avalerait : une erreur d'application qui contient, elle
    aussi, le mot « Failed ». Écarter large serait pire que ne rien écarter — une vraie panne
    passerait inaperçue.
    """
    page.goto(live_server, wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=15_000)
    page.wait_for_load_state("networkidle")   # la météo est bloquée ⇒ le filtre est ARMÉ

    page.evaluate(
        """() => { console.error('TypeError: Failed to load memo board at renderBoard'); }""")

    assert any("renderBoard" in t for t in console_errors), (
        "une vraie erreur d'application doit être collectée même quand le filtre hors ligne "
        "est armé (collectées : %r)" % console_errors)
