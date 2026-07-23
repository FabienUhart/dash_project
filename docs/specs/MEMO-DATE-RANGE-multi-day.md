# [MEMO-DATE-RANGE] — Plage de dates sur un mémo (hôtels multi-nuits, événements multi-jours)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Constat Fabien : un hôtel « 3→6 nov (3 nuits) » n'apparaît que le 3 nov dans la frise/agenda — la plage n'existe que dans le texte. ⚠️ Ce lot fait le PREMIER BUMP D'EXPORT depuis la v23 → `APP_VERSION = "24"` (donnée utilisateur réelle, doit voyager dans l'export — invariant 1).**

## Modèle

- **Colonne additive `memos.due_end`** (`TEXT DEFAULT NULL`, date `YYYY-MM-DD`), optionnelle, valide seulement si `due_date` posée et `due_end ≥ due_date`. `due_time` (v18) reste liée au début ; pas d'heure de fin en V1.
- **Export v24** : `due_end` ajouté au JSON mémo (additif). **Import** : v24 → repris ; v23 et antérieurs → `due_end` absent = NULL (compat totale, invariant 2). Bump X → `APP_VERSION="24"`, entrée invariant 1 dans CLAUDE.md, historique.
- **Garde-fous** : `due_end` sans `due_date` = rejeté (400) ; effacer la date (`× date`) efface aussi la fin ; récurrence ET plage **mutuellement exclusives en V1** (400 explicite — à assouplir plus tard si besoin).

## UI (owner + invités selon rôle, 3 pages)

- Pop-in mémo : champ **« → fin »** discret à côté de la date (input date, visible seulement si une date est posée, à la manière de l'heure v18). Même chose côté pop-in invité (rôles éditeur/zone — mêmes règles que la date aujourd'hui).
- **Badges** : un mémo à plage affiche « 3 → 6 nov » (au lieu de la date seule) sur cards/plan/agenda — généré, plus besoin de l'écrire dans le titre.
- **« En retard »** : basé sur la **fin** quand elle existe (un hôtel en cours de séjour n'est PAS en retard ; en retard seulement après due_end). Adapter le tri/les sections (En cours aujourd'hui si `due_date ≤ auj ≤ due_end`).

## Agenda & frise voyage (la demande d'origine)

- **Agenda** ([AGENDA]/mois) : le mémo apparaît sur **chaque jour** de sa plage (rendu léger : barre continue ou répétition du chip — au plus simple compatible avec l'existant, pas de refonte).
- **Carte voyage / frise Jour N** ([MAP-TIMELINE]) : le chip « Jour N » inclut les mémos dont la **plage couvre** ce jour (`due_date ≤ jour ≤ due_end`) ; l'hôtel Osaka apparaît donc Jours 1-2-3-4 de son séjour ; la vignette numérotée et `applyDay` suivent la même règle ; le point reste UNIQUE sur la carte (pas de doublon de marqueur).
- Récap frise : un séjour affiche « 3→6 nov » dans sa tuile.

## Contraintes

- Lot = **V24.0.Z** (bump X → Y repart à 0, Z continue — convention). Migration additive, `py_compile`, `node --check`.
- Invariants 1 (bump documenté), 2 (import non destructif), 5 (les routes /share réutilisent la même validation — un éditeur invité peut poser une fin), 6/8/9.
- `_data_version` couvre `due_end` (poll invités).
- Rien d'autre ne bouge : votes, photos, vocaux, rôles intacts.

## Tests avant fin (copie de base)

1. Poser 3→6 nov sur l'hôtel Osaka → badge « 3 → 6 nov » ; frise : présent Jours 1..4 ; agenda : présent chaque jour ; « En retard » seulement après le 6.
2. `due_end < due_date` → 400 ; `due_end` sans date → 400 ; effacer la date → fin effacée ; récurrence + plage → 400.
3. Invité éditeur pose/retire une fin ; suiveur ne peut pas (matrice).
4. **Export v24 → ré-import base vierge** : plages reprises ; **import d'un export v23** : OK, due_end NULL, zéro régression ; re-export = v24.
5. Mémo sans plage : strictement identique à avant (badge, frise, agenda, retard).

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V24.0.Z] + IDEAS → Fait + CLAUDE.md invariant 1 v24) → rebuild (handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : parcours hôtel Osaka réel + tests 1-5.
