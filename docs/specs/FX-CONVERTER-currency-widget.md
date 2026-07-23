# [FX-CONVERTER] — Widget convertisseur de devises (JPY↔EUR + sélecteur)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Source : fiche IDEAS.md § [FX-CONVERTER], mise à jour pour l'état actuel du projet.**

## Versionnage (⚠️ la fiche IDEAS.md est obsolète sur ce point)

- **Aucun changement du format d'export** → `APP_VERSION` reste **"23"** (la fiche disait « 22 », écrite avant les lots v23). Pas de bump X, pas d'entrée d'invariant 1.
- Lot = **V23.2.90** (Y bump : nouvelle feature ; Z = dernier `REALISATION.md` [V23.1.89] + 1 — revérifier au moment de journaliser).

## Objectif

Widget convertisseur de devises (contexte : voyage Japon, JPY↔EUR par défaut), **calqué sur le widget Pomodoro** ([POMODORO], `initPomodoro()` dans `templates/partials/_shared.js.html`, ~l. 2514) : lanceur flottant + panneau déplaçables, afficher/masquer, **parité owner / share / hub**.

## Backend

### Cache serveur des taux — 1 fetch/jour maximum

- Source : `https://api.frankfurter.app/latest?from=EUR` (données BCE, gratuit, sans clé). Réponse = `{date, base:"EUR", rates:{JPY:…, USD:…}}`.
- Stockage : **clé `app_state`** `fx_cache` = JSON `{date, base:"EUR", rates, fetched_at}` (additif — pas de nouvelle table, `app_state` existe déjà avec helpers get/set ~l. 4343).
- **Refresh paresseux** : à chaque requête fx, si `date` stockée ≠ aujourd'hui (**Europe/Paris**, réutiliser `_APP_TZ`) → refetch (urllib stdlib, timeout court ~5 s) et écrase ; sinon servir le cache. Pas de cron, pas de thread. Multi-workers gunicorn : dernière écriture gagne, sans conséquence.
- **Échec réseau → jamais de crash ni de 500** : servir le dernier cache (le front affiche « taux du {date} ») ; si aucun cache n'a jamais existé, réponse `{date:null, rates:null}` propre et le widget affiche « taux indisponibles ».
- **Exclusions** :
  - **Export** : `_build_export` n'exporte l'`app_state` que clé par clé (ex. `reaction_emojis`) → ne PAS ajouter `fx_cache` (cache technique, pas une donnée utilisateur). Ré-import d'un export complet = toujours 0 ajout.
  - **`_data_version`** (~l. 4833) : **exclure `fx_cache`** comme `activity_seen_at` (volatile) — sinon le refresh quotidien déclenche un faux « données modifiées » sur le poll 15 s.
- `requirements.txt` inchangé (urllib stdlib).

### Routes (lecture seule, aucune donnée utilisateur exposée)

- Owner : `GET /api/fx` → `{date, base, rates}` (derrière Authelia).
- Invité : `GET /share/<token>/fx` — token de partage revalidé (existant/actif), **pas** d'approbation ni `can_edit` requis (taux publics, lecture).
- Hub : `GET /share/hub/<hub_token>/fx` — hub revalidé, même logique.
- Les deux routes invité vivent **sous `/share/*`** → couvertes par le bypass Authelia existant (invariant 5, jamais de préfixe de premier niveau). **Sonde bypass obligatoire après ajout** : `fetch(path, {credentials:'omit', redirect:'manual'})` non authentifié → réponse `basic` (200/404), pas `opaqueredirect`.

## Frontend (parité 3 pages via le partial)

- **`initFxWidget(cfg)`** dans `_shared.js.html`, sur le modèle exact d'`initPomodoro()` ; `cfg = {fetchUrl}` par page : owner `'/api/fx'`, share `'/share/' + TOKEN + '/fx'`, hub l'équivalent hub. Appelé sur les 3 pages comme `initPomodoro()`.
- **Lanceur** `#fx-launch` : glyphe monochrome `¥€`. **Panneau** `#fx-panel`. Les deux **déplaçables** (Pointer Events comme le Pomodoro, `clampPos` viewport, positions persistées `fxPos`/`fxLaunchPos`), **✕** pour masquer + pastille de ré-affichage `#fx-reshow`, préférence `fxHidden` (localStorage, par navigateur).
- **Case afficher/masquer** : owner → Paramètres, à côté de la case Pomodoro existante (`#pomo-visible-cb`, index.html ~l. 1923) → `#fx-visible-cb` « Afficher le convertisseur ¥€ ». Côté share/hub : même mécanique que le Pomodoro sur ces pages (✕ + pastille ; case seulement s'il existe déjà une surface de réglages — ne rien inventer).
- **Conversion** : 2 champs numériques + 2 sélecteurs de devise + bouton swap `↔`. Bidirectionnel live (taper à gauche met à jour la droite et inversement). Taux croisé **côté client** depuis la table base EUR : `montant × rate(to)/rate(from)` (EUR = 1). Arrondis : 2 décimales par défaut, **0 décimale pour JPY**. Couple persisté (`fxPair` localStorage), défaut **JPY→EUR**. Sélecteurs : JPY/EUR/USD/GBP/CHF en tête, le reste trié alphabétiquement.
- Ligne discrète « taux BCE du {date} » sous les champs ; si la date servie ≠ aujourd'hui, la mettre légèrement en évidence (repli réseau).
- **Style** : tokens/classes existants uniquement (invariant 9, gabarit Pomodoro), monochrome ; pas de GSAP sur un `<dialog>` (invariant 8) ; **aucune lib ni CDN navigateur** (invariant 6 — le seul appel externe est le fetch **serveur** vers Frankfurter).

## Documentation à mettre à jour dans le même lot

- `CLAUDE.md` invariant 6 : ajouter `api.frankfurter.app` à la liste des appels externes autorisés (**côté serveur, 1/jour**), et une ligne dans l'historique des évolutions ([FX-CONVERTER], export inchangé v23).
- `REALISATION.md` : entrée `[V23.2.90]`. `IDEAS.md` : basculer la fiche en « Fait ».

## Tests avant fin (cf. CLAUDE.md « Comment tester » — toujours sur COPIE de la base)

1. `python3 -m py_compile app.py` + `cp data/dashboard.db /tmp/test.db` + démarrage (migration = aucune ici, mais l'app démarre et `GET /api/links` OK).
2. `GET /api/fx` deux fois : 1ʳᵉ = fetch réel + cache, 2ᵉ = cache (pas de 2ᵉ sortie réseau — log ou compteur temporaire pour le prouver).
3. Échec réseau simulé (host invalide temporaire) → vieux cache servi, pas de 500.
4. Sonde bypass non authentifiée sur `/share/<token>/fx` ET `/share/hub/<hub_token>/fx`.
5. Widget sur les 3 pages : conversion JPY↔EUR correcte (vérifier à la main contre les taux servis), swap, changement de devise, persistance positions/couple/masquage après reload.
6. Ré-import d'un export complet → 0 ajout, `fx_cache` absent du JSON exporté.
7. Poll owner : vérifier que le refresh des taux ne déclenche PAS de reload (exclusion `_data_version`).

## Fin de réalisation (process CLAUDE.md)

Tester → journaliser (`REALISATION.md` [V23.2.90] + `IDEAS.md`) → `docker compose up -d --build` (hook → `.claude/handoff.json`) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation finale par Cowork via Chrome (owner + invité + hub) sur `http://localhost:8099/`.
