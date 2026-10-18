"""[DASH-API] § 2 — les règles des six tuiles portées en Python, éprouvées par la fixture JUMELLE.

`tests/fixtures/tiles_cases.json` est jouée ici (Python pur : `_tile_counts`) ET par
`tests/front/test_tiles_twin.py` (le board dans Chrome). Si l'un des deux dérive — un « en retard »
décalé d'un jour côté API, par exemple — c'est ce fichier qui rougit : l'API et le board doivent
donner les MÊMES chiffres sur les MÊMES mémos.

Les offsets sont résolus contre un « aujourd'hui » fixé (2026-10-18) côté Python : la fonction
pure prend la date en paramètre, donc le test ne dépend pas de l'horloge.
"""
import json
import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "tiles_cases.json")
TODAY = date(2026, 10, 18)


def _cases():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _iso(offset):
    return "" if offset is None else (TODAY + timedelta(days=offset)).isoformat()


def _memos(case):
    out = []
    for i, m in enumerate(case["memos"]):
        out.append({
            "id": i + 1, "done": bool(m.get("done")),
            "due_date": _iso(m.get("due_offset")),
            "due_end": _iso(m.get("due_end_offset")) if m.get("due_offset") is not None else "",
        })
    return out


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_les_comptes_python_suivent_la_fixture(app_module, case):
    got = app_module._tile_counts(_memos(case), TODAY.isoformat())
    assert {k: got[k] for k in case["expected"]} == case["expected"], case["name"]


def test_fin_effective_et_couverture(app_module):
    """Portage à l'identique de `memoDueEndDay` / `memoCoversDay` (partial l.152-160)."""
    f = app_module._memo_due_end_day
    assert f({"due_date": "2026-10-10", "due_end": "2026-10-12"}) == "2026-10-12"
    assert f({"due_date": "2026-10-10", "due_end": "2026-10-09"}) == "2026-10-10", "fin < début : ignorée"
    assert f({"due_date": "2026-10-10", "due_end": ""}) == "2026-10-10"
    assert f({"due_date": "", "due_end": "2026-10-12"}) == ""
    c = app_module._memo_covers_day
    m = {"due_date": "2026-10-10", "due_end": "2026-10-12"}
    assert c(m, "2026-10-10") and c(m, "2026-10-11") and c(m, "2026-10-12")
    assert not c(m, "2026-10-09") and not c(m, "2026-10-13")
    assert not c({"due_date": "", "due_end": ""}, "2026-10-10")


def test_l_api_counts_rejoue_la_fixture_melange(client):
    """La même fixture, cette fois par la route `GET /api/v1/counts` sur de VRAIS mémos : les
    offsets sont résolus contre l'aujourd'hui du serveur, passé en `?today=` pour rester
    déterministe (le paramètre sert aussi un client dans un autre fuseau)."""
    case = [c for c in _cases() if c["name"] == "mélange"][0]
    t = client.post("/api/tokens", json={"name": "t", "scopes": "read,write", "source": "cli"}).get_json()
    h = {"Authorization": "Bearer " + t["token"]}
    for i, m in enumerate(_memos(case)):
        r = client.post("/api/v1/memos", json={"title": "cas %d" % i, "due_date": m["due_date"],
                                               "due_end": m["due_end"] or None}, headers=h)
        assert r.status_code == 201, r.data
        if m["done"]:
            assert client.post("/api/v1/memos/%d/done" % r.get_json()["id"], headers=h).status_code == 200
    got = client.get("/api/v1/counts?today=" + TODAY.isoformat(), headers=h).get_json()
    assert {k: got[k] for k in case["expected"]} == case["expected"]
    assert "history" in got and got["history"] == 2, "deux mémos terminés = deux lignes d'historique"
    # et le filtre de la liste suit les mêmes règles
    for filt in ("open", "overdue", "today", "scheduled", "done"):
        r = client.get("/api/v1/memos?filter=%s&today=%s&limit=200" % (filt, TODAY.isoformat()), headers=h)
        assert r.status_code == 200, r.data
        attendu = case["expected"]["all" if filt == "open" else filt]
        assert len(r.get_json()["items"]) == attendu, (filt, r.get_json())
