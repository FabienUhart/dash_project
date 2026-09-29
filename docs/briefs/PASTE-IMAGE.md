# Brief CC — [PASTE-IMAGE] : coller une image du presse-papiers dans « 📷 Photos »

> **Front pur, partagé owner / invité / hub via `renderMemoPhotos`, zéro route nouvelle, `app.py`
> intact, export 28 inchangé.** Demande Fabien du 29 sept. 2026 (« je peux copier l'image dans le
> navigateur et je voudrais la coller dans les mémos, pas devoir l'enregistrer et l'importer »).
> Arbitrages Fabien : destination **Photos** (jamais Fichiers), **invités aussi**, **mobile aussi**.
> Doctrine TDD. Cible **V28.5.272**.

## 0. Ce qui change, en une phrase

Quand l'éditeur d'un mémo est ouvert, ⌘V / Ctrl+V (ou « Coller » du menu contextuel mobile) avec une
image dans le presse-papiers l'ajoute à la section « 📷 Photos » du mémo, avec une vignette d'attente
puis la vraie vignette, sans passer par un fichier.

## 1. Constats (29 sept., V28.4.271)

- Aucun gestionnaire `paste` dans l'app (grep `clipboardData` = 0).
- « 📷 Photos » = `renderMemoPhotos(cfg)` (`_shared.js.html` ~l.4949), partagé par `index.html`
  (~l.8137), `share.html` (~l.1871), `hub.html` (~l.2366). Chaque page fournit `cfg.onUpload(files)`
  (POST `/api/memos/<id>/images` owner, `/share/<token>/memo/<id>/images` invité + `X-Guest-Token`)
  et `cfg.onChange()`. Le serveur vérifie extension + signature (`_save_uploaded_image`,
  `ALLOWED_IMG_EXT` = png/jpg/jpeg/gif/webp) et génère les vignettes.
- L'`<input type=file>` de la section n'accepte que `image/png,image/jpeg` alors que le serveur
  accepte aussi gif/webp (écart à corriger au passage, point 6).

## 2. Décisions (fermes)

1. **Où** : dans `renderMemoPhotos`, quand `cfg.canEdit` est vrai. La section pose un écouteur
   `paste` sur son **`<dialog>` ancêtre le plus proche** (`wrap.closest('dialog')`), à défaut sur
   `document`. Il est retiré quand la section est démontée (re-rendu ou fermeture : garder une
   référence et `removeEventListener` avant tout nouveau `addEventListener` — une seule instance
   active par éditeur, jamais deux uploads pour un collage).
2. **Quoi** : uniquement les `clipboardData.files` (ou `items` de `kind === 'file'`) dont le type
   commence par `image/`. Si le presse-papiers contient **aussi du texte** (`types` inclut
   `text/plain` ou `text/html` non vide), on ne fait **rien** : le collage texte suit son cours
   (Quill, titre, champs). Si le focus est dans un `<input>` ou `<textarea>` ou dans Quill et que
   le presse-papiers ne contient qu'une image, on **prend** l'image (`preventDefault`) : c'est le
   cas Chrome « copier l'image » → l'utilisateur est souvent dans le corps du mémo.
3. **Nommage** : le fichier du presse-papiers arrive en `image.png` : on le renomme
   `Collage AAAA-MM-JJ HHhMM.png` (extension déduite du MIME : png/jpeg/gif/webp), via
   `new File([blob], name, {type})`. Plusieurs images collées d'un coup → suffixe `-2`, `-3`.
4. **Retour visuel** : dès le collage, une vignette d'attente (`.mp-thumb.mp-pending`, même gabarit
   64 px, fond `--panel-2`, glyphe ⏳ centré, pas de croix) est insérée en fin de grille ; à la fin
   `cfg.onChange()` re-rend la section avec la vraie vignette. Échec (4xx, réseau) → vignette
   retirée + `notify('Collage impossible : …', {error:true})` avec le message serveur s'il existe.
   Aucune confirmation avant envoi. Pas de barre de progression (petits fichiers).
5. **Surfaces** : owner (`memo-edit-dialog`), invité (`share.html`, `canEditMemo`), hub — sans
   code spécifique : tout vit dans `renderMemoPhotos`. Le board, la colonne MÉMOS et la fiche
   dossier **ne réagissent pas** au collage (pas de mémo créé par surprise). Commentaires : hors lot.
6. **Mobile** : même code. iOS/Android envoient `paste` avec fichier depuis le menu contextuel
   « Coller » quand un champ a le focus ; on s'appuie dessus, sans détection d'OS. Au passage,
   l'`accept` de l'`<input type=file>` passe à `image/png,image/jpeg,image/gif,image/webp` pour
   coller au serveur.
7. **Hors périmètre** : coller dans un commentaire, dans la fiche dossier, un non-image (PDF),
   insertion inline dans Quill (interdite aujourd'hui, on ne change pas), drag-and-drop (existe).

## 3. Ce qui NE bouge PAS

Routes et validation serveur ; `cfg` de `renderMemoPhotos` (on **ajoute** rien à la signature :
`onUpload`/`onChange` suffisent) ; visionneuse, rotation, EXIF, carte ; export 28 ; invariant 5
(aucune URL dans le partial) ; invariant 8 (pas de GSAP sur dialog) ; invariant 9 (classes `.mp-*`
existantes + une `.mp-pending`).

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_paste_image.py`. Un collage se simule par
`page.evaluate` : construire un `File` PNG 1×1 (bytes réels, signature valide), créer un
`ClipboardEvent('paste', {clipboardData: new DataTransfer()})` après `dataTransfer.items.add(file)`,
et `dispatchEvent` sur l'élément focalisé.

1. Owner : éditeur ouvert, focus dans Quill, collage PNG → `POST /api/memos/<id>/images` appelé une
   fois (`page.expect_request`), vignette `.mp-pending` visible pendant l'envoi, puis grille avec
   1 image de plus, `memo.images` synchronisé (card du board montre la vignette).
2. Collage **texte + image** (DataTransfer avec `text/plain` et un fichier) → **aucune** requête,
   le texte est collé dans Quill.
3. Collage d'un `text/plain` seul dans le titre → aucune requête, titre modifié.
4. Deux images en un collage → deux POST, noms `Collage … .png` et `… -2.png` (vérifier le
   `filename` multipart).
5. Éditeur **fermé**, collage sur le board → aucune requête, aucune vignette.
6. Réponse 400 simulée (`page.route`) → vignette d'attente retirée, toast d'erreur, grille inchangée.
7. **Invité** (share.html, contributeur approuvé) : collage → POST `/share/<token>/memo/<id>/images`
   avec `X-Guest-Token`, vignette ajoutée. Lecteur seul (`canEdit` faux) → aucune requête.
8. Mobile 412 px (owner) : même scénario que 1.
9. Ouvrir/fermer l'éditeur 3 fois puis coller → **un seul** POST (pas d'écouteurs empilés).

Mutations à poser puis tuer : (a) `preventDefault` retiré (l'image part quand même → double effet
dans Quill : test 1 vérifie que Quill n'a pas reçu de `<img>`) ; (b) filtre `image/` retiré (test 3) ;
(c) écouteur non retiré (test 9) ; (d) `canEdit` ignoré (test 7 lecteur) ; (e) pending non retirée
sur erreur (test 6).

## 5. Livraison

`templates/partials/_shared.js.html`, `tests/front/test_paste_image.py`, `REALISATION.md`
`[V28.5.272]`, `IDEAS.md` (retirer [PASTE-IMAGE] de la file, ajouter la graine [FILE-SIDE-VIEWER]
si absente), ce brief commité. Cycle : tests rouges → code → rebuild LOCAL → `make test` →
journal + handoff → **STOP**. Passe Cowork desktop + mobile (avec Fabien, vrai ⌘V dans Chrome),
puis GO.

## 6. Addendum (Fabien, 29 sept. 15:19) — bouton « 📋 Coller une image »

Le collage clavier (§ 2) est livré et marche ; Fabien veut en plus une **porte visible** dans la
section Photos. Même version V28.5.272.

1. Dans `renderMemoPhotos`, quand `cfg.canEdit`, un bouton « 📋 Coller une image » à droite de
   « ＋ Ajouter une photo » (même gabarit `plusBtn` / Luciole, invariant 9). **Masqué** si
   `navigator.clipboard?.read` n'existe pas (Firefox sans drapeau, contexte non sécurisé).
2. Au clic : `navigator.clipboard.read()` (geste utilisateur → Chrome demande la permission une
   fois, Safari/iOS accepte au tap). Pour chaque `ClipboardItem`, prendre le premier type `image/*`
   (`getType`), construire le `File` avec le **même renommage** `Collage AAAA-MM-JJ HHhMM.ext`
   (`-2`, `-3` si plusieurs) et passer par le **même chemin** que le collage clavier : vignette
   d'attente `.mp-pending` → `cfg.onUpload([file])` → `cfg.onChange()`. Une seule fonction
   interne `pasteFiles(files)` partagée par l'écouteur `paste` et le bouton.
3. Aucune image dans le presse-papiers → `notify('Pas d’image dans le presse-papiers.')` (pas une
   erreur rouge). Permission refusée / `read()` rejette → `notify('Accès au presse-papiers refusé.',
   {error:true})`. Jamais d'exception non capturée.
4. Owner, invité, hub : rien de spécifique, tout est dans le partial.

Tests (`test_paste_image.py`, ajoutés) :
10. Contexte Playwright avec permission `clipboard-read` ; `navigator.clipboard.read` remplacé via
    `page.evaluate` par une promesse renvoyant un `ClipboardItem` PNG 1×1 → clic bouton → un POST,
    vignette d'attente puis grille +1, nom `Collage ….png`.
11. `read()` renvoyant un item `text/plain` seul → aucun POST, toast « Pas d'image ».
12. `read()` rejetant (`NotAllowedError`) → aucun POST, toast erreur, grille inchangée.
13. `navigator.clipboard.read` supprimé avant rendu → bouton absent.
14. Lecteur invité (`canEdit` faux) → bouton absent.

Mutation à poser puis tuer : filtre `image/` retiré (test 11 rougit) ; bouton affiché sans API
(test 13 rougit).
