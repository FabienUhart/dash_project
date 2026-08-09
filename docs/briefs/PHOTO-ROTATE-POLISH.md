# Brief CC — [PHOTO-ROTATE-POLISH] : bouton Enregistrer stable + rafraîchissement fiable

> **Lot fonctionnel** (`app.py` en-têtes de cache + `templates/partials/_shared.js.html`), doctrine
> **TDD rouge-vert**. Deux défauts remontés par Fabien sur la rotation-sauvegarde (V27.39.245), l'un
> **vérifié en live** (décalage de barre), l'autre **diagnostiqué au code** (cache-bust). Décisions
> prises avec lui : **(A)** bouton toujours présent mais **grisé/désactivé** tant qu'il n'y a rien à
> sauver ; **(B)** rafraîchissement **robuste par revalidation ETag** (fin du cache-bust en secondes).
> Applicatif → rebuild local → **tag + Deploy** (prod = V27.40.246).

---

## Vérification live (prod, via Claude in Chrome) — À LIRE EN PREMIER

Reproduit et tranché en direct sur la prod (V27.39.245) : la **rotation elle-même est CORRECTE**. Aperçu = fichier réellement enregistré, **prouvé sur le fichier brut** (ouverture directe de /uploads/<name> avec un cache-buster unique, hors visionneuse) : après une sauvegarde, l original sur le disque est bien à l orientation choisie. **Ne PAS toucher la route rotate_image ni le sens de transpose _ROTATE_TRANSPOSE — ils sont justes.**

**Tout le bug vient du CACHE.** Les images sont servies en cache fort 24 h sans revalidation, et le cache-bust front est en secondes. Après un save, la visionneuse (et la vignette, et la réouverture) resservent l ANCIENNE image → l utilisateur croit que rien n a pris (ou que c est de travers), reclique, et chaque reclic re-pivote pour de vrai → le fichier finit dans une mauvaise orientation. Constaté : le viewer montrait des orientations incohérentes après save alors que le fichier changeait bien à chaque fois. Donc **le Volet B (revalidation ETag) est LE correctif de fond** ; le Volet A (bouton grisé, anti-décalage) reste valable. Aucune correction de rotation à faire.

> NB : pendant le test, une image de « Document via dossierfacile » (dossier Mine) a été redressée et laissée **droite** (vérifiée sur le fichier). Les autres images de travers restent à traiter une fois ce correctif livré.

---

## Volet A — le bouton « Enregistrer » ne doit plus décaler la barre

**Constat (reproduit en live).** Dans `runImageViewer`, `saveRot` est masqué par `display:none` puis
révélé quand l'angle change. La barre `.iv-bar` étant **centrée**, l'apparition du bouton **réélargit
et recentre** la rangée → les flèches ↺ ↻ (et tout le reste) **sautent** sur le côté. Gênant à l'usage.

**Correctif (idée de Fabien).** Le bouton **existe toujours** dans la barre, mais **désactivé/grisé**
tant que `angleNet() === 0`, et **activé** dès qu'on a tourné. Largeur constante → **zéro décalage**.

- À la création : l'ajouter **sans** `display:none`, `disabled` d'emblée.
  ```js
  const saveRot = cfg.rotateUrl ? ivBtn('button', 'device-floppy', 'Enregistrer la rotation') : null;
  if (saveRot) { saveRot.disabled = true; bar.appendChild(saveRot); }   // toujours présent
  ```
- `updateSaveBtn()` bascule l'état **activé**, plus la visibilité :
  ```js
  function updateSaveBtn() { if (saveRot) saveRot.disabled = angleNet() === 0; }
  ```
- Ajouter un **style désactivé discret** pour `.iv-btn` (il n'en a pas) : opacité réduite, `cursor:default`,
  **pas** de teinte accent au survol quand `:disabled`. Monochrome, cohérent avec le reste. Le bouton
  désactivé ne doit pas avoir l'air cliquable.
- Le handler de clic garde son garde `if (!angle) return;` (ceinture + bretelles).

---

## Volet B — la sauvegarde doit se voir du **premier** coup, partout

**Constat.** Les images (dérivées **et** originaux) sont servies avec un **cache fort sans
revalidation** — `send_from_directory(..., max_age=86400)` (route des dérivées + `/uploads/<name>`).
Le nom de fichier ne change pas après une rotation, donc le navigateur **ressert l'ancienne image**.
Le front compense avec `?v=rotated_at`, mais `rotated_at` est en **secondes** : deux sauvegardes dans
la **même seconde** produisent la **même URL** → image non rafraîchie → l'utilisateur croit que rien
n'a pris et **reclique**, et **chaque clic re-pivote pour de vrai** (90→180→270). D'où « il faut
cliquer plusieurs fois » et le résultat qui ne se stabilise qu'en rouvrant la galerie. En prime, la
**vignette de la card** ne suit pas de façon fiable.

**Correctif retenu par Fabien : la revalidation ETag** (le plus robuste — corrige la visionneuse, la
vignette **et** la réouverture d'un seul geste, sans bricolage de paramètre).

1. **Servir les images avec revalidation** au lieu d'un cache figé 24 h. `send_from_directory` sait
   émettre `ETag`/`Last-Modified` et honorer `If-None-Match`/`If-Modified-Since` avec
   `conditional=True`. Il faut **empêcher le navigateur de sauter la revalidation** : passer le
   `Cache-Control` en **`no-cache`** (revalider à chaque fois ; 304 bon marché tant que rien ne
   change, 200 avec la nouvelle image juste après une rotation car le mtime/ETag a changé). Appliquer
   aux **deux** routes (dérivées + `/uploads/<name>`) :
   ```python
   resp = send_from_directory(DERIVED_DIR, dname, max_age=0, conditional=True)
   resp.headers["Cache-Control"] = "no-cache"   # revalidation obligatoire, jamais servi sans ETag check
   return resp
   ```
   > Choix d'en-tête à toi : `no-cache` + ETag est le plus sûr. Si tu crains le surcoût des
   > requêtes conditionnelles sur une grosse galerie, un `max-age` court (ex. 30–60 s) + ETag est un
   > compromis acceptable — **mais** le critère non négociable est : **après une rotation, l'image
   > corrigée s'affiche partout sans hard-refresh**. Documente le choix au journal.
2. **Alléger le front.** Avec la revalidation, le hack `busts`/`?v=rotated_at` (secondes) n'est plus
   la garantie — on peut le **retirer**. Pour un rafraîchissement **instantané** de la visionneuse au
   clic Enregistrer, garder un **rechargement forcé unique** de l'image courante (jeton **ms**
   `Date.now()`, ou `img.src = img.src.split('?')[0] + '?size=s&_r=' + Date.now()`, ou un `fetch(url,
   {cache:'reload'})` suivi d'une réassignation) — **pas** les secondes serveur. Le reste (vignette
   de la card via `onRotated`/`loadAll`, réouverture de la galerie) s'appuie sur l'ETag et se corrige
   tout seul.
3. **Plus de sur-rotation.** Avec (A) le bouton désactivé quand rien à sauver et (B) l'image qui
   reflète immédiatement l'état réel, l'utilisateur ne reclique plus dans le vide. Vérifier qu'un
   double-clic rapide ne cumule pas (le `saveRot.disabled = true` pendant le POST est déjà là).

---

## Tests (TDD)

**Back (`tests/back/`)**
1. `test_derivative_served_with_revalidation` — `GET` d'une dérivée renvoie un **ETag** (ou
   Last-Modified) et un `Cache-Control` qui **force la revalidation** (`no-cache`, ou `max-age` court) ;
   une requête conditionnelle `If-None-Match` avec le bon ETag → **304**.
2. `test_derivative_etag_changes_after_rotate` — ETag `E1` avant ; `POST /api/images/<name>/rotate` ;
   nouvel ETag `E2` **différent** + **200** (contenu changé). C'est la preuve que le navigateur
   refetcherait. Idem pour l'original `/uploads/<name>` s'il est aussi réécrit.
3. Les tests de rotation existants (`test_image_rotate.py`) restent **verts**.

**Front (e2e / DOM)**
4. Bouton Enregistrer **présent et `disabled`** à l'angle 0 ; après un clic ↻, **`enabled`**. Et le
   **nombre de boutons de la barre est identique** entre angle 0 et après rotation (preuve : plus de
   décalage). Ouvre par une vraie porte (galerie), pas `runImageViewer` en direct.

Éprouve par mutation au moins le changement d'ETag après rotation (#2) et l'état disabled↔enabled (#4).

---

## Definition of Done

1. Volet A : bouton toujours présent, `disabled` tant que `angleNet()===0`, style désactivé discret,
   **aucun décalage** de la barre.
2. Volet B : dérivées + `/uploads/<name>` servis **avec revalidation** (ETag, `Cache-Control`
   revalidant) ; hack `?v=secondes` retiré ; rafraîchissement **instantané** de la visionneuse au
   clic, et propagation à la vignette + réouverture via ETag.
3. `make test` **entièrement vert** ; tests §ci-dessus rouges avant / verts après.
4. **Vérif à l'œil Fabien** (le juge) : ouvrir une photo de travers → le bouton est **grisé** ; ↻ →
   il **s'active** sans bouger la barre → Enregistrer **une fois** → l'image est droite **tout de
   suite** (visionneuse), et le reste (vignette, fermeture/réouverture, rechargement de page) est
   droit aussi. Plus besoin de cliquer plusieurs fois.
5. `git status` : `app.py`, `templates/partials/_shared.js.html`, `tests/…`, `REALISATION.md`. Pas de
   `.idea`. Rebuild local. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**,
   puis **tag + Deploy**.

## Portée

Uniquement la robustesse du rotate-save (UX barre + rafraîchissement). Pas de nouvelle capacité, pas
la carte, pas les invités. La revalidation ETag bénéficie à **toutes** les images (bonus), mais on ne
touche que les deux routes de service — pas la génération des dérivées.
