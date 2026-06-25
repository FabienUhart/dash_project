# ADR-001 : Mutualiser les helpers front entre `index.html` (propriétaire) et `share.html` (invité)

**Statut :** Accepté — Option C (partial Jinja inliné au rendu)
**Date :** 2026-06-25
**Décideurs :** Fabien (mainteneur unique)

## Contexte

Le frontend est réparti en deux templates **autonomes** : `templates/index.html` (5603 lignes, dashboard propriétaire) et `templates/share.html` (2425 lignes, page invité). Chaque évolution récente (filtre carte par sous-projet, regroupement par provenance, sidebar façon `tree`, vue Plan, agrandissement du chevron) a dû être **codée deux fois**, une fois par template.

Mesure de la duplication : **~31 fonctions JS portent le même nom dans les deux fichiers**, dont :

- des **helpers purs / sans état** : `el`, `usableProjColor`, `provenanceColor`, `isFocused`, `isGroupFocused`, `isSubFocused`, `groupNames`, `hasUngrouped`, `notify`, `setTheme`, `countUp`, `stagger`, `announce`, `applyA11y`, `syncHeaderHeight`, plus toute la mécanique de mentions (`registerMentionBlot`, `addMentionMatcher`, `attachInputMention`, `setupMentions`) ;
- de la **logique de rendu carte** quasi identique : `draw`, `renderSubbar`, `renderGroupbar`, `renderSelbar`, `memoRow`, `node`, `buildRow`, `refresh` ;
- des fonctions de **rendu navigation** au nom identique mais à corps **différent** car les données diffèrent : `renderSidebar` (s'appuie sur `state` côté owner, sur `DATA` scopé côté invité).

À l'inverse, le **backend (`app.py`) est déjà factorisé** : 57 helpers privés, et les chemins owner/invité partagent la logique sensible — `update_memo` **et** `share_update_memo` appellent le même `_perform_memo_update(...)`, les validations (`_clean_location`, `_assignees_json`, `_map_groups_json`) sont communes. La dette est donc **frontend uniquement**.

**Forces en présence :**

- **Invariant 6** (CLAUDE.md) : « un seul fichier HTML, pas de séparation CSS/JS du code maison, pas de build ». C'est la cause directe de la duplication : deux fichiers autonomes ⇒ aucun module partagé ⇒ copier-coller.
- **Invariant 5** : la page invité est servie par des routes publiques `/share/...` (bypass Authelia) et doit rester strictement scopée ; `/static/` est derrière Authelia, donc tout asset chargé par l'invité doit passer par la liste blanche `/share/assets/<nom>`.
- **Contraintes projet** : auto-hébergement total (Zimaboard, pas de CDN runtime), pas d'étape de build, mainteneur unique, vanilla JS sans framework.

## Décision

Extraire les **helpers purs et la logique de rendu réellement commune** dans **une source unique**, et l'**inliner dans les deux templates au rendu Jinja** via `{% include %}`, plutôt que de continuer à dupliquer. On conserve ainsi une sortie HTML auto-contenue (l'esprit de l'invariant 6) tout en ayant **une seule source de vérité**.

Périmètre de la première passe : uniquement les fonctions **sans état et sans dépendance à `state`/`DATA`** (formatage, couleurs, connecteurs `tree`, maths de points de carte, accessibilité, mentions). Les fonctions de rendu liées aux données (`renderSidebar`, etc.) restent dupliquées pour l'instant (voir Conséquences).

## Options considérées

### Option A : Statu quo (duplication assumée)

| Dimension | Évaluation |
|-----------|------------|
| Complexité | Faible (rien à changer) |
| Coût | Élevé en maintenance continue (tout codé 2×, risque de divergence) |
| Évolutivité | Mauvaise (chaque feature owner+invité = double effort) |
| Familiarité | Maximale |

**Pour :** aucune décision à prendre ; invariant 6 intact.
**Contre :** divergence silencieuse déjà observée (la page invité a pris du retard sur owner) ; double effort à chaque évolution ; bugs corrigés d'un côté seulement.

### Option B : Fichier `static/shared.js` chargé via `<script src>`

| Dimension | Évaluation |
|-----------|------------|
| Complexité | Moyenne |
| Coût | Faible une fois en place |
| Évolutivité | Bonne |
| Familiarité | Bonne (déjà fait pour Quill/GSAP/Leaflet) |

**Pour :** une seule source ; cohérent avec l'auto-hébergement existant dans `static/` ; pas de build.
**Contre :** requête HTTP supplémentaire ; surtout, l'invité ne voit pas `/static/` (Authelia) → il faut **whitelister** le fichier dans `SHARE_ASSETS` / `/share/assets/<nom>` et gérer son chemin différemment selon owner/invité. La sortie n'est plus strictement « un seul fichier » (entorse plus nette à l'invariant 6).

### Option C : Partial Jinja `{% include %}` inliné au rendu *(recommandée)*

| Dimension | Évaluation |
|-----------|------------|
| Complexité | Faible à moyenne |
| Coût | Faible |
| Évolutivité | Bonne |
| Familiarité | Bonne (Flask/Jinja déjà utilisé pour rendre ces templates) |

Un fichier source unique, p. ex. `templates/partials/_shared.js.html`, contenant un bloc `<script>…</script>` avec les helpers purs, inclus dans les deux templates :

```jinja
{% include 'partials/_shared.js.html' %}
```

**Pour :** **une seule source de vérité** ; la sortie HTML reste **auto-contenue** (helpers inlinés au rendu) → l'esprit de l'invariant 6 est préservé ; **aucune requête HTTP en plus** ; **pas de whitelist `/share/assets`** (rien n'est servi séparément, donc invariant 5 non impacté) ; pas de build.
**Contre :** le code maison n'est plus dans un fichier `.html` unique au niveau **source** (mais l'output livré, lui, reste mono-fichier) ; nécessite de réécrire l'invariant 6 pour distinguer *source* et *sortie livrée*.

### Option D : Étape de build / framework (bundler, composants)

| Dimension | Évaluation |
|-----------|------------|
| Complexité | Élevée |
| Coût | Élevé (toolchain, CI, maintenance) |
| Évolutivité | Excellente |
| Familiarité | Faible / contraire à l'éthos du projet |

**Pour :** vraie modularité, composants partagés owner/invité.
**Contre :** introduit un build (contraire à un principe explicite), surdimensionné pour un mainteneur unique sur un Zimaboard. **Rejetée.**

## Analyse des trade-offs

Le cœur du choix oppose **auto-containment au niveau source** (invariant 6 littéral) et **DRY**. On ne peut pas avoir les deux tels quels. L'option C résout la tension en déplaçant la frontière : on garde l'auto-containment de la **sortie livrée** (ce qui comptait vraiment : pas de build, pas de dépendance runtime externe, page autonome) et on abandonne seulement l'auto-containment de la **source**, qui n'apportait aucune valeur — seulement de la duplication.

L'option B atteint le même but mais bute sur l'invariant 5 (servir un asset à l'invité = whitelist `/share/assets` + double chemin), ce que C évite entièrement puisque rien n'est servi séparément.

L'option A est la plus risquée à terme : la divergence owner/invité s'est déjà produite (la page invité accusait du retard), et elle se reproduira.

## Conséquences

- **Plus facile :** corriger un bug ou ajouter un helper une seule fois ; cohérence owner/invité garantie pour tout ce qui est mutualisé ; templates allégés.
- **Plus difficile / à revisiter :** il faut **réécrire l'invariant 6** pour distinguer « source » et « sortie livrée » (ex. : « la sortie HTML reste auto-contenue et sans build ; les helpers purs partagés vivent dans `templates/partials/_shared.js.html`, inclus au rendu »). Les fonctions de rendu dépendantes des données (`renderSidebar`, `renderTree`, board) restent dupliquées tant qu'on ne les a pas paramétrées par une couche d'accès aux données commune — chantier distinct, plus risqué à cause de l'invariant 5.
- **Vigilance :** ne mettre dans le partial **que** du code réellement identique et sans état ; ne jamais y faire fuiter de logique qui élargirait le périmètre de l'invité (invariant 5). Tester les deux pages après extraction.

## Action items

1. [x] Valider l'option C et mettre à jour **l'invariant 6** dans `CLAUDE.md` *(fait juin 2026)*.
2. [x] Créer `templates/partials/_shared.js.html` avec les helpers purs **réellement identiques** *(fait)*. Périmètre revu après diff params-aware : **10 fonctions** retenues — `usableProjColor`, `provenanceColor`, `setTheme`, `stagger`, `announce`, `syncHeaderHeight`, mentions (`registerMentionBlot`, `addMentionMatcher`, `attachInputMention`, `setupMentions`). **Écartées** : `el`, `notify`, `countUp`, `applyA11y` (corps **différents**) ; `isFocused`/`isGroupFocused`/`isSubFocused`/`groupNames`/`hasUngrouped` (**closures** du rendu carte, pas top-level → item 4).
3. [x] Ajouter `{% include 'partials/_shared.js.html' %}` dans `index.html` et `share.html`, supprimer les copies locales *(fait)*.
4. [x] *(fait juin 2026, v2)* Mutualisation de la **logique de rendu carte** : `openMapDialog`/`openShareMap` + internes (`draw`, `renderSubbar`, `renderGroupbar`, `renderSelbar`, `buildRow`, focus helpers) fusionnés en un seul `runMapDialog(cfg)` dans le partial ; chaque page = wrapper passant son config (données/persistance/sauvegardes). Prérequis : `el()` unifié rétro-compatible *(Phase 1)*.
5. [x] Vérifier non-régression : `py_compile` OK, `node --check` partial+pages OK, `GET /` et `GET /share/<token>` = 200, chaque helper inliné 1×/page *(fait ; vérif manuelle desktop/mobile à faire par le mainteneur)*.
6. [~] *(partiel juin 2026, v2)* Primitive d'arbre `treeConnector(ancestorsLast, isLast)` extraite dans le partial (partagée par les deux sidebars et vues Plan). La **fusion complète** des `renderSidebar`/`renderTree` reste volontairement **non faite** : assemblages de sections différents (owner = liens+catégories+projets+Plan+corbeille+partages ; invité = projets+Plan scopés), mauvais ratio risque/valeur.
