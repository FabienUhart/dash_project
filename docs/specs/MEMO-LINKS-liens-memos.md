# [MEMO-LINKS] — Rattacher un mémo à un autre (liens symétriques + exposition consentie)

**Brief pour Claude Code — lot V27.Y.Z (⚠️ BUMP EXPORT v26 → v27, voir D8).**
Lire `CLAUDE.md` avant. Z = compteur continu de `REALISATION.md`.
Maquettes validées Fabien le 29 juil. (fiche `IDEAS.md` Quick wins).
**Tranches A + C VALIDÉES par Fabien le 30 juil. sur maquette cliquable**
(scénario Zà Zà ↔ Hôtel Florence de bout en bout : picker proches-d'abord,
chips 2 côtés pleine/pointillée, ×=délier, propositions par nuit dans la
frise, plafond 20). **Tranche B (exposition consentie) : décisions ci-dessous
encore À CONFIRMER par Fabien avant son lancement** — la tranche A n'en
dépend pas (lien privé↔partagé = 403 explicite tant que B n'est pas livrée).
**Lot découpé en 3 TRANCHES livrables séparément** (un handoff par tranche possible) :
- **Tranche A (V27.0.x)** : socle — table + export v27 + éditeur/chips + clic → éditeur.
- **Tranche B (V27.1.x)** : exposition consentie des mémos privés + versions invité.
- **Tranche C (V27.2.x)** : [TIMELINE-SUGGESTIONS] — héritage de fenêtre dans la frise.

## 1. Contexte

Aujourd'hui rien ne relie deux mémos entre eux : le resto « Trattoria Zà Zà » et
l'« Hôtel Florence 28→31 » coexistent sans rapport exprimable (les dossiers font la
hiérarchie, pas l'association). Voulu : un **lien symétrique** posable depuis l'éditeur,
visible des deux côtés, qui servira aussi de véhicule à deux mécanismes : l'**exposition
consentie** d'un mémo privé d'invité dans un partage ([GUEST-HOME]) et les
**propositions de la frise voyage** (un resto sans date hérite de la fenêtre de l'hôtel
auquel il est relié). Terrain de test : dossier démo « 🇮🇹 Italie (démo) » (id 76 local,
PERMANENT — Zà Zà sans date candidate au lien avec l'hôtel Florence).

## 2. Décisions — Tranche A : liens symétriques (V27.0.x)

- **D1 — Modèle : table additive `memo_links`** (`CREATE TABLE IF NOT EXISTS`, jamais
  destructif) : `id, src_memo_id, dst_memo_id, created_at, created_by`. Le lien est
  **symétrique en EFFET** (visible et suivable des deux côtés) mais **orienté en
  MÉMOIRE** : `src` = le mémo depuis lequel il a été posé (pilote le style des chips,
  D3). **Une seule ligne par paire** quel que soit le sens (garde unicité sur la paire
  non ordonnée — pas de doublon A→B + B→A, re-poser dans l'autre sens = no-op).
  Auto-lien interdit (400). **Plafond 20 liens par mémo** (400 explicite au-delà —
  garde-fou anti-dérive, pas un besoin réel). `created_by` = pattern v19 (`''` = owner,
  sinon « Nom <email> »). Suppression/purge d'un mémo → **liens purgés en cascade**
  (`_purge_memo_row`) ; mémo en **corbeille** → ses liens sont **masqués** partout mais
  conservés (restauration = ils reviennent ; purge définitive = supprimés).
- **D2 — Éditeur : section « 🔗 Relié à »** dans la pop-in d'édition (3 pages, sous les
  Photos/Fichiers) : champ de recherche **façon recherche globale** (mêmes helpers de
  matching titre/contenu), Entrée ou clic sur un résultat = pose le lien (chip ajoutée
  sans fermer l'éditeur), **×** sur une chip = délier (confirmation légère façon
  `confirmPopin` seulement si le lien porte une exposition consentie, D5 — sinon délier
  direct). Le **picker classe en tête les mémos géolocalisés PROCHES** du mémo courant
  quand il a une position (« à 400 m » — distance haversine, helper partagé dans le
  partial), puis les mémos du même dossier, puis le reste par pertinence texte.
- **D3 — Chips sur les cards, DES DEUX CÔTÉS** (board, 3 pages) : sur le mémo source,
  chip **bordure pleine** « 🔗 <titre du relié> » ; sur le mémo cible, chip **bordure
  pointillée** « ⤺ <titre> » (« référencé par »). Titre = `memoLeadText` tronqué
  (~30 car.). **Clic sur une chip = ouvre l'éditeur du mémo relié** (mécanique
  [MEMO-CARD-CLICK] : `openMemoEditor` direct, sans changer de vue ; côté invité, même
  ouverture que le clic card existant). Gabarits `.prio-btn`/tokens existants
  (invariant 9), pas de nouveau langage visuel.
- **D4 — Qui peut relier quoi (serveur décide, invariant 5)** : **owner** = tout
  (mono-base). **Invité** : routes sous `/share/...` uniquement, invité **approuvé**
  requis ; il peut relier deux mémos **du scope de son accès** selon sa capacité
  d'écriture (matrice [GUEST-ROLES] : éditeur oui ; commentateur/suiveur non — relier
  modifie la donnée), OU un mémo de **son espace perso** vers un mémo d'un partage
  (= exposition consentie, tranche B ; tant que la tranche B n'est pas livrée, ce cas
  répond **403 explicite**). Lien entre deux partages distincts d'un même invité :
  **hors périmètre V1** (403). Le scope est **revalidé serveur** à la pose ET à la
  lecture — le front ne décide jamais de ce qui est visible.
- **Exposition des liens dans les payloads** : émis avec les mémos (`_memo_dict` /
  `_share_memo_dict` : liste `links` [{memo_id, direction, title…}] bornée au scope du
  lecteur — un lien vers un mémo HORS scope de l'invité est **omis** silencieusement,
  jamais « titre visible mais 403 au clic »). Pas de nouvelle route de lecture.

## 3. Décisions — Tranche B : exposition consentie + versions invité (V27.1.x)

- **D5 — Exposer un mémo privé via un lien** ([GUEST-HOME]) : quand un invité relie un
  mémo de SON espace perso à un mémo d'un partage X → **pop-in d'avertissement**
  (« Ce mémo deviendra visible et modifiable par les invités de “X” ») avec consentement
  explicite (bouton « Exposer et relier »). **SEUL L'AUTEUR** du mémo privé
  (`created_by`) peut l'exposer — l'owner aussi, il voit tout (transparence : « privé »
  = vis-à-vis des AUTRES INVITÉS, pas de l'owner). Après consentement : **bandeau
  warning PERMANENT** sur le mémo dans son espace (« Visible et modifiable par les
  invités de X — Délier ») ; **Délier** (bouton du bandeau OU × de la chip) = le mémo
  redevient privé **instantanément**. Le mémo reste **UNIQUE** dans son espace (aucune
  copie) ; les autres invités du partage X le voient via la chip et dans le board avec
  la mention **« · de <Prénom> »** (nom seul, e-mail owner-only comme partout).
- **D6 — Écriture selon rôle du partage** : le mémo exposé est modifiable par les
  invités de X **selon leur rôle** (éditeur = tout, commentateur = commente,
  suiveur = lit) — l'élargissement de scope par lien consenti est appliqué **côté
  serveur** (les routes /share existantes acceptent le mémo exposé comme s'il était du
  scope, garde par la table des liens + consentement, invariant 5). L'auteur, lui,
  garde tout pouvoir sur son mémo. Le consentement est porté par le lien : **délier =
  fin d'accès immédiate** (aucun état résiduel).
- **D7 — Versions pour l'auteur invité** : routes d'historique/restauration de
  révisions ouvertes en `/share/...` pour **SES mémos** (garde auteur stricte par
  `created_by`, mêmes réponses que les routes owner correspondantes, scope revalidé) —
  filet si un autre invité abîme son mémo exposé. L'owner garde ses routes actuelles.

## 4. Décisions — Tranche C : [TIMELINE-SUGGESTIONS] (V27.2.x)

- **D9 — Héritage de fenêtre par LIEN explicite** (jamais de proximité GPS
  automatique) : dans la **frise voyage uniquement** (`tripMode`), un mémo **SANS date**
  relié à un mémo **À PLAGE** hérite de sa fenêtre : il apparaît sur chaque **nuit** de
  la plage ([TIMELINE-CALENDAR-DAYS]) en **chip « proposition »** — pointillée,
  discrète, visuellement distincte des étapes fermes — dans la tuile du jour ET dans le
  filtre jour de la carte (`applyDay`). Déplacer le séjour = les propositions suivent
  (zéro date sur le resto). Relié à un mémo daté SANS plage → proposition sur ce seul
  jour. Relié à plusieurs mémos datés → proposition sur l'union des fenêtres.
- **D10 — Les DEUX voies coexistent** (nuance Fabien) : poser À LA MAIN une plage sur
  un resto reste valide et le rend « ferme » ([MEMO-DATE-RANGE]) ; les GROUPES de la
  carte restent le filtre hotels/vols/restos dans tous les cas. Un mémo **daté** relié
  à une plage n'hérite de RIEN (sa date fait foi). Les propositions ne comptent pas
  dans `memoDaySet` (un jour couvert seulement par des propositions reste un jour
  « vide » côté chips calendaires — ce sont des suggestions, pas du planning).
- V2 (backlog, PAS dans ce lot) : suggestion proactive « N restos proches de cet
  hôtel — relier ? ».

## 5. Décision — export v27 (livrée avec la tranche A)

- **D8 — BUMP EXPORT v26 → v27** : les liens sont une donnée utilisateur réelle → ils
  voyagent. Export : liste top-level **`memo_links`** `[{src_uid, dst_uid, created_at,
  created_by}]` (uid de mémos, jamais d'id). Import **uid-d'abord** : les deux mémos
  résolus par uid (sinon lien ignoré, tolérant, jamais de 400), dédup par paire non
  ordonnée (`INSERT` conditionnel — ré-import v27 = 0 doublon), **additif non
  destructif**. Absent à l'import (v1→v26) = aucun lien = rendu identique, compat
  ascendante garantie (invariant 2). L'état d'exposition consentie est **implicite dans
  le lien** (pas de flag séparé) ; les partages n'étant pas exportés, après restauration
  sur base neuve un lien privé↔partagé retombe naturellement inerte jusqu'à
  ré-approbation (comportement voulu, pattern [GUEST-HOME] D6). `APP_VERSION="27"`,
  invariant 1 + historique CLAUDE.md mis à jour. **Sauvegarde export v27 à refaire par
  Fabien après déploiement.**

## 6. Points d'attention

- **Pas de hiérarchie, pas de cycle** : le lien est une association plate — aucune
  logique d'arbre, A↔B↔C autorisé, aucun parcours récursif nulle part (l'héritage D9
  se limite aux voisins DIRECTS du mémo sans date — profondeur 1, pas de transitivité).
- Chips : anti-débordement sur les cards (max ~3 chips + « +n » si plus, comme les
  pictos [CARD-PREVIEW]) ; jamais de HTML injecté (titres passés en texte).
- Tests sur COPIE de base (jamais `data/dashboard.db`) ; sonde bypass
  (`credentials:'omit'`) sur toute nouvelle route `/share/...` (invariant 5).
- `node --check` 4 surfaces, `py_compile`, rendu Jinja ; helpers partagés dans
  `_shared.js.html` (invariants 6/9) ; aucune lib nouvelle, aucun CDN.
- Ne PAS toucher à l'agenda général ni aux chips calendaires ([TIMELINE-CALENDAR-DAYS]
  reste la référence des jours) ; la tranche C consomme ses helpers (`tripRange`,
  `memoDays`) sans les modifier.

## 7. Acceptation (validation Cowork ensuite — Italie démo + Voyage Japon)

**Tranche A** : 1. Owner : relier Zà Zà ↔ Hôtel Florence depuis l'éditeur → chips des
deux côtés (pleine côté posé, pointillée en face), clic chip = éditeur du relié,
× = délier, re-poser dans l'autre sens = pas de doublon. 2. Invité éditeur : relier deux
mémos du partage OK ; suiveur → 403 ; lien vers un mémo hors scope jamais émis dans le
payload invité. 3. Corbeille : mémo supprimé → chips disparues ; restauré → revenues ;
purge → liens purgés. 4. Export v27 : `memo_links` par uid ; ré-import = 0 doublon ;
import v26 réel = OK, zéro lien, zéro crash.
**Tranche B** : 5. Invité relie un mémo de son espace à un partage → pop-in
d'avertissement, consentement, bandeau permanent, mention « · de <Prénom> » chez les
autres ; un AUTRE invité ne peut PAS exposer ce mémo (403). 6. Écriture selon rôle
(éditeur modifie, commentateur commente, suiveur lit) ; délier → 403 immédiat pour les
autres, bandeau disparu. 7. L'auteur invité voit l'historique de SON mémo et restaure
une révision ; il ne peut pas lister l'historique d'un mémo d'autrui (403).
**Tranche C** : 8. Zà Zà (sans date) reliée à l'hôtel Florence 28→31 → chip
« proposition » les nuits 28/29/30, dans la tuile ET le filtre jour ; déplacer le séjour
→ les propositions suivent ; poser une date réelle sur Zà Zà → la proposition devient
étape ferme (plus de pointillé). 9. Jour couvert uniquement par des propositions =
chip calendaire toujours « vide ». 10. Parité 3 pages sur tout.

## 8. Fin de réalisation

Une entrée `REALISATION.md` **par tranche** ([V27.0.Z] / [V27.1.Z] / [V27.2.Z]),
journal IDEAS→REALISATION, rebuild local, handoff ready à chaque tranche.
**Ni commit ni push** sans feu vert Fabien (validation Cowork de chaque tranche d'abord).
