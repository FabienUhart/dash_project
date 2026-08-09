# Brief CC — [MAP-PHOTO-COUNT] : le bouton Carte compte AUSSI les photos géolocalisées

> **Lot fonctionnel** (`app.py` + `templates/index.html` + tests), doctrine **TDD rouge-vert**.
> Décidé avec Fabien : le bouton **Carte** d'un dossier doit apparaître **dès qu'il y a un point de
> géo dans les mémos — localisation manuelle OU photo géotaguée** — et **le badge compte tous ces
> points**. Estimation : **7/10**. Applicatif → rebuild local → **tag + Deploy** au bout.

---

## 1. Le constat (confirmé par Fabien + audit code)

Un dossier dont les mémos ont des **photos géolocalisées** (ex. « newss » → mémo « REVUs », 3 photos
avec GPS) mais **aucune localisation manuelle** sur un mémo n'affiche **pas** le bouton Carte. On ne
peut donc même pas ouvrir la carte pour voir ces photos. La donnée existe pourtant : `_record_image_meta`
peuple `image_meta` (lat/lng/`has_gps`) à chaque upload, et la visionneuse affiche bien le lieu.

**Cause :** le bouton (`templates/index.html`, `if (mapPoints.length)` ~l.8671) ne dépend que de
`boardMapPoints()`, qui ne lit que `m.location` (localisation **manuelle** du mémo, `_parse_location`),
**jamais** `image_meta`. Le calque photo n'est chargé qu'à l'ouverture de la carte. Ce garde est
inchangé depuis juin — ce n'est donc pas une régression récente mais un **angle mort** : le bouton a
toujours ignoré la géo des photos. On le corrige.

---

## 2. Backend — exposer un compteur de photos géolocalisées par mémo

Dans `GET /api/memos` (`list_memos`, ~l.3651), ajouter à chaque dict de mémo un champ
**`geo_photo_count`** = nombre de photos **géolocalisées** (`has_gps = 1`) et **non en corbeille**
de ce mémo. **En batch** (pas de N+1), sur le modèle de `_attachments_map` déjà utilisé l.3685 :

```python
# [MAP-PHOTO-COUNT] nb de photos GÉOLOCALISÉES par mémo (hors corbeille image) — pour que le
# bouton Carte reflète la géo des photos, pas seulement la localisation manuelle des mémos.
ids = [r["id"] for r in rows]
geo_counts = {}
if ids:
    ph = ",".join("?" * len(ids))
    for row in db.execute(
        f"SELECT memo_id, COUNT(*) AS n FROM image_meta "
        f"WHERE has_gps = 1 AND memo_id IN ({ph}) "
        f"AND filename NOT IN (SELECT filename FROM image_trash) "
        f"GROUP BY memo_id", ids).fetchall():
        geo_counts[row["memo_id"]] = row["n"]
# puis, dans la boucle qui construit les dicts :
d["geo_photo_count"] = geo_counts.get(d["id"], 0)
```

> Réutilise **exactement** le même filtre corbeille que `_project_photos` (`has_gps`, `NOT IN
> image_trash`) pour que le compteur et le calque **ne divergent jamais**. Ne PAS toucher
> `_memo_dict` (pas de requête DB dedans — le comptage vit dans `list_memos`, en batch).
> Le champ n'entre **pas** dans l'export (donnée dérivée, invariant 1 : `APP_VERSION` reste 27).

---

## 3. Frontend — garde du bouton, badge, et ouverture sans avortement

### (a) `boardMapPoints` reste tel quel (points-mémo). On calcule le total photo à côté

Dans le bloc du bouton Carte (`index.html` ~l.8670), scoper le **même** ensemble de mémos que
`boardMapPoints()` (soit `visibleMemos().filter(boardScopeFilter())`) et sommer `geo_photo_count` :

```js
const mapPoints = boardMapPoints();
const realProject = state.memoProject !== 'all' && state.memoProject !== 'inbox';
// [MAP-PHOTO-COUNT] total des photos géolocalisées du même périmètre. Le calque photo n'existe
// que sur un vrai projet (loadPhotos scopé) → on ne compte les photos que là (cohérent avec la spec
// « pas de calque sur all/inbox »).
const photoGeo = realProject
  ? visibleMemos().filter(boardScopeFilter()).reduce((s, m) => s + (m.geo_photo_count || 0), 0)
  : 0;
if (mapPoints.length || photoGeo) {
  tb.add({ icon: 'map', label: 'Carte', count: mapPoints.length + photoGeo,   // badge = TOUS les points
    title: 'Voir les points géolocalisés de cette vue (mémos et photos) sur une carte',
    onClick: () => openMapDialog(mapName, boardMapPoints(), boardMapPoints,
      // ouvre sur le calque photo si aucun point-mémo (sinon la carte avorterait, cf. §b)
      mapPoints.length ? {} : { autoPhoto: true }) });
  tbCount++;
}
```

### (b) Ne pas avorter quand il n'y a que des photos

`runMapDialog` fait `if (!points.length && !cfg.autoPhoto) { notify('Aucun élément géolocalisé…'); return; }`
(`_shared.js.html` ~l.1275). D'où le `autoPhoto: true` ci-dessus **quand `mapPoints` est vide** : la
carte s'ouvre directement sur le **calque photo** (`loadPhotos` est déjà câblé côté owner pour un vrai
projet, l.~4324) au lieu de refuser de s'ouvrir. Vérifie que, dans ce cas, le calque se charge et les
marqueurs photo s'affichent. Si `mapPoints` **n'est pas** vide, ouverture normale (le 📷 reste
disponible en bascule).

> **À vérifier** (et signaler si le réel diffère) : que `autoPhoto:true` + `loadPhotos` présent
> suffit à afficher les photos sans point-mémo. Si `runMapDialog` a besoin d'autre chose (ex. un
> `points` non vide pour centrer), centrer sur le 1er point photo — sans réintroduire l'avortement.

---

## 4. Tests — le flux complet (c'est la demande explicite de Fabien)

**Réseau interdit** : `_record_image_meta` appelle `_image_exif` → `_reverse_geocode` (Nominatim). La
garde zéro-réseau le bloquerait (comme au lot rotate). **Monkeypatch `app._image_exif`** pour renvoyer
un dict connu — ça évite le réseau ET le forgeage d'EXIF GPS.

### Back (`tests/back/`)

1. **`test_upload_geotagged_photo_records_has_gps`** — `monkeypatch _image_exif → {lat, lng, label,
   datetime}` ; upload d'une image sur un mémo → la ligne `image_meta` a **`has_gps = 1`** + lat/lng.
2. **`test_memos_expose_geo_photo_count`** — même montage → `GET /api/memos` renvoie
   **`geo_photo_count >= 1`** pour ce mémo ; un mémo sans photo géo → **0**.
3. **`test_geo_photo_count_excludes_trashed_image`** — une photo géo mise en **corbeille image** ne
   compte plus (aligné sur `_project_photos`).
4. **`test_photo_without_gps_not_counted`** — `_image_exif → {}` (pas de GPS) → `has_gps = 0`,
   `geo_photo_count` inchangé.

Éprouve par **mutation** au moins le filtre `has_gps = 1` (#4) et l'exclusion corbeille (#3).

### Front (e2e, la vraie régression)

5. **e2e** : un dossier (vrai projet) dont **un mémo a une photo géolocalisée et AUCUNE localisation
   manuelle** → le bouton **Carte** est **présent** dans la barre du dossier, et un clic ouvre la
   carte **sans** le message « Aucun élément géolocalisé ». Monte l'état par l'API (upload + stub
   `_image_exif` côté serveur de test, ou insertion directe dans `image_meta`). Ouvre par la **vraie
   barre**, pas en appelant `openMapDialog` en direct — c'est la leçon du lot précédent : un test qui
   court-circuite la porte ne prouve rien sur la porte.

---

## 5. Definition of Done

1. `geo_photo_count` exposé par `GET /api/memos` (batch, `has_gps=1`, hors `image_trash`), **aucune
   requête dans `_memo_dict`**, export 27 inchangé.
2. Bouton Carte : apparaît si `mapPoints.length || photoGeo` (vrai projet) ; badge = `mapPoints.length + photoGeo` ;
   ouverture en `autoPhoto` quand il n'y a que des photos → **pas d'avortement**, calque photo visible.
3. Tests §4 **rouges avant / verts après**, mutation sur les gardes clés ; e2e par la vraie barre.
4. `make test` **entièrement vert** (back + e2e) ; garde zéro-réseau verte (géocodeur stubbé).
5. `git status` : `app.py`, `templates/index.html`, `tests/…`, `REALISATION.md`. Pas de `.idea`.
6. **Vérif à l'œil Fabien** (le juge) : ouvrir « newss » → le bouton Carte est là (badge = nb de
   photos géo) → clic → la carte s'ouvre et montre les photos de REVUs.
7. Rebuild local, journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**, puis
   **tag + Deploy** (prod actuelle : V27.39.245).

## 6. Portée

Le bouton Carte du **dossier** (barre d'en-tête), owner. Pas de nouveau calque, pas de refonte de la
carte, pas la carte invité (parité `/share/*` = lot séparé si tu la veux). Une intention : que la
présence de photos géolocalisées **suffise** à ouvrir la carte du dossier.
