# Spec — [GUEST-ROLES V2] : rôles, capacités, délégation
**Rédigée par Cowork le 8 août 2026, arbitrages Fabien des 7-8 août (session-log). À valider par Fabien avant tout brief. Les tranches de réalisation sont en fin de document — AUCUN code avant validation.**

## 1. Principes
1. **Le serveur vérifie des CAPACITÉS, jamais des noms de rôles** — `can(invité, capacité, dossier)` est l'unique porte ; l'UI ne fait que refléter.
2. **Moindre privilège** : un invité arrive toujours au rôle d'accueil du dossier (défaut : Lecteur) ; tout le reste est explicite.
3. **L'owner (Fabien) est au-dessus de tout, partout, toujours** — aucun rôle invité ne peut le restreindre ni agir hors de son périmètre de partage (invariant 5 inchangé : tout vit sous `/share/*`, périmètre vérifié serveur).
4. **Additif et réversible** : tables/colonnes additives, aucune régression pour les invités existants (migration §7), tout acte d'administration est journalisé et révocable.

## 2. Capacités atomiques
`voir` · `commenter` (écrire, réagir, répondre) · `voter` (participer aux scrutins dossier ET commentaire) · `cocher` (listes) · `editer` (mémos : texte/date/priorité/photos/vocaux, créer des mémos et sous-dossiers) · `creer-vote` (dossier + `/vote_choix`) · `moderer` (tombale sur commentaire d'autrui, clore tout scrutin, épingler) · `administrer` (rôles des autres, demandes de rôle, interrupteurs du dossier, nommer jusqu'à Admin) · *(réservées : futures — ex. `exporter`)*

## 3. Rôles = préréglages (validés Fabien 8/08)
| Rôle | Capacités |
|---|---|
| **Lecteur** (accueil par défaut) | voir |
| **Commentateur** | + commenter, voter |
| **Éditeur** | + cocher, editer, creer-vote |
| **Modérateur** | + moderer |
| **Administrateur** | + administrer (sur son sous-arbre) |

- **Voter vit chez le Commentateur** (voter = une forme de parole) ; **cocher chez l'Éditeur** (cocher modifie la donnée).
- **Surcharges granulaires par invité** : sur la fiche d'un invité, ajouter/retirer une capacité à la pièce (ex. Lecteur + voter). Le rôle reste l'étiquette affichée ; la surcharge est listée à côté.

## 4. Administrateur & délégation (validé Fabien 8/08)
- **Créateur = Admin de naissance** : l'invité qui crée un sous-dossier (le `created_by` v26 existe déjà) est Administrateur de ce sous-dossier et de ses descendants.
- **Nomination** : l'owner — ou un Admin dans son sous-arbre — peut nommer un Admin sur n'importe quel dossier de ce sous-arbre.
- **Un Admin délègue jusqu'à Administrateur** (« comme eux »), borné à son sous-arbre. Vérification serveur : remonter la chaîne des ancêtres du dossier visé.
- **Garde-fous (décision Fabien : notification, PAS d'approbation préalable)** : chaque acte d'administration invité → entrée journalisée + 🔔 owner + visible page Partages (« Phiphi a nommé Zack Éditeur sur Voyage eclipse ») ; l'owner révoque tout d'un clic ; un Admin ne peut ni toucher l'owner, ni s'élever hors de son sous-arbre.

## 5. Accueil sécurisé (validé Fabien 7/08)
- **Rôle d'accueil par dossier** (défaut Lecteur, réglable par l'owner/Admin du dossier).
- **Message d'accueil paramétrable** affiché au nouvel approuvé : « Bienvenue — tu es Lecteur ; ton rôle sera défini, tu peux en faire la demande. »
- **Demande de rôle** : bouton côté invité (« demander : Commentateur / Éditeur… ») → 🔔 aux Admins du dossier + owner → accord en 1 clic. Réutilise le circuit d'approbation existant (PIN → approved), un étage au-dessus.
- **Deux étages de commande (ajout Fabien 8/08, scénario « lien collé dans WhatsApp »)** : le LIEN se modifie après coup (rôle d'accueil, message) — par défaut ça ne vaut que pour les FUTURS arrivants, puisque le rôle descend du lien vers l'invité à l'arrivée. Une action explicite « appliquer aussi aux invités déjà entrés par ce lien » propage le nouveau rôle d'accueil à tous ceux du lien, **en préservant les surcharges individuelles** (une personne ajustée à la main n'est jamais écrasée par une action de masse). Révoquer le lien reste possible sans toucher les invités déjà approuvés.
- **Magic-link (piste actée, tranche finale)** : le mail [GUEST-MAIL] évolue — lien signé à expiration qui identifie ET approuve d'office (zéro PIN à saisir, toujours zéro mot de passe : l'invariant « pas d'auth dans l'app » tient).

## 6. Trois interrupteurs par partage
| Interrupteur | Défaut (= comportement actuel, zéro rupture) |
|---|---|
| Historique visible avant l'arrivée (révisions/commentaires antérieurs à `approved_at`) | **ON** |
| Commentaires croisés entre invités (OFF = chacun ne voit que ses fils + owner) | **ON** |
| Votes (participation/création selon rôles) | **ON** |

## 7. Migration des invités existants
Mapping au déploiement, **aucune perte de droits** : partage `role=editor`/`can_edit` → **Éditeur** ; `commenter` → **Commentateur** ; lecture seule → **Lecteur**. (Marie, Nono, Phiphi, uhart_f, copains VC : à vérifier un par un dans la page Partages après migration — checklist de la passe Cowork.)

## 8. Données (esquisse — CC affine)
- Rôle et surcharges portés par **(invité × dossier)** avec héritage descendant : table additive `guest_roles(guest_id, project_id, role, caps_add, caps_remove, granted_by, granted_at)` ; absence de ligne = rôle d'accueil du dossier le plus proche.
- `role_requests(guest_id, project_id, role_requested, status, at)`.
- Interrupteurs : colonnes additives sur `shares` (ou table `share_settings`).
- **Export : invités/partages n'y sont pas aujourd'hui → pas de bump attendu** ; CC contre-vérifie (règle : aucune clef nouvelle dans le JSON v27).

## 9. Impacts & risques
- **Audit COMPLET des routes `/share/*`** : chaque route écrit sa capacité requise (tableau route→capacité à produire en tranche 1 — c'est le vrai chantier). **➜ FAIT (analyse seule, 8/08) : [`ROUTE-CAPS.md`](ROUTE-CAPS.md)** — les 49 routes `/share/*` et hub, leur garde actuelle, la capacité requise et 9 écarts (`E1`→`E9`) ; trace d'une écriture invitée à travers les 3 couches : [`GUEST-ROLES-T1-TRACE.md`](GUEST-ROLES-T1-TRACE.md). **10 surprises (`S1`→`S10`) y attendent un arbitrage AVANT le code** — notamment `S1` (le rôle `contributor` existant n'a pas d'équivalent dans les 5 rôles ci-dessus), `S4` (§4 « créateur = Admin de naissance » est inopérant : `share_add_project` n'écrit pas `created_by`) et `S5` (`/vote_choix` ne coûte aujourd'hui que `commenter`).
- Page **🔗 Partages V2** à DEUX ÉTAGES : fiche du LIEN (rôle d'accueil, message, propagation « pour tous », révocation) et fiche de l'INVITÉ (rôle, surcharges, demandes, journal des actes d'admin) — avec le **geste rapide** demandé par Fabien : depuis la fiche d'un invité, changer son rôle sur UN dossier en deux clics (dossier → rôle), sans passer par le lien. **Maquette Cowork avant la tranche UI**.
- [GUEST-PROFILE] (fiche, avatar, bandeau) s'appuie sur la même fiche invité — lot suivant de la file.
- Perfs : `can()` doit être O(1)-ish (cache par requête de la chaîne d'ancêtres).

## 10. Tranches de réalisation proposées
1. **T1 — Fondations serveur** : tables, `can()`, tableau route→capacité, audit + tests complets sur copie (aucun changement d'UI, comportement identique après migration).
2. **T2 — Accueil & demandes** : rôle d'accueil, message, demande de rôle, 🔔.
3. **T3 — Page Partages V2** (après maquette) : gestion rôles/surcharges/interrupteurs.
4. **T4 — Délégation Admin** (créateur de naissance, nomination, journal des actes).
5. **T5 — Magic-link** (évolution GUEST-MAIL).

*Fil rouge des passes : Marie (Éditrice résidente sur « Maison » — arbitrage Fabien 8/08 : la base disait vrai, cette phrase était fausse ; mes sessions de VALIDATION continuent de ne jamais écrire sous son identité), les copains VC (Commentateurs votants), les co-voyageurs Japon (Éditeurs), Phiphi (Admin de « Voyage eclipse »).*
## 11. Arbitrages de relecture — Fabien, 8/08/2026 (la spec est VALIDÉE avec ces amendements)

Rendus un à un après l'audit [GUEST-ROLES-T1-AUDIT] (`ROUTE-CAPS.md` §7-8). Ils PRIMENT sur les
sections précédentes en cas de contradiction.

1. **Trous de sécurité E3 · E5 · E8 · E9 · E10 → intégrés à T1** (pas de hotfix séparé). E10, trouvé
   par la contre-passe Cowork : `share_register` ré-approuve un invité RÉVOQUÉ qui connaît le PIN
   (`app.py:7595`, aucun test de `rejected`) — T1 le ferme (un `rejected` ne se ré-inscrit pas ; un
   message clair l'informe). E9 : `_hub_folders` filtre les statuts non approuvés. E8 : les 5 routes
   de vote nommé revérifient la capacité À L'USAGE (créateur ≥ rang courant), plus de droit
   survivant à la rétrogradation. E3 : throttle + `hmac.compare_digest` sur le PIN de partage
   (parité hub). E5 : contrôle de droit AVANT le test d'unicité (fin de la sonde de noms).
2. **E1 → les interrupteurs §6 ne s'appliquent qu'aux invités IDENTIFIÉS.** La lecture anonyme par
   jeton reste ce qu'elle est (zéro rupture) ; un anonyme voit ce que le lien montre.
3. **S1 → capacités atomiques.** `creer` et `editer` sont deux capacités séparées ; « éditer les
   siens » reste une propriété de la ressource (mécanique `own` existante). Le rôle `contributor`
   actuel migre en **Commentateur + surcharge `creer`** : aucune perte, aucun 6e rôle.
4. **S5 → `/vote_choix` reste au prix de `commenter`** (acté V27.29.207, zéro régression) ; la
   capacité `creer-vote` ne gouverne que les scrutins de DOSSIER. L'interrupteur Votes §6 coupe tout.
5. **S3 → le micro fait partie de `commenter`.** Exception explicite : la PJ « audio de
   commentaire » relève de `commenter`, pas de `creer`.
6. **S7/S8 → le PLUS PERMISSIF gagne** entre élévations par-ressource (`role_floor`, overrides
   `perm_* = 'all'`, dossier perso — les trois mécanismes SURVIVENT tels quels) et surcharges
   par-personne (`caps_add`) ; **exception : `caps_remove` est un retrait ciblé ABSOLU** qui tient
   même en zone élevée. Le rôle d'accueil est nommé **`welcome_role`** (valeur copiée à l'arrivée),
   distinct du plancher permanent `role_floor`.
7. **Défauts confirmés** : S2 — la séparation `cocher`/`editer` se vérifie PAR CHAMP dans
   `_perform_memo_update` (même PUT, la spec l'assume) ; S4 — T1 pose `created_by` à la création
   invitée AVANT tout §4 (pré-requis ; l'existant est irrattrapable, assumé ; champ v26 existant →
   pas de bump) ; S6 — `moderer` = code neuf, déplacé en T3/T4 ; S9 — la checklist de migration se
   fait sur `shares.role` ET les trois axes d'élévation, pas sur `can_edit` ; S10 — aucun bump
   d'export, `APP_VERSION` reste 27. Dette annexe : `_share_guest_or_403` (mort) supprimé en T1,
   `_role_gate` devient LE préambule unique des 25 routes d'écriture.
