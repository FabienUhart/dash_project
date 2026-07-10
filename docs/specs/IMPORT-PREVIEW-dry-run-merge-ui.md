# [IMPORT-PREVIEW] — Prévisualisation d'import + résolution de conflits (V20.14)

**Statut : spec VERROUILLÉE (10 juil. 2026, maquettes v1+v2 validées par Fabien en session Cowork). Implémenter telle quelle ; tout écart = question avant code.**

## 1. Objectif

Le flux « ⬆ Importer un dossier ici » ([EXPORT-SUBTREE] V20.12) ne s'applique plus à l'aveugle : un **dry-run** analyse le fichier, une **pop-in de prévisualisation** montre l'arbre de ce qui va arriver (avec code couleur et bilan chiffré), les **conflits s'y résolvent** inline (fini le skip silencieux du mémo en corbeille), et **rien ne s'écrit** tant que l'utilisateur n'a pas cliqué « Importer N éléments ».

## 2. Décisions figées

- **D1 — Périmètre : UNIQUEMENT le flux « Importer un dossier ici »** (pop-in projet). L'import global des Paramètres (restauration de sauvegarde) reste STRICTEMENT inchangé — là-bas, des centaines d'uids existants sont le cas normal, pas un conflit. Un appel API direct sans dry-run garde aussi le comportement actuel (compat scripts).
- **D2 — Code couleur (maquette v2)** : 🟢 **vert = ajouté** ; 🟣 **violet = déjà présent → on fusionne dedans** (dossier retrouvé : jamais recréé ni modifié, il reçoit les nouveautés) ; ⚪ **gris = déjà présent à l'identique → ignoré** ; 🟠 **ambre = conflit à trancher**. **Légende affichée** sous l'arbre. Teintes via les tokens/couleurs existants du thème (les hex des maquettes = intention, pas valeur imposée) — 2 thèmes (invariant 9).
- **D3 — Stratégies de conflit** : ① **Écraser / Restaurer** (met à jour l'existant ; s'il est en corbeille, le restaure — résout le « mémo fantôme » du 10 juil.) ; ② **Dupliquer** (uid régénéré, copie propre — cohérence de sous-arbre : si son projet est dupliqué aussi, le mémo dupliqué pointe le projet dupliqué, jamais l'original) ; ③ **Ignorer** (comportement actuel, **pré-sélectionné par défaut**). Choix par élément ; si > 3 conflits, ajouter une rangée « Tout : Écraser / Dupliquer / Ignorer » qui pré-remplit les lignes (surcharge unitaire possible ensuite).
- **D4 — Rien n'est écrit avant confirmation.** Le dry-run est en lecture pure (aucune transaction, pas de bump `_data_version`). « Annuler » = zéro effet.

## 3. API (owner-only, derrière Authelia — rien côté /share)

- `POST /api/import?dry_run=1` (+ `target_parent_id` éventuel, mêmes validations que V20.12) : analyse **sans aucune écriture** → rapport JSON :
  - `projects`: arbre [{name, status: `new` | `merge` (existant retrouvé), children…}] ;
  - `memos`: [{uid, title, project_name, status: `new` | `skip` (identique) | `conflict`, conflict_kind: `active` | `trashed`, updated_local, updated_fichier}] ;
  - `bilan`: compteurs par état.
  - Distinction skip/conflict : uid présent ET (contenu différent OU en corbeille) → `conflict` ; uid présent et identique → `skip`. Critère de comparaison simple (updated_at et/ou hash des champs exportés) — choix exact documenté dans REALISATION.
- `POST /api/import` réel : accepte en plus `resolutions` dans le body : `{ "<uid>": "overwrite" | "duplicate" | "skip" }`. `overwrite` sur un mémo en corbeille = restauration (`deleted_at=''`) **dans le projet visé par l'import** ; `duplicate` = nouvel uid à la volée. Absent/uid non listé = `skip` (comportement actuel → un client existant qui n'envoie pas `resolutions` ne change pas de comportement).

## 4. UI (pop-in façon maquette v2, invariants 8/9)

Dialog : titre « Importer “<nom>” ici ? », ligne destination « 📁 <dossier cible> », **arbre indenté** avec badges pilules par état (D2), **ligne de résolution par conflit** (3 boutons, Ignorer pré-actif), **légende** des 4 couleurs, **bilan** (« 1 dossier + 2 mémos ajoutés · 2 retrouvés (fusion) · 1 ignoré · 1 conflit »), boutons Annuler / « **Importer N éléments** » (N = ajouts + résolutions ≠ ignorer ; N = 0 → bouton désactivé libellé « Rien à importer »). Pas de GSAP sur le `<dialog>` (invariant 8). Arbre long → zone scrollable dans la pop-in.

## 5. Cas limites

- Fichier sans aucun conflit → la pop-in s'affiche quand même (c'est la **prévisualisation**, pas juste l'arbitrage).
- Dossier racine du fichier déjà présent (match par nom, sémantique V20.12) → violet « on fusionne dedans », jamais dupliqué par défaut.
- Mémo fantôme (en corbeille, projet d'origine supprimé) → `conflict/trashed` ; « Restaurer » le re-rattache au projet correspondant de l'import.
- Fichier invalide / vide → erreur propre avant toute pop-in (400 existant).
- Deux imports simultanés : le dry-run n'ayant rien réservé, l'import réel revalide tout (les résolutions sur un uid disparu entre-temps → traité comme `new`).

## 6. Tests d'acceptation

1. Dry-run = zéro écriture (compteurs mémos/projets identiques avant/après, `_data_version` inchangé).
2. Rapport exact sur un fichier mixte (nouveau dossier + dossier existant + mémo nouveau + identique + conflit actif + conflit corbeille).
3. `overwrite` sur conflit corbeille → mémo restauré dans le bon projet, contenu mis à jour.
4. `duplicate` → nouvel uid, original intact (y compris s'il est en corbeille), cohérence projet dupliqué.
5. `skip`/absence de résolutions → strictement le comportement V20.12.
6. Résolutions mixtes en un seul import (1 overwrite + 1 duplicate + 1 skip).
7. Import global Paramètres : inchangé octet pour octet dans son comportement.
8. UI : pop-in conforme maquette (badges, légende, bilan, N dynamique, désactivation à 0), 2 thèmes.
9. `py_compile` + `node --check`. Export v20 inchangé. Invariants 1/2/8/9.

## 7. Hors périmètre

Affichage des « mémos fantômes » dans la vue Corbeille (fiche backlog séparée) ; conflits sur l'import global ; résolution côté invité.
