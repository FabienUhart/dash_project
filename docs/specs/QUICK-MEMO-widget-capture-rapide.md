# [QUICK-MEMO] + [MEMO-QUICK-STICKY] — Capture rapide de mémo (widget flottant + sticky colonne)

**Brief pour Claude Code — lot V25.1.Z (frontend pur, EXPORT v25 INCHANGÉ, zéro route/schéma nouveau).**
Lire `CLAUDE.md` avant de commencer. Z = compteur continu de `REALISATION.md` ; deux entrées de
journal (une par réalisation) si tu les livres en deux temps, sinon une entrée combinée.

## 1. Contexte

Constats Fabien (29 juil.) : créer un mémo impose d'être dans la vue Mémos, et même là, la
zone « + Note rapide… » (`#memo-quick`) est APRÈS les ~200 post-its de la colonne
(`aside#memo-panel`) → scroll interminable, sur iPad surtout. Objectif : capturer une note
depuis n'importe quelle vue, en deux gestes. Cas d'usage cible : noter un resto dans le métro
de Tokyo (→ synergie [OFFLINE]).

## 2. Décisions (tranchées avec Fabien — implémenter, ne pas rediscuter)

- **D1 — Gabarit Pomodoro/FX-CONVERTER à l'identique** (invariant 9) : helper
  **`initQuickMemo(cfg)`** dans `_shared.js.html`, lanceur flottant ✏️ + panneau
  **déplaçables** (Pointer Events, clamp fenêtre), positions persistées (`qmPos`,
  `qmLaunchPos`), masquable (`qmHidden` + pastille re-show + case « Capture rapide » dans les
  réglages, à côté de Pomodoro/FX). Panneau = **div flottant comme le Pomodoro** — PAS un
  `<dialog>` (et donc jamais de GSAP dessus, invariant 8 sans objet mais rester vigilant).
- **D2 — Panneau minimal** : champ titre + **textarea texte simple** (PAS de Quill — la
  capture est brute, on rouvre le mémo pour enrichir) + **sélecteur de dossier** + bouton
  Créer. Après création : `flashSaved()`/notify, champs vidés, panneau reste ouvert
  (captures en rafale), rafraîchissement des données comme après un ajout normal.
- **D3 — Dossier par défaut** : même destination que `#memo-quick` aujourd'hui (cohérence
  Inbox) ; **pré-sélection du dossier courant** quand on est sur un board de projet
  (`state.memoProject` owner / racine ou filtre courant côté share).
- **D4 — Périmètre V1 : owner (`index.html`) + invité (`share.html`)**. Le hub est EXCLU
  (agrège plusieurs partages → destination ambiguë ; candidat V2). Côté invité : le widget
  n'apparaît que si le rôle permet la création (matrice [GUEST-ROLES], comme les contrôles
  existants) ; POST `/share/<token>/projects`-like : on utilise la route mémo EXISTANTE
  `POST /share/<token>/memos` avec `X-Guest-Token` — **zéro nouvelle route, invariant 5
  intact** (le scope est revalidé serveur comme aujourd'hui).
- **D5 — Synergie [OFFLINE] (owner)** : hors ligne, la création part dans la **file de
  notes Inbox idempotente existante** du SW (celle de V24.1.111) → note ⏳ puis resync.
  Ne PAS créer de deuxième file ; brancher le widget sur le même chemin que `#memo-quick`.
- **D6 — [MEMO-QUICK-STICKY]** (quick win, même lot) : `#memo-quick` devient **sticky en
  bas** de la colonne mémos (`position: sticky; bottom: 0`, fond opaque `var(--panel)`,
  léger padding + z-index pour que les cards ne transparaissent pas) ; et le « ＋ » de
  l'en-tête MÉMOS (`#memo-add-btn`, aujourd'hui mobile-only via [HEADER-ADD-CONTEXT]) est
  **révélé aussi sur desktop** (comportement existant : ouvrir/scroll/focus).

## 3. Implémentation — points d'attention

- Le panneau vit **HORS des zones re-rendues** par `renderAll()`/le poll 15 s (comme le
  Pomodoro), sinon la saisie serait perdue à chaque refresh. Vérifier aussi que le poll ne
  vide pas les champs pendant la frappe.
- `cfg` par page : endpoint de création, liste des dossiers (arbre indenté owner ; dossiers
  du périmètre côté share), valeur par défaut, hook de refresh post-création, flags rôle.
- Owner : POST `/api/memos` existant (titre + contenu → même format que `#memo-quick` ;
  si le POST ignore certains champs, faire comme l'existant — pas d'invention d'API).
- Raccourcis : Entrée dans le titre = créer ; Échap = replier le panneau. Pas de raccourci
  global clavier (réservé à [CMD-K], hors périmètre).
- Styles : tokens/classes existants (`.prio-btn`, patterns Pomodoro/FX), invariant 6 (zéro
  lib), monochrome discret, tap-targets ≥ 40 px (usage tactile iPad).

## 4. Acceptation (validation Cowork ensuite)

1. Depuis Liens, Agenda, Plan et un board projet (owner) : capturer un mémo en ≤ 2 gestes ;
   défaut Inbox ; sur un board → dossier courant pré-sélectionné ; rafale de 2 notes sans
   re-cliquer.
2. Positions lanceur/panneau persistées après reload ; masquer via réglages → pastille
   re-show ; état par utilisateur (localStorage), parité light/dark.
3. Invité éditeur/contributeur : widget visible, création OK (`created_by` correct) ;
   suiveur/viewer : pas de widget. Scope revalidé serveur (rien de nouveau).
4. Owner offline (simulation `navigator.onLine` + events) : création → ⏳ file Inbox →
   resync au retour online, sans doublon (idempotence existante).
5. Colonne mémos : `#memo-quick` visible en bas de la fenêtre quel que soit le scroll ;
   « ＋ » d'en-tête visible desktop et fonctionnel ; rien ne transparaît sous le sticky.
6. `node --check` sur les templates + `python3 -m py_compile app.py` (app.py ne devrait
   PAS bouger — si tu dois le toucher, le signaler dans le handoff) ; export toujours 25 ;
   aucune nouvelle route.

## 5. Fin de réalisation

Journal IDEAS→REALISATION, rebuild local (`docker compose up -d --build`, localhost:8099),
`.claude/handoff.json` status "ready". **Ni commit ni push** sans feu vert Fabien.


---

## ADDENDUM V1.1 — [QUICK-MEMO-HUB] (29 juil., retour de test Fabien)

**Constat** : les invités réels passent par le **hub** ([ONE-LINK-MULTI]), pas par les pages
`/share/<t>` directes → le widget V1 leur est invisible. La D4 (hub exclu) est **révisée** :
le hub embarque le widget en V1.1.

**Cadrage** :
- Même `initQuickMemo(cfg)` du partial, activé dans `hub.html` (comme `initFxWidget`).
- **Sélecteur de dossier multi-partages** : options = tous les dossiers des partages
  APPROUVÉS du hub où la création est permise (rôle éditeur/contributeur — mêmes données
  que les « + » existants du hub ; un hub 100 % lecture = pas de widget, comme un viewer).
  Chaque option porte son couple (share token, project_id) ; groupes `<optgroup>` par
  partage si plusieurs. Défaut = dossier actuellement ouvert dans le hub, sinon la racine
  du 1ᵉʳ partage éditable.
- **Submit** : POST `/share/<token>/memos` EXISTANT avec le `X-Guest-Token` du partage de
  l'option choisie — zéro route nouvelle, scope revalidé serveur (invariant 5).
- Pas d'offline (D5 inchangée, owner-only). Préférences position/masquage : mêmes clés
  localStorage (par navigateur, donc par invité — OK).
- Acceptation : hub de claude.test (éditeur) → widget + création dans le bon dossier du
  bon partage ; hub d'un invité 100 % suiveur → rien ; `node --check` ; export 25 inchangé.
