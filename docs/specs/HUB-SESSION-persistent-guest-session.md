# SPEC — [HUB-SESSION] Session invité mémorisée (plus de re-saisie du code)

**Statut : VERROUILLÉE — en attente de validation Fabien. Aucun code avant OK.**
Cible : **V19.9**. Zone **SÉCURITÉ-SENSIBLE** (accès invité = invariant 5).
`guest_hubs` non exportée → **pas de bump du format d'export** (reste v19).

---

## 1. Problème (constaté sur le terrain)

Un invité approuvé doit re-saisir son code PIN à chaque visite du hub, alors que
`hub.html` mémorise déjà une preuve en localStorage (`dashhubproof:<HUB_TOKEN>`,
posée à `approve()`, testée par `init()`). Deux causes identifiées :

1. **Safari iOS (ITP) purge le localStorage** après ~7 jours sans visite du site.
   Les invités réels (iPhone) re-saisissent donc le code chaque semaine. Les cookies
   **posés par le serveur** (HTTP `Set-Cookie`) ne sont PAS soumis à cette purge.
2. **Preuve fragile** : la valeur stockée est `data.folders[0].guest_token` — le jeton
   du *premier dossier*. Si l'owner retire CE dossier (`DELETE /api/guests/<id>`),
   la preuve meurt (403 → écran code) même si les autres dossiers de l'invité sont intacts.

## 2. Principe (à valider)

**Preuve de session côté serveur, transportée par cookie HTTP.**

- Nouveau jeton `session_token` par hub (par personne), **indépendant des dossiers**.
- Posé en **cookie `HttpOnly`** par le serveur au bon PIN ; re-posé à chaque `/data`
  réussi (**expiration glissante** : un invité actif ne re-saisit jamais le code).
- Le localStorage actuel **reste en repli** (inchangé) ; le cookie est additif.
- Révocation : régénérer le **code** OU le **lien** invalide la session (tous les
  appareils re-passent par le PIN) ; retirer l'invité supprime le hub → cookie inerte.

## 3. Modèle de données (additif, non destructif)

Colonne additive sur `guest_hubs` (migration `PRAGMA table_info` + `ALTER TABLE`,
comme les autres — jamais de DROP) :

```
guest_hubs.session_token TEXT DEFAULT ''   -- secrets.token_urlsafe(24) ; '' = aucune session
```

- **Un seul token par hub, partagé par les appareils** : chaque appareil qui saisit le
  bon PIN reçoit le même token en cookie. Invalider = régénérer → tous re-PIN.
- Jamais exporté (`guest_hubs` ne l'est déjà pas) → export/import **strictement inchangés**.
- Jamais exposé dans `/api/hubs` ni dans aucun JSON owner/invité (transport = cookie only).

## 4. Cookie (définition exacte)

Posé par `hub_approve` (bon PIN) et re-posé par `hub_data` (proof valide) :

```
Name     : dashhubsession            (un par hub grâce au Path, pas besoin d'id dans le nom)
Value    : <session_token>
Path     : /share/hub/<hub_token>    (envoyé UNIQUEMENT aux routes de CE hub)
Max-Age  : 15552000 (180 j)          (glissant : re-posé à chaque /data OK)
HttpOnly : oui                       (illisible en JS — XSS ne peut pas le voler)
SameSite : Lax
Secure   : si `request.is_secure` OU `X-Forwarded-Proto: https` (Caddy) —
           conditionnel pour que localhost:8099 (HTTP) fonctionne en test
```

Pourquoi `Path=/share/hub/<hub_token>` :
- deux invités sur le même navigateur → cookies **coexistent** (paths distincts) ;
- rotation du **lien** → nouveau path → l'ancien cookie n'est plus jamais envoyé
  (en plus de l'invalidation serveur du token, ceinture + bretelles) ;
- le cookie n'est jamais envoyé à `/share/<token>` ni au reste de l'app.

## 5. Serveur (app.py)

### 5.1 `hub_approve` (bon PIN) — 3 ajouts
1. si `hub["session_token"]` vide → en générer un (`token_urlsafe(24)`) et le stocker ;
2. poser le cookie (définition §4) sur la réponse JSON existante ;
3. tout le reste (cascade d'approbation, throttle, anti-timing, 403 générique) **inchangé**.

### 5.2 `_hub_proof_guest` → devient `_hub_proof(db, hub)`
Preuve valide si **l'une des deux** :
- **cookie** : `request.cookies.get('dashhubsession')` non vide ET
  `hub["session_token"]` non vide ET `hmac.compare_digest(cookie, hub["session_token"])` ;
- **header** (existant, inchangé — repli) : `X-Guest-Token` = un `share_guests.guest_token`
  **approuvé** dont l'e-mail == celui du hub.

Le hub est déjà résolu par `hub_token` avant l'appel → un cookie volé/forgé présenté
sur un autre hub échoue (comparaison avec LE token de CE hub). Réponses 403/404
génériques inchangées (pas d'énumération).

### 5.3 `hub_data` — 2 ajouts
1. accepte la preuve §5.2 (cookie OU header) ;
2. si preuve OK → **re-pose le cookie** (Max-Age repart pour 180 j).
La **cascade d'approbation reste réservée au PIN** (`approve`) : le cookie ne
promeut jamais un `share_guests` pending (décision : périmètre minimal ; les octrois
owner sont déjà pré-approuvés par `grant_guest_project`, donc `/data` les voit).

### 5.4 Révocations
- `POST /api/hubs/<token>/rotate-pin` → **aussi** `session_token = token_urlsafe(24)`
  (nouveau code ⇒ toutes les sessions retombent sur l'écran code) ;
- `POST /api/hubs/<token>/rotate` (lien) → **aussi** régénérer `session_token`
  (l'ancien path ne matche plus, mais on invalide aussi côté serveur) ;
- `DELETE /api/hubs/<token>` (retirer l'invité) → ligne supprimée, cookie inerte (déjà le cas).
- Retirer UN dossier (`DELETE /api/guests/<id>`) → **ne touche PAS la session**
  (c'est le but : la preuve n'est plus liée aux dossiers).

### 5.5 Écritures : AUCUN changement
Toute écriture passe toujours par `/share/<share_token>/...` + header `X-Guest-Token`
du dossier, revalidée serveur (scope + can_edit). Le cookie n'authentifie **que**
`/share/hub/<token>/data` (lecture) → pas de surface CSRF nouvelle (GET sans effet
de bord ; `approve` exige le PIN dans le corps).

## 6. Front (`hub.html`) — delta minimal

1. `init()` : aujourd'hui `if (hubProof()) loadDash(); else showCode();` →
   **toujours `loadDash()`** (le cookie part tout seul avec le fetch same-origin,
   header `X-Guest-Token` envoyé si le localStorage l'a encore, sinon vide).
   `loadDash` affiche déjà l'écran code sur 403 → comportement inchangé sans session.
2. `approve()` : inchangé (le Set-Cookie arrive avec la réponse ; le localStorage
   continue d'être posé en repli).
3. Rien d'autre. `share.html`/`index.html` **non touchés**.

## 7. Invariants

- **5** : aucune route nouvelle, tout reste sous `/share/hub/*` (bypass Authelia
  existant) ; le serveur revalide tout ; pas de master token (le cookie ne donne que
  la lecture du hub de CET e-mail, les écritures gardent leurs jetons par dossier) ;
  anti-timing (`compare_digest`), throttle PIN et réponses génériques inchangés.
- **1/2** : export/import intacts (v19), migration additive idempotente.
- **6/8/9** : pas d'asset, pas de dialog, pas de style — front quasi intact.

## 8. Tests d'acceptation (validation Chrome, owner + invité)

1. PIN correct → `Set-Cookie` présent ; reload → **pas d'écran code**.
2. `localStorage.clear()` + reload → **pas d'écran code** (cookie seul suffit).
3. Cookie supprimé + localStorage vidé + reload → écran code (repli normal).
4. Retirer le **premier dossier** de l'invité → reload → **pas d'écran code**
   (la cause n°2 est morte), les autres dossiers restent éditables.
5. « Régénérer le code » → reload invité → écran code (session invalidée partout).
6. « Régénérer le lien » → nouvelle URL → écran code ; ancienne URL → 404.
7. Deux invités (A, B) sur le même navigateur → chacun sa session, pas d'écrasement.
8. Écriture sur un dossier `can_edit` après reconnexion cookie-only → 200
   (les `guest_token` par dossier sont reposés par `/data`, V19.8.16).
9. Sonde non authentifiée (`credentials:'omit'`) : `/share/hub/<token>` et `/data`
   atteignent l'app (bypass `/share/*` intact, pas de redirection Authelia).
10. `python3 -m py_compile` + migration sur copie de base + ré-import d'un export
    complet → 0 ajout (export inchangé).

## 9. Hors périmètre (volontaire)

- Pas de « se déconnecter » côté invité (fermer/ignorer suffit ; révocation = owner).
- Pas de sessions par appareil (un token par hub — simplicité ; rotation = global).
- Pas de mémorisation sur `/share/<token>` hors hub (le hub est le chemin nominal).
- Pas de changement de la purge localStorage (repli conservé tel quel).
