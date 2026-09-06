# Brief CC — [GUEST-ROLE-APPROVAL] : le propriétaire valide les délégations à enjeu

> **Back + front, doctrine TDD rouge-vert.** Décision Fabien (audit `docs/audits/AUDIT-ROLES-INVITES.md`) :
> on **encadre** la délégation, avec un **seuil**. Aujourd'hui un Admin invité agit **tout de suite** et
> l'owner n'est que **notifié** (doctrine inscrite l.934 : « NOTIFICATION, pas d'approbation préalable »).
> **On introduit un feu vert du propriétaire, mais seulement à partir d'un certain niveau** :
>
> - **Lecteur et commentateur** : un invité-admin les accorde **librement** (immédiat), comme
>   aujourd'hui — bas enjeu (« pour l'instant c'est la famille et des amis derrière l'app »). Toujours
>   journalisé et révocable.
> - **Contributeur, éditeur, modérateur, admin** : l'octroi par un invité devient une **proposition en
>   attente**, effective **seulement après approbation du propriétaire**.
>
> Le **seuil est une constante nommée** (`APPROVAL_MIN_RANK = _ROLE_RANK["contributor"]`), pour le
> remonter/descendre trivialement quand le public s'élargira. Le plafond reste **admin** (un invité peut
> toujours *proposer* jusqu'à admin) ; le journal et la révocation d'un clic restent en place (filet
> **après** coup, en plus du feu vert **avant**). Applicatif → rebuild local → **tag + Deploy** (prod
> actuelle : V27.42.254).

---

## 0. Ce qui change, en une phrase

Pour les rôles **à enjeu** (contributeur et au-dessus), l'**invité-admin devient un proposeur** et le
**propriétaire est le seul à finaliser** : l'octroi crée une **proposition en attente** qui ne touche
`guest_roles` qu'une fois **le propriétaire** l'a approuvée. Pour **lecteur et commentateur**, l'octroi
par un invité reste **immédiat** (comportement actuel), journalisé et révocable. Le tri se fait sur le
**rang du rôle visé** comparé à `APPROVAL_MIN_RANK`. Rien d'autre du modèle de rôles ne bouge
(capacités, périmètre sous-arbre, plafond admin, propriétaire intouchable, refus silencieux).

## 1. Les invariants à respecter (inchangés)

1. **Le serveur reste juge** (invariant 5). L'UI ne fait que refléter.
2. **Périmètre borné au sous-arbre** administré (`_admin_scope_ok` inchangé) : un invité ne propose que
   dans les dossiers qu'il administre.
3. **Cible = même lien**, **jamais soi-même**, **jamais le propriétaire** — gardes actuelles conservées.
4. **Plafond admin** : une proposition ne dépasse jamais `admin` (`ASSIGNABLE_ROLES`).
5. **Refus silencieux** : une proposition écartée par l'owner ne notifie rien au proposeur ni à la
   cible (même doctrine que les demandes actuelles).
6. **Le propriétaire, lui, n'est jamais mis en attente** : ses propres octrois (routes `/api/…`)
   restent **immédiats**. Il est le point de référence, pas un délégué.
7. **Le seuil est une constante** : `APPROVAL_MIN_RANK = _ROLE_RANK["contributor"]` (= 2). Un octroi
   invité dont le **rang du rôle visé ≥ APPROVAL_MIN_RANK** passe par la file ; **< APPROVAL_MIN_RANK**
   (lecteur 0, commentateur 1) est immédiat. Poser la constante près de `_ROLE_RANK` (~l.4985) avec un
   commentaire « seuil d'approbation owner — à remonter si le public s'élargit ». Le calcul du rang
   d'un octroi combinant `caps_add`/`caps_remove` : prendre le rang **effectif** du rôle résultant
   (au moins le rang du `role` nommé ; si des caps ajoutées dépassent, prendre le plus élevé — ne pas
   laisser un octroi « commentateur + cap éditer » filer sans feu vert).

## 2. Le correctif, route par route

Le seul chemin d'écriture d'un rôle reste `_apply_guest_role` (l.6583) — **on ne le double pas**. On
change **quand un invité a le droit de l'appeler tout de suite** : seulement pour lecteur/commentateur.
Au-dessus du seuil, les deux routes invité qui l'appellent aujourd'hui directement deviennent des
**créateurs de proposition**.

1. **`share_set_guest_role`** (PUT `/share/<token>/guests/<id>/role`, l.6630) — nomination directe par
   un invité-admin. Gardes actuelles **conservées** (approuvé, `administrer` sur le dossier visé,
   cible même lien, pas soi-même, plafond admin). **Changement** : calculer le rang du rôle visé.
   - **rang < `APPROVAL_MIN_RANK`** (lecteur/commentateur) → appelle `_apply_guest_role` **tout de
     suite**, exactement comme aujourd'hui (journalisé, révocable). Réponse « appliqué ».
   - **rang ≥ `APPROVAL_MIN_RANK`** (contributeur+) → **enregistre une proposition en attente**
     (actor = l'invité, cible, dossier, rôle, caps_add, caps_remove) et répond « en attente de
     validation ». `guest_roles` **n'est pas** touché.
2. **`share_decide_role_request`** (POST `/share/<token>/role-request/<req_id>`, l.6770) — quand un
   invité-admin **accorde** une demande d'un autre invité. Même seuil : accorder un **commentateur**
   (le plus haut de `REQUESTABLE_ROLES` côté demande est `editor`, mais en pratique une demande de
   commentateur) reste **immédiat** ; accorder **contributeur+** **crée une proposition en attente**
   (l'invité *endosse*, il ne finalise pas) ; « ignore » inchangé (silencieux). Quand c'est mis en
   attente, la demande d'origine peut être marquée « transmise » plutôt que « granted » — du moment que
   la cible ne gagne rien tant que l'owner n'a pas tranché.
3. **Côté propriétaire** — `decide_role_request` (POST `/api/role-requests/<id>`, l.7378) et les octrois
   owner `/api/…` : **finalisent** (appellent `_apply_guest_role`), **immédiats**, inchangés. C'est ici
   que la proposition d'un invité devient réelle : l'owner voit la file, approuve → `_apply_guest_role`
   s'exécute (journalisé, révocable), ou écarte → refus silencieux.
4. **`admin_actions` / révocation d'un clic** : **conservés**. La proposition approuvée passe par
   `_apply_guest_role(journal=True)` exactement comme aujourd'hui → l'owner garde le filet *après* coup
   en plus du feu vert *avant*. Mettre à jour le commentaire de doctrine l.934 (il dit le contraire).

## 3. Données (à toi le choix, contraintes imposées)

Il existe déjà une file d'approbation côté owner : table `role_requests` + `_pending_role_requests`
(l.7347) + `decide_role_request`. Elle est aujourd'hui taillée pour « un invité demande un rôle **pour
lui-même** » (colonnes `guest_id`, `project_id`, `role_requested`, plafond `REQUESTABLE_ROLES` =
commenter/editor).

Deux voies acceptables — **documente celle retenue au journal** :

- **(A) Étendre `role_requests`** : ajouter de quoi porter une proposition d'admin invité (proposeur
  `actor_guest_id`, cible `target_guest_id`, `caps_add`/`caps_remove`, et lever le plafond à `admin`
  pour ces lignes-là). Une seule file, un seul écran owner. Migration **additive** (colonnes nullables,
  `APP_VERSION` reste 27, non exportée — comme les tables voisines).
- **(B) Nouvelle table `pending_grants`** dédiée aux propositions d'admin invité, à côté de
  `role_requests`. Plus propre conceptuellement, deux files à agréger côté owner.

Dans les deux cas : **additive, non exportée**, unicité raisonnable (une proposition vivante par
(cible, dossier) — une nouvelle remplace l'ancienne en attente, comme `guest_roles`).

## 4. Front

1. **Côté invité-admin** (`share.html` « Gérer les accès », `share_admin_view` l.6674) : le retour dépend
   du seuil. Pour **lecteur/commentateur**, le rôle s'applique et **s'affiche tout de suite** (comme
   aujourd'hui). Pour **contributeur+**, l'UI affiche **« Proposé — en attente de validation du
   propriétaire »** sur la personne (pas « Éditeur » comme si c'était fait) ; le rôle **effectif affiché
   ne change pas** tant que l'owner n'a pas validé (l'UI reflète le serveur, invariant 1). Réutiliser le
   style d'état « en attente » déjà présent pour les demandes. Le retour serveur de la route (« appliqué »
   vs « en attente ») pilote l'affichage — le front ne redécide pas le seuil (invariant 5).
2. **Côté propriétaire** (l'écran des demandes de rôle, `/api/role-requests`) : la file liste désormais
   **aussi** les propositions des invités-admins, avec **qui propose**, **pour qui**, **quel rôle**,
   **quel dossier**. Approuver / écarter y sont les deux seules actions. Réutiliser l'écran existant
   (invariant 9), pas un nouveau panneau.
3. **Compteur / pastille** : si un indicateur « demandes en attente » existe déjà côté owner, il
   compte aussi ces propositions.

## 5. Tests (TDD — par une vraie porte, leçon des lots précédents)

**Back**
1. `test_guest_nomination_contributor_creates_pending` — un invité-admin appelle
   `PUT /share/<t>/guests/<id>/role` avec **contributeur** (≥ seuil), dans son sous-arbre → **200 « en
   attente »**, **aucune** ligne `guest_roles` écrite, une proposition en attente existe. Rouge avant
   (aujourd'hui c'est écrit direct) / vert après.
1bis. `test_guest_nomination_commenter_is_immediate` — même appel avec **commentateur** (< seuil) →
   `guest_roles` écrit **tout de suite**, `admin_actions` journalise, **aucune** proposition créée, la
   capacité `commenter` de la cible est active immédiatement. (Idem **lecteur**.) C'est la nuance Fabien :
   le droit de commentaire se donne librement.
2. `test_owner_approval_applies_role` — l'owner approuve cette proposition → `guest_roles` reçoit le
   rôle, `admin_actions` journalise, la proposition passe « approuvée ». La **capacité** de la cible
   change **seulement maintenant** (`_can` / `_memo_guest_caps` le prouvent).
3. `test_owner_reject_is_silent` — l'owner écarte → aucune écriture de rôle, proposition close, rien de
   signifié à la cible.
4. `test_guest_grant_of_request_also_pends` — un invité-admin « accorde » une demande d'un autre invité
   → crée une **proposition en attente** (ne finalise pas) ; la cible ne gagne toujours rien avant
   l'owner.
5. **Gardes conservées** (rouge attendu si on les retire) : hors sous-arbre → 403 ; cible autre lien →
   404 ; soi-même → 403 ; rôle > admin → borné ; propriétaire jamais ciblable.
6. `test_owner_grant_is_immediate` — un octroi owner (`/api/…`) reste **immédiat** (non-régression :
   le feu vert ne s'applique **qu'aux invités**).

**Front (e2e / DOM)**
7. Invité-admin : après nomination, la personne affiche **« en attente »**, pas le nouveau rôle.
8. Owner : la file d'approbation montre la proposition (proposeur + cible + rôle + dossier) ; approuver
   la fait disparaître et le rôle devient effectif au rechargement.

**Mutation** : rebrancher `share_set_guest_role` sur `_apply_guest_role` direct (sans seuil) → #1
rougit ; abaisser `APPROVAL_MIN_RANK` à `commenter` (donc mettre le commentateur en attente) → #1bis
rougit ; rendre l'octroi owner « en attente » → #6 rougit.

## 6. Definition of Done

1. Un octroi **par un invité** de **contributeur ou plus** n'est effectif qu'après approbation **du
   propriétaire** (nomination directe **et** endossement de demande passent par la file). **Lecteur et
   commentateur** restent **immédiats** côté invité. Seuil = constante `APPROVAL_MIN_RANK`. Octrois
   owner immédiats. Plafond admin conservé. Gardes de périmètre/cible/soi/owner conservées. Refus
   silencieux.
2. `admin_actions` + révocation d'un clic **conservés** ; commentaire de doctrine l.934 **corrigé**.
3. Front : invité voit « en attente », owner voit la proposition dans la file existante (invariant 9).
4. `make test` **entièrement vert** ; tests §5 rouges avant / verts après ; mutations tuées.
5. `git status` : `app.py`, `templates/share.html` (+ l'écran owner des demandes : `index.html` ou
   partial), `tests/…`, `REALISATION.md`. Migration additive, `APP_VERSION` inchangée. Pas de `.idea`.
   Rebuild local.
6. **Vérif à l'œil Fabien** (le juge) : en invité-admin, nommer quelqu'un → « en attente » (rien ne
   change pour la cible) ; côté propriétaire, la demande apparaît → j'approuve → le rôle prend ; je peux
   toujours révoquer après coup. Une nomination refusée ne dit rien à personne.
7. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**, puis **tag + Deploy**.

## 7. Portée

Uniquement : **interposer l'approbation du propriétaire** entre un invité et l'écriture d'un rôle **à
enjeu** (contributeur+), lecteur/commentateur restant libres. Pas de nouvelle capacité, pas de refonte
du modèle de rôles, pas de changement de plafond, pas de nouveau langage visuel. Une intention : que
**la montée en droits qui compte** reste, in fine, une décision du propriétaire — sans retirer à
l'invité le droit de faire commenter librement, ni de **proposer** le reste dans son sous-arbre.
