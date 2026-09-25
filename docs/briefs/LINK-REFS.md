# Brief CC — [LINK-REFS] : relier un lien à un mémo ou un dossier, dans les deux sens

> **Back + front, owner-only, export v28.** Maquette validée par Fabien le 6 sept. 2026
> (`docs/maquettes/maquette-link-refs.html` — « c'est ce que je veux »). Clôt son mémo prod 257
> (« rajouter une possibilité de rapport entre un lien et un mémo facilement »). Doctrine TDD.
> Prod actuelle : V27.44.259. **⚠ Ce lot bump le format d'export : X passe à 28 → tags V28.0.x.**

## 0. Ce qui change, en une phrase

Un **lien** (table `links`, vue Liens) peut être **relié** à un **mémo** ou à un **dossier** ; la relation est
symétrique et se voit des deux côtés : chips « Relié à » sur la card mémo (🔗 favicon + ↗), sur la card
lien (📝 / 📁) et une ligne « Liens reliés » sur le board d'un dossier ; un seul picker « Relier à… ».

## 1. Décisions (fermes — maquette validée)

1. **Clic sur un chip 🔗 depuis un mémo → la card du lien** dans la vue Liens (bascule de vue + scroll +
   surbrillance brève, gabarit du flash existant) ; le **↗** du chip (séparé par un filet) ouvre `url_public`
   (ou `url_local` à défaut) dans un nouvel onglet. Deux gestes, jamais d'ambiguïté.
2. **Clic 📝 depuis un lien → fiche du mémo** (`openMemoEditor`, comme le 👁) ; **clic 📁 → board du dossier**
   (`state.view='memos'; state.memoProject=id`).
3. **Ligne « Liens reliés » sur le board d'un dossier**, sous la description (~l.8868 `proj-desc`) — affichée
   **seulement** s'il y a au moins un lien relié (jamais de rangée vide), avec « + relier ».
4. **Un seul picker** « Relier « X » à… » (composant partagé, gabarit de `memoLinksSection` du partial
   ~l.4221 étendu par un `kinds`) : onglets Tout / 📝 Mémos / 📁 Dossiers / 🔗 Liens, préfixes `m#`/`p#`/`l#`,
   recherche via `searchFold`/`searchMatch` ([SEARCH-FOLD]), cases à cocher, « Relier ». Trois points
   d'entrée : éditeur de mémo (section « 🔗 Relié à », ~l.7453 `renderMeLinks`, qui montre déjà les liens
   mémo↔mémo — on y AJOUTE les 🔗, on ne crée pas une seconde section), pop-in d'édition du lien
   (`#link-dialog` ~l.2231, sous « Mémo »), board du dossier (« + relier »).
5. **Invités : exposition CONSENTIE, en lecture (tranche C).** Question Fabien du 6 sept. : « l'invité aurait
   droit aux relations des mémos auxquels il a droit ? » → **oui**, par le même principe que les liens mémo↔mémo
   v27 : ce qui est dans son périmètre se voit, le reste est omis. Relier un lien à un mémo/dossier partagé est
   un acte du propriétaire = son consentement à le montrer. Pour un mémo ou un dossier **dans le scope du jeton**,
   `_share_memo_dict` / hub `/data` portent `link_refs: [{name, url_public, og_domain}]` — **JAMAIS `url_local`,
   jamais la note `memo`, jamais les tags, jamais d'id/uid du lien** (la table `links` reste hors périmètre : on
   expose une *projection* de trois champs, pas le lien). Un lien sans `url_public` n'est pas exposé du tout
   (un service LAN n'a rien à faire chez un invité). Côté invité le chip 🔗 est **en lecture seule** (pas de
   « + relier », pas de ✕) et son clic ouvre **directement `url_public`** dans un nouvel onglet (il n'a pas de
   vue Liens où aller) ; pas de favicon (icône trait) pour ne pas ajouter de route image scopée. **Aucune route
   `/share/*` nouvelle** (invariant 5) — tout passe par les payloads existants. Écriture invitée : **non**, même
   `can_edit` (une tranche D si le besoin vient). Tests : #9 devient « projection stricte » (voir §7).
6. **Les liens mémo↔mémo (v27) ne bougent pas** : même rangée, les 🔗 s'y ajoutent.

## 2. Modèle — table additive `link_refs`

```
link_refs (id, link_id, kind TEXT CHECK(kind IN ('memo','project')), target_id INTEGER,
           created_at TEXT, created_by TEXT DEFAULT '',
           UNIQUE(link_id, kind, target_id))
```
`CREATE TABLE IF NOT EXISTS`, jamais destructive (invariant 1). `created_by` = pattern v19 (`''` = owner).
**Plafonds** : `LINK_REFS_MAX = 20` par lien ET par cible (400 explicite). **Cascade** : suppression du lien
(`delete_link` ~l.2023) → ses refs ; purge définitive d'un mémo (`_purge_memo_row`) → ses refs ; suppression
d'un dossier (`delete_project`) → ses refs. **Corbeille** : mémo en corbeille → ses refs **masquées partout
mais conservées** (restauration = elles reviennent), même doctrine que `memo_links`. Cible inexistante /
en corbeille à la création → 404. Auto-cohérence : un lien ne se relie pas à lui-même (kind ≠ link, rien à
faire).

## 3. Routes (owner, derrière Authelia — AUCUNE sous `/share/*`)

- `POST /api/links/<id>/refs` `{kind, target_id}` → 201 + lien à jour ; `DELETE /api/links/<id>/refs/<kind>/<target_id>` → 204.
- Miroirs de confort (mêmes gardes, même table) : `POST /api/memos/<id>/link-refs` `{link_id}` et
  `POST /api/projects/<id>/link-refs` `{link_id}` + leurs DELETE — pour que chaque point d'entrée écrive
  depuis son côté sans bricoler l'id du lien côté front. **Une seule fonction d'écriture** `_link_ref_add/_del`,
  jamais dupliquée.

## 4. Sérialisation (runtime-only, JAMAIS exportée — comme `links` de v27)

- `_memo_dict` : `link_refs: [{link_id, name, favicon, url_public, url_local, og_domain}]` (pas les og_*
  complets — juste de quoi dessiner le chip ; favicon = la route favicon existante).
- `LINK_FIELDS` / GET `/api/links` : `refs: [{kind, id, uid, title, emoji, project_id}]` (titre du mémo =
  `title || extrait`, nom du dossier).
- `/api/projects` : `link_refs: [{link_id, name, favicon, url_public}]` (pour la ligne du board).
- `_share_memo_dict` / hub : projection `link_refs: [{name, url_public, og_domain}]` **uniquement** pour un mémo/dossier
  dans le scope, uniquement les liens à `url_public` non vide (décision 5). Aucun autre champ, jamais.

## 5. Export v28 — ⚠ bump de format (invariant 1)

- `APP_VERSION = "28"` ; liste top-level **`link_refs`** `[{link_uid, kind, target_uid, created_at, created_by}]`
  — par **uid** (liens : `links.uid` v3 ; mémos : `memos.uid` ; dossiers : `projects.uid` v25), jamais d'id ;
  bornée aux objets exportés (sous-arbre [EXPORT-SUBTREE] inclus : une ref vers un lien/dossier hors
  sous-arbre est omise) ; refs des mémos en corbeille exclues.
- **Import** : uid-d'abord **tolérant** (uid inconnu → ref ignorée, jamais de 400), `INSERT OR IGNORE` sur la
  clé unique (ré-import v28 = 0 doublon), **additif non destructif** (une ref locale n'est jamais retirée),
  compteur `imported_link_refs` dans la réponse. Absent à l'import (v1→v27) = aucune ref = rendu identique
  → compat ascendante garantie (invariant 2).
- **À mettre à jour dans le même lot** : `CLAUDE.md` invariant 1 (entrée **v28** au bout de la liste, même
  gabarit que v27) + § Versionnage (« Actuellement 28 ») ; `tests/back/test_invariants.py` :
  `test_export_version_is_27` → **28** et le round-trip couvre `link_refs` ; README (modèle + API) ;
  `IDEAS.md`/`REALISATION.md` ; le footer suit `APP_VERSION`. **Tags : V28.0.260** puis V28.0.x.

## 6. Front (owner)

- **Chip 🔗** (partial, composant `linkRefChip`) : gabarit `.bdg`/chips existants, favicon 14 px (`onerror` →
  icône trait), nom ellipsé, ↗ à droite séparé par un filet, `stopPropagation` sur le ↗. Monochrome, tokens
  existants (invariant 9), aucune animation permanente ([[LUCIOLE]]).
- **Card mémo** (`memoPictosRow`/rangée « Relié à » existante) : les 🔗 après les 📝. **Card lien**
  (`linkCardEl`) : rangée « Relié à » avec 📝/📁 + « + relier », sous le bloc OG s'il existe. **Board dossier** :
  ligne « Liens reliés » (décision 3).
- **Picker** : décision 4. Candidats liens = `state.links` ; mémos = non supprimés ; dossiers = tous.
  Classement : proches-d'abord (même dossier / même sous-arbre) comme aujourd'hui, puis alphabétique foldé.
- **Navigation** : `goToLinkCard(id)` (vue Liens, `filterCat='all'` si la card serait masquée par le filtre de
  catégorie, scroll + flash) ; `goToProjectBoard(id)`.
- Re-rendu après écriture sans reload complet (comme `renderMeLinks`).

## 7. Tests (TDD — rouges avant)

**Back** (`tests/back/test_link_refs.py`) :
1. `test_add_ref_memo_and_project_symmetric` — POST côté lien puis lecture côté mémo/dossier ; et l'inverse.
2. `test_ref_unique_pair_and_caps` — doublon → idempotent (pas de 2e ligne) ; 21e → 400.
3. `test_ref_target_must_exist` — mémo inconnu / en corbeille / dossier inconnu → 404.
4. `test_refs_cascade_on_delete` — supprimer le lien, purger le mémo, supprimer le dossier → refs parties.
5. `test_trashed_memo_hides_refs_but_keeps_them` — corbeille → absentes des payloads ; restauration → de retour.
6. `test_export_v28_link_refs_by_uid_and_roundtrip` — export porte `version: 28` + `link_refs` par uid, sans
   id ; import sur base neuve → refs recréées ; ré-import = 0 doublon ; ref vers uid inconnu ignorée.
7. `test_v27_export_still_importable` — un export v27 (sans `link_refs`) s'importe, rendu identique.
8. `test_subtree_export_omits_out_of_scope_refs`.
9. `test_guest_link_refs_strict_projection` — pour un mémo dans le scope : `link_refs` présent avec EXACTEMENT
   les clés `{name, url_public, og_domain}` (assert sur l'ensemble des clés — `url_local`, `memo`, `tags`, `id`,
   `uid` absents) ; un lien sans `url_public` absent ; un mémo hors scope → pas de fuite ; aucune route
   `/share/**/refs` (POST invité → 404/405) ; hub idem.
10. Invariants : `test_export_version_is_28` (renommé), round-trip sans perte couvre `link_refs`.

**Front / e2e** (owner) : chip 🔗 sur la card mémo → clic → vue Liens + card du lien visible/flashée ;
↗ → nouvel onglet vers url_public (intercepter `window.open`/target) ; card lien → 📝 ouvre l'éditeur, 📁
ouvre le board ; board Finance → ligne « Liens reliés » présente si ref, absente sinon ; picker : onglets +
`l#actual` + « rentila » sans accent ; **share/hub** : la card du même mémo montre le chip 🔗 en lecture seule (pas de « + relier »), clic → `window.open(url_public)` ; un lien LAN-seul n'apparaît pas.

**Mutations** (toutes tuées) : retirer la cascade (#4 rougit) ; ajouter `url_local` (ou `id`) à la projection invitée (#9 rougit) ; exposer un lien sans `url_public` (#9 rougit) ; exporter `link_id` au lieu de `link_uid` (#6 rougit) ; retirer la tolérance uid inconnu (#6
rougit) ; ligne « Liens reliés » rendue à vide (e2e board rougit).

## 8. Découpe autorisée

**A = back + export v28 + tests** (V28.0.260), **B = front owner** (V28.0.261), **C = projection + chips invités** (V28.0.262) si indigeste — mais **un seul
train** au GO : on ne déploie pas un v28 sans son front.

## 9. Definition of Done

`make test` vert ; tests §7 rouges avant ; mutations tuées ; CLAUDE.md invariant 1 + Versionnage à jour ;
README ; REALISATION.md `[V28.0.260]`… ; IDEAS.md (retirer de la file) ; migration additive re-vérifiée sur la
vraie base ; export contre-vérifié par fetch (`version: 28`, `link_refs` par uid, zéro `id`) ; rebuild local ;
journal + handoff ; **STOP**. Commit/tag/push après passe Cowork + GO explicite de Fabien.
Vérif à l'œil Fabien : relier « Déclarer les loyers » à Rentila depuis l'éditeur, voir le chip, cliquer →
card Rentila, ↗ → site ; depuis Rentila, relier le dossier Finance → ligne sur le board.

---

## Addendum 25 sept. 2026 — filtre « Reliés » dans la vue Liens (demande Fabien)

Fabien veut « voir facilement les liens qui sont rattachés à des mémos ». Les chips 📝/📁 sur la card
(§1.1–1.2) le montrent lien par lien ; il manque la vue d'ensemble. **Ajout au périmètre, même train** :

1. **Un filtre « 📝 Reliés »** dans la vue Liens, à côté du tri de [LINK-SORT] (même rangée, `#links-actions`
   desktop / `#links-blockhead` mobile) : bascule à trois positions **Tous** (défaut) / **Reliés** (≥ 1 ref,
   mémo OU dossier) / **Non reliés** (0 ref). Front pur : `link.refs` est déjà dans la sérialisation runtime
   (§4), donc `visibleLinks()` filtre sur `(l.refs || []).length`. Persisté en `localStorage['dash:linkRefsFilter']`.
2. **Compteur** dans le libellé : « Reliés (12) » — calculé sur `state.links`, pas sur la liste filtrée.
3. **Un tri « Reliés d'abord »** n'est PAS ajouté (le filtre suffit ; un tri de plus brouillerait [LINK-SORT]).
4. **Composition** : filtre catégorie ∧ recherche ∧ filtre Reliés, puis tri. `visibleLinks()` reste la seule
   source de vérité du filtrage.
5. **Test e2e supplémentaire** (#12) : 3 liens, 1 relié à un mémo, 1 relié à un dossier, 1 sans ref → « Reliés »
   en montre 2 avec « (2) », « Non reliés » 1 ; retirer la ref (✕) fait basculer le lien en direct sans
   rechargement. Mutation : filtre calculé sur `refs.length > 1` (doit rougir).
6. **Invités** : rien (pas de vue Liens chez eux, §1.5 inchangé).
