# Brief CC — [FRISE-STEP-NOGPS] : un chip de frise sans position bascule le jour et invite à en ajouter une

> **Front pur (`_shared.js` + cfg par page), zéro route nouvelle si le géocodage est déjà exposé côté
> share (à vérifier, sinon une route `/share/<token>/geocode` en projection stricte), `app.py`
> intact sinon, export 28 inchangé.** Constat Fabien du 30 sept. 2026 (carte Voyage Japon, prod) :
> sur Jour 5, cliquer le chip « nol kyoto sanjo — passage… » (6 nov.) ne fait rien ; il faut
> cliquer « Jour 6 » d'abord. Arbitrage Fabien : niveau 2 (inviter à géolocaliser) + niveau 1
> (signaler) ; niveau 3 (deviner) en graine. Doctrine TDD. Cible **V28.10.277**
> ([GUEST-SEARCH-GRAMMAR] passe en V28.11.278).

## 1. Cause du bug

`renderFrieze` (~l.2340) : chip **avec** GPS → `switchDayThenLocate` + `setView` ; chip **sans**
GPS → `openPassageOnPorter(p)` (~l.2118), qui retourne **avant** toute bascule de jour quand
`cfg.passageInfo(p.id)` n'a pas de `ll` (mémo 290 : ni position, ni dossier porteur géolocalisé).
Le chip garde `cursor: pointer`, donc il a l'air cliquable.

## 2. Décisions (fermes)

1. **Signaler** (niveau 1) : un chip sans position ni porteur géolocalisé porte un glyphe discret
   « 📍 » barré / atténué (icône trait, `title="Pas de position"`) ; la liste de droite ajoute en
   bas une section « Sans position · n » qui liste ces mémos (mêmes lignes, sans pastille couleur,
   clic = même comportement que le chip).
2. **Toujours** basculer le jour et sélectionner le chip au clic, avant tout test de géolocalisation
   (`switchDayThenLocate` + `selectStep` remontés avant le `return` de `openPassageOnPorter` ; les
   chips sans `cfg.passageInfo` reçoivent aussi ce `click`). `flyTo` + bulle carte seulement si `ll`.
3. **Inviter** (niveau 2) : pour un chip sans position, une **bulle ancrée sur le chip** (pas sur la
   carte ; `div` positionné, pas un `<dialog>` — invariant 8 ; classes Luciole existantes) :
   « Pas de position » + champ « 📍 Adresse… (Entrée) » + bouton « Ma position » (géoloc navigateur),
   Échap / clic ailleurs = fermer. Entrée → `cfg.geocode(q)` (owner : `geocodeAddress` existant via
   `/api/geocode` ; share/hub : cfg fournie par la page, route de projection si absente) → si
   résultat : `cfg.saveLocation(p, {lat, lng, label})` (owner : `PUT /api/memos/<id>` ; invité :
   route share existante d'édition du mémo, uniquement si `can_edit`) → le point apparaît, la carte
   se centre (`setView 15`), le chip perd son glyphe, la bulle se ferme, toast discret « Position
   ajoutée ». Sans résultat : message dans la bulle « Adresse introuvable ». Lecteur (pas de droit
   d'édition) : la bulle affiche seulement « Pas de position ».
4. Re-clic sur le chip sélectionné : ferme la bulle et désélectionne, jour inchangé.
5. **Hors périmètre** (graine [FRISE-GUESS-LOCATION]) : proposer la position d'un mémo relié
   (LINK-REFS) ou d'un mémo homonyme du même jour (« KYOTO · nol kyoto sanjo » en a une).

## 3. Ce qui NE bouge PAS

Chips géolocalisés, bulles carte, `applyDay`, snapshot/restore, `/api/geocode`, export 28,
invariant 5 (aucune URL dans le partial : tout passe par `cfg.geocode` / `cfg.saveLocation`).

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_frise_step_nogps.py` (dossier voyage 2 jours : J1 un mémo géolocalisé ; J2 un mémo
sans position dans un sous-dossier sans position, + un mémo J2 géolocalisé ; géocodage mocké par
`page.route('/api/geocode*')`).
1. Filtre Jour 1 → clic chip sans position → Jour 2 actif, chip sélectionné, bulle « Pas de
   position » ouverte sur le chip, centre de carte inchangé, glyphe présent sur le chip, section
   « Sans position · 1 » à droite.
2. Saisir « Kyoto Sanjo » + Entrée → `PUT /api/memos/<id>` avec `location.lat/lng/label`, point
   ajouté, carte centrée, glyphe disparu, section « Sans position » vide/masquée, toast.
3. Géocodage sans résultat (route renvoyant `[]`) → message « Adresse introuvable », aucun PUT.
4. Chip géolocalisé J2 depuis Jour 1 → Jour 2 + `setView` (non-régression).
5. Re-clic sur le chip sélectionné → bulle fermée, désélection, jour inchangé.
6. Share (contributeur) : même parcours que 2 via les routes share ; lecteur : bulle sans champ,
   aucun PUT.
7. Zéro erreur console.
Mutations : `return` remis avant la bascule (1) ; `saveLocation` non appelé (2) ; champ affiché au
lecteur (6) ; glyphe jamais posé (1).

## 5. Livraison

`templates/partials/_shared.js.html`, `templates/index.html`, `templates/share.html`,
`templates/hub.html` (cfg), `app.py` seulement si route de projection nécessaire (+ tests back),
`tests/front/test_frise_step_nogps.py`, `REALISATION.md`, `IDEAS.md` (retirer le lot, ajouter la
graine [FRISE-GUESS-LOCATION]), ce brief. Cycle habituel, **STOP** au rebuild local, passe Cowork
owner + share, GO.
