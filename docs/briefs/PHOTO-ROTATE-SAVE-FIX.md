# Brief CC — [PHOTO-ROTATE-SAVE-FIX] : le bouton « Enregistrer la rotation » sur **toutes** les portes

> **Correctif dans le lot NON commité** [PHOTO-ROTATE-SAVE] (V27.39.245). Vérif à l'œil de Fabien :
> la rotation s'affiche bien, **mais le bouton disquette n'apparaît pas** quand on ouvre la photo
> par la **vignette d'une card compacte** (ni par la couverture immersive, ni par la grille photos
> de la fiche/éditeur). Symptôme confirmé par Fabien : *« ça fonctionne bien, juste il n'y a pas de
> bouton sauvegarder pour persister »*.
>
> **La route est bonne — c'est le branchement front qui est incomplet.** Ne rien toucher côté
> serveur. Front only + un e2e. On corrige **avant de committer** (décision Fabien) : ça reste le
> même lot, même version, on ré-STOP pour une passe Cowork.

---

## 1. La cause : config de visionneuse dupliquée, rotate câblé à 2 portes sur ~6

`runImageViewer` n'affiche le bouton `device-floppy` que si l'appelant passe `cfg.rotateUrl`. Or
`rotateUrl`/`onRotated` n'ont été ajoutés qu'à **deux** points d'ouverture des **photos d'un mémo**
(owner) :

- ✅ `templates/index.html` — `pictos.onImages` (le picto 📷) — OK
- ✅ `_shared.js.html` — `runPhotoView` `openFull` (carte-photo projet) — OK

Les **autres portes vers les mêmes `memo.images`** ne le passent pas → pas de bouton :

- ❌ `templates/index.html` — **`applyCardThumb` `onOpen`** (vignette de card **compacte**) — *c'est
  la porte que Fabien a cliquée sur REVUs*
- ❌ `templates/index.html` — **`applyCardCover` `onOpen`** (couverture en mode **Immersif**)
- ❌ `templates/index.html` — **`onOpenPhoto`** dans `memoViewCfg()` (la **fiche** 👁 du mémo)
- ❌ `_shared.js.html` — **`renderMemoPhotos`** (grille « 📷 Photos » de l'éditeur/fiche) : sa
  `runImageViewer` ne relaie pas `rotateUrl`. **Pire** : `renderMePhotos` (index) lui passe déjà
  `canRotate: true` — mais `renderMemoPhotos` **ne lit jamais** ce flag → coup d'épée dans l'eau.

> Chercher les lignes par **nom** (`applyCardThumb`, `applyCardCover`, `onOpenPhoto`, `renderMemoPhotos`),
> pas par numéro (ils bougent). Ne PAS toucher les `openImage` d'**attachements** (`imageUrl: x => x.url`) :
> la rotation des pièces jointes-images est **hors v1** (comme au brief initial).

---

## 2. Le correctif : une seule fabrique + un relai (anti-récidive)

Le bon geste n'est pas de recopier `rotateUrl` aux 4 endroits (on en oubliera un au prochain lot).
On **centralise**.

### (a) `index.html` — une fabrique unique de config visionneuse-photos owner

Créer **un** helper qui construit la config `runImageViewer` d'un mémo, avec **tout** dedans
(navigation, suppression, **rotation**), et l'appeler partout :

```js
// [PHOTO-ROTATE-SAVE-FIX] source UNIQUE de la config visionneuse des photos d'un mémo (owner).
// Toute porte (picto, vignette compacte, couverture, fiche) passe par ici → le bouton
// « Enregistrer la rotation » est présent PAR CONSTRUCTION, plus par copier-coller.
function ownerMemoPhotoViewer(memo, startIndex) {
  return {
    images: memo.images, startIndex: startIndex || 0,
    imageUrl: (n) => `/uploads/${n}`, downloadUrl: (n) => `/uploads/${n}`,
    exifUrl: (n) => `/api/image-exif/${n}`,
    canDelete: true,
    onDelete: async (n) => { await fetch(`/api/memos/${memo.id}/images/${n}`, { method: 'DELETE' }); await loadAll(); },
    rotateUrl: (n) => `/api/images/${n}/rotate`,
    onRotated: () => { loadAll(); },
  };
}
```

Puis **remplacer** les 4 configs inline par un appel à la fabrique :

- `pictos.onImages` → `() => runImageViewer(ownerMemoPhotoViewer(memo))`
- `applyCardThumb` `onOpen` → `() => runImageViewer(ownerMemoPhotoViewer(memo))`
- `applyCardCover` `onOpen` → `() => runImageViewer(ownerMemoPhotoViewer(memo))`
- `memoViewCfg().onOpenPhoto` → `(images, i) => runImageViewer(ownerMemoPhotoViewer(memo, i))`
  (⚠ ce site reçoit `(images, i)` ; garder `startIndex = i`. Vérifier que `memo` est bien en scope
  dans `memoViewCfg` — sinon reconstruire la cfg avec les mêmes URLs et `startIndex: i`.)

### (b) `_shared.js.html` — `renderMemoPhotos` doit **relayer** `canRotate`

Aligner sur ce que fait déjà `runPhotoView` : dans la `runImageViewer` de `renderMemoPhotos`,
ajouter

```js
rotateUrl: cfg.canRotate ? ((n) => '/api/images/' + n + '/rotate') : null,
onRotated: cfg.canRotate ? (() => { if (cfg.onChange) cfg.onChange(); }) : null,
```

Ainsi `renderMePhotos` (qui envoie déjà `canRotate: true`) fonctionne, et les invités (pas de
`canRotate`) restent inchangés. **Ne pas** mettre `canRotate` par défaut à `true` : owner-only.

> Après coup, **vérifier qu'aucune autre porte owner vers `memo.images` ne subsiste** sans la
> fabrique (grep `runImageViewer` dans `index.html`, ne garder hors fabrique que les attachements
> `x.url`). Si une existe, la brancher aussi ou **signaler**.

---

## 3. Le garde-fou : e2e par la **vignette** (la porte qui a cassé)

L'e2e actuel appelle `runImageViewer` en direct — il n'aurait jamais vu ce trou. Ajouter un e2e qui
**ouvre par le vrai DOM d'une card compacte** :

1. créer un mémo owner avec ≥ 1 image, board en **Compact** ;
2. cliquer la **vignette de la card** (`applyCardThumb`) ;
3. assert : le bouton **« Enregistrer la rotation »** (`device-floppy`) est **présent** dans la
   barre de la visionneuse (masqué tant qu'on n'a pas tourné, donc tester sa **présence dans le
   DOM**, puis cliquer ↻ et vérifier qu'il **s'affiche**).

> Si le sélecteur de la vignette est fragile (les deux sélecteurs de carte de l'e2e initial avaient
> expiré), rabats-toi sur la **couverture immersive** ou la grille de la fiche — l'essentiel est de
> passer par **une porte réelle**, pas par `runImageViewer` direct. **Signale** le chemin retenu.

---

## 4. Definition of Done

1. `ownerMemoPhotoViewer` (ou nom équivalent) en **source unique** dans `index.html`, appelée par
   picto / vignette compacte / couverture immersive / fiche. `renderMemoPhotos` relaie `canRotate`.
2. Vérif à l'œil (à refaire, c'est le juge) : ouvrir une photo de travers **par la vignette d'une
   card compacte** → ↻ → **le bouton disquette apparaît** → Enregistrer → fermer/rouvrir : **droite**,
   vignette de la card comprise. Idem par la couverture immersive et la fiche.
3. e2e « ouverture par une porte réelle » vert. `make test` **entièrement vert** (back + e2e).
4. `git status` : `templates/index.html`, `templates/partials/_shared.js.html`, le test e2e, et
   `REALISATION.md`. **Aucun `app.py`** (la route est déjà bonne). Ne pas committer `.idea/`.
5. Rebuild local `docker compose up -d --build`. Journal + `handoff.json`, **STOP** — c'est le même
   lot [PHOTO-ROTATE-SAVE] : on ré-passe Cowork puis **GO → commit + tag + push + Deploy** de la
   V27.39.245 (le §6 périmé du brief initial est corrigé : la prod est déjà sur V27.38.244).

## 5. Portée

Uniquement le branchement des portes + le garde-fou. Pas de nouvelle capacité, pas de serveur, pas
d'attachements. Une intention : que « Enregistrer la rotation » soit là **partout** où l'owner
regarde une photo.
