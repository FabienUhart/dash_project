# SPEC — [HUB-DASHBOARD] Le hub devient un dashboard agrégé

**Statut : VERROUILLÉE — en attente de validation Fabien. Aucun code avant OK.**
Cible : **V19.5**. Suite de **[ONE-LINK-MULTI] (V19.4.7)**. Zone **SÉCURITÉ-SENSIBLE** (invariant 5).
Partage non exporté → **pas de bump du format d'export** (reste v19).
**Inverse la décision #4 d'ONE-LINK-MULTI** : `hub.html` n'est plus un lanceur de liens mais
un **mini-dashboard agrégé** montrant tout le contenu de l'invité d'un coup.

---

## 1. Cible (validée — « je veux tout »)

Après saisie du code, `/g/<hub_token>` affiche un dashboard invité **multi-racines** :
- **sidebar** listant tous les dossiers/sous-projets partagés (chaque share = une **racine**) ;
- **vue Plan globale** = arbre projets → sous-projets → mémos sur l'**union** de ses shares ;
- **Mémos / Carte / recherche** scopés à cette union ;
- **focalisation** d'un seul dossier possible via la sidebar, mais **par défaut il voit tout**.

C'est la **généralisation de `share.html`** (déjà un dashboard invité pour **1** share) à **N
racines**. Aucun contenu nouveau : strictement l'**union des shares approuvés** de l'e-mail.

---

## 2. Authentification du hub (preuve d'approbation — PAS de master token)

Problème : `/g/<hub_token>/data` doit n'être servi qu'à l'**invité approuvé** du hub, sans
inventer de jeton qui « ouvre tout ».

**Mécanisme retenu (zéro colonne, zéro master token)** : la **preuve = un `guest_token`
réel, approuvé, appartenant à l'e-mail du hub**. Ces `guest_token` ne sont remis au front que
par `POST /g/<hub_token>/approve` (qui exige le PIN) ou par le PIN direct d'un `/share`. Donc en
posséder un **prouve** que la personne a franchi un PIN légitime pour cet e-mail.

- À l'approbation, le front mémorise déjà `localStorage['dashguest:'+token]` par dossier
  (V19.4.7). Il mémorise **en plus** `localStorage['dashhubproof:'+hub_token]` = le `guest_token`
  d'un des dossiers (le 1er) → sert d'**en-tête de preuve** pour `/g/<hub_token>/data`.
- `GET /g/<hub_token>/data` exige l'en-tête **`X-Guest-Token`** ; le serveur valide :
  1. `hub = _hub_by_token(hub_token)` (sinon 404 neutre) ;
  2. il existe **un** `share_guests` avec `guest_token = X-Guest-Token`
     **ET** `lower(email) = hub.email` **ET** `status = 'approved'` (sinon **403** : « code requis »).
- **Aucun master token** : ce `guest_token` est un jeton de partage **déjà existant** ; chaque
  écriture passera par le `/share/<token>` correspondant, **revalidé serveur** (cf. §4).

> Conséquence : si le dossier servant de preuve est révoqué, le front retombe sur l'écran code
> (re-`approve`) — comportement sûr, pas de fuite.

---

## 3. Endpoint public `GET /g/<hub_token>/data` (lecture agrégée)

Construit l'**union des shares APPROUVÉS** de `hub.email` en **réutilisant** la logique
par-share existante (`_share_scope_memos`, `_project_descendants`, `_share_memo_dict`,
`_comment_dict`). = **fusion + déduplication de N `share_data`**.

### 3.1 Sélection des shares
```
shares_of_email = SELECT s.* FROM shares s JOIN share_guests g ON g.share_id = s.id
                  WHERE lower(g.email) = hub.email AND g.status = 'approved'
```
(un share peut apparaître une fois par e-mail — `g` unique par (share_id,email)).

### 3.2 Racines (sidebar)
- 1 **racine par share** : `kind='project'` → le projet cible (+ son arbre descendant) ;
  `kind='memo'` → le mémo seul (racine « mémo isolé »).
- Chaque racine porte `{ share_token, can_edit, kind, root_id|memo_id }`.

### 3.3 Projets & mémos (union dédupliquée)
- **Projets** : union des `_project_descendants(target)` de tous les shares `project`.
  Dédup par `id`. Chaque projet **tagué** `share_token` + `can_edit` du **share gagnant** (§3.5).
  `parent_id` conservé **tel quel** ; s'il pointe hors union (parent non partagé), il est
  **réécrit à `null`** côté payload (la racine devient ce projet) — l'arbre reste cohérent et
  **ne révèle jamais** un parent non partagé.
- **Mémos** : union des `_share_scope_memos(share)` de tous les shares. Dédup par `id`. Chaque
  mémo tagué `share_token` + `can_edit` gagnant. Commentaires inclus comme dans `share_data`.
- **Corbeille** : union des `_share_scope_memos(share, deleted=True)` des shares **can_edit**.

### 3.4 Champs globaux (comme `share_data`)
`priorities`, `marker_color` (défaut carte), `members` = **union** (propriétaire + invités
approuvés de **tous** les shares de l'e-mail, dédupliqués). `roots` (liste §3.2).
Pas de `root_id` unique → remplacé par `roots[]`. `kind` global = `'hub'`.

### 3.5 Chevauchement → **share gagnant** (déterministe, documenté)
Un item (projet/mémo) peut être couvert par plusieurs shares (parent partagé **et** enfant
partagé, droits différents). Le **share gagnant** d'un item, parmi les shares de l'e-mail qui
le **couvrent réellement** (donc une écriture y passera la revalidation scope) :
1. **`can_edit = 1` prioritaire** sur lecture seule (droit le plus permissif **applicable**) ;
2. puis **le plus spécifique** : plus petit `_project_descendants` couvrant l'item
   (= racine la plus proche) ;
3. puis **`shares.id` le plus petit** (stable).
→ `share_token` + `can_edit` de l'item = ceux du gagnant. Garantit que le `/share/<token>`
ciblé **couvre** l'item (revalidation serveur OK) et applique le **bon** droit.

> **Invariant 5** : on n'élargit jamais — un item n'est `can_edit` que s'il existe **au moins
> un** share **modifiable approuvé** qui le couvre déjà. Sinon lecture seule.

---

## 4. Écritures — routage par item (ZÉRO nouvelle route)

- Chaque item porte son `share_token` gagnant. Le front écrit vers les routes **existantes**
  `PUT/POST/DELETE /share/<share_token>/...` avec l'en-tête `X-Guest-Token =
  localStorage['dashguest:'+share_token]`.
- Le serveur **revalide le scope** sur chaque `/share/<token>` (inchangé : `_share_by_token`,
  `_guest_from_request` approuvé, `_share_scope_*`). Le hub **n'ajoute aucune route d'écriture**.
- Création d'un mémo / sous-projet : routée vers le `share_token` de la **racine/branche
  courante** (le projet sélectionné dans la sidebar). En vue globale sans sélection, la
  création cible la racine **can_edit** du projet choisi dans le sélecteur (réutilise le
  sélecteur de projet existant de `share.html`, restreint aux projets `can_edit`).
- Déplacement d'un mémo entre deux dossiers **de shares différents** : **hors périmètre V19.5**
  (le `/share/<t>/memo` PUT `project_id` ne valide que les cibles **dans son scope**). Le
  « Déplacer vers… » invité reste **intra-share** (cibles limitées au share courant), comme
  aujourd'hui. À documenter dans l'UI (déplacement inter-dossiers = côté propriétaire).

---

## 5. Front — généralisation de `share.html` → N racines

- **`hub.html`** charge `/g/<hub_token>/data`, pose un `DATA` **multi-racines** (même forme que
  `share.html` mais `roots[]` au lieu de `root_id`, et chaque projet/mémo porte `share_token`/
  `can_edit`).
- **Réutilisation** : extraire dans **`templates/partials/_shared.js.html`** les rendus
  **strictement identiques et sans état** entre `share.html` et `hub.html` (sidebar `tree`,
  vue Plan, cartes mémo, carte Leaflet via `runMapDialog` déjà mutualisé). Les helpers
  d'**écriture** prennent désormais le **token de l'item** en paramètre :
  `guestToken(token)` / `apiBase(token)` au lieu du `TOKEN` global.
- **`can_edit` par item** : un mémo d'un dossier lecture seule reste non éditable même si un
  autre dossier de l'invité est modifiable (droit = celui du share gagnant de CET item).
- **Repli lanceur** : si `roots.length === 1`, l'affichage est naturellement mono-dossier
  (équivalent visuel à `share.html`) ; le **lanceur V19.4.7** est conservé comme **fallback**
  si `/g/data` échoue (assets manquants, données indisponibles) → la liste de liens cliquables
  reste accessible.
- `share.html` **inchangé** pour les liens directs `/share/<token>` (un seul share).

---

## 6. Invariant 5 — analyse de sécurité (verrou)

- **Contenu = strictement l'union des shares APPROUVÉS** de l'e-mail. Chaque projet/mémo provient
  d'un `_share_scope_*` d'un share **approuvé** de cet e-mail. Jamais d'item hors de ces scopes.
- **Pas de master token** : la lecture exige un `guest_token` **réel approuvé de l'e-mail** ;
  chaque écriture passe par un `/share/<token>` **revalidé** serveur. Le hub n'ouvre **rien de
  plus** que ce que l'invité a déjà.
- **Droits par item** = ceux de son **share gagnant** ; jamais d'élévation (un item n'est
  `can_edit` que si un share modifiable approuvé le couvre).
- **Parent hors union réécrit à `null`** → l'arbre ne révèle jamais un projet non partagé.
- **Isolation inter-invités** : tous les SELECT filtrent `lower(email)=hub.email`. Le
  `guest_token` de preuve est lié à cet e-mail. Aucune route ne liste d'autres hubs/invités.
- **hub_token / pin / throttle / anti-énumération / cascade** : **inchangés** (V19.4.7).
  `GET /g/<hub_token>/data` répond **403 générique** sans preuve valide (pas de distinction
  hub-inexistant / preuve-invalide au-delà du 404 du hub lui-même).
- **Aucune route d'écriture nouvelle** : surface d'attaque = `GET /g/<hub_token>/data`
  (lecture, scope = union approuvée) uniquement.

---

## 7. Plan de tests (sur **copie** de la base)

1. **Union exacte** : x@ex.com a A(✏️) + B(👁). `/g/<hub>/data` (preuve = guest_token de A)
   → projets/mémos = exactement descendants(A) ∪ descendants(B), **rien d'autre**.
2. **Isolation** : y@ex.com (dossier C) ; le data de x ne contient jamais C ; celui de y jamais A/B.
3. **Droits par item** : éditer un mémo de A → `PUT /share/<tokenA>/memo/<id>` réussit ;
   éditer un mémo de B (lecture) → **403** (revalidation serveur), l'UI le présente non éditable.
4. **Routage write** : la requête part bien sur le `share_token` **gagnant** de l'item
   (vérifier l'URL appelée + `X-Guest-Token` = `dashguest:<tokenGagnant>`).
5. **Chevauchement** : parent P(👁) + enfant E(✏️) partagés au même e-mail ; un mémo de E est
   `can_edit=1` (gagnant = E), un mémo de P hors E est `can_edit=0`. Déterminisme stable.
6. **Preuve invalide** : `/g/<hub>/data` sans en-tête / avec un guest_token d'un AUTRE e-mail
   → **403** ; avec hub_token bidon → **404**.
7. **Révocation** : retirer le dossier A (DELETE share_guest) → A disparaît du data de x ;
   si A servait de preuve, le front re-demande le code (403 → écran PIN).
8. **(b) Retirer l'invité / (c)(d) rotations** : comportements V19.4.7 inchangés.
9. **Export / migration** : `/api/export` identique (v19, pas de `guest_hubs`/`shares`) ;
   `init_db()` idempotent ; aucune colonne ajoutée.
10. **Pas de master token** : grep/inspection — aucune route ne sert un scope hors des shares
    approuvés de l'e-mail ; toutes les écritures restent sur `/share/<token>` revalidés.

---

## 8. Périmètre — ce que le lot NE fait PAS

- Pas de déplacement de mémo **inter-dossiers/inter-shares** côté invité (intra-share seulement).
- Aucune nouvelle **route d'écriture** ; aucune modif des routes `/share/<token>/*` ni de leur scope.
- Pas de changement du format d'export/import (v19) ni du schéma (`guest_hubs` inchangée).
- Pas de fusion de `share.html` et `hub.html` en un seul fichier (réutilisation via le partial).

---

## 9. Auto-évaluation (grille AIDD)

| Critère | Score | Note |
|---|---|---|
| Clarté du besoin | 10/10 | « je veux tout », repris d'IDEAS.md |
| Réutilisation de l'existant | 9/10 | `_share_scope_*`/`_share_memo_dict`/`runMapDialog` réutilisés ; routes d'écriture **/share inchangées** ; 1 seul nouvel endpoint (lecture) |
| Sécurité (invariant 5) | 9/10 | union approuvée stricte, pas de master token, droits par item, parent hors-union masqué, throttle/anti-énum inchangés |
| Non-destructivité / compat | 10/10 | zéro colonne, export inchangé, `share.html` intact |
| Testabilité | 9/10 | 10 scénarios sur copie (union, isolation, droits, routage, chevauchement, preuve, révocation) |
| Périmètre maîtrisé | 8/10 | refactor front réel (généralisation N racines) — risque concentré côté rendu, borné par le repli lanceur |
| **Global** | **9/10** | verrouillable |

### Points à trancher avant build (décisions demandées)
1. **Preuve d'accès** : `X-Guest-Token` = un guest_token approuvé de l'e-mail (proposé, **zéro
   colonne**) — OK ? *(alternative : colonne `guest_hubs.session_token` émise à l'approbation ;
   plus « propre » conceptuellement mais ajoute une colonne et une rotation de session.)*
2. **Chevauchement** : règle gagnant = **can_edit > spécificité > id** (proposé) — OK ?
3. **Déplacement inter-dossiers** invité **hors périmètre** V19.5 (intra-share seulement) — OK ?
4. **Repli lanceur** conservé comme fallback (assets/données KO) — OK ? *(sinon page d'erreur simple.)*
5. **Création** (mémo/sous-projet) routée vers la **racine can_edit sélectionnée** ; sélecteur
   restreint aux projets `can_edit` — OK ?

---

**FIN DE SPEC — j'attends ta validation (et tes réponses aux 5 points) avant tout code.**
