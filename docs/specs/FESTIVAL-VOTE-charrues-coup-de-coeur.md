# [FESTIVAL-VOTE] — Dossier « Vieilles Charrues 2026 » : coups de cœur ❤️ + votes envies + écran Résultats

**Statut** : brief verrouillé (cadrage Fabien × Cowork, 13 juil. 2026) → **à coder par Claude Code**.
**Cible** : **V23.1.z** (mineure, pas de bump export — voir § Versionnage).
**⏰ URGENT : le festival a lieu du jeudi 16 au dimanche 19 juillet 2026.** Le lot doit être livré, validé et déployé en prod **au plus tard mercredi 15 au soir** pour que les amis puissent voter avant le départ.

## Contexte & objectif

Fabien va aux Vieilles Charrues avec des amis. Plusieurs scènes, des artistes qui jouent en même temps : il faut construire le parcours du groupe. Chacun (Fabien + invités) doit pouvoir :

1. Marquer ses **coups de cœur ❤️** — ses incontournables. Règle dure : **une même personne ne peut pas avoir deux ❤️ dont les créneaux se chevauchent** (on ne peut pas être à deux concerts à la fois). Plusieurs ❤️ possibles tant qu'ils sont compatibles.
2. Voter librement pour ses **envies secondaires** (vote multi classique, illimité).
3. Consulter un **écran « Résultats »** en continu (le vote reste ouvert) : les artistes les plus demandés + les coups de cœur nominatifs de chaque ami. Visible par l'owner ET les invités approuvés ; anonyme = lecture seule.

## Décisions verrouillées (Fabien)

- Coup de cœur = **plusieurs par personne, sans chevauchement de créneau** (contrôle serveur, pas seulement UI).
- Structure du dossier calquée sur le site officiel : **timetable par scène → jour → passage**.
- Écran Résultats **dédié**, visible par **tout le monde en continu**, vote jamais figé (pas de deadline).
- Lot prioritaire, passe **avant** le cluster [NAV & MOBILE] restant.

## Données & seed

Fichier fourni : `docs/specs/festival-vote-seed-vieilles-charrues-2026.json` — **83 passages** extraits du site officiel (widget timetable, 13 juil. 2026) : 6 scènes (Glenmor 15, Kerouac 16, Grall 18, Gwernig 12, Guinguette 18, Esplanade 4), avec **jour, date, heure de début ET de fin**.

- Structure à créer : dossier racine **« Vieilles Charrues 2026 »** + 6 sous-dossiers (un par scène), un **mémo par passage** : `title` = nom d'artiste, `due_date` = date du jour de festival, `due_time` = heure de début, `location` = scène (texte). Emoji suggéré 🎤 (ou 🎪 pour Guinguette/Esplanade).
- **Un mémo = un PASSAGE** (artiste × créneau) : les répétitions Guinguette/Esplanade (DRAGSHOW, PUMPELOP, BATTLEDRUM GALACTICA, BOREAL SOUND SYSTEM…) donnent bien plusieurs mémos, distingués par jour/heure.
- **Convention post-minuit** : un passage appartient à son **jour de festival** même s'il déborde (INTERPOL « samedi 00:15 » = nuit de samedi à dimanche, `due_date` = 2026-07-18). Pour tout calcul : si `start` < 12:00 → +24h ; si `end` ≤ `start` → `end` +24h.
- Mécanisme de seed au choix de CC : script one-shot idempotent (relançable local puis prod sans doublon), ou fichier d'import v23 passé par [IMPORT-PREVIEW]. L'idempotence est le critère.

## Plan du festival & carte (ajout cadrage 13 juil.)

Deux intégrations du plan officiel, décidées par Fabien — **zéro code nouveau**, uniquement du seed s'appuyant sur l'existant :

1. **Plan en pièce jointe du dossier racine** via [FOLDER-ATTACHMENTS] (V23.0.74) : les images du plan illustré 2026 attachées au dossier « Vieilles Charrues 2026 » → consultables par les amis depuis le partage (aperçu inline image). **Source** : le plan illustré 2026 n'est pas encore dans la médiathèque WP du site (vérifié le 13 juil. via `/wp-json/wp/v2/media`) — images récupérées par Fabien (Google Images), déposées directement dans **`docs/specs/`** (fichiers `plan-festival-2026-*.png|jpg`, ou à défaut toute image de `docs/specs/` dont le nom contient « plan »). Si absentes au moment du seed : sauter la pièce jointe du plan illustré (garder le plan d'accès), le noter dans le handoff — non bloquant. En complément, joindre aussi le **plan d'accès officiel 2026** : `https://www.vieillescharrues.asso.fr/wp-content/uploads/2026/06/Plan_acces-2026_fd-1-scaled.png` (téléchargement one-shot au seed, pas de dépendance runtime — invariant 6).
2. **Scènes géolocalisées** : chaque sous-dossier scène reçoit une `location` `{lat, lng, label}` (fournie dans le seed, bloc `scene_locations`) → les 6 scènes apparaissent comme pins sur la carte Leaflet existante du dossier, owner ET invités. Coordonnées approximatives (centre officiel du site Kerampuilh + disposition relative du plan illustré), ajustables ensuite.
3. **⚠️ Ne PAS géolocaliser les 83 mémos-passages** : 15-18 marqueurs superposés par scène rendraient la carte illisible (pas de clustering sur le calque points-mémo). Les ❤️/votes se consultent sur le board et l'écran Résultats ; la carte sert à se repérer entre les scènes. (Si un jour on veut les voix sur la carte, ce sera un lot dédié.)

## [FESTIVAL-MAP-OVERLAY] — micro-lot ajouté le 13 juil. (après validation V23.1.75)

**Demande Fabien** : dans la pop-in carte du dossier (owner ET invité), pouvoir afficher **le plan illustré du festival en surcouche** du fond OSM, calé sur le site, les pins scènes restant au-dessus.

- **Image prête** : `docs/specs/assets/plan-overlay-2026.png` (778×601, RGBA) — les 2 captures fusionnées, fond rose et marges rendus **transparents** (seul le site « flotte » sur OSM). À copier/servir depuis `static/` (aucun CDN, invariant 6).
- **UI** : un chip toggle **« 🎪 Plan »** dans la barre de la pop-in carte (à côté de Voix/Photos/Frise), owner `index.html` + invité `share.html` (helpers partagés, invariant 9). Off par défaut ; état mémorisé en localStorage. `L.imageOverlay(url, bounds, {opacity: 0.9})` au-dessus du fond, **sous** les marqueurs.
- **Géoréférencement** : le plan est stylisé, pas à l'échelle — caler à l'œil pour que les scènes DESSINÉES tombent près de leurs pins (Glenmor NO 48.2729,-3.5601 ; Grall S 48.2714,-3.5576 ; Gwernig NE 48.273,-3.5575). Point de départ : `bounds = [[48.2706, -3.5618], [48.2739, -3.5544]]` (polygone OSM du site : 48.27114→48.27324 / -3.56073→-3.55630, l'overlay déborde un peu). **Exposer les bounds en constante unique commentée** pour ajustement facile.
- **Activation** : uniquement quand la carte affiche des pins de PROJETS du dossier « Vieilles Charrues 2026 » — au plus simple : constante `MAP_OVERLAYS = {<nom ou id racine>: {url, bounds}}` dans le partial, en dur, assumé (V1 festival, généralisation plus tard si besoin). Zéro schéma, zéro route.
- **Acceptation** : toggle on/off owner + invité, overlay sous les pins, opacité lisible, pas de fuite sur les autres cartes (restaurants/Japon), console propre, mobile OK. Export/DB intouchés → toujours **V23.1.z**.

## Modèle de données (proposition — CC libre sur l'implémentation, invariant 1 : additif)

- **Heure de fin** : colonne additive `memos.end_time TEXT DEFAULT ''` (même gabarit que `due_time`, migration `PRAGMA table_info` comme les précédentes). **Non exportée en V23.1** (comme `votes.event_date`) → pas de bump de format. Éditable dans la fiche mémo (champ « fin » à côté de l'heure, owner + invité can_edit).
- **Coups de cœur** : table additive `memo_hearts (project_id, voter, memo_id, created_at)` — `voter` = même sémantique que `memo_votes.voter` (owner/e-mail invité). Unicité (voter, memo_id). **Non exportée en V23.1.**
- **Envies secondaires** : réutiliser les **votes nommés existants** — un scrutin **multi** « Envies » couvrant **tous les passages du dossier racine + sous-dossiers**. Si le scope actuel (`_vote_scope_memo_ids`) ne couvre pas les descendants, au choix : l'étendre (additif), ou fallback un scrutin « Envies » par sous-dossier scène (moins bien pour le podium global mais acceptable).

## Règle anti-chevauchement (serveur, obligatoire)

Au POST d'un ❤️ par un votant sur le mémo M :

1. Charger les ❤️ existants du votant dans le **même dossier racine**.
2. Normaliser chaque créneau : minutes depuis 00:00 du `due_date` ; si début < 720 (12:00) → +1440 ; si fin ≤ début → fin +1440. Mémo sans `end_time` → durée par défaut 60 min.
3. Conflit si `startA < endB && startB < endA` (comparaison sur datetime absolu : date + minutes normalisées).
4. Conflit → **409** avec payload explicite `{error, conflict: {memo_id, artist, scene, day, start, end}}` → l'UI affiche « Déjà ❤️ NICK CAVE sur ce créneau » et propose de **remplacer** (l'UI ré-appelle avec `replace: true`, le serveur retire l'ancien et pose le nouveau, atomiquement).
5. Re-cliquer son propre ❤️ = retrait (toggle, comme les réactions).

## Routes (invariant 5 : bypass `/share/*`, token revalidé)

- Owner : `POST /api/memo/<id>/heart` (toggle + `replace`), résultats inclus dans le payload projet ou route dédiée.
- Invité : `POST /share/<token>/memo/<id>/heart` — **invité approuvé requis, `can_edit` NON requis** (précédent [COMMENT-REACTIONS] : « réagir n'est pas éditer » ; ❤️ non plus). Anonyme = 403. Hors scope du partage = 404.
- Résultats : `GET /api/project/<id>/festival-results` + `GET /share/<token>/festival-results` → `{passages: [{memo_id, artist, scene, day, start, end, hearts: [noms], votes: n}], total_voters}`. Noms affichés via la même résolution que `_vote_display_name` (invariant identité).

## UI (3 pages en miroir — invariant 9, helpers dans `_shared.js.html`)

- **Carte mémo (dossier festival)** : chip **❤️ n** cliquable (toggle) à côté du vote existant. Le chip ❤️ n'apparaît que sur les mémos ayant `due_date` + `due_time` (un passage) — générique, pas de flag « festival » en dur.
- **Écran Résultats** : bouton « 🏆 Résultats » au niveau du dossier racine (owner `index.html`, invité `share.html`, hub `hub.html` si trivial sinon V23.1 suivante). Pop-in ou vue :
  - **Podium** : passages triés par (❤️ desc, votes desc), top mis en avant, compteurs visibles.
  - **Par ami** : « Marie ❤️ ORELSAN (dim 21:30, Glenmor) + NICK CAVE (ven 22:00, Glenmor) », pour chaque votant.
  - **Par jour** : filtre Jeudi/Vendredi/Samedi/Dimanche pour préparer le parcours du jour.
  - Live : re-fetch à l'ouverture (pas de websocket).
- Pas de GSAP sur `<dialog>` (invariant 8). Pas de CDN runtime (invariant 6). Mobile OK (~500 px).

## Versionnage & journal

- **V23.1.z** : `end_time`, `memo_hearts` et l'écran Résultats sont **non exportés** → format d'export reste **v23**, `APP_VERSION` inchangée côté format. Rappel invariant : tout export reste v23+.
- Si CC juge indispensable d'exporter ❤️/`end_time` (round-trip), alors bump **v24** — à signaler dans le handoff, mais l'option non exportée est préférée pour tenir le délai.
- Journaliser dans `REALISATION.md` ([V23.1.z]) + basculer la fiche IDEAS.md en livré. Aucun commit/tag/push sans feu vert Fabien.

## Acceptation (validation Cowork via Chrome, owner + invité)

1. Seed : dossier + 6 sous-dossiers + 83 passages présents, horaires corrects (contrôle par échantillon : KATY PERRY jeu 22:30→00:00 Glenmor ; INTERPOL sam 00:15→01:30 Kerouac ; FEST NOZ sam 23:00→02:00 Gwernig). Seed relancé = 0 doublon. Plan attaché au dossier racine (aperçu inline owner + invité) ; carte du dossier = 6 pins scènes (et **seulement** 6 — pas de nuage de 83 points).
2. ❤️ owner : pose, toggle-retrait, conflit 409 (ex. ❤️ ORELSAN dim 21:30-23:00 Glenmor puis ❤️ LINDIGO dim 21:00-22:15 Gwernig → conflit ; TOMORA dim 23:10 → pas de conflit avec ORELSAN ; RILÈS dim 00:30 → pas de conflit avec TOMORA 23:10-00:25… vérifier la logique +24h), remplacement via `replace`.
3. ❤️ invité approuvé (share `can_edit:0` suffit pour ❤️ mais rappel : l'inscription invité exige un share `can_edit:1`) : 200 ; anonyme : 403 ; mémo hors scope : 404.
4. Votes « Envies » : multi, tous sous-dossiers couverts, compteurs OK owner + invité.
5. Résultats : mêmes chiffres owner/invité, noms corrects, filtre par jour, mise à jour après un nouveau vote (re-fetch). Console propre.
6. `node --check` + `py_compile`. Export/import v23 d'un dossier avec ❤️ : pas de crash, pas de fantôme (les ❤️ ne voyagent pas).
7. Rebuild local + `.claude/handoff.json` (status/version/url) pour la validation Cowork.
