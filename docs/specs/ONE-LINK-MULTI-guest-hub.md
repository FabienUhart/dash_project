# SPEC — [ONE-LINK-MULTI] Un seul lien par invité (« hub »)

**Statut : VERROUILLÉE — en attente de validation Fabien. Aucun code avant OK.**
Cible : **V19.4**. Zone **SÉCURITÉ-SENSIBLE** (partage = invariant 5).
Partage non exporté → **pas de bump du format d'export** (reste v19).

---

## 1. Principe (validé)

Le lien appartient à la **personne (e-mail)**, pas au dossier.
Un invité = **un lien + un code stables, à vie**. Ajouter/retirer des dossiers change le
**contenu** de sa page hub, jamais le lien (`hub_token`) ni le code (`pin`).

Aujourd'hui (rappel de l'existant, inchangé) : un partage = 1 ligne `shares`
(token, kind, target_id, can_edit, pin) ; un accès = 1 ligne `share_guests`
(share_id, email, name, guest_token, status, approved_at). Le **même e-mail invité sur
3 dossiers = 3 lignes `share_guests`**, donc aujourd'hui 3 liens + 3 codes à envoyer.
Le hub résout ça **sans toucher au modèle existant** : il **agrège** ces lignes par e-mail.

---

## 2. Modèle de données (additif, non destructif)

Nouvelle table, créée par `init_db()` (`CREATE TABLE IF NOT EXISTS`, jamais de DROP) :

```
guest_hubs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT NOT NULL UNIQUE,      -- minuscule, normalisée comme partout
  name        TEXT DEFAULT '',           -- cosmétique (cohérent avec share_guests.name)
  hub_token   TEXT NOT NULL UNIQUE,      -- secrets.token_urlsafe(24), ≥16 chars
  pin         TEXT DEFAULT '',           -- code à 4 chiffres, lié à l'e-mail (pas au dossier)
  created_at  TEXT DEFAULT ''
)
```

- **Une ligne par e-mail.** `shares` / `share_guests` **inchangés** (réutilisés tels quels).
- Le hub n'ajoute **aucune** colonne aux tables existantes.
- `guest_hubs` et `shares`/`share_guests` ne sont **pas exportés** (déjà la règle) →
  `/api/export` et `/api/import` strictement **inchangés** (toujours v19).
- Migration : un seul bloc `CREATE TABLE IF NOT EXISTS` (idempotent multi-workers).

### Helper central
`_ensure_hub(db, email, name="") -> row` :
- normalise l'e-mail (`strip().lower()`), valide (`@`, ≤120) ;
- `SELECT … WHERE email=?` ; si absent → INSERT `hub_token=token_urlsafe(24)`,
  `pin = f"{secrets.randbelow(10000):04d}"`, `created_at=now` ;
- si présent et `name` fourni non vide → met à jour `name` (cosmétique, comme `rename`) ;
- renvoie la ligne (hub_token + pin stables).

---

## 3. Octroi (création / agrégation)

**« Partager » un projet/dossier à un e-mail** (chemin owner existant `POST /api/guests/grant`,
et toute approbation d'un `share_guests` pour un e-mail) **garantit le hub** :

1. crée/réutilise le `share` scopé (inchangé : `grant_guest_project`) ;
2. crée/approuve le `share_guests` (email, share_id) (inchangé) ;
3. **appelle `_ensure_hub(db, email, name)`** → garantit la ligne `guest_hubs`.

Partager **un autre dossier** (droits différents) au **même e-mail** :
- crée un nouveau `share` + `share_guests` (comme aujourd'hui) ;
- `_ensure_hub` retrouve le **même** hub (email UNIQUE) → **rien de nouveau à envoyer**,
  le dossier apparaît tout seul dans la page hub de la personne.

Points d'appel de `_ensure_hub` (tous les endroits où un e-mail devient invité approuvé) :
- `grant_guest_project` (octroi owner principal) ;
- `share_register` (auto-inscription invité par PIN sur un lien `/share/<token>`) ;
- `_guest_from_request` (création d'un `share_guests` approuvé) — par cohérence, pour que
  **tout** invité approuvé ait un hub.

> Idempotent : ces appels ne créent jamais de doublon (email UNIQUE), ne changent jamais
> un `hub_token`/`pin` existant.

---

## 4. Routes publiques (bypass Authelia, comme `/share`)

### 4.1 `GET /g/<hub_token>` → page hub
- Rend **`templates/hub.html`** (nouveau), shell statique (assets via `/share/assets/<name>`,
  liste blanche `SHARE_ASSETS` existante ; pas de Quill nécessaire — page de liste simple,
  CSS inline + favicon + éventuellement gsap déjà whitelisté). Aucune donnée invité dans
  le HTML rendu côté serveur (la liste vient d'un POST après code).
- `hub_token` introuvable → page neutre « lien invalide ou révoqué » (même esprit que
  `/share` invalide). **Pas d'énumération** : `hub_token` = 24 octets urlsafe, non devinable,
  `len ≥ 16` exigé.

### 4.2 `POST /g/<hub_token>/approve {pin}` → ouverture de session + liste
- Vérifie `hub_token` valide, puis `pin == hub.pin` (comparaison **constante**
  `hmac.compare_digest`, anti-timing). **Mauvais pin → 403 `{error}`** affiché **inline**
  (jamais d'`alert`, jamais de détail qui distingue « hub inexistant » de « pin faux » →
  message générique « code invalide »).
- Sur succès :
  1. **Cascade d'approbation** : `UPDATE share_guests SET status='approved', approved_at=now
     WHERE lower(email) = hub.email AND status != 'approved'` (n'affecte que CET e-mail).
  2. Renvoie le payload **scopé à cet e-mail uniquement** :
     ```
     { name, folders: [ {
         token,            // le share token existant
         guest_token,      // le guest_token de CE share_guests (pour ouvrir sans re-code)
         label,            // nom du projet / titre du mémo (jamais le contenu)
         emoji, color,     // déco projet (vide pour un mémo)
         kind,             // 'project' | 'memo'
         can_edit,         // ✏️/👁
         url               // "/share/<token>"
       } ] }
     ```
     `folders` = **exactement** les `share_guests` de cet e-mail (JOIN `shares`), cibles
     supprimées exclues. **Jamais** d'autres invités, jamais de PIN d'autres liens.
- **Brute-force PIN** : compteur en mémoire par `hub_token` (fenêtre glissante, ex. 10
  tentatives / 10 min → 429), même garde que le plafond `share_guests` existant. Pas de
  lockout persistant (pas de colonne).

### 4.3 Front `hub.html`
- Au chargement : si pas de session locale, affiche **un champ code** (4 chiffres) + le nom
  de la personne (générique si vide). POST approve.
- Sur succès : pour **chaque** folder, `localStorage.setItem('dashguest:'+token, guest_token)`
  → **pré-amorce** la clé que `share.html` lit déjà (`guestToken()` ligne 718) ⇒ ouvrir un
  dossier ne **re-demande pas** le code (invariant « un seul code »). Rend la liste cliquable
  (nom/emoji/couleur, badge ✏️/👁, lien `/share/<token>`).
- Persistance de session hub : `localStorage['dashhub:'+hub_token]` = payload `folders`
  (cache d'affichage). Au refresh, la page réutilise ce cache **et** les `dashguest:*` déjà
  posées ; un bouton « Actualiser » re-POST approve (re-demande le code) pour récupérer un
  dossier nouvellement partagé. **Aucun PIN stocké en clair** côté client.
- Mauvais code → erreur **inline** (`#hub-error`), champ code vidé + refocus, le reste intact
  (miroir du fix formulaire invité déjà en place).

> **Pourquoi le code reste nécessaire malgré `hub_token` secret** : `hub_token` liste les
> noms de dossiers de la personne ; le **PIN** garde la remise des `guest_token` (capacité
> d'écrire) et l'ouverture effective des `/share`. Deux facteurs : URL secrète + code.

---

## 5. Invariant 5 — analyse de sécurité (verrou)

- Le hub **n'expose jamais plus que l'union des `share_guests` déjà accordés à cet e-mail**.
  Il ne crée aucun accès ; il agrège des accès existants. Aucun élargissement de périmètre.
- **Chaque `/share/<token>` garde son propre contrôle de scope serveur** (`_share_scope_memos`,
  `_share_by_token`, vérif `guest["status"]=='approved'`) — **inchangé**. Le hub ne court-circuite
  aucune vérif : il se contente de poser le `guest_token` que `/share` validera lui-même.
- `pin` lié à l'**e-mail du hub** (un seul code pour la personne), distinct des `shares.pin`
  par dossier (qui restent valides pour l'auto-inscription directe sur un lien `/share`).
- **Pas de fuite inter-invités** : tous les SELECT du hub filtrent `lower(email)=hub.email`.
- **Pas d'énumération** : `hub_token` 24 o urlsafe ; réponses neutres si invalide ; PIN en
  comparaison constante + throttle ; messages d'erreur génériques.
- Nouvelle surface publique = `GET /g/<hub_token>` + `POST /g/<hub_token>/approve` uniquement,
  toutes deux **scopées à un seul e-mail** et **sans écriture hors approbation de ses propres
  share_guests**. Conforme à la règle « toute nouvelle route publique valide le token et reste
  dans le périmètre » (invariant 5).

---

## 6. Trois suppressions distinctes (UI 🔗 Partages) — bien séparées

| # | Action UI | Effet | Lien hub | Code |
|---|-----------|-------|----------|------|
| (a) | **« × » par dossier** | retire **ce** dossier pour cette personne | **inchangé** | inchangé |
| (b) | **« Retirer l'invité »** | coupe **tout** → lien **mort** | **détruit** | détruit |
| (c) | **« Régénérer le lien »** | **rotation** du `hub_token` (accès conservés) | **change** (nouvelle URL à renvoyer) | inchangé |
| (d) | **« Régénérer le code »** | **rotation** du `pin` (accès conservés) | inchangé | **change** (nouveau code à renvoyer) |

- **(a)** = `DELETE /api/guests/<id>` **existant** (supprime 1 `share_guests`). Le `share`
  survit pour les autres. Le dossier disparaît du hub. **Hub & pin inchangés.**
  (Si la personne n'a plus aucun `share_guests`, le hub devient vide mais **subsiste** —
  re-partager le re-remplit sans nouveau lien.)
- **(b)** `DELETE /api/hubs/<hub_token>` (nouveau) : `DELETE share_guests WHERE lower(email)=email`
  **puis** `DELETE guest_hubs WHERE id=…`. Le `hub_token` ne résout plus → lien mort. Les
  `shares` (dossiers) **subsistent** (peuvent servir d'autres invités). Re-partager =
  `_ensure_hub` recrée un **nouveau** hub (nouveau lien + nouveau code).
- **(c)** `POST /api/hubs/<hub_token>/rotate` (nouveau) : `UPDATE guest_hubs SET hub_token=<neuf>`.
  `share_guests`/`pin` **conservés** → accès intacts, **seule l'URL change**.
- **(d)** `POST /api/hubs/<hub_token>/rotate-pin` (nouveau) : `UPDATE guest_hubs SET pin=<neuf 4 chiffres>`.
  `hub_token`/`share_guests` **conservés** → accès intacts, **seul le code change**.
  **Découplé de (c) à dessein** : lien fuité ≠ code fuité, l'owner tourne l'un, l'autre, ou les deux.

> Garde-fou UI : (b) et (c) sont au niveau **en-tête de personne** avec confirmation
> (`confirmPopin`, danger pour (b)) ; (a) reste un **× discret par ligne dossier**. Libellés
> explicites pour ne pas « tout couper » par erreur.

---

## 7. UI propriétaire (🔗 Partages — section « INVITÉS par personne » existante)

Déjà groupé par e-mail. Ajouts au **niveau en-tête de chaque personne** :
- **UN lien-hub** `/<host>/g/<hub_token>` : bouton **Copier** + bouton **QR** (réutilise
  `GET /api/qr?data=` + la pop-in QR existante) ;
- **le code** (hub.pin) affiché (réutilise le style code existant) ;
- actions **(b) Retirer l'invité** (danger), **(c) Régénérer le lien** et **(d) Régénérer le code** (découplées).
- Les lignes par dossier gardent leur **× = (a)** + le badge ✏️/👁 + (existant) copie du
  `/share/<token>` individuel (toujours valable pour l'accès direct au dossier).

API owner pour alimenter cette UI :
- `GET /api/hubs` → `[{ email, name, hub_token, pin, folders_count }]` (un par e-mail ayant
  un hub) **ou** enrichissement de `GET /api/guests` (au choix à l'implémentation ; **owner-only**,
  derrière Authelia comme tout `/api/*`).
- `_ensure_hub` est aussi appelé à l'ouverture de la vue si un invité historique n'a pas
  encore de hub (rattrapage des invités d'avant le lot) — **idempotent**.

---

## 8. Plan de tests (sur **copie** de la base, jamais `data/dashboard.db`)

Migration & non-régression :
1. `python3 -m py_compile app.py` ; `init_db()` sur une base existante → l'app démarre,
   `guest_hubs` créée, **aucune** donnée touchée.
2. `/api/export` **identique** avant/après (pas de clé `guest_hubs`/`shares`), `version` = 19 ;
   ré-import d'un export complet → 0 ajout.

Fonctionnel hub :
3. Partager projet A (✏️) à `x@ex.com` → `guest_hubs` créé (1 lien + 1 code). Partager projet B
   (👁) au **même** e-mail → **même** `hub_token`/`pin`, B apparaît dans le hub.
4. `POST /g/<hub_token>/approve` **bon pin** → `folders` = exactement {A, B} avec leurs
   `guest_token` ; ouvrir `/share/<tokenA>` et `/share/<tokenB>` **sans re-code** (clé
   `dashguest:*` posée) ; écriture autorisée selon ✏️/👁.
5. **Mauvais pin** → 403 inline, aucune `folders`, aucun `guest_token` renvoyé.
6. **Isolation** : créer `y@ex.com` avec projet C ; `approve` du hub de `x` ne renvoie
   **jamais** C ; le hub de `y` ne renvoie jamais A/B. Aucun SELECT ne croise les e-mails.
7. **Énumération** : `GET /g/<hubtoken-bidon>` → page neutre ; `approve` sur token bidon →
   403 générique (indiscernable de mauvais pin).

Trois suppressions :
8. **(a)** `DELETE /api/guests/<idB>` → B retiré du hub ; A toujours là ; `hub_token`/`pin`
   inchangés ; `/share/<tokenB>` refuse l'écriture (plus de `share_guests` approuvé) mais le
   `share` B existe encore pour d'autres.
9. **(b)** `DELETE /api/hubs/<hub_token>` → `share_guests` de l'e-mail supprimés + hub supprimé ;
   `GET /g/<hub_token>` → lien mort ; `shares` A/B intacts ; re-partager A → **nouveau** hub
   (nouveau lien + code).
10. **(c)** `POST /api/hubs/<hub_token>/rotate` → nouveau `hub_token` ; ancien lien mort,
    nouveau lien liste A/B sans re-saisir les accès ; `pin` inchangé.

Throttle :
11. 11 `approve` à pin faux en <10 min → 429 ; le bon pin remarche après la fenêtre.

---

## 9. Périmètre — ce que le lot NE fait PAS

- Ne modifie **aucune** route `/share/<token>/*` ni leur scope (seulement pré-amorçage du
  `guest_token` côté client par le hub).
- Ne change **pas** le format d'export/import (v19), ni le schéma `shares`/`share_guests`.
- Ne supprime jamais un `share` en (a)/(b) (un dossier peut servir plusieurs personnes).
- Pas de notification e-mail (hors périmètre, comme le reste du projet).

---

## 10. Auto-évaluation (grille AIDD)

| Critère | Score | Note |
|---|---|---|
| Clarté du besoin | 10/10 | comportement validé, repris d'IDEAS.md verbatim |
| Réutilisation de l'existant | 10/10 | 0 colonne ajoutée aux tables existantes, routes `/share` & `grant` & `qr` réutilisées, clé `dashguest:` réutilisée |
| Sécurité (invariant 5) | 9/10 | union stricte, scope `/share` inchangé, 2 facteurs (URL+PIN), anti-timing/throttle ; **point ouvert** ci-dessous |
| Non-destructivité / compat | 10/10 | additif `CREATE TABLE IF NOT EXISTS`, export inchangé |
| Testabilité | 10/10 | 11 scénarios sur copie, isolation + énumération couvertes |
| Périmètre maîtrisé | 9/10 | une page + 4 routes (2 publiques /g, 2 owner /api/hubs) + réutilisations |
| **Global** | **9,5/10** | verrouillable |

### Points à trancher avant build (décisions demandées)
1. **Cascade d'approbation au PIN** : OK pour approuver d'office **tous** les `share_guests`
   de l'e-mail au bon code (c'est le cœur « un seul code »), y compris ceux en `pending`
   (auto-inscriptions non encore validées) ? → **Proposé : OUI** (le code hub fait foi).
   Sinon : n'approuver que ceux déjà `approved` et laisser les `pending` à la validation owner.
2. **Régénérer (c)** : rotation du **token seul** (proposé) ou aussi du **pin** ? Spec dit
   « rotation du token » → **token seul**.
3. **Endpoint owner** : enrichir `GET /api/guests` ou ajouter `GET /api/hubs` ? →
   **Proposé : `GET /api/hubs`** (plus net, évite d'alourdir `/api/guests`).
4. **hub.html** : page minimale autonome (CSS inline, thème clair/sombre comme `share.html`,
   pas de Quill/Leaflet) → confirmer qu'on ne veut **pas** de mini-dashboard ici, juste la
   **liste de dossiers** qui renvoie vers les `/share` existants. → **Proposé : liste seule.**

---

**FIN DE SPEC — j'attends ta validation (et tes réponses aux 4 points) avant tout code.**
