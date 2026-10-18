"""[DASH-API] § 2 — le BOARD rejoue la fixture jumelle des six tuiles.

`tests/fixtures/tiles_cases.json` est la même que côté Python (`tests/back/test_tiles_twin.py`) :
les mémos sont injectés dans `state.memos` avec des dates résolues contre l'aujourd'hui du
navigateur, le board est rendu, et les chiffres des tuiles sont lus. Si l'API (Python) et le
board (JS) ne comptent plus pareil, l'un des deux fichiers rougit.

Le board masque le « 0 » ([TOOLBAR-LAYOUT] § 1.5) : une tuile sans compteur vaut 0.
"""
import json
import os

import pytest

pytestmark = pytest.mark.e2e

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "tiles_cases.json")


def _cases():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _boot(page, live_server):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof renderBoard === 'function' && Array.isArray(state.memos)")


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_le_board_compte_comme_la_fixture(page, live_server, console_errors, case):
    _boot(page, live_server)
    got = page.evaluate("""(memos) => {
      const iso = (off) => { if (off == null) return ''; const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() + off); return dateStr(d); };
      state.memos = memos.map((m, i) => ({
        id: 100000 + i, uid: 'twin-' + i, title: 'twin ' + i, content: '', done: !!m.done,
        due_date: iso(m.due_offset), due_end: m.due_offset == null ? '' : iso(m.due_end_offset == null ? null : m.due_end_offset),
        due_time: '', priority: 0, subtasks: [], images: [], assignees: [], urls: [], links: [], link_refs: [],
        attachments: [], project_id: null, created_at: '2026-01-01T00:00:00+00:00', updated_at: '2026-01-01T00:00:00+00:00',
      }));
      state.history = [];
      state.view = 'memos'; state.memoProject = 'all'; state.memoFilter = 'all'; state.search = '';
      renderBoard();
      const out = {};
      for (const key of ['all', 'overdue', 'today', 'scheduled', 'done']) {
        const cls = key === 'all' ? 'f-inbox' : 'f-' + key;
        const tile = document.querySelector('#memo-filters .mfilter.' + cls);
        const n = tile ? tile.querySelector('.mf-count') : null;
        out[key] = n ? Number(n.textContent) : 0;
      }
      return out;
    }""", case["memos"])
    # les compteurs s'animent (countUp) : on attend la valeur finale
    for _ in range(30):
        if got == case["expected"]:
            break
        page.wait_for_timeout(100)
        got = page.evaluate("""() => { const out = {}; for (const key of ['all','overdue','today','scheduled','done']) {
          const cls = key === 'all' ? 'f-inbox' : 'f-' + key; const t = document.querySelector('#memo-filters .mfilter.' + cls);
          const n = t ? t.querySelector('.mf-count') : null; out[key] = n ? Number(n.textContent) : 0; } return out; }""")
    assert got == case["expected"], case["name"]
    assert console_errors == []
