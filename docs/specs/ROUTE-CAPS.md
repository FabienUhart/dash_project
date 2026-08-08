# ROUTE-CAPS — toutes les routes `/share/*` et leur capacité

**[GUEST-ROLES-T1-AUDIT] — audit, 8 août 2026, code à V27.29.209. ANALYSE SEULE : aucune ligne de
code, de schéma ni de route n'a été touchée.** Tranche 1 de [`GUEST-ROLES-V2.md`](GUEST-ROLES-V2.md)
(§9 « audit COMPLET des routes `/share/*` »). Trace détaillée d'une écriture :
[`GUEST-ROLES-T1-TRACE.md`](GUEST-ROLES-T1-TRACE.md).

> **➜ SUITE DONNÉE — T1 livré en V27.30.210.** Ce document reste le **relevé de l'état d'avant** :
> il décrit le code à V27.29.209 et ne doit pas être réécrit au présent. Ce que T1 a changé, et
> ce qui reste ouvert, est consigné au **§9 « Après T1 »** en fin de document (et en détail dans
> `REALISATION.md`). Le tableau des routes garde donc sa valeur de carte : mêmes routes, mêmes
> capacités attendues — seules les gardes ont été mises en conformité.

**Périmètre** : les **49 décorateurs `@app.route` sous `/share/`** (partage + hub), relevés
exhaustivement dans `app.py`. Aucune route publique invité ne vit ailleurs (invariant 5 — vérifié :
`grep '@app.route("/share'` = 49 lignes, et aucun autre préfixe de premier niveau).

---

## 0. Comment lire le tableau

- **Garde actuelle** = ce que le code vérifie *aujourd'hui*, dans l'ordre.
  - `jeton` = `_share_by_token` / `_hub_by_token` seul ;
  - `approuvé` = `_guest_from_request` + `status == 'approved'` ;
  - `périmètre` = `_share_scope_memos` / `_project_descendants` recalculés serveur ;
  - `matrice:<action>` = `_role_allows(db, share, '<action>', …)` avec son contexte ;
  - `auteur` = match par e-mail (`_voter_key`) sur `created_by` / `author`.
- **Capacité requise** = vocabulaire de la spec V2 §2 (`voir` · `commenter` · `voter` · `cocher` ·
  `editer` · `creer-vote` · `moderer` · `administrer`). J'ajoute **`creer`** — la spec range « créer
  des mémos et sous-dossiers » dans `editer`, alors que le code en fait un rang distinct
  (`contributor`) ; voir écart **S1**.
- **Écart** = ce qui ne colle pas : vérifie trop peu, trop, ou pas comme la page voisine.

**Rappel du modèle actuel** (`app.py:4698-4855`) : 4 rôles cumulatifs
`viewer < commenter < contributor < editor`, matrice `_ACTION_MIN_ROLE` = `read/comment/react/vote/
create/own/edit`, rang **élevé** par `role_floor` (zone héritable) et par la propriété d'un dossier
perso, **abaissé** (jusqu'à `viewer`) par les overrides `perm_comment`/`perm_vote = 'all'`.

---

## 1. Lecture — le jeton seul suffit (aucune identité requise)

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 1 | `/share/assets/<name>` | GET | sert Quill/Leaflet/GSAP… | liste blanche `SHARE_ASSETS` | — | — |
| 2 | `/share/<token>` | GET | page invité | jeton | `voir` | — |
| 3 | `/share/<token>/manifest.webmanifest` | GET | manifest PWA généré | jeton | `voir` | — |
| 4 | `/share/<token>/data` | GET | **tout** le périmètre : mémos, commentaires, PJ, votes, membres, corbeille | jeton (+ `X-Guest-Token` **optionnel**, pour l'identité) | `voir` | **E1**, **E2** |
| 5 | `/share/<token>/me` | GET | statut de l'appelant | jeton | — | — |
| 6 | `/share/<token>/fx` | GET | taux BCE | jeton | `voir` | — |
| 7 | `/share/<token>/image/<name>` | GET | image (+`?size=t\|s`) | jeton + périmètre | `voir` | — |
| 8 | `/share/<token>/image-exif/<name>` | GET | EXIF | jeton + périmètre | `voir` | — |
| 9 | `/share/<token>/photos` | GET | calque photo | jeton + périmètre | `voir` | — |
| 10 | `/share/<token>/attachment/<id>` | GET | télécharge/affiche une PJ | jeton + `_attach_in_share_scope` | `voir` | — |
| 11 | `/share/<token>/project/<id>/files` | GET | vue Fichiers du sous-arbre | jeton + sous-arbre | `voir` | — |
| 12 | `/share/<token>/memo/<id>/download.zip` | GET | zip d'un mémo | jeton + périmètre | `voir` | — |
| 13 | `/share/<token>/project/<id>/download.zip` | GET | zip d'un dossier | jeton + sous-arbre | `voir` | — |
| 14 | `/share/<token>/festival-results` | GET | écran Résultats | jeton + périmètre | `voir` | — |

> **E1 — la lecture est ANONYME.** Aucune de ces 14 routes ne demande un invité approuvé : le jeton
> **est** le droit de lire. Conséquence directe pour la spec : les **interrupteurs §6** (« historique
> visible avant l'arrivée », « commentaires croisés ») **n'ont aucun point d'ancrage** sur un lecteur
> anonyme — on ne peut pas filtrer « ses fils » sans savoir qui c'est. Il faudra soit les réserver
> aux appelants identifiés (et assumer qu'un anonyme voit tout), soit exiger l'approbation pour lire
> quand un interrupteur est OFF (rupture de comportement, à trancher par Fabien).
>
> **E2 — `/data` ne connaît pas les capacités *de dossier*.** Il expose `can_add` par dossier (rang
> effectif ✅) mais `can_comment_default`/`can_vote_default` sont calculés sur le **rôle brut du
> lien**, et la **corbeille** n'est servie que si `_ROLE_RANK[my_role] >= contributor` — rôle brut
> lui aussi (`app.py:7552`). Un invité élevé par `role_floor` ou par son dossier perso a donc le
> droit de restaurer (la route dit oui) mais **ne voit pas la corbeille** (le payload dit non).
> Même écart côté hub (`app.py:7267`).

## 2. Identité — le PIN

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 15 | `/share/<token>/register` | POST | PIN → invité **approuvé** + `guest_token`, provisionne hub + espace perso | jeton + PIN + plafond 30/lien | — (porte d'entrée) | **E3** |

> **E3 — le PIN d'un partage n'est ni throttlé ni comparé à temps constant.** `hub_approve` a les
> deux (`_hub_pin_throttled` → 429, `hmac.compare_digest`) ; `share_register` n'a **ni l'un ni
> l'autre** (`app.py:7587`, comparaison `!=` directe). PIN à 4 chiffres = 10 000 essais, et le
> plafond de 30 `share_guests` ne freine rien : il est testé **après** le PIN, donc les échecs ne
> créent aucune ligne. **Portée à garder en tête** : il faut déjà détenir le jeton du lien (24
> octets), et ce jeton donne **déjà** toute la lecture (E1) — le PIN ne garde que l'**écriture**. Le
> scénario réel est donc « lien transféré dans un groupe WhatsApp » → un tiers passe de lecteur à
> contributeur. Asymétrie avec le hub, corrigeable en quelques lignes. Journalisé ⚠, **non corrigé
> ici** (le brief interdit le code).

## 3. Écriture — mémos et dossiers

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 16 | `/share/<token>/memos` | POST | crée un mémo | jeton + kind=project + approuvé + `matrice:create` **sur le dossier cible** | `creer` | — |
| 17 | `/share/<token>/memo/<id>` | PUT | **tout** modifier : contenu, titre, dates, priorité, assignés, carte, **`done`**, et **déplacer** (`create` sur la cible) | jeton + approuvé + périmètre + `matrice:own` | `editer` **+ `cocher`** | **S2** |
| 18 | `/share/<token>/memo/<id>` | DELETE | corbeille (douce) | idem + `matrice:own` | `editer` | — |
| 19 | `/share/<token>/memo/<id>/restore` | POST | restaure de la corbeille | idem + `matrice:own` | `editer` | voir **E2** |
| 20 | `/share/<token>/memo/<id>/images` | POST | ajoute une photo | approuvé + périmètre + `matrice:create` (ctx dossier ✅) | `creer` | — |
| 21 | `/share/<token>/memo/<id>/images/<name>` | DELETE | corbeille image [IMAGE-TRASH] | approuvé + périmètre + `matrice:own` | `editer` | — |
| 22 | `/share/<token>/memo/<id>/attachments` | POST | ajoute des PJ (**aussi le vocal**) | approuvé + périmètre + `matrice:create` (ctx dossier ✅) | `creer` | **S3** |
| 23 | `/share/<token>/project/<id>/attachments` | POST | PJ de dossier | `_role_gate(create, project_id)` ✅ | `creer` | — |
| 24 | `/share/<token>/attachment/<id>` | DELETE | supprime une PJ | approuvé + périmètre + `matrice:own` **sans contexte dossier** | `editer` | **E4** |
| 25 | `/share/<token>/projects` | POST | crée un sous-dossier | approuvé + kind=project + unicité (409) **puis** `matrice:create` | `creer` | **E5**, **S4** |
| 26 | `/share/<token>/project/<id>` | PUT | renomme / déplace / couleur / description | approuvé + périmètre + `matrice:edit` **sur ce dossier** (+ `edit` sur la cible du déplacement) | `editer` | — |
| 27 | `/share/<token>/geocode` | GET | recherche Nominatim | approuvé + `_role_gate(create)` **sans contexte** | `creer` | **E6** |

> **E4 — la PJ de mémo perd son contexte dossier.** `_role_allows(…, memo_row=r)` reçoit la ligne
> `attachments` : pour une PJ de **dossier**, `r['project_id']` est rempli (contexte correct) ; pour
> une PJ de **mémo** il est `NULL` → `_effective_rank` tombe sur le rang **brut du lien**. Un invité
> éditeur uniquement par `role_floor` ou par son dossier perso **peut déposer** une PJ (route 22,
> contexte ✅) et **ne peut pas la retirer** (route 24). Asymétrie réelle, reproductible.
>
> **E5 — l'unicité du nom est testée AVANT le droit.** `app.py:8120` renvoie `409 « un dossier de ce
> nom existe déjà »` alors que le contrôle de capacité est ligne `8123`. Un simple lecteur approuvé
> peut donc **sonder les noms de dossiers** du sous-arbre (409 vs 403). Fuite mineure, correction
> triviale (inverser deux blocs) — **pas faite ici**, c'est du code.
>
> **E6 — `geocode` sans contexte** : `_role_gate(db, share, "create")` sans `project_id` ⇒ rang brut
> du lien. Un invité élevé seulement dans sa zone ne peut pas géocoder alors qu'il peut créer.
> Cousin d'E4 et de **E7**.

## 4. Le fil — commentaires, réactions, scrutins de commentaire

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 28 | `/share/<token>/memo/<id>/comments` | POST | poste un message **ou un scrutin** (`/vote_choix`) | approuvé + périmètre + `matrice:comment` (overrides inclus) | `commenter` **+ `creer-vote`** | **S5** |
| 29 | `/share/<token>/comment/<id>` | DELETE | tombale sur **son** message | approuvé + périmètre + **auteur** (e-mail) | `commenter` (son propre) / `moderer` (celui d'autrui — **non implémenté**) | **S6** |
| 30 | `/share/<token>/comment/<id>/react` | POST | réaction emoji (toggle) | approuvé + périmètre + `matrice:react` + palette | `commenter` | — |
| 31 | `/share/<token>/comment-poll/<id>/vote` | POST | vote dans un scrutin de fil | approuvé + périmètre + `matrice:comment` | `voter` | **S7** |
| 32 | `/share/<token>/comment-poll/<id>/close` | POST | clôt son scrutin | idem + **auteur** | `creer-vote` / `moderer` | **S6** |
| 33 | `/share/<token>/memo/<id>/seen` | POST | accusé de lecture | approuvé + périmètre + `matrice:comment` **sans contexte** | `commenter` | **E7** |
| 34 | `/share/<token>/memo/<id>/links` | POST | relie deux mémos | approuvé + **les deux** dans le périmètre + `matrice:own` **sur les deux** | `editer` | — |
| 35 | `/share/<token>/memo/<id>/links/<other>` | DELETE | délie | idem | `editer` | — |

> **E7 — `seen` sans contexte projet** (`app.py:8729`, `_role_allows(…, "comment")` sans `memo_row`
> ni `project_id`) : rang brut du lien. Un lecteur élevé à commentateur par `role_floor` commente
> (route 28 ✅) mais ne pose pas d'accusé de lecture (route 33 ❌) — son 👁 manque au fil. Même
> famille qu'E4/E6 : **trois routes oublient de passer le contexte**, alors que tout le mécanisme
> d'élévation dépend de lui.

## 5. Votes de dossier (`memo_votes`, `votes` nommés, ❤️)

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 36 | `/share/<token>/memo/<id>/vote` | POST | vote (simple ou nommé) | approuvé + périmètre + `matrice:vote` + dossier ouvert (409 si clos) | `voter` | — |
| 37 | `/share/<token>/memo/<id>/heart` | POST | coup de cœur ❤️ | approuvé + périmètre + `matrice:vote` + anti-chevauchement | `voter` | — |
| 38 | `/share/<token>/votes` | POST | crée un scrutin nommé | approuvé + `matrice:create` **sur le dossier** + `_resolve_vote_create == 'guests'` | `creer-vote` | **S5** |
| 39 | `/share/<token>/votes/<vid>` | PUT | modifie un scrutin | approuvé + **créateur** + périmètre — **aucun contrôle de rang** | `creer-vote` | **E8** |
| 40 | `/share/<token>/votes/<vid>/close` | POST | clôt | idem | `creer-vote`/`moderer` | **E8** |
| 41 | `/share/<token>/votes/<vid>/reopen` | POST | rouvre | idem | `creer-vote`/`moderer` | **E8** |
| 42 | `/share/<token>/votes/<vid>/reset` | POST | **efface toutes les voix** | idem | `moderer` | **E8** |
| 43 | `/share/<token>/votes/<vid>` | DELETE | supprime le scrutin | idem | `moderer` | **E8** |

> **E8 — cinq routes ne regardent que « qui l'a créé », jamais le rôle actuel.**
> `_share_vote_guest_or_403` (`app.py:8570`) ne vérifie que l'**approbation** ; `_share_managed_vote`
> ajoute le périmètre et le match créateur. Résultat : un invité **rétrogradé à Lecteur** conserve
> le droit de rouvrir, réinitialiser (= effacer les voix de tout le monde) et supprimer les scrutins
> qu'il avait créés. C'est le seul endroit du repo où un droit **survit à la perte du rôle**. Dans le
> vocabulaire V2 : la capacité doit être **revérifiée à l'usage**, pas héritée de la création.

## 6. Hub (`/share/hub/<hub_token>/…`)

| # | Route | M | Ce qu'elle fait | Garde actuelle | Capacité V2 | Écart |
|---|---|---|---|---|---|---|
| 44 | `/share/hub/<hub_token>` | GET | coquille HTML (aucune donnée) | hub existe | — | — |
| 45 | `/share/hub/<hub_token>/manifest.webmanifest` | GET | manifest PWA | hub existe | — | — |
| 46 | `/share/hub/<hub_token>/fx` | GET | taux BCE | hub existe | `voir` | — |
| 47 | `/share/hub/<hub_token>/approve` | POST | PIN → cascade d'approbation de **cet e-mail** + cookie de session | PIN (temps constant) + throttle 429 | — | — |
| 48 | `/share/hub/<hub_token>/data` | GET | union des dossiers approuvés + `folders` (jetons) | `_hub_proof` (cookie **ou** `X-Guest-Token` approuvé) | `voir` | **E9** |
| 49 | `/share/hub/<hub_token>/send-link` | POST | se renvoie **son** lien par mail | `_hub_proof` + SMTP + 2/h | — | — |

> **Le hub n'a AUCUNE route d'écriture** — c'est une propriété structurante et elle tient : toute
> écriture du hub repart sur `/share/<token>/…` avec le `guest_token` du dossier concerné. Les
> gardes des sections 3-5 sont donc les **seules** portes d'écriture invité du repo. Le hub choisit
> juste *quel* partage porte l'action (`_hub_winner`, rôle le plus haut > spécificité > id).
>
> **E9 — `folders` ne filtre pas le statut** (`_hub_folders`, `app.py:5033`) : la requête lit
> `g.status` mais ne s'en sert pas. Un invité **révoqué** (`status='rejected'`) reçoit encore, dans
> le payload de son hub, le **jeton de partage** du dossier dont on vient de le retirer — et la
> lecture ne demande aucune approbation (E1). `hub.html:687` le persiste même en `localStorage` et
> `fallbackLauncher` en fait une tuile cliquable. **La révocation ne retire donc pas la lecture.**
> Journalisé ⚠ ; aucune correction ici (le brief l'interdit).

---

## 7. Récapitulatif des écarts

| Réf | Nature | Gravité | Où |
|---|---|---|---|
| **E1** | la lecture est anonyme → les interrupteurs §6 n'ont pas d'ancrage | spec | §1 |
| **E2** | corbeille + `can_*_default` calculés sur le rôle **brut**, pas effectif | incohérence | `7513`, `7552`, `7267` |
| **E3** | `share_register` : ni throttle ni comparaison à temps constant sur le PIN | ⚠ sécurité | `7587` |
| **E4** | PJ de mémo : contrôle sans contexte dossier (créer ✅ / supprimer ❌) | incohérence | `7969` |
| **E5** | unicité de nom testée avant le droit → sonde de noms par un lecteur | fuite mineure | `8120` |
| **E6** | `geocode` sans contexte dossier | incohérence | `8743` |
| **E7** | `seen` sans contexte dossier | incohérence | `8729` |
| **E8** | 5 routes de vote nommé : créateur ≥ rôle, droit survivant à la rétrogradation | ⚠ droits | `8570`, `8579` |
| **E9** | hub : jeton re-servi à un invité révoqué → révocation sans effet en lecture | ⚠ sécurité | `5033` |

**Dette annexe relevée au passage (aucune action ici)** :
- `_share_guest_or_403` (`app.py:7681`) est du **code mort** — zéro appelant, et il porte l'ancien
  modèle `can_edit` que la matrice a remplacé. À supprimer dans T1.
- `_role_gate` (`app.py:4967`) se documente comme « garde **unique** des routes `/share` d'écriture »
  mais n'est utilisé que par **2 routes sur 25** ; les 23 autres réécrivent le même préambule à la
  main. C'est exactement ce que T1 doit rassembler.

---

## 8. Surprises à trancher AVANT le code

**S1 — le rôle `contributor` n'existe pas dans la spec V2.** Le code a **4** rôles ; la spec en
propose **5** dont aucun ne correspond à `contributor` (= créer, et éditer **seulement ses propres**
items). §7 ne le mappe donc nulle part. Le promouvoir en Éditeur = donner à quelqu'un le droit de
modifier les mémos des autres ; le rétrograder en Commentateur = lui retirer la création. Les deux
violent « aucune perte de droits ». **Décision requise** : garder un 6ᵉ rôle (« Contributeur »,
entre Commentateur et Éditeur) ou faire de `creer` + `editer-les-siens` deux capacités atomiques
combinables. *(Ma recommandation : capacités atomiques `creer` et `editer`, la notion « les siens »
devenant une propriété de la ressource — c'est déjà ce que fait `_role_allows('own')`.)*

**S2 — `cocher` et `editer` n'ont pas de frontière de route.** La spec les sépare (cocher chez
l'Éditeur, mais capacité distincte). Or `done`, `subtasks`, le contenu, les dates et le déplacement
passent **tous** par le même `PUT /share/<token>/memo/<id>`. Séparer `cocher` de `editer` impose une
vérification **par champ** dans `_perform_memo_update`, pas par route. À dire explicitement dans la
spec, sinon T1 livrera une capacité `cocher` qui ne peut pas être accordée seule.

**S3 — le vocal invité traverse deux capacités.** `voiceCommentButton` uploade d'abord une PJ
(`creer`) puis poste le commentaire (`commenter`). Un « Commentateur » strict perd le micro. À
arbitrer : exception explicite (les PJ « audio de commentaire » relèvent de `commenter`) ou perte
assumée et annoncée.

**S4 — « Créateur = Admin de naissance » (§4) NE MARCHE PAS aujourd'hui.** La spec s'appuie sur
« le `created_by` v26 existe déjà ». Il existe — mais `share_add_project` (`app.py:8128`)
**n'écrit pas `created_by`** : un dossier créé par un invité via le partage naît avec
`created_by = ''`, c'est-à-dire **attribué au propriétaire**. Seul `_ensure_guest_home` renseigne ce
champ. Donc `_owns_guest_space_folder` ne reconnaît que l'espace perso auto-provisionné, jamais un
sous-dossier créé à la main. T1 doit **d'abord** poser `created_by` à la création invitée — et §4
doit dire que c'est un pré-requis, pas un acquis. (Effet de bord à cadrer : les dossiers déjà créés
par des invités sont, en base, indistinguables de ceux de Fabien — pas de rattrapage possible.)

**S5 — `creer-vote` est aujourd'hui accordé par DEUX mécanismes différents et incohérents.**
Un scrutin de **fil** (`/vote_choix`, route 28) ne coûte que `commenter` — décision assumée en
V27.29.207 (« créer un scrutin = commenter », zéro route nouvelle). Un scrutin de **dossier**
(route 38) exige `create` **et** le réglage `vote_create == 'guests'`. La spec V2 met les deux dans
une seule capacité `creer-vote` (« dossier ET `/vote_choix` ») : appliquée telle quelle, elle
**retirerait** `/vote_choix` aux Commentateurs, qui l'ont depuis trois jours. À trancher : deux
capacités distinctes, ou une seule au prix d'une régression.

**S6 — `moderer` n'existe nulle part.** Supprimer le message d'un autre, clore le scrutin d'un
autre, épingler : **aucune route invité ne le permet aujourd'hui** (seul l'auteur agit). La capacité
`moderer` de §2 est donc du **code entièrement neuf**, pas un re-câblage — elle ne relève pas de T1
(« comportement identique après migration »). À déplacer explicitement en T3/T4.

**S7 — deux axes de surcharge coexistent, la spec n'en connaît qu'un.** Le code a déjà :
(a) `role_floor` par dossier héritable = plancher pour **tous** les invités du sous-arbre ;
(b) `perm_comment`/`perm_vote = 'all'` par mémo ou dossier = abaissement du rang requis **pour tous** ;
(c) la propriété d'un dossier perso = éditeur plein dans son sous-arbre.
La spec §3 n'introduit que les surcharges **par invité** (`caps_add`/`caps_remove`). Les deux axes
sont légitimes et **orthogonaux** (par-ressource vs par-personne) : §8 doit dire lequel gagne quand
ils se contredisent, et surtout que le modèle de données **ne remplace pas** (a)/(b)/(c) — sinon
[GUEST-HOME] et les dossiers « ouverts au vote » cassent.

**S8 — §5 « rôle d'accueil par dossier » ≠ `role_floor`.** Les deux se ressemblent à s'y méprendre
et ne font pas la même chose : `role_floor` est un **plancher permanent** appliqué à tout le monde
en continu ; le rôle d'accueil est une **valeur initiale** copiée à l'arrivée, ensuite modifiable
par invité. Les nommer pareil dans le code garantit une confusion. À nommer distinctement dans §5
(`welcome_role` vs `role_floor`), et à décider si `role_floor` survit ou est absorbé.

**S9 — la migration §7 est déjà faite à moitié, et le mapping proposé est faux.** §7 parle de
« `role=editor`/`can_edit` → Éditeur ; `commenter` → Commentateur ; lecture seule → Lecteur ». En
base, `shares.role` porte déjà les 4 valeurs et `_share_role` retombe sur `can_edit` seulement quand
`role` est vide. La checklist de la passe Cowork doit donc porter sur `role` **et** sur les trois
axes d'élévation (S7), pas sur `can_edit` — sinon Marie « Lectrice résidente » sera déclarée
conforme alors qu'un `role_floor` de zone la fait commentatrice quelque part.

**S10 — pas de bump d'export, confirmé.** Contre-vérification demandée par §8 : `guest_roles`,
`role_requests` et les interrupteurs vivent tous sur `shares`/`share_guests`/tables neuves, **hors
export** (les partages ne sont pas exportés — invariant 1, v26 ne sort que `created_by` des projets).
**Aucune clef nouvelle dans le JSON v27 → `APP_VERSION` reste 27.** Seule exception à surveiller :
si T1 pose `created_by` sur les dossiers créés par un invité (**S4**), la valeur **est** exportée
(v26) — c'est un remplissage d'un champ existant, pas un nouveau champ : compat inchangée.

---

## 9. Après T1 (V27.30.210) — ce qui est fermé, ce qui reste

Livré le 8 août 2026. Le moteur de `_role_allows` a été remplacé par des **capacités atomiques**
(`_guest_caps` / `_can`), sans toucher au vocabulaire d'actions des 25 routes d'écriture.

| Réf | État | Comment |
|---|---|---|
| **E1** | **assumé** (§11.2) | la lecture anonyme par jeton ne change pas ; les interrupteurs §6 ne s'appliqueront qu'aux invités identifiés (T2/T3) |
| **E2** | **fermé** | corbeille, `can_add`, `can_create_vote` calculés sur les capacités effectives (share ET hub) |
| **E3** | **fermé** | `share_register` : throttle + `hmac.compare_digest`, parité hub (10 essais / 10 min) |
| **E4** | **fermé** | la PJ d'un mémo reçoit le dossier du mémo porteur comme contexte |
| **E5** | **fermé** | droit vérifié avant l'unicité de nom (plus de sonde par 409) |
| **E6** | **fermé** | `geocode` → `_can_anywhere(creer)` dans le périmètre, faute de cible |
| **E7** | **fermé** | `seen` reçoit le mémo comme contexte |
| **E8** | **fermé** | les 5 routes de vote nommé revérifient `creer-vote` **à l'usage** |
| **E9** | **fermé** | `_hub_folders` filtre `status = 'approved'` : la révocation retire enfin la lecture |
| **E10** | **fermé** | un `rejected` ne se ré-inscrit ni par le PIN du partage, ni par celui du hub |
| **S1** | **tranché** (§11.3) | `contributor` = Commentateur + `creer` ; pas de 6ᵉ rôle |
| **S2** | **fermé** | `cocher` vérifié **par champ** (`done`/`subtasks`), corps mixte rejeté en entier |
| **S3** | **tranché** (§11.5) | le micro relève de `commenter` |
| **S4** | **fermé** | `share_add_project` pose `created_by` (+ `_find_guest_home` borné, effet de bord neutralisé) |
| **S5** | **tranché** (§11.4) | `/vote_choix` reste à `commenter` ; `creer-vote` ne gouverne que les scrutins de dossier |
| **S6** | **reporté** T3/T4 | `moderer` reste sans route (capacité définie, jamais exigée) |
| **S7/S8** | **fermé** | préséance §11.6 implémentée ; `role_floor` (plancher permanent) et `welcome_role` (valeur d'arrivée, T2) restent deux choses distinctes |
| **S9** | **fait** | checklist ci-dessous |
| **S10** | **vérifié** | export toujours v27, aucune clef nouvelle (testé) |

**Checklist de migration (S9), relevée en base le 8/08 avant livraison** — lue sur `shares.role`
ET les trois axes d'élévation, jamais sur `can_edit` :

- 12 partages : **11 `editor`**, **1 `commenter`**. **Aucun `viewer`, aucun `contributor`.**
- **Aucun `role_floor`**, **aucun override `perm_comment`/`perm_vote`** sur un dossier ou un mémo.
- 20 invités, **tous `approved`** (aucun `rejected`, `pending` n'existe plus depuis [GUEST-AUTO-APPROVE]).
- Conclusion : la traduction en capacités **n'a aucun effet observable** sur les invités existants.
  Le seul écart théorique — un lien `contributor` perdrait la création de scrutin de DOSSIER, qui
  passe de `creer` à `creer-vote` — ne concerne **personne** (aucun lien de ce rôle).
- ⚠️ **À vérifier par Fabien, ce n'est pas un défaut de migration mais un désaccord entre la spec
  et la base** : le fil rouge décrit « Marie (Lectrice résidente, jamais d'écriture) », or en base
  **Marie est `editor` sur « Maison »**. Si l'intention est bien la lecture seule, c'est le rôle du
  LIEN qu'il faut corriger (page 🔗 Partages) — le moteur, lui, applique fidèlement ce qu'il lit.
