# SPEC — [GUEST-EDIT] Modifier les invités (nom, e-mail) + dernière connexion

**Statut : VERROUILLÉE — décisions validées par Fabien (2 juil. 2026).**
Cible : **V19.11** (après [SETTINGS-TABS] V19.10). Zone **SÉCURITÉ-SENSIBLE**
(l'e-mail est la clé d'identité du partage — invariant 5).
`share_guests`/`guest_hubs` non exportées → **pas de bump du format d'export** (reste v19).

---

## 1. Décisions figées

1. **Collision** : si le nouvel e-mail a déjà des accès (`share_guests` OU `guest_hubs`)
   → **refus** (409, message « cet e-mail a déjà des accès »). La fusion d'invités
   n'est PAS dans ce lot.
2. **Session transparente** : changer l'e-mail ne touche NI le lien (`hub_token`),
   NI le code (`pin`), NI la session (`session_token`), NI les `guest_token` —
   correction de faute de frappe = l'invité ne remarque rien.
3. **Dernière connexion par invité** (une date par personne, pas par dossier).

## 2. Modifier un invité (nom + e-mail) — owner-only

### Backend
Route owner-only `POST /api/guests/update` `{email, name, new_email}` :
- `email` = clé de l'invité actuel (normalisé `strip().lower()` comme partout) ;
- `name` : si fourni → même effet que l'actuel `/api/guests/rename`
  (MAJ `share_guests.name` de TOUS les accès de l'e-mail + `guest_hubs.name`) ;
- `new_email` : si fourni et ≠ `email` :
  - validation : `@` présent, ≤120, normalisé minuscule (mêmes règles que `grant`) ;
  - **collision** : `SELECT` sur `share_guests` et `guest_hubs` avec `new_email`
    → si trouvé, **409** sans rien modifier ;
  - **re-keyage atomique** (une seule transaction) :
    `UPDATE share_guests SET email = ? WHERE lower(email) = ?` (pending inclus)
    + `UPDATE guest_hubs SET email = ? WHERE lower(email) = ?` ;
  - **rien d'autre ne bouge** (décision 2) : tokens, PIN, session, statuts intacts.
- 404 si l'e-mail actuel n'a aucun accès. Garder `/api/guests/rename` tel quel
  (compat) ou le faire déléguer à `update` — au choix de l'implémentation.

### Ce qu'on ne réécrit PAS (historique immuable, comme le rename actuel)
Les attributions déjà enregistrées gardent l'ancienne identité : commentaires signés,
`memos.created_by` (« Nom <ancien e-mail> »), `memo_revisions.editor`. C'est assumé
et cohérent avec le comportement du renommage existant. L'e-mail d'invitation
(`send-invite`, destinataire forcé = e-mail du hub) partira automatiquement vers le
nouvel e-mail après changement.

### UI (vue 🔗 Partages)
Le ✎ d'en-tête d'invité (rename inline actuel) ouvre désormais une **pop-in
« Modifier l'invité »** : champ nom + champ e-mail + Annuler/Enregistrer.
Erreur 409 affichée **inline** dans la pop-in (pas de `notify` bloquant, pas
d'effacement de la saisie — même pattern que le formulaire d'accès invité).
Classes/tokens existants (invariant 9), entrée CSS du dialog (invariant 8).

## 3. Dernière connexion — par invité

### Modèle
Colonne additive `guest_hubs.last_seen_at TEXT DEFAULT ''` (migration
`PRAGMA table_info` + `ALTER TABLE`, jamais de DROP).

### Mise à jour (helper unique `_touch_guest_seen(db, email)`)
Appelé quand un invité **prouve** son identité :
- `hub_approve` (bon PIN) ;
- `hub_data` (preuve cookie OU header valide) ;
- `GET /share/<token>/data` quand un `X-Guest-Token` **approuvé** est présent
  (un invité peut n'utiliser que son lien direct, sans passer par le hub) —
  retrouver le hub par l'e-mail du guest ; s'il n'a pas de hub, no-op silencieux.

**Throttle** : n'écrire que si `last_seen_at` est vide ou vieux de **> 5 minutes**
(le refresh auto des pages invité tourne toutes les 15 s → sans garde, une écriture
SQLite par invité actif toutes les 15 s, inutile sur le Zimaboard).

### Exposition (owner-only)
`GET /api/hubs` gagne `last_seen_at` (ISO, `''` = jamais). **Jamais** exposé côté
invité (`share_data`/`hub_data` inchangés sur ce point).

### UI (vue 🔗 Partages)
Dans l'en-tête de chaque invité : « 🕐 vu il y a 2 h » (date relative, absolue au
survol via `title`) ou « jamais connecté ». Réutiliser le helper de dates relatives
existant si disponible, sinon petit helper local. Badge texte discret type `.badge`.

## 4. Invariants

- **5** : routes owner-only derrière Authelia (aucune route publique nouvelle) ;
  le re-keyage préserve l'isolation par e-mail (collision refusée → jamais deux
  identités fusionnées silencieusement) ; rien n'est exposé aux invités.
- **1/2** : export/import intacts (v19), migrations additives idempotentes.
- **8/9** : pop-in en CSS, classes/tokens existants.

## 5. Tests d'acceptation

1. Renommer via la pop-in → nom mis à jour partout (vue Partages, suggestions).
2. Changer l'e-mail → l'invité recharge son hub : **toujours connecté** (cookie),
   mêmes dossiers, écriture `can_edit` → 200 ; `/api/hubs` montre le nouvel e-mail.
3. Changement vers un e-mail **déjà invité** → 409, rien modifié, erreur inline.
4. E-mail invalide (`sans-arobase`, >120) → 400, rien modifié.
5. Pending inclus : un accès pending de l'ancien e-mail suit le nouveau.
6. `last_seen_at` : vide à la création (« jamais connecté ») ; posé au bon PIN ;
   rafraîchi par une visite hub (cookie) ET par un accès `/share/<token>/data`
   direct ; PAS réécrit si < 5 min (vérifier en base) ; visible dans /api/hubs
   et la vue Partages ; absent de `share_data`/`hub_data`.
7. `python3 -m py_compile` + migration sur copie + export : `version: 19`,
   ré-import complet → 0 ajout ; `last_seen_at`/e-mails absents de l'export.

## 6. Hors périmètre (volontaire)

- Fusion de deux invités (lot futur si besoin).
- Historique de connexions (on garde UNE date, pas une table de logs).
- Last-seen par dossier.
- Réécriture des attributions historiques.
