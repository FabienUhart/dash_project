#!/usr/bin/env python3
"""[FESTIVAL-VOTE] Générateur du seed « Vieilles Charrues 2026 ».

Lit `docs/specs/festival-vote-seed-vieilles-charrues-2026.json` (83 passages, 6 scènes
géolocalisées) et écrit un fichier d'IMPORT au format v23 standard :
`docs/specs/festival-vote-charrues-import-v23.json`.

Idempotence : chaque mémo-passage porte un `uid` DÉTERMINISTE (uuid5 d'une clé stable
scène|date|début|artiste) → un ré-import (local puis prod) via le flux d'import existant
(`POST /api/import`) matche par uid et ne crée AUCUN doublon. Le `content` est aussi rendu
unique par passage (scène · jour · créneau) pour survivre au dédup-par-contenu du 1er import
(les répétitions DRAGSHOW/PUMPELOP/BOREAL… donnent bien plusieurs mémos distincts).

RÈGLES DU BRIEF/PLAN respectées :
- Structure : dossier RACINE « Vieilles Charrues 2026 » + 6 sous-dossiers scènes, un mémo par
  passage (title=artiste, due_date=jour, due_time=début, end_time=fin).
- Convention post-minuit : le passage garde son JOUR de festival (due_date), même après minuit
  — la normalisation +24h vit côté serveur (`_slot_minutes`), le seed ne calcule rien.
- Les 6 sous-dossiers scènes reçoivent une `location {lat,lng,label}` (→ 6 pins sur la carte).
  Les 83 mémos n'ont AUCUNE location (pas de nuage de 83 points superposés — plan §3).
- `end_time` est accepté EN ENTRÉE d'import v23 (jamais réémis à l'export → sortie reste v23).

Aucun accès SQL direct, aucune dépendance runtime : sortie = un JSON avalé par l'import.
"""
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = os.path.join(os.path.dirname(HERE), "docs", "specs")
SEED_IN = os.path.join(SPECS, "festival-vote-seed-vieilles-charrues-2026.json")
IMPORT_OUT = os.path.join(SPECS, "festival-vote-charrues-import-v23.json")

ROOT_NAME = "Vieilles Charrues 2026"
# Namespace stable (figé) → uuid5 reproductible d'une exécution à l'autre.
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://dash.local/festival-vote/charrues-2026")
# Scènes « guinguette/spectacle » → 🎪 ; scènes concert → 🎤.
TENT_SCENES = {"Guinguette", "Esplanade"}


def scene_emoji(scene):
    return "🎪" if scene in TENT_SCENES else "🎤"


def passage_uid(p):
    key = "charrues2026|%s|%s|%s|%s" % (p["scene"], p["date"], p["start"], p["artist"])
    return str(uuid.uuid5(NS, key))


def build_import(seed):
    projects = [{"name": ROOT_NAME, "emoji": "🎪", "description":
                 "Programmation officielle — coups de cœur ❤️ et envies. "
                 "Un ❤️ = un incontournable ; pas deux ❤️ sur des créneaux qui se chevauchent."}]
    loc_by_scene = {s["scene"]: s for s in seed["scene_locations"]}
    for scene in seed["scenes"]:
        loc = loc_by_scene.get(scene)
        projects.append({
            "name": scene,
            "parent": ROOT_NAME,
            "emoji": scene_emoji(scene),
            "location": ({"lat": loc["lat"], "lng": loc["lng"], "label": loc["label"]}
                         if loc else None),
        })
    memos = []
    for p in seed["passages"]:
        memos.append({
            "uid": passage_uid(p),
            "title": p["artist"],
            # content unique par passage (anti-collapse au 1er import) ET informatif.
            "content": "%s · %s %s → %s" % (p["scene"], p["day"], p["start"], p["end"]),
            "project": p["scene"],
            "due_date": p["date"],
            "due_time": p["start"],
            "end_time": p["end"],
        })
    return {"version": 23, "projects": projects, "memos": memos,
            "links": [], "categories": []}


def main():
    with open(SEED_IN, encoding="utf-8") as f:
        seed = json.load(f)
    out = build_import(seed)
    with open(IMPORT_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    n_scenes = len(seed["scenes"])
    print("Écrit %s" % IMPORT_OUT)
    print("  projets : 1 racine + %d scènes" % n_scenes)
    print("  mémos   : %d passages" % len(out["memos"]))
    # Contrôle d'échantillon (brief §1).
    by_artist = {m["title"]: m for m in out["memos"]}
    # [FESTIVAL-DATES] Vraies dates calendaires : un passage d'après-minuit porte le
    # LENDEMAIN (INTERPOL nuit sam→dim = 2026-07-19 00:15). Le regroupement « journée de
    # festival » se fait à l'AFFICHAGE (helper front `festivalDay`).
    for art, dd, dt, et in (("KATY PERRY", "2026-07-16", "22:30", "00:00"),
                            ("INTERPOL", "2026-07-19", "00:15", "01:30"),
                            ("FEST NOZ", "2026-07-18", "23:00", "02:00")):
        m = by_artist.get(art)
        ok = m and m["due_date"] == dd and m["due_time"] == dt and m["end_time"] == et
        print("  échantillon %-11s : %s" % (art, "OK" if ok else "!! " + str(m)))


if __name__ == "__main__":
    main()
