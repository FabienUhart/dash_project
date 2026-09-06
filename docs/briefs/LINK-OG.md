# Brief CC — [LINK-OG] : aperçu de lien (OpenGraph) sur les cards de liens

> **Lot de la maquette v3 des cards — le plus gros gain visuel, et le seul avec du backend.**
> Doctrine **TDD**. Décisions prises avec Fabien (voir §0). Enrichir les cards de la table `links`
> avec l'OpenGraph de `url_public` : **miniature téléchargée et cachée localement**, titre/desc/domaine.
>
> **Lot conséquent (backend + front, owner + invité).** Découpe recommandée si indigeste : **A =
> backend** (colonnes, fetch SSRF-safe, cache image, route refresh, backfill, sérialisation, tests) ;
> **B = rendu front** (card owner + invité). Livre A, note B en `[LINK-OG-B]`. Ne force pas un lot
> indigeste.

---

## 0. Décisions Fabien (fermes)

1. **Contenu** : on **ajoute** la miniature (og:image) + le **domaine** à la card ; on **garde le
   nom et la description que Fabien a saisis** ; on ne **remplit** depuis l'OG **que si son champ est
   vide** — **jamais d'écrasement** de son texte.
2. **Image** : **téléchargée et cachée localement** (comme les dérivées de photos), servie depuis le
   serveur — **pas** de lien vers l'image distante (pas de fuite d'IP, pas de casse).
3. **Moment du fetch** : **à l'enregistrement** (création/màj de `url_public`) + un **bouton
   Rafraîchir** + un **backfill unique** des liens existants.
4. **Sécurité & périmètre (non négociable, pas une décision)** : fetch **owner-only** ; **uniquement
   `url_public`**, jamais `url_local` (LAN) ; protection **SSRF** ; garde **zéro-réseau** respectée
   (tests stubbent le fetcher). Les invités **voient** l'aperçu caché, ne **déclenchent** jamais de fetch.

> **Raffinements issus de la revue de Fabien** (intégrés aux sections concernées ci-dessous) :
> latence (fetch **hors** du chemin de sauvegarde), taille/format image (plafond + vignette seule),
> backfill **relançable** (retente les échecs), cas limites front (`onerror`, troncature), et
> **scope** de la route image invité.

---

## 1. Modèle de données — colonnes DÉRIVÉES sur `links`

Table `links` aujourd'hui : `name`, `descr`, `url_public`, `url_local`, `memo`, `category_id`, `tags`,
`uid`, … (pas d'OG). Ajouter des colonnes **additives, DÉRIVÉES, JAMAIS exportées** (invariant 1 :
`APP_VERSION` reste 27 ; comme `image_meta`) :

- `og_title TEXT DEFAULT ''`, `og_desc TEXT DEFAULT ''`, `og_domain TEXT DEFAULT ''`
- `og_image TEXT DEFAULT ''` — **nom du fichier image caché localement** (vide si pas d'image)
- `og_fetched_at TEXT DEFAULT ''` — horodatage du dernier fetch (sert aussi de **jeton de
  cache-bust** pour l'image, cf. leçon [PHOTO-ROTATE-MEMCACHE])
- `og_status TEXT DEFAULT ''` — `ok` / `none` (pas de balises) / `failed` (réseau/refus) — pour ne
  pas re-fetcher en boucle et pour l'affichage de repli

> **`name`/`descr` de Fabien ne sont JAMAIS mutés.** Le « remplir si vide » est un **repli à
> l'affichage** : titre affiché = `name || og_title` ; description affichée = `descr || og_desc`.
> Ainsi sa curation reste intacte, un Rafraîchir ne touche que les colonnes `og_*`, et rien à
> restaurer s'il vide un champ. (Migration additive, jamais destructive.)

## 2. Le fetch OG (backend, owner-only, SSRF-safe)

Un helper `_fetch_og(url)` :

1. **Garde SSRF, avant tout appel** : schéma ∈ {http, https} ; résoudre l'hôte et **refuser** toute
   IP privée/loopback/link-local/multicast et l'endpoint métadonnée `169.254.169.254` ; **re-valider
   à chaque redirection** (une redirection peut viser un privé). `url_local` n'est **jamais** passé
   ici. En cas de refus → `og_status='failed'`, aucun réseau touché au-delà de la résolution.
2. **Télécharge la page** avec **timeout court** (~3 s), **taille bornée** (ex. 512 Ko de HTML lus,
   pas plus), **redirections limitées** (≤ 3, chaque saut re-validé SSRF). Parse les balises
   `og:title`, `og:description`, `og:image`, sinon repli `<title>` / `<meta name=description>` /
   `<link rel=icon>`. `og_domain` = hôte de `url_public`.
3. **Télécharge l'image** (`og:image`, résolue en URL absolue) avec les **mêmes gardes SSRF** +
   timeout + **plafond de taille du téléchargement** (~5 Mo max, coupé au-delà) + **vérif signature**
   (`_looks_like_image`). **On ne stocke QUE la vignette**, pas l'original (retour Fabien : pas de PNG
   4K inutile) : conversion **JPEG q82 ~600 px** via Pillow (réutilise `_gen_derived`), le
   téléchargement brut est **jeté** après. Cache sous `data/uploads/og/`, nom = `uid_du_lien.jpg`
   (**écrasé** au refresh → idempotent). Échec image → `og_image=''`, le reste de l'OG reste utilisable.
4. Renseigne `og_*` + `og_fetched_at` + `og_status`. **Best-effort, ne bloque/casse jamais** l'appelant
   (try/except silencieux, comme `_record_image_meta`).

Câblage :
- `create_link` / `update_link` : après l'écriture, si `url_public` est non vide (et nouveau/changé),
  **ne PAS fetcher dans la requête** — marquer `og_status='pending'` et **répondre immédiatement**
  (retour Fabien : un site lent ne doit jamais faire attendre l'enregistrement). Le fetch se fait
  **hors du chemin de sauvegarde** : le front, voyant `pending`, appelle la route Rafraîchir, **ou**
  le backfill/sweep owner (ci-dessous) ramasse les `pending`. **Escalation notée** : si le volume
  grossit, passer à une vraie **file asynchrone** — inutile à l'échelle actuelle, mais `pending` est
  déjà le point d'accroche.
- **Route Rafraîchir** : `POST /api/links/<id>/og-refresh` (owner) → `_fetch_og(url_public)` → renvoie
  le lien à jour. **Aucune** variante `/share/*` (invariant 5).
- **Backfill / sweep** : un passage (comme `_backfill_image_meta`) sur les liens à `url_public` non
  vide dont `og_fetched_at` est **vide OU `og_status='failed'`** (on **retente** les échecs
  temporaires, on **saute** les `ok`) — **idempotent et relançable sans danger** (image écrasée par
  lien, pas de doublon), best-effort, owner-only. Ramasse aussi les `pending` laissés par create/update.

## 3. Servir l'image cachée

- **Owner** : servir `data/uploads/og/<name>` (route dédiée ou via l'existant), avec **cache-bust par
  `og_fetched_at`** dans l'URL (leçon [PHOTO-ROTATE-MEMCACHE] : un Rafraîchir doit se voir tout de
  suite ; le même fichier peut changer de contenu). Revalidation ETag bienvenue (réutiliser
  `_image_response`).
- **Invité** : route `/share/<token>/og-image/<name>` — **vérifie le SCOPE** (retour Fabien) : le
  token doit donner accès au lien **propriétaire de cette image**, pas juste être un token valide
  servant n'importe quel fichier `og/` (sinon **fuite inter-partages**). Résoudre `name` → lien →
  vérifier qu'il est dans le périmètre du token, comme les autres routes image invité. Lecture seule.
  L'invité **ne fetch jamais**.

## 4. Sérialisation

- `LINK_FIELDS` (owner) et la sérialisation **invitée** des liens exposent : `og_title`, `og_desc`,
  `og_domain`, `og_image` (→ URL owner ou `/share/<token>/og-image/…`), `og_fetched_at`, `og_status`.
- Champs dérivés → **hors export** (invariant 1).

## 5. Front — la card d'aperçu (owner + invité)  *(partie B si découpe)*

Rendre la card lien selon la maquette `docs/maquettes/maquette-cards-v3.html` (bloc « Lien —
aperçu OG ») : **miniature à gauche** (`og_image` servie localement, cache-bust `?v=og_fetched_at`),
puis **domaine** (petit, muted), **titre** (`name || og_title`), **description** (`descr || og_desc`).
Repli **gracieux** si `og_status ∈ {none, failed, pending}` ou pas d'image : la card garde son look
actuel (nom + descr + URL/domaine). Monochrome, classes existantes (invariant 9). Owner **et** page
invité. Bouton **Rafraîchir** (owner) dans l'édition du lien ou son menu ⋯.

**Cas limites (retour Fabien)** : la miniature `<img>` porte un **`onerror`** → si le fichier caché
est manquant/illisible (supprimé, corrompu), basculer sur le look **texte-seul**, jamais une image
cassée. **Troncature** (ellipsis) sur **domaine, titre ET description** (déjà dans la maquette :
`nowrap` + `text-overflow`) — vérifier qu'un domaine ou un titre très long ne casse pas la mise en
page. Un `pending` s'affiche comme le repli (pas de trou), le temps que le sweep passe.

## 6. Tests (TDD)

**Back** (fetcher **stubbé** — la garde zéro-réseau bloque le vrai réseau, comme FX/Nominatim) :

1. `test_create_link_fetches_og` — `_fetch_og` stubbé renvoyant title/desc/image bytes → colonnes
   `og_*` peuplées, **image téléchargée et vignette présente** dans le cache.
2. `test_og_does_not_overwrite_user_text` — lien avec `name`/`descr` remplis → après fetch, `name` et
   `descr` **inchangés** ; l'affichage effectif prend `name`/`descr`. Un lien à champs vides → repli
   sur `og_title`/`og_desc`.
3. `test_og_ssrf_blocks_private` — `url_public` visant `127.0.0.1` / `192.168.x` / `169.254.169.254`
   → **refusé**, `og_status='failed'`, **aucun** fetch (prouvé par la garde / un compteur).
4. `test_url_local_never_fetched` — seul `url_public` est passé à `_fetch_og`, jamais `url_local`.
5. `test_no_og_tags_fallback` — page sans balises → `og_status='none'`, card en repli.
6. `test_refresh_route_owner_only` — `POST /api/links/<id>/og-refresh` existe côté owner ; **aucune**
   route `/share/**/og-refresh` (invariant 5).
7. `test_guest_sees_cached_og_no_fetch` — la sérialisation invitée expose l'og caché ; ouvrir la page
   invité **ne déclenche aucun fetch** (garde verte).
8. `test_og_image_bounded_and_thumbnailed` — image source volumineuse (stub) → le fichier stocké est
   une **vignette bornée** (JPEG ~600 px), pas le brut ; téléchargement coupé au-delà du plafond (~5 Mo).
9. `test_guest_og_image_scope` — un token ne sert que les images `og/` des liens **de son périmètre** ;
   viser l'og d'un lien hors scope → 404/403 (retour Fabien : pas de fuite inter-partages).
10. `test_save_does_not_fetch_inline` — create/update pose `og_status='pending'` et **ne touche pas le
    réseau** dans la requête (garde verte pendant le save) ; c'est le refresh/sweep qui fetch.
11. Éprouver par **mutation** : garde SSRF retirée (#3 rougit) ; « remplir si vide » qui écrase
    (#2 rougit) ; scope invité retiré (#9 rougit).

**Front / e2e** : une card lien avec og → rendu miniature + titre + domaine ; sans og → repli.

## 7. Definition of Done

1. Colonnes `og_*` dérivées (hors export) ; `_fetch_og` SSRF-safe + image téléchargée/cachée +
   vignette ; câblé à create/update + route Rafraîchir owner + backfill ; sérialisation owner +
   invité ; **`url_public` seul**, owner-only, garde zéro-réseau verte (fetcher stubbé).
2. Front : card d'aperçu (owner + invité) selon la maquette, repli gracieux, cache-bust `og_fetched_at`.
   *(Ou B notée `[LINK-OG-B]` si découpe.)*
3. `make test` **entièrement vert** ; tests §6 rouges avant / verts après ; SSRF + non-écrasement
   éprouvés par mutation.
4. `git status` propre (pas de `.idea` ; le dossier cache `data/uploads/og/` **jamais** commité, même
   règle que `uploads/`/`derived/`). Rebuild local.
5. **Vérif à l'œil Fabien** : un lien avec `url_public` (ex. meduseo.com) → card avec miniature +
   titre + domaine ; ton texte préservé ; Rafraîchir met à jour ; côté invité, l'aperçu s'affiche
   (image servie depuis ton serveur).
6. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**, puis **tag + Deploy**.

## 8. Portée

Uniquement l'aperçu OG des **cards de liens** (table `links`). Pas les URLs dans le corps des mémos,
pas de refonte de l'édition de lien au-delà du bouton Rafraîchir. Une intention : un lien = une belle
carte, sans fuite ni risque.
