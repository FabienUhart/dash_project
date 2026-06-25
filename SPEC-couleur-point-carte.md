# Spec — Couleur de point personnalisable sur la carte

Statut : **implémenté** (export v16, APP_VERSION "16", 2026-06-25). Édition validée **depuis le détail du mémo ET la pop-in carte** (point 6 + section 10). Override exposé `point_color` côté partage. Voir l'entrée v16 du CLAUDE.md.

## 1. Objectif

En plus de la **couleur par défaut globale** (Paramètres → CARTE, clé `map_marker_color`, livrée précédemment), permettre de **changer la couleur d'un point précis** directement depuis la carte. Cas d'usage : faire ressortir un point particulier sans toucher à tous les autres ni à sa priorité.

## 2. Décisions validées

- **Édition depuis la carte** : on change la couleur en agissant sur le point dans la pop-in carte (pas dans la pop-in « Modifier le mémo »).
- **Priorité des couleurs** : la couleur perso du point **gagne** sur tout le reste.
- **Couleur perso prioritaire** s'applique aussi bien au point d'un mémo qu'au point d'un projet (les deux apparaissent sur la carte).

## 3. Résolution de la couleur d'un point (nouvel ordre)

Pour un **mémo** :

```
couleur perso du mémo  >  couleur de priorité  >  couleur par défaut (Paramètres)
```

Pour un **point de projet** :

```
couleur perso du projet (marker_color)  >  couleur du projet (projects.color)  >  vert #81c784
```

`marker_color` vide (`""`) = pas d'override → on retombe sur la logique actuelle. C'est ce qui garantit la compat ascendante : tous les éléments existants ont `marker_color = ""` et gardent exactement leur rendu actuel.

> Rappel de l'existant : aujourd'hui `boardMapPoints()` (index.html) fait `couleur priorité || state.mapMarkerColor`, et le point de projet `projects.color || '#81c784'`. On insère juste `marker_color` **devant**.

## 4. Modèle de données

Deux nouvelles colonnes, ajoutées en migration **additive** dans `init_db()` (jamais destructif — invariant 1) :

| Table | Colonne | Type | Défaut | Validation |
|---|---|---|---|---|
| `memos` | `marker_color` | `TEXT` | `''` | `_clean_hex_color()` ou `''` |
| `projects` | `marker_color` | `TEXT` | `''` | `_clean_hex_color()` ou `''` |

Réutilise le helper déjà en place `_clean_hex_color(value, default)` (regex `^#[0-9a-fA-F]{6}$`), avec une variante « vide autorisé » : si la valeur est vide → on stocke `''` (suppression de l'override) ; sinon hex strict, jamais de HTML (cohérent avec l'invariant 6 et la validation de `map_marker_color`).

Migration (pattern identique aux colonnes récentes, ex. `title`/`assignees`) :

```python
if "marker_color" not in mcols:
    conn.execute("ALTER TABLE memos ADD COLUMN marker_color TEXT DEFAULT ''")
if "marker_color" not in pcols:
    conn.execute("ALTER TABLE projects ADD COLUMN marker_color TEXT DEFAULT ''")
```

## 5. API

### Propriétaire

- **Mémo** : pas de nouvelle route. On étend `_perform_memo_update()` (et donc `PUT /api/memos/<id>`) pour accepter un champ `marker_color` (présent = on met à jour, absent = inchangé ; `""` = on efface l'override). Ajout au `UPDATE memos SET …` et à `_memo_dict()` (déjà `dict(row)`, donc exposé automatiquement une fois la colonne créée — à vérifier qu'aucune sérialisation ne la masque).
- **Projet** : on étend `PUT /api/projects/<id>` (`update_project`) de la même façon avec `marker_color`.

### Invité (page partagée)

- Un invité **approuvé avec `can_edit`** peut changer la couleur d'un point dans le périmètre partagé, depuis la carte de `share.html` (`openShareMap()`).
- Route mémo : on étend le `PUT /share/<token>/memo/<id>` existant pour accepter `marker_color` (scope vérifié serveur, invité approuvé — invariant 5).
- Route projet : on étend `PUT /share/<token>/project` de la même façon.
- `_share_memo_dict()` et le dict projet de `share_data` exposent `marker_color` pour que la carte invité applique l'override (en plus de `marker_color` global déjà exposé via `payload["marker_color"]` = défaut).

> ⚠️ Ne pas confondre les deux `marker_color` dans `share_data` : `payload["marker_color"]` = **couleur par défaut globale** ; le `marker_color` de chaque mémo/projet = **override par point**. On peut renommer l'override en `point_color` côté payload pour lever l'ambiguïté si tu préfères (à décider).

## 6. UI — édition depuis la carte

La pop-in carte (`#map-dialog`, sur `index.html` ET `share.html`) a déjà un **panneau latéral listant les points** (`#map-list`), chaque ligne = une pastille de couleur + le titre, clic = centrage + popup.

Ajouts sur chaque ligne de la liste :

- Un petit **`<input type="color">`** (ou la pastille existante rendue cliquable) qui ouvre le sélecteur, pré-rempli avec la couleur courante du point.
- Un bouton **↺ / Défaut** par ligne pour effacer l'override (`marker_color = ""`) → le point reprend sa couleur de priorité / projet / défaut.
- À la sélection : `PUT` sur le mémo/projet concerné, mise à jour de `state` (ou `DATA` côté invité), et **re-render de la carte** (le marqueur Leaflet `circleMarker` et la pastille de la liste changent immédiatement, sans recharger — comme validé pour le réglage global).

Détails :

- Le point doit savoir s'il vient d'un **mémo** ou d'un **projet** (pour choisir la bonne route). `boardMapPoints()` / `openShareMap()` poussent déjà des points typés implicitement (le point projet a un titre préfixé `📁`). On ajoute un champ explicite `kind` (`'memo'` | `'project'`) et l'`id` cible sur chaque point pour router proprement.
- Côté invité, l'input couleur n'apparaît que si `DATA.can_edit` est vrai.
- Respect de l'invariant 8 (animations) : aucune animation GSAP sur le `<dialog>` carte ; on ne touche qu'aux marqueurs et aux lignes de liste.

## 7. Export / Import — version 16

- **Export** : `marker_color` ajouté à chaque mémo et à chaque projet ; `version` passe à `16` ; `APP_VERSION = "16"` (footer « v16 »).
- **Import** : compat ascendante intégrale (invariant 1). Les exports v1→v15 n'ont pas `marker_color` → traité comme `""` (aucun override), donc aucun changement de rendu. Un export v16 réimporté restitue les overrides.
  - Application non destructive (invariant 2) : à l'upsert mémo (≈ `app.py:3279`/`3297`) et projet, `marker_color` suit la même règle que les autres champs — on enrichit / met à jour, on n'écrase pas un override existant avec une valeur plus ancienne lors d'un match sans uid.
- Mettre à jour la **ligne d'invariant 1** de `CLAUDE.md` (description de v16) et l'historique des évolutions.

## 8. Invariants respectés

1. Migration additive, jamais destructive (init_db ALTER + défaut `''`).
2. Import non destructif, compat v1→v15 garantie (champ absent = `''`).
4. Sans objet (pas de favicons / URLs).
5. Partage : écriture invité = `can_edit` + invité approuvé + scope vérifié, périmètre inchangé.
6. Pas de CDN, pas de HTML stocké (hex strict via `_clean_hex_color`).
8. Pas de GSAP sur le `<dialog>` carte.

## 9. Plan de test (avant commit)

```bash
python3 -m py_compile app.py
cp data/dashboard.db /tmp/test.db
DB_PATH=/tmp/test.db flask --app app run -p 8099
```

Scénarios :

1. **Migration** : démarrage sur base existante OK, `GET /api/memos` et `/api/projects` OK, `marker_color` présent et vide partout.
2. **Override mémo** : `PUT /api/memos/<id>` avec `marker_color:"#2e7d32"` → la carte affiche ce point en vert, **même s'il a une priorité P1** (perso gagne).
3. **Effacer l'override** : `PUT … marker_color:""` → le point reprend couleur priorité, sinon défaut Paramètres.
4. **Validation** : `marker_color:"red; <script>"` → rejeté, stocké `''`, aucun HTML.
5. **Projet** : idem sur un point de projet (override > `projects.color`).
6. **Export/Import** : export v16 → ré-import → 0 doublon, overrides restitués ; import v15 → aucun override, rendu identique à avant.
7. **Partage** : invité `can_edit` change la couleur d'un point de son périmètre → persiste, visible côté propriétaire ; invité lecture seule → pas d'input couleur.
8. **Navigateur** (Claude in Chrome) : changer la couleur d'un point depuis la carte, vérifier re-render live du marqueur + pastille, et persistance après rechargement.

## 10. Points ouverts à trancher

- **Nom du champ dans le payload de partage** : garder `marker_color` (risque de confusion avec le défaut global) ou renommer l'override en `point_color` ? *(reco : `point_color` pour l'override, `marker_color` reste le défaut global.)*
- **Couleur projet** : l'override projet est un `marker_color` distinct de `projects.color` (qui sert aussi la pastille sidebar). Confirmé qu'on ne veut PAS réutiliser `projects.color` (sinon changer la couleur d'un point changerait la pastille du projet partout).
- **Geste UI exact** : input color sur chaque ligne de la liste latérale (reco) vs clic droit / menu sur le marqueur lui-même.
