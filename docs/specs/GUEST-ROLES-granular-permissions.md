# [GUEST-ROLES] — Rôles d'invités à 4 niveaux + overrides par mémo/dossier

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Contexte : voyage Japon (2 couples co-organisateurs + familles/amis qui suivent). Décisions Fabien : 4 rôles, et granularité par mémo (ex. ouvrir le VOTE d'un mémo même au rôle le plus bas).**

## Les 4 rôles (colonne additive `shares.role`)

1. **👁 Suiveur** (`viewer`) : voit tout le scope du partage (mémos, photos, carte, frise, fichiers), écoute les vocaux. Ne poste rien.
2. **💬 Commentateur** (`commenter`) : + commente (texte ET vocal), réagit 😊, vote. Le niveau familles/amis.
3. **➕ Contributeur** (`contributor`) : + ajoute mémos/photos/fichiers/vocaux, et modifie/supprime **uniquement SES ajouts** (match e-mail sur `created_by` — mémos v19, commentaires, attachments v22 : tout existe déjà).
4. **✏️ Éditeur** (`editor`) : tout modifier — le `can_edit` actuel.

**Migration additive** (invariant 1) : `shares.role TEXT DEFAULT ''` ; résolution `_share_role(share)` : `role` non vide sinon `can_edit=1 → editor` / `0 → viewer`. **`can_edit` n'est PAS supprimé** (jamais destructif) ; les liens existants gardent leur comportement à l'identique. Les partages ne sont pas exportés → **AUCUN changement du format d'export**.

⚠️ Compat comportementale assumée : aujourd'hui réactions et votes exigent seulement « approuvé » (pas can_edit) → un lien lecture existant passe `viewer` et PERD réactions/vote par défaut. Pour ne rien casser : à la migration, initialiser `role='commenter'` pour les shares `can_edit=0` existants (équivalent du comportement actuel), `editor` pour can_edit=1. Les nouveaux liens choisissent librement.

## Matrice serveur (le cœur — invariant 5, à écrire en UN endroit)

Helper unique `_require_role(share, action)` consulté par TOUTES les routes `/share/*` d'écriture ; actions → rôle minimal :

| action | minimum |
|---|---|
| lire / écouter / télécharger | viewer |
| commenter, vocal-commentaire, réagir, voter, marquer vu | commenter |
| créer mémo / sous-projet, uploader photo/fichier/vocal-mémo | contributor |
| modifier/supprimer SES propres items (`created_by` = son e-mail) | contributor |
| modifier/supprimer tout, grouper carte, déplacer, cocher les mémos des autres | editor |

- L'approbation (PIN/X-Guest-Token) reste requise pour TOUTE écriture, comme aujourd'hui.
- 403 générique (pas de fuite d'info), scope revalidé à chaque requête (rien ne change).
- Le hub route déjà vers les `/share/<token>` de chaque dossier : il hérite des rôles sans travail spécifique (vérifier que l'UI hub lit le rôle exposé pour masquer les contrôles).

## Overrides granulaires (la demande clé de Fabien)

- **Principe** : l'owner peut abaisser le rôle requis d'UNE action sur UN mémo (ou un dossier, héritable). Ex. : scrutin « resto du 5 » → vote ouvert aux `viewer` ; mémo « livre d'or » → commentaires ouverts aux `viewer`.
- **Actions overridables V1 : `vote` et `comment`** (commentaires + réactions + vocaux de commentaire). Les autres restent à la matrice — V2 si besoin.
- **Stockage** : colonnes additives **NON exportées** (précédent `vote_excluded`/voix v20 — donnée d'atelier, un ré-import ne les restaure pas, documenté) : `memos.perm_vote`, `memos.perm_comment`, `projects.perm_vote`, `projects.perm_comment` (`TEXT DEFAULT ''` = hérite). **Résolution héritable** pattern `_resolve_trip()` : mémo → son dossier → ancêtres → matrice du rôle. Un override ne peut qu'**abaisser** l'exigence (jamais interdire à un éditeur).
- **Config owner-only** : dans le détail du mémo (section « Droits invités », chips façon `.prio-btn` : Héritage / Ouvert à tous les invités) et dans la pop-in dossier. PAS configurable via `/share` (même un éditeur ne touche pas aux droits — owner-only strict).
- **Exposition** : `share_data`/hub `/data` exposent par mémo les capacités RÉSOLUES (`can_vote`, `can_comment`, booléens serveur) — l'UI invité affiche/masque selon ça, mais la vérité reste le serveur.

## Dossier « zone invités » — élévation de rôle par sous-arbre (idée Fabien, 23 juil. 2026, même lot)

Cas d'usage : un dossier « 🏖 Espace famille » dans le voyage où TOUS les invités du partage ont les droits entiers (créer, modifier, photos, vocaux — y compris entre eux), pendant que le reste du sous-arbre reste au rôle du lien.

- **Colonne additive `projects.role_floor`** (`TEXT DEFAULT ''` = hérite, sinon `commenter|contributor|editor`), **héritable** pattern `_resolve_trip()` : dans ce sous-arbre, le rôle effectif d'un invité = `max(rôle du partage, role_floor résolu)`. Élévation SEULEMENT (jamais d'abaissement — un éditeur reste éditeur partout).
- Résolution branchée dans le même `_require_role(share, action, memo|project)` que les overrides `perm_*` — UN seul point de vérité serveur.
- **Owner-only** (pop-in dossier, chips « Zone invités : héritage / commentateur / contributeur / éditeur ») ; PAS configurable via `/share`, même par un éditeur. **Non exporté** (comme `perm_*`, précédent v20 documenté).
- Exposition : les capacités résolues par mémo/dossier déjà prévues (`can_vote`, `can_comment`, + `can_edit_item`, `can_create`) couvrent le cas — l'UI invité s'adapte sans logique nouvelle.
- Garde-fous : l'élévation s'applique au sous-arbre du dossier UNIQUEMENT (un déplacement de mémo HORS du dossier par un invité élevé = refusé si sa cible est hors de sa zone d'édition) ; la corbeille/purge reste régie par les règles actuelles (suppression douce).
- Tests additionnels : invité `viewer` du parent → droits entiers dans la zone (création, édition d'un mémo d'un AUTRE invité, upload, vocal), 403 hors zone ; imbrication (zone dans zone) ; désactivation du floor → retour immédiat au rôle du lien (poll `_data_version`).
- NB : le montage « deux liens » (parent en lecture + sous-dossier modifiable, agrégés par le hub) fonctionne DÉJÀ aujourd'hui — `role_floor` en est la version un-seul-lien.

## Dossier personnel auto-provisionné par invité (idée Fabien, 23 juil. 2026)

Cas d'usage : chaque invité, dès la création de son compte, reçoit un dossier À SON NOM où il fait ce qu'il veut (mémos, sous-dossiers, photos, vocaux).

- **Flag additive `projects.guest_space`** (`INTEGER DEFAULT 0`, owner-only, non exporté) : marque un dossier « 🏖 Espace invités ».
- **Provision paresseuse et idempotente** : au premier accès d'un invité **approuvé** dont le partage couvre un dossier `guest_space` (déclencheur = `/share/<t>/data` ou hub `/data`, PAS de hook à l'approbation — plus simple et rejouable), le serveur crée s'il n'existe pas un sous-dossier au **prénom de l'invité**, rattaché par **e-mail** via une colonne additive **`projects.created_by`** (pattern `created_by` v19 des mémos ; **non exportée en V1**, documenté — un ré-import perd l'attribution, précédent perm_*/voix). Collision de prénoms → suffixe discret (« Marie · m.dupont »). Renommage d'invité ([GUEST-EDIT]) → l'attribution par e-mail survit, le nom du dossier n'est PAS réécrit (cosmétique, l'invité peut le renommer lui-même).
- **Droits dans SON dossier** : l'invité est **éditeur plein** sur tout le sous-arbre de son dossier (équivalent `role_floor=editor` personnel, résolu dans `_require_role` par match `created_by` = son e-mail sur le dossier racine perso) — y compris créer des sous-dossiers (route [GUEST-SUBPROJECT] existante), y déplacer SES mémos, renommer son dossier. **Chez les autres invités** : rôle du lien (défaut commentateur = ils voient et commentent les studios des autres — l'esprit famille ; l'owner peut abaisser via le rôle du lien).
- **Garde-fous** : pas de déplacement de contenu HORS de sa zone d'édition (même règle que role_floor) ; l'invité ne peut PAS supprimer son dossier racine perso (seulement son contenu — la suppression du dossier reste owner) ; suppression douce/corbeille inchangées ; l'owner voit et gère tout, badges d'attribution 👤 existants.
- **UI** : chip « 🏖 Espace invités » dans la pop-in dossier (owner) ; côté invité, son dossier apparaît naturellement dans l'arbre de son partage/hub (aucune UI dédiée nécessaire en V1).
- **Tests additionnels** : 1er accès invité approuvé → dossier créé une seule fois (rejouer /data ×3 = 1 dossier) ; deux invités même prénom → 2 dossiers distincts ; invité A éditeur chez lui, commentateur chez B (403 sur l'édition d'un mémo de B, commentaire OK) ; owner voit tout ; invité retiré → son dossier RESTE (contenu = données du voyage, précédent non destructif — l'owner décide).

## UI

- **Pop-in Partager + vue 🔗 Partages** : la bascule Lecture/Modifiable devient un sélecteur 4 rôles (chips, libellés + une ligne d'explication chacun) ; badges de rôle sur les accès existants ; QR/récap mis à jour.
- **Pages invité** : les contrôles s'affichent selon les capacités résolues (bouton Voter visible pour un suiveur si override, etc.). Un contributeur voit ✎/🗑 uniquement sur ses items.
- Réutiliser les tokens/patterns existants (invariant 9), rien de neuf visuellement.

## Contraintes

- **Export inchangé (v23)** : `role` (shares non exportés) + overrides (non exportés, documentés comme les voix). Lot = **V23.12.Z** — ou position choisie par Fabien dans la file ; Z = dernier `REALISATION.md` + 1.
- Invariants 1/2/5/6/8/9. Sonde bypass inutile (aucune route nouvelle) mais **revue systématique de CHAQUE route `/share` d'écriture** pour brancher `_require_role` — lister la correspondance route→action dans le message de fin.
- `_data_version` : + colonnes perm_* et role (changement de droits = les invités doivent voir l'UI changer au poll).

## Tests avant fin

1. Migration sur copie : liens existants inchangés en comportement (can_edit=0 → commenter : réagit/vote/commente comme avant ; can_edit=1 → editor).
2. Matrice : pour chaque rôle, une action permise et une refusée (403) — au minimum 8 cas serveur via fetch.
3. Contributeur : crée un mémo → peut l'éditer/supprimer ; ne peut PAS toucher un mémo owner (403) ; ses attachments idem.
4. Override vote : scrutin avec `perm_vote` ouvert → un `viewer` approuvé vote ; sans override → 403. Héritage dossier → mémos descendants.
5. Override commentaire : `viewer` commente (texte + vocal) sur le mémo ouvert, 403 ailleurs ; réactions suivent.
6. UI : sélecteur de rôle, badges Partages, contrôles invités affichés/masqués selon capacités résolues (owner + share + hub).
7. Export → ré-import : identique à avant (rien des rôles/overrides dans le JSON) ; `py_compile`.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` + `IDEAS.md` → Fait) → rebuild (handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : matrice serveur au fetch, parcours invité par rôle, overrides. **V2 (backlog)** : expiration des liens, mémos privés (masqués du partage), autres actions overridables.
