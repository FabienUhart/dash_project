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
