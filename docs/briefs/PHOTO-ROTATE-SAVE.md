# Brief CC — [PHOTO-ROTATE-SAVE] : pivoter une photo **et l'enregistrer** (Option A)

> **Lot fonctionnel** (touche `app.py` + `templates/partials/_shared.js.html`), doctrine **TDD
> rouge-vert**. Décidé avec Fabien : **Option A** (ré-encodage de l'original), **7/10**, **owner v1**
> (invités `can_edit` en v2), **tag + Deploy** au bout.
>
> **Constat utilisateur** : dans la visionneuse, on peut pivoter une photo de travers (flèches ↺ ↻)
> mais ça **ne se sauvegarde pas** — c'est de l'**AFFICHAGE SEUL** par conception (`transform` CSS,
> aucun fetch, remis à zéro à la fermeture). Les photos concernées sont celles **sans drapeau EXIF
> d'orientation** (celles qui en ont un sont déjà redressées par `exif_transpose` sur les dérivées).
>
> **Rebuild local** obligatoire (changement applicatif). `make test` **entièrement vert** (back +
> e2e) → journal + handoff → **STOP**. Commit après passe Cowork + GO, puis **tag + Deploy**.

---

## 0. Le geste (UX arrêtée avec Fabien)

On **réutilise les flèches ↺ ↻ existantes** de `runImageViewer` (elles font déjà `rot -= 90 / += 90`).
On **n'invente aucun nouveau bouton de rotation**. On ajoute seulement :

- un bouton **« Sauvegarder »** dans la barre du viewer, **masqué par défaut**, qui **apparaît dès que
  l'angle affiché change** (`rot % 360 !== 0`) et **disparaît** quand on revient à 0 ou qu'on
  sauvegarde ;
- au clic : POST de l'angle net au serveur → l'original est **physiquement pivoté**, les dérivées
  `t`/`s` régénérées → l'image corrigée s'affiche **immédiatement** (cache-busting), `rot` remis à 0,
  bouton re-masqué.

**Owner v1 uniquement.** Attention : `canEdit`/`canDelete` sont **aussi vrais pour un invité
contributeur** — on ne peut donc PAS gater le bouton dessus. Il faut une **capacité dédiée**
(cf. §3).

---

## 1. Le vrai piège du lot : la **double-rotation EXIF**

Ce que l'utilisateur voit dans le viewer, c'est la **dérivée `s`**, générée par `_gen_derived` qui
applique déjà `ImageOps.exif_transpose(im)`. Donc l'affiché = `exif_transpose(original)`. La rotation
demandée est **relative à ça**.

Si on se contente de tourner les octets de l'original **sans neutraliser son tag d'orientation EXIF**,
alors au prochain `_gen_derived` le `exif_transpose` **re-tournera** l'image → **double rotation**.
La logique serveur doit donc **cuire l'orientation dans les pixels puis remettre le tag Orientation
à 1** (voir §2). C'est le cœur correct du lot — un test le prouve (§4, `test_..._no_double_rotation`).

Sens de rotation, à ne pas inverter :
- CSS `rotate(deg)` positif = **sens horaire** ; `rotR` fait `rot += 90` (horaire), `rotL` `rot -= 90`.
- Pillow `Image.rotate(angle)` positif = **anti-horaire**. Pour reproduire l'horaire **sans
  ré-échantillonnage**, utilise `transpose` (multiples de 90 exacts) :
  - `rot ≡ 90` (horaire) → `im.transpose(Image.ROTATE_270)`
  - `rot ≡ 180`         → `im.transpose(Image.ROTATE_180)`
  - `rot ≡ 270` (horaire) → `im.transpose(Image.ROTATE_90)`
  (`Image.ROTATE_*` est anti-horaire chez Pillow ; d'où le 270↔90 croisé.) `transpose` évite
  l'interpolation → **rotation propre**, dans l'esprit « lossless quand multiple de 90 ».

---

## 2. La route serveur (owner, `/api/`)

Nouvelle route **owner** (pas de variante `/share/*` — invariant 5 : les invités ne pivotent pas en
v1) :

```
POST /api/images/<name>/rotate      corps JSON { "angle": 90 | 180 | 270 }
```

`name` = **nom de fichier stocké** (le uuid), celui que le viewer manipule déjà (`images[idx]`,
`_gen_derived(name)`, `_delete_derived(name)`). Validation stricte :

- `SAFE_IMG_NAME.match(name)` sinon **400** (déjà utilisé partout).
- `angle` ∈ {90, 180, 270} (après `% 360`) sinon **400** « angle invalide ». `angle % 360 == 0` →
  **400** (rien à faire) ou 200 no-op — **au choix, mais testé**.
- ext ∈ {jpg, jpeg, png, webp} ; **gif refusé** (animé → jamais de dérivée) → **400/415**.
- fichier absent de `UPLOAD_DIR` → **404**.

Traitement (Pillow, déjà importé : `Image`, `ImageOps`) :

```python
from PIL import Image, ImageOps
src = os.path.join(UPLOAD_DIR, name)
with Image.open(src) as im:
    im = ImageOps.exif_transpose(im)          # (1) cuit l'orientation EXIF existante -> pixels = ce que l'user voyait
    im = im.transpose(_TRANSPOSE[angle % 360]) # (2) applique la rotation demandée (sens horaire, cf. §1)
    exif = im.getexif()                        # (3) on PRESERVE l'EXIF (GPS/date pour la carte PHOTO-MAP)...
    exif[0x0112] = 1                           #     ...mais Orientation = 1 (sinon double-rotation)
    save_kwargs = {}
    fmt = (im.format or ...) # déduire du ext : JPEG q>=90 optimize, PNG lossless, WEBP q>=90
    im.save(src, <format>, exif=exif.tobytes(), **save_kwargs)  # écrase l'original (Option A)
_delete_derived(name)                          # (4) purge t_/s_ ...
_gen_derived(name)                             #     ... et régénère à partir de l'original corrigé
```

Points de vigilance :

- **Préserver l'EXIF, ne remettre QUE `Orientation` à 1.** Ça garde les tags **GPS/date** dont
  dépend la carte du projet (`image_meta` / PHOTO-MAP). Ne **pas** toucher la table `image_meta` :
  une rotation ne change ni le lieu ni la date, la ligne cachée reste valide.
- **JPEG** : réenregistrer à **qualité élevée** (≥ 90, `optimize=True`) — Fabien a accepté la perte
  minime d'un ré-encodage ; le `transpose` évite l'interpolation, donc la seule perte est celle du
  ré-encodage JPEG, négligeable sur une ou deux rotations à 90°.
- **PNG** : sans perte, pas d'EXIF d'orientation en général → simple `transpose` + save.
- **WEBP** : traiter l'EXIF comme le JPEG s'il existe, sinon simple save.
- Réponse **200** `{ "ok": true, "name": name, "rotated_at": <epoch> }`. `rotated_at` sert au
  **cache-busting** front (§3). Aucune fuite d'autre chose.
- **Zéro réseau** : la route ne touche que le disque → la garde `conftest.py` reste verte.

---

## 3. Le front (`runImageViewer` + le point d'appel owner)

### 3.1 Capacité owner (gate)

`runImageViewer(cfg)` gagne une capacité **optionnelle** `cfg.rotateUrl` (fonction `name → URL`),
sur le même modèle que `downloadUrl`/`exifUrl`/`onDelete` déjà optionnels :

- **Owner uniquement** passe `rotateUrl` → le bouton « Sauvegarder » existe.
- Invité / hub / carte : **ne passent rien** → pas de bouton (comportement inchangé).

Il faut **fil rouge la capacité depuis le point d'appel owner** : `renderMemoPhotos` (l.~2526,
`openFull → runImageViewer`) est appelé **et côté owner (index) et côté invité (share)** avec le même
code. Ajoute donc à `renderMemoPhotos` un flag **owner-only** (ex. `cfg.canRotate`) que **seule la
page owner** met à `true`, et qui, si présent, fait passer `rotateUrl: (n) => '/api/images/' + n + '/rotate'`
à `runImageViewer`. Les gabarits invités/hub ne le mettent pas.

> **Vérifie les points d'appel réels** de `renderMemoPhotos`/`runImageViewer` et **quel gabarit est
> owner vs invité** (index.html = owner ; `share*`/hub = invité). N'active `canRotate` **que** sur le
> chemin owner. En cas de doute, garde l'attache la plus étroite : **les photos du mémo côté owner**.
> (Les pièces jointes-images `attachSection`/`openImage` peuvent recevoir la même capacité plus tard
> — hors périmètre v1, note-le si tu veux, ne le fais pas.)

### 3.2 Le bouton « Sauvegarder » (dans la barre `iv-bar`)

- Fabriqué comme les autres (`ivBtn('button', 'device-floppy'|'check'|'save', 'Sauvegarder')`,
  réutilise une **icône Tabler existante** + le gabarit `.iv-btn` — invariant 9, aucun nouveau style
  ad hoc si évitable), inséré **seulement si `cfg.rotateUrl`**.
- **Visibilité** : masqué par défaut ; dans `applyTransform()` (ou un petit `updateSaveBtn()` appelé
  par `rotL`/`rotR` et `render()`), afficher ssi `((rot % 360) + 360) % 360 !== 0`. `render()` remet
  déjà `rot = 0` à chaque navigation → le bouton doit **se re-masquer** en changeant d'image.
- **Au clic** :
  1. calcule `angle = (((rot % 360) + 360) % 360)` ; si 0, ne rien faire ;
  2. `POST cfg.rotateUrl(name)` avec `{angle}` (mêmes `headers` que les autres écritures du viewer si
     le contexte en fournit) ;
  3. succès → **cache-bust** : recharge l'image courante avec `?v=<rotated_at>` (l'URL de dérivée est
     à cache fort `max_age`, donc **sans param le navigateur ré-affiche l'ancienne**), remet
     `rot=0; scale=1; tx=ty=0`, `applyTransform()`, re-masque le bouton ;
  4. **propager** à la grille : la vignette du mémo (`mp-thumb`, servie en `t`) doit refléter la
     correction **sans hard-refresh** — déclenche le rafraîchissement standard (`cfg.onChange` si
     dispo, ou recharge des données du mémo) en propageant le même `?v=` de cache-bust. **Pas de
     demi-feature** : après sauvegarde, l'image droite s'affiche **partout** (viewer + grille) sans
     que Fabien ait à recharger la page.
  4. échec → petit toast d'erreur (`toast(...)` existe), on **ne remet pas** `rot` à 0 (l'utilisateur
     peut re-tenter).
- **Feedback** : désactiver le bouton pendant le POST (anti double-clic).

> Le mécanisme exact de cache-bust est ton choix (param `?v=rotated_at` recommandé, appliqué à
> `img.src` et aux vignettes de la grille). Le **critère** : l'image corrigée visible immédiatement,
> viewer **et** grille.

---

## 4. TDD — rouge d'abord (back)

Nouveau fichier ou ajout à `tests/back/` (ex. `tests/back/test_image_rotate.py`, marqueur
`invariant`). Écris les tests **avant** la route (ils échouent en 404 → **rouge prouvé**), puis
implémente → **vert**. Monte les images de test avec Pillow (JPEG/PNG en mémoire) via l'upload réel
ou en écrivant dans `UPLOAD_DIR` + insert `attachments`/`memos.images` selon le plus simple.

1. **`test_rotate_90_swaps_dimensions_and_persists`** — image paysage `W>H` → `POST …/rotate {90}`
   → 200 ; le **fichier original sur disque** a maintenant `H×W` (dimensions échangées) ; la dérivée
   `s_<name>.jpg` régénérée est elle aussi tournée (dimensions cohérentes).
2. **`test_rotate_normalizes_exif_no_double_rotation`** — image **avec tag EXIF Orientation ≠ 1** →
   après rotate, l'original sauvé a **Orientation == 1** et ses **pixels** correspondent à
   `rotate(exif_transpose(source), angle)` (donc `_gen_derived` ne re-tourne pas). C'est la
   régression-clé du §1.
3. **`test_rotate_preserves_gps_exif`** — image avec tag GPS/DateTime → après rotate, ces tags sont
   **toujours présents** (seule `Orientation` a changé). Protège la carte PHOTO-MAP.
4. **`test_rotate_rejects_non_multiple_of_90`** — `angle=45` → **400** ; original **inchangé**.
5. **`test_rotate_rejects_gif`** — un `.gif` → **400/415**, inchangé.
6. **`test_rotate_unknown_image_404`** — nom valide mais fichier absent → **404**.
7. **`test_rotate_bad_name_400`** — nom hors `SAFE_IMG_NAME` → **400**.
8. **`test_rotate_regenerates_derivatives`** — dérivées présentes **avant** ; après rotate elles sont
   **reconstruites** (mtime/dimension changés), pas juste supprimées.
9. **`test_no_guest_rotate_route`** *(invariant 5)* — il n'existe **aucune** route `/share/**/rotate`
   (les invités ne pivotent pas en v1) : un POST sur un chemin invité plausible → 404. (Preuve
   structurelle du « owner-only ».)

Éprouve par **mutation** au moins : la neutralisation EXIF (#2), la régénération des dérivées (#8) et
le refus non-90 (#4) — casse la garde, vérifie qu'exactement le bon test rougit.

**e2e (léger, optionnel mais recommandé)** : ouvrir une photo owner, cliquer ↻ → le bouton
« Sauvegarder » **apparaît** ; cliquer → 200 et l'image se recharge. Si l'e2e est trop coûteux à
monter proprement, **note-le** plutôt que de livrer un e2e fragile.

---

## 5. Definition of Done

1. Route `POST /api/images/<name>/rotate` (owner, Option A : ré-encode + **Orientation=1** +
   EXIF GPS/date préservés + dérivées régénérées), **aucune** variante invité.
2. Front : bouton « Sauvegarder » dans `runImageViewer`, **gaté par `cfg.rotateUrl` owner-only**,
   apparaît quand `rot % 360 ≠ 0`, cache-bust viewer **et** grille après succès.
3. TDD : tests §4 **rouges avant / verts après**, gardes-clés éprouvées par mutation.
4. `make test` **entièrement vert** (back + e2e) ; la garde zéro-réseau reste verte.
5. `git status` : `app.py`, `templates/partials/_shared.js.html`, gabarit(s) owner threadant
   `canRotate`, `tests/back/test_image_rotate.py`, `REALISATION.md`, `docs/briefs/PHOTO-ROTATE-SAVE.md`.
   **Rebuild local** `docker compose up -d --build` (changement applicatif) + vérif à l'œil : pivoter
   une vraie photo de travers, sauvegarder, **fermer/rouvrir → elle reste droite**, et la vignette du
   mémo est droite elle aussi.
6. Journal + `handoff.json`, puis **STOP**. Commit après passe Cowork + **GO Fabien**, puis
   **tag + Deploy** (c'est un vrai correctif fonctionnel ; la prod est sur V27.37.229).

---

## 6. Note déploiement (à l'attention de Fabien via Cowork)

Ce Deploy fera passer la prod de **V27.37.229** à la tête de `main` : il **embarque donc aussi** le
delta déjà sur `main` mais pas encore en prod — notamment **[IMPORT-SKIP-FIX]** (vrai correctif : «
Ignorer » à l'import enfin honoré) et les vagues **[TESTS-PORT]** / **[TEST-NET-GUARD]** (test-only,
zéro impact applicatif). Rien d'inattendu, mais autant le savoir : un seul Deploy solde tout ce qui
dormait.

## 7. Portée

Petit lot fonctionnel, une intention : **pivoter ET enregistrer, côté owner, sur les photos du mémo.**
Extensions **hors v1**, à noter seulement : invités `can_edit` (route `/share/*`, invariant 5),
pièces jointes-images (même bouton), et un éventuel « recadrage ». Ne les fais pas ici.
