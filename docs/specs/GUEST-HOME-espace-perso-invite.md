# [GUEST-HOME] — Espace personnel de l'invité (hors partages) + retrait du provisioning `guest_space`

**Brief pour Claude Code — lot V26.0.Z (⚠️ BUMP EXPORT v25 → v26, voir D6).**
Lire `CLAUDE.md` avant. Z = compteur continu de `REALISATION.md`.

## 1. Contexte

Constat Fabien (29 juil.) : le « dossier perso » actuel d'un invité est un sous-dossier
provisionné DANS le dossier partagé (`_provision_guest_spaces`, dossiers flagués
`guest_space`). Voulu : à la création de son compte, l'invité reçoit — UNE seule fois —
SON espace, HORS de tout dossier partagé, où il peut tout créer/modifier. Vérifié en vraie
base : l'ancien mécanisme est **inutilisé** (0 dossier `created_by`, 0 flag `guest_space`)
→ retrait propre possible, rien à migrer.

## 2. Décisions (tranchées avec Fabien — implémenter, ne pas rediscuter)

- **D1 — Création à l'APPROBATION, une fois par e-mail.** Helper idempotent
  `_ensure_guest_home(db, email, name)` appelé aux points où un invité devient `approved`
  (register par PIN — y c. ré-approbation d'un existant — ET approbation manuelle owner).
  Dédup GLOBALE par e-mail : s'il existe déjà un dossier dont `created_by` matche l'e-mail
  (match par `_voter_email`, robuste au renommage) sous « 👥 Invités », ne rien créer.
- **D2 — Emplacement** : dossier racine **« 👥 Invités »** (créé au premier besoin,
  `created_by=''` — il appartient à l'owner), contenant un dossier **« 🏠 Prénom »** par
  invité avec `created_by = « Nom <email> »`. Prénom = 1ᵉʳ mot du nom, repli partie locale
  de l'e-mail. Collision de nom entre frères (interdite depuis v25) → suffixe
  « · email-local » (pattern de l'ancien provisioning).
- **D3 — Accès invité = partage automatique dédié** : `shares` kind=project, target = son
  dossier, **role=editor**, PIN aléatoire, + entrée `share_guests` **auto-approuvée** pour
  cet e-mail (avec `guest_token`) → l'espace apparaît dans son **hub** comme les autres
  dossiers (« 🏠 Prénom »), sans PIN à saisir. Zéro nouveau mécanisme de droits : role
  editor + `_owns_guest_space_folder` (created_by) couvrent « il peut tout » (invariant 5,
  scope revalidé serveur comme partout).
- **D4 — RETRAIT de l'ancien provisioning** : supprimer `_provision_guest_spaces` et ses
  appels + le flag/UI « zone espace invités » (`guest_space`) des pop-ins projet. La
  COLONNE `projects.guest_space` reste en base, morte (invariant 1 — pas de migration
  destructive). **`role_floor` (zones) et `_owns_guest_space_folder` sont CONSERVÉS** —
  le second est le moteur de droits de D3. Journaliser le retrait (CLAUDE.md + REALISATION).
- **D5 — L'owner garde la main** : « 👥 Invités » et les espaces sont des projets normaux
  dans sa sidebar (supprimables — la suppression cascade déjà les partages). Révocation
  d'un invité ≠ suppression de son espace (les données restent ; hors périmètre V1).
- **D6 — BUMP EXPORT v26** : les projets émettent désormais **`created_by`** (les mémos
  l'ont déjà) — sans lui, après restauration sur base neuve, la dédup D1 et l'élévation
  par propriété seraient perdues (re-approbation → espace dupliqué). Import : restaure
  `created_by` (uid-d'abord comme v25) ; compat v1→v25 : absent → ''. `APP_VERSION="26"`,
  invariant 1 de CLAUDE.md + historique mis à jour. Les partages/guests ne sont toujours
  PAS exportés (secrets) : après restauration, une ré-approbation raccroche l'espace
  existant via la dédup created_by — c'est le comportement voulu.

## 2bis. AMENDEMENT D1 (29 juil., retour de test Fabien) — invités DÉJÀ approuvés

Le déclencheur « à l'approbation » ne couvre pas les invités approuvés AVANT le lot
(claude.test, marie, uhart_f… — plus aucun événement d'approbation ne se produira pour
eux). **Compléter par une provision PARESSEUSE** : appeler `_ensure_guest_home` (idempotent,
dédup par e-mail inchangée) aux points de LECTURE authentifiés :
- `hub_data` : juste après `_hub_proof` OK (à côté du `_touch_guest_seen`), AVANT de
  construire la réponse → l'espace apparaît dès le premier chargement du hub ;
- `share_data` (page /share directe) : si guest APPROUVÉ (même emplacement logique) —
  couvre les invités qui n'utilisent jamais leur hub.
Coût : un SELECT de dédup par requête (négligeable). Jamais pour un non-approuvé/anonyme.
Acceptation : hub d'un invité historique approuvé → « 🏠 Prénom » présent au premier
chargement, pas de doublon aux chargements suivants.

## 3. Points d'attention

- `share_register` : l'appel `_ensure_guest_home` vaut pour les nouveaux ET le chemin
  « existing → approved ». Approbation owner : même appel. Jamais pour un non-approuvé.
- Le hub liste les partages approuvés de l'e-mail → l'espace y apparaît sans travail
  supplémentaire ; vérifier l'ordre d'affichage (espace en tête si trivial, sinon tel quel).
- Suppression du dossier « 🏠 x » par l'owner puis ré-approbation du même invité → un
  nouvel espace est recréé (comportement attendu, dédup ne matche plus).
- `py_compile` + rendu Jinja ; tests sur COPIE de base (jamais `data/dashboard.db`).

## 4. Acceptation (validation Cowork ensuite)

1. Register PIN d'un nouvel invité [test] → « 👥 Invités »/« 🏠 Prénom » créés, partage
   auto editor, hub montre l'espace sans PIN ; il y crée mémo + sous-dossier + PJ, modifie
   et supprime tout (editor plein) ; il ne voit rien d'autre.
2. Approbation du MÊME e-mail sur un 2ᵉ lien → AUCUN 2ᵉ espace ; deux invités différents →
   deux espaces ; collision de prénom → suffixe.
3. UI owner : plus de flag « zone espace invités » ; `role_floor` fonctionne toujours.
4. Export v26 : `created_by` émis sur les projets ; ré-import complet = 0 ajout/0 doublon ;
   import d'un export v25 réel = OK (compat) ; après import sur base VIERGE +
   ré-approbation → l'espace existant est raccroché, pas dupliqué.
5. `python3 -m py_compile app.py` + `node --check` ; sauvegarde export à refaire par
   Fabien après déploiement (format v26).

## 5. Fin de réalisation

Journal IDEAS→REALISATION [V26.0.Z], rebuild local, handoff ready.
**Ni commit ni push** sans feu vert Fabien (validation Cowork d'abord — parcours complet
register → hub → espace, en local).
