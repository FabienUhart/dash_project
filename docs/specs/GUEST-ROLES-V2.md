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
- **Audit COMPLET des routes `/share/*`** : chaque route écrit sa capacité requise (tableau route→capacité à produire en tranche 1 — c'est le vrai chantier).
- Page **🔗 Partages V2** (fiche invité : rôle, surcharges, demandes, journal des actes d'admin) — **maquette Cowork avant la tranche UI**.
- [GUEST-PROFILE] (fiche, avatar, bandeau) s'appuie sur la même fiche invité — lot suivant de la file.
- Perfs : `can()` doit être O(1)-ish (cache par requête de la chaîne d'ancêtres).

## 10. Tranches de réalisation proposées
1. **T1 — Fondations serveur** : tables, `can()`, tableau route→capacité, audit + tests complets sur copie (aucun changement d'UI, comportement identique après migration).
2. **T2 — Accueil & demandes** : rôle d'accueil, message, demande de rôle, 🔔.
3. **T3 — Page Partages V2** (après maquette) : gestion rôles/surcharges/interrupteurs.
4. **T4 — Délégation Admin** (créateur de naissance, nomination, journal des actes).
5. **T5 — Magic-link** (évolution GUEST-MAIL).

*Fil rouge des passes : Marie (Lectrice résidente, jamais d'écriture), les copains VC (Commentateurs votants), les co-voyageurs Japon (Éditeurs), Phiphi (Admin de « Voyage eclipse »).*
