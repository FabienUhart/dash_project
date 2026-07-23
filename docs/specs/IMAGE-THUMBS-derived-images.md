# [IMAGE-THUMBS] — Images dérivées côté serveur (vignettes + taille écran)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Décision Fabien : option « dérivées Pillow », originaux intacts.**

## Problème

Aucun redimensionnement n'existe : `/uploads/<nom>` sert l'original partout (cards, filmstrip [VIEWER-FILMSTRIP], visionneuse, carte photos, desktop ET mobile). Photos réelles : 8-9 Mo pièce → chargements très lents en mobile (vécu au festival), et chaque vignette de card tire le fichier complet pour un affichage 50 px.

## Décisions figées

1. **Deux tailles dérivées** générées côté serveur : **`t`** (vignette, ~400 px de grand côté — cards, bande de vignettes, calque photo carte) et **`s`** (taille écran, ~1600 px de grand côté — visionneuse). JPEG qualité ~82, orientation EXIF appliquée (`ImageOps.exif_transpose`).
2. **Originaux JAMAIS modifiés** sur disque ; le bouton ⬇ de la visionneuse télécharge toujours le brut.
3. Nouvelle dépendance **`Pillow`** (épinglée) dans `requirements.txt` — décision explicite de Fabien (ExifRead reste pour l'EXIF, rien ne change là).
4. **Donnée dérivée, pattern `image_meta`** : re-calculable depuis les fichiers → **rien dans l'export** (le JSON continue de ne porter que les noms d'images originales, compat v23 inchangée, pas de bump).

## Versionnage

- Export **inchangé** (`APP_VERSION` reste "23"). Lot = **V23.4.Z** (nouvelle mineure, backend ; Z = dernier `REALISATION.md` + 1 — après le train quick wins V23.3.91→95).

## Spécification

### Stockage

- Dérivées dans **`data/uploads/derived/`** (même volume Docker) : `t_<nom>.jpg` et `s_<nom>.jpg` (préfixe, pas de collision possible avec les noms `uuid4().hex.ext` validés par regex).
- **Cas particuliers** : GIF (animé possible) → **pas de dérivée**, servir l'original ; image plus petite que la cible → pas d'agrandissement (copie/lien vers l'original à la volée côté route, pas de fichier dupliqué) ; échec Pillow (fichier corrompu) → log silencieux, fallback original.

### Génération

- **À l'upload** : partout où `_save_uploaded_image()` accepte un fichier (owner ET invité — sites d'appel existants), générer `t` + `s` juste après l'écriture (même transaction de vie que `_record_image_meta`).
- **Backfill des images existantes** : daemon thread idempotent au démarrage (modèle exact de `_backfill_image_meta` : skip si dérivées déjà présentes, throttle léger, jamais bloquant).
- **Filet** : si une route dérivée est appelée et que le fichier manque (backfill pas passé), générer à la volée puis servir ; en cas d'échec, servir l'original (dégradation propre, jamais de 404 pour une image existante).

### Routes — AUCUNE route nouvelle, un query param

- **`?size=t|s`** sur les routes image **existantes** : owner `/uploads/<nom>` et invité `/share/<token>/image/<nom>` (le contrôle de scope existant s'applique tel quel — invariant 5, aucun périmètre élargi). Sans param ou valeur inconnue = original (compat totale).
- Valider `size` par liste blanche stricte (`t`/`s`), jamais interpolé dans un chemin sans passer par les noms générés.

### Purge en cascade

- Toute suppression définitive d'un fichier image (les 4 sites qui appellent `_forget_image_meta` : suppression per-image owner/invité, purge mémo, `_purge_trash`) supprime **aussi** `t_`/`s_` — étendre le helper existant plutôt qu'en créer un parallèle.

### Frontend (3 pages + partial)

- **`size=t`** : miniatures des cards, bande de vignettes de la visionneuse ([VIEWER-FILMSTRIP]), marqueurs/frise du calque photo carte, section 📷 de la pop-in ([MEMO-EDITOR-IMAGES]).
- **`size=s`** : image principale de la visionneuse (`runImageViewer.imageUrl`).
- **original** : bouton ⬇ (`downloadUrl`) et badge EXIF (le serveur lit l'original, inchangé).
- Hors périmètre V1 : les aperçus d'**attachments** (v22) gardent leur comportement actuel (à traiter plus tard si besoin).

## Docker / déploiement

- `requirements.txt` += `Pillow==<version stable épinglée>` ; rebuild image (wheels dispo sur la base Debian, pas de compilation attendue). `data/uploads/derived/` créé au démarrage (`os.makedirs(..., exist_ok=True)`).

## Tests avant fin (copie de base, jamais `data/dashboard.db`)

1. `python3 -m py_compile app.py` + démarrage : `data/uploads/derived/` créé, backfill lance et log le nombre généré (11 fichiers actuels, ~19 photos du mémo test).
2. Upload d'une photo 8 Mo → `t_`/`s_` créés ; `/uploads/<nom>?size=t` ≪ 100 Ko ; sans param = original octet pour octet.
3. Invité : `/share/<token>/image/<nom>?size=t` OK dans le scope, refusé hors scope (comme aujourd'hui) ; sonde bypass inchangée.
4. Suppression d'une image → original + 2 dérivées disparus. Purge corbeille idem.
5. GIF → servi brut quel que soit `size`. Fichier corrompu → original servi, pas de 500.
6. `GET /api/export` → JSON strictement identique à avant (aucune mention des dérivées) ; ré-import → 0 ajout.
7. Visionneuse : image principale nette (~1600 px) et rapide, ⬇ = original, vignettes de bande en `t`.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.4.Z] + `IDEAS.md` → Fait) + **mettre à jour `CLAUDE.md`** (section uploads/invariant 6 : mentionner Pillow et `data/uploads/derived/` — donnée dérivée jamais exportée, ne jamais y toucher dans un commit) → `docker compose up -d --build` (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork via Chrome : poids réseau vignettes vs originaux (onglet Network), owner + invité.
