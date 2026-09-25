# Brief CC — [MOBILE-NAV] : sur téléphone, les dossiers dans un panneau, et un en-tête d'une ligne

> **Front pur, owner-only, zéro route, `app.py` intact, export 27 inchangé.** Issu de la passe mobile Cowork
> du 25 sept. 2026 (`docs/tests/test-application-mobile.md`, points 1, 3, 4) ; démo injectée dans
> localhost:8099 validée par Fabien le même jour (« j'aime ta démo »). Doctrine TDD. Cible **V27.47.262**.
> Placé **n° 2 de la file**, derrière [LINK-REFS] (en cours). **Desktop strictement inchangé.**

## 0. Ce qui change, en deux phrases

Sur téléphone (≤ 900 px), la bande horizontale de 60 entrées qui remplace la sidebar disparaît : un bouton
📁 dans l'en-tête ouvre un **panneau « Dossiers » qui monte du bas** (gabarit de `#search-sheet`) avec les
raccourcis, un filtre foldé et l'arbre replié. L'en-tête tient sur **une seule ligne** (D · recherche · 📁 ·
🔔 · ⚙), le bouton thème passe dans Paramètres, et le bloc MÉMOS de l'accueil s'ouvre par défaut.

## 1. Mesures qui motivent le lot (base locale, 412 px)

`nav#sidebar` en mobile = bande de 61 px de haut, **8 236 px de large, 60 items** ; en-tête = 3 rangées
(titre + recherche + horloge / 3 icônes / bande) ≈ 175 px de chrome sur 921 ; le premier mémo commence à
~300 px. Après la démo : en-tête 64 px, premier mémo à 128 px.

## 2. Décisions (fermes — démo validée)

### Le panneau Dossiers
1. **Un `<dialog id="folders-sheet">`**, même gabarit et mêmes règles que `#search-sheet` (partial,
   `_searchStyle` ~l.7635 : plein largeur, `inset:auto 0 0 0`, coins 16 px en haut, hauteur 86vh,
   `::backdrop` 50 %, animation d'entrée CSS seulement — **invariant 8, jamais de GSAP sur le dialog**).
   Poignée en haut, fermeture par tap sur le fond, par ✕, et par Échap. Ouvert par un bouton
   `#folders-btn` (`class="icon"`, icône trait `#ic-folder` si elle existe, sinon ajouter une icône
   trait au sprite — **pas d'emoji dans l'en-tête**), placé juste après `#search-wrap`.
2. **Contenu, dans l'ordre** :
   - **Rangée de raccourcis** horizontale (défilable) : ⭐ Favoris · 🔗 Partages · 📝 Mémos · 🌳 Plan ·
     📆 Agenda · 🗑 Corbeille — les MÊMES nœuds `.cat-item` que la sidebar (compteurs inclus), rendus par
     la même fonction, pas une copie. Un tap = l'action de la sidebar + fermeture.
   - **Champ « Filtrer les dossiers… »** : filtre `searchFold` sur le nom ([SEARCH-FOLD]) ; un dossier
     dont un descendant matche reste visible et **déplié** ; champ vide = arbre replié tel que mémorisé.
     `font-size:16px` (sinon iOS zoome).
   - **L'arbre** : Inbox en tête, puis les racines dans l'ordre `position` ; chevron ▸/▾ **séparé** du
     nom (tap sur le chevron = plier/déplier sans quitter le panneau ; tap sur le nom = ouvrir le
     dossier et fermer le panneau). Indentation par niveau (18 px), emoji + nom + compteur `memo_count`,
     **dossier courant** (`state.memoProject`) en matière accent (bordure + texte, jamais d'aplat —
     Luciole). État plié/déplié persisté dans la MÊME clé que la sidebar desktop (`treeOpen:` existant)
     — un seul état d'arbre, deux rendus.
   - Rangée de bas : « ＋ Nouveau dossier » (même action que le ＋ de la sidebar).
3. **Réutilisation stricte** (invariant 9 + ADR-001) : le rendu d'un item d'arbre est **factorisé** avec
   `renderSidebar` (une fonction `projectItemEl(p, {depth, chevron})` appelée par les deux), pas dupliqué.
   Le panneau vit dans `index.html` (owner) ; **rien dans le partial** tant que share/hub n'en ont pas
   besoin (leur sidebar mobile est un autre lot — parité V2).
4. **Le D&D vers la sidebar** (déposer un mémo/lien dans un dossier) n'existe pas dans le panneau — en
   mobile il n'existait déjà pas de façon utilisable ; le menu « Déplacer vers… » existant reste la voie.

### L'en-tête
5. **≤ 900 px, une seule ligne** : `#home-btn` affiche **« D »** seul (Fabien : « garder le D suffit »),
   `#search-wrap` prend la place (`flex:1;min-width:0`), puis `#folders-btn`, `#activity-btn`,
   `#settings-btn`. **`#clock-wrap` et `#weather` masqués** en mobile (l'heure est dans la barre système
   du téléphone ; la météo reste visible en desktop).
6. **Le bouton thème quitte l'en-tête mobile** (Fabien : « mettre l'effet sombre dans Paramètres pour
   donner plus de place à la barre ») : `#theme-btn` masqué ≤ 900 px, et un **interrupteur « Thème :
   clair / sombre »** ajouté dans `#settings-dialog`, onglet **👤 Identité** (en tête, avant le nom),
   deux boutons `.prio-btn` (sélectionné = accent, comme les onglets) branchés sur `setTheme` — même
   fonction, même clé `localStorage.theme`. En desktop `#theme-btn` reste ; l'interrupteur des
   Paramètres est visible sur les deux (une seule source de vérité, deux entrées).
7. **La bande `nav#sidebar` mobile disparaît** (`display:none` ≤ 900 px) — le CSS qui la couchait en bande
   (~l.1974) est retiré, pas surchargé.

### L'accueil
8. **Bloc MÉMOS ouvert par défaut ≤ 900 px**, état persisté `localStorage['dash:memoPanelOpen']`
   (`'1'`/`'0'`, absent = ouvert en mobile, inchangé en desktop). Le `<details>` existant garde son
   `toggle` ; on ne fait qu'écouter et restaurer.

### Hors périmètre (lots suivants)
Formulaire de création replié par défaut, languettes du bord gauche, titre répété, cards de liens compactes
→ [MOBILE-POLISH]. Share/hub → parité V2.

## 3. Ce qui NE bouge PAS

Desktop > 900 px : sidebar, en-tête, thème, tout identique (test #1). `renderSidebar` garde son contrat.
Feuille de recherche, dock, tri des liens/mémos, share/hub, `app.py`, export 27.

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_mobile_nav.py` (Playwright, viewport 412×915, `is_mobile=True, has_touch=True` ; un
décor de 3 dossiers dont un enfant, 2 favoris).

1. **Desktop non régressé** (1280 px) : `nav#sidebar` visible, `#folders-btn` absent du rendu, `#theme-btn`
   visible, en-tête d'une ligne comme avant (non-régression, verte d'emblée et assumée).
2. Mobile : `nav#sidebar` **non affiché**, en-tête ≤ 70 px de haut, `#home-btn` texte = « D »,
   `#clock-wrap`/`#weather`/`#theme-btn` non affichés, `#folders-btn` visible.
3. Tap 📁 → `#folders-sheet[open]`, raccourcis présents avec les mêmes compteurs que `/api/projects`
   (Mémos = total), arbre avec Inbox + racines, enfant **masqué** (replié).
4. Chevron : tap ▸ déplie l'enfant **sans fermer** ; état retrouvé après fermeture/réouverture et après
   rechargement (clé partagée avec la sidebar desktop : ouvrir en mobile → déplié en desktop).
5. Tap sur un nom → panneau fermé, `state.memoProject` = ce dossier, board affiché, item marqué courant
   à la réouverture.
6. Filtre : « japon » (foldé, essayer « JAPÓN ») garde le parent déplié et masque les autres ; champ vidé
   → arbre replié d'origine.
7. Fermetures : fond, ✕, Échap ; zéro erreur console.
8. Thème : dans Paramètres › Identité, « clair » pose `data-theme=light` et `localStorage.theme`, persiste
   au rechargement ; en desktop `#theme-btn` et l'interrupteur restent synchronisés.
9. Accueil mobile : bloc MÉMOS ouvert par défaut ; replié à la main → replié après rechargement ; en desktop
   comportement inchangé.
10. Aucun débordement horizontal (`scrollWidth ≤ innerWidth`) sur accueil, Liens, Mémos, panneau ouvert.

**Mutations à poser et tuer** (≥ 6) : bande sidebar laissée affichée (2) · chevron qui ferme le panneau
(4) · clé d'arbre distincte de `treeOpen:` (4) · filtre sans `searchFold` (6) · `setTheme` non appelé par
l'interrupteur (8) · défaut MÉMOS replié en mobile (9) · `projectItemEl` dupliqué au lieu de partagé
(revue : `grep` d'un seul point de rendu — ce n'est pas une mutation, c'est un contrôle de revue).

## 5. Livraison

`templates/index.html`, `tests/front/test_mobile_nav.py`, `REALISATION.md` `[V27.47.262]`, `IDEAS.md`
(retirer [MOBILE-NAV]), `docs/briefs/MOBILE-NAV.md`. Cycle : tests rouges → code → rebuild LOCAL →
`make test` → journal + handoff → **STOP**. Passe Cowork **en mobile avec Fabien** (il bascule l'onglet),
puis GO avant tout commit/tag/push.
