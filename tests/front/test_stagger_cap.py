"""[STAGGER-CAP] — l'entrée en cascade des cards ne doit plus laisser l'écran noir.

Bug mesuré le 28 sept. 2026 (local, 181 mémos) : après `renderAll`, 0 card visible à 50 ms, 16 à
0,8 s, 65 à 3 s, 181 à 9 s. `stagger()` (partial) posait `autoAlpha:0` sur TOUTES les cards puis
les faisait entrer à 0,045 s d'écart CHACUNE : la durée de l'entrée croissait avec le nombre de
mémos (336 en prod ≈ 15 s avant la dernière).

Ce que ces parcours PROTÈGENT :

- **la borne** : seules les cards dans le viewport (et au plus les 24 premières) entrent en
  fondu ; les autres sont visibles d'emblée, et l'écart total de la cascade est borné
  (`stagger:{amount}`) — 300 ms après l'ouverture d'un dossier de 150 mémos, ≥ 90 % des cards
  sont déjà à opacité 1 ;
- **l'animation reste** : les premières cards entrent toujours en fondu (le lot borne l'entrée,
  il ne la supprime pas) ;
- **un seul helper** (ADR-001) : `#links .card`, `.share-card` et `#list .task` passent par le
  même `stagger()` — le test synthétique le vérifie hors de toute vue.
"""
import pytest

pytestmark = pytest.mark.e2e

BUREAU = {"width": 1500, "height": 1000}
N_MEMOS = 150
DOSSIER = "Cascade bornée"

_MEMOS = []
_PROJETS = []


@pytest.fixture(autouse=True)
def _nettoyer(live_server):
    """Le `live_server` est session-scoped : ce fichier remballe son décor (la colonne MÉMOS
    agrège tous les mémos, 150 restes pollueraient les tests suivants)."""
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


def _semer(live_server, n=N_MEMOS):
    import requests
    s = requests.Session()
    r = s.post(live_server + "/api/projects", json={"name": DOSSIER}, timeout=5)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    _PROJETS.append(pid)
    for i in range(n):
        r = s.post(live_server + "/api/memos",
                   json={"title": "SC %03d" % i, "content": "décor de cascade", "project_id": pid},
                   timeout=5)
        assert r.status_code in (200, 201), r.text
        _MEMOS.append(r.json()["id"])
    return pid


def _boot(page, live_server):
    page.set_viewport_size(BUREAU)
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".cat-item", timeout=10_000)
    page.wait_for_load_state("networkidle")
    # Laisse l'intro du premier rendu se finir : on mesure l'entrée d'une VUE, pas l'intro.
    page.wait_for_timeout(600)


# Ouvre le dossier par la vraie porte (sidebar) et attend que le board soit peint ; rend
# l'instant du rendu (performance.now()) et l'état des premières cards à cet instant.
_OUVRIR = """async (label) => {
  const item = [...document.querySelectorAll('#sidebar .cat-item')]
    .find(i => ((i.querySelector('.cat-label') || {}).textContent || '') === label);
  item.click();
  const t0 = performance.now();
  while (document.querySelectorAll('#memo-board .task').length < %d) {
    if (performance.now() - t0 > 3000) break;
    await new Promise(r => requestAnimationFrame(r));
  }
  const first = document.querySelector('#memo-board .task');
  return {
    n: document.querySelectorAll('#memo-board .task').length,
    firstTweening: !!(window.gsap && first && window.gsap.isTweening(first)),
  };
}""" % N_MEMOS

_OPAQUES = """() => {
  const ts = [...document.querySelectorAll('#memo-board .task')];
  const ok = ts.filter(t => {
    const cs = getComputedStyle(t);
    return cs.visibility !== 'hidden' && parseFloat(cs.opacity) >= 0.999;
  }).length;
  return { total: ts.length, ok };
}"""


def test_cascade_bornee_sur_un_gros_dossier(page, live_server, console_errors):
    """150 mémos : 300 ms après l'ouverture du dossier, ≥ 90 % des cards sont à opacité 1.

    Rouge avant le lot : la cascade de 0,045 s × 150 laisse la quasi-totalité à 0.
    """
    _semer(live_server)
    _boot(page, live_server)
    etat = page.evaluate(_OUVRIR, DOSSIER)
    assert etat["n"] == N_MEMOS, etat
    page.wait_for_timeout(300)
    m = page.evaluate(_OPAQUES)
    assert m["total"] == N_MEMOS
    assert m["ok"] >= 0.9 * N_MEMOS, "seulement %d/%d cards visibles à 300 ms" % (m["ok"], m["total"])
    # Et TOUT est visible une fois la cascade (bornée) finie.
    page.wait_for_timeout(1200)
    m = page.evaluate(_OPAQUES)
    assert m["ok"] == N_MEMOS, m
    assert console_errors == []


def test_les_premieres_cards_entrent_encore_en_fondu(page, live_server, console_errors):
    """Non-régression : borner n'est pas supprimer — la première card est en cours de tween
    juste après le rendu, et part d'une opacité < 1."""
    _semer(live_server, n=30)
    _boot(page, live_server)
    page.evaluate(_OUVRIR.replace("< %d" % N_MEMOS, "< 30"), DOSSIER)
    etat = page.evaluate("""() => {
      const f = document.querySelector('#memo-board .task');
      return { tw: !!(window.gsap && window.gsap.isTweening(f)),
               op: parseFloat(getComputedStyle(f).opacity) };
    }""")
    assert etat["tw"], etat
    assert etat["op"] < 1, etat
    assert console_errors == []


def test_helper_borne_hors_viewport_et_duree(page, live_server, console_errors):
    """Le helper lui-même, sur 200 nœuds synthétiques (même chemin que #links .card,
    .share-card, #list .task) : hors viewport → visibles d'emblée, jamais plus de 24 animés,
    cascade totale bornée (dernier départ ≤ 0,35 s)."""
    _boot(page, live_server)
    r = page.evaluate("""() => {
      const box = document.createElement('div');
      box.id = 'sc-synth';
      box.style.cssText = 'position:absolute;top:0;left:0;width:300px;z-index:9999';
      for (let i = 0; i < 200; i++) {
        const d = document.createElement('div');
        d.className = 'sc-node';
        d.style.cssText = 'height:30px';
        box.appendChild(d);
      }
      document.body.appendChild(box);
      window.scrollTo(0, 0);
      stagger('#sc-synth .sc-node');
      const ns = [...document.querySelectorAll('#sc-synth .sc-node')];
      const animes = ns.filter(n => window.gsap.isTweening(n));
      const horsVue = ns.filter(n => n.getBoundingClientRect().top >= window.innerHeight);
      const horsVueVisibles = horsVue.filter(n => {
        const cs = getComputedStyle(n);
        return cs.visibility !== 'hidden' && parseFloat(cs.opacity) >= 0.999;
      }).length;
      const tws = window.gsap.getTweensOf(animes);
      const fin = Math.max(0, ...tws.map(t => t.totalDuration ? t.totalDuration() : t.duration()));
      box.remove();
      return { animes: animes.length, horsVue: horsVue.length, horsVueVisibles, fin };
    }""")
    assert 0 < r["animes"] <= 24, r
    assert r["horsVue"] > 0 and r["horsVueVisibles"] == r["horsVue"], r
    # duration 0.4 + amount 0.35 → ≤ 0.75 s au total, quel que soit le nombre de nœuds.
    assert r["fin"] <= 0.8, r
    assert console_errors == []
