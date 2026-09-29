# Brief CC — [SIDEBAR-COLLAPSE] : replier l'arbre des dossiers, sortir « Invités », deux icônes

> **Front pur, owner + panneau mobile, zéro route, `app.py` intact, export 28 inchangé.** Demande Fabien du
> 29 sept. 2026 (« pouvoir réduire les éléments — dossiers et sous-dossiers de mémos — comme ÉTIQUETTES,
> qui est parfait »), démo injectée dans localhost:8099 validée. Doctrine TDD. Cible **V28.3.270**.

## 0. Ce qui change, en une phrase

Sous « Fichiers » et Inbox, l'arbre des dossiers reçoit son propre en-tête **▾ 📂 DOSSIERS**, repliable et
mémorisé comme LIENS / PROJETS / ÉTIQUETTES ; le dossier système « 👥 Invités » quitte la liste des dossiers
de Fabien pour le bas de l'arbre ; la tuile « En cours » cesse de copier l'icône de l'Inbox.

## 1. Décisions (fermes — démo validée)

1. **Constat** : « Fichiers » (~l.3924) n'est PAS le parent de l'arbre, c'est la vue globale des fichiers ;
   Inbox et les dossiers ne sont que posés dessous. Ne pas rendre « Fichiers » repliable (ça mélangerait
   deux notions) : on **insère un en-tête de section `DOSSIERS`** entre Inbox et le premier dossier racine.
2. **En-tête** : `div.sb-section-head` **existant** (~l.3765, chevron `.sb-chevron`, libellé
   `.sb-section-label`) — aucune classe nouvelle (invariant 9). Libellé « 📂 DOSSIERS » ; **replié, le
   compteur total** des mémos de l'arbre (hors Invités) s'affiche à droite (`.count`), déplié il disparaît.
   État via le mécanisme existant `sbSectionOpen('dossiers')` / `toggleSbSection` (~l.3499, clé
   `sbSection:dossiers`), défaut ouvert. Mode rail (`sb-rail`) : masqué comme les autres en-têtes.
3. **Inbox reste visible** au-dessus de l'en-tête quand l'arbre est replié (c'est la boîte d'entrée,
   arbitrage Fabien). Mémos / Plan / Agenda / Fichiers ne bougent pas.
4. **⇅ « Tout replier / tout déplier »** à droite de l'en-tête (`.sb-add`, même gabarit que le ＋ de
   PROJETS, `title`) : si au moins un dossier à enfants est ouvert → tout replier, sinon tout déplier ;
   écrit les clés `treeOpen:<id>` existantes (donc le panneau mobile suit). `stopPropagation` : ne bascule
   pas la section.
5. **« 👥 Invités »** (dossier racine `GUEST_HOME_ROOT_NAME`, app.py l.6102, `created_by=''`,
   `parent_id IS NULL`) est rendu **après** tous les autres dossiers racine, précédé d'un filet
   (`border-top: 1px solid var(--border)`), opacité 0.85, **hors du compteur** de l'en-tête ; il garde son
   chevron et ses enfants (espaces des invités). Identification par **nom + racine**, comme app.py — pas
   d'id en dur. Il est **exclu du tri manuel** de la sidebar (D&D de réordonnancement) : on ne le remonte pas.
   Même règle dans le panneau Dossiers mobile ([MOBILE-NAV]), qui partage `projectItemEl`.
6. **Tuile « En cours »** du board (~l.9816) : icône `📥` → `▶️` non, **trait monochrome** : utiliser
   l'icône SVG du sprite `#ic-…` la plus proche de « à faire » (cercle vide / play) — à défaut `🗒`. Motif :
   Inbox = mémos sans dossier, « En cours » = tous les mémos non terminés ; même icône = contresens
   (Fabien, 29 sept.). Les autres tuiles ne bougent pas.
7. **Pastille de la tuile Carte** (`tb.add({ icon: 'map', label: 'Carte', count … })` ~l.9595) : le nombre
   reçoit un `title` « n points géolocalisés » et le libellé devient « Carte · n » si la place le permet ;
   sinon `title` seul. Pas de nouveau composant.
8. **Hors périmètre** : replier FAVORIS / Partages / Corbeille (déjà géré pour FAVORIS, pas demandé pour
   les deux autres), share/hub, tags.

## 2. Ce qui NE bouge PAS

`renderSidebar` garde son contrat ; D&D vers un dossier ; `treeOpen:<id>` ; sections LIENS / PROJETS /
ÉTIQUETTES ; panneau mobile (il lit les mêmes clés) ; `app.py` ; export 28.

## 3. Tests (TDD — rouges d'abord)

`tests/front/test_sidebar_collapse.py` (décor : 4 dossiers racine dont un avec enfant, + un dossier racine
nommé exactement `Invités` avec un enfant, 6 mémos répartis, 2 en Inbox).

1. En-tête « DOSSIERS » présent entre Inbox et le premier dossier ; Inbox visible.
2. Clic → tous les `.cat-item` de dossiers masqués (Invités inclus), Inbox toujours visible, compteur =
   somme des `memo_count` hors Invités ; état retrouvé après rechargement (`sbSection:dossiers`) ;
   re-clic → arbre revenu, compteur masqué.
3. ⇅ : avec un dossier ouvert → tout replié (`treeOpen:<id>` à 0, enfants masqués) ; re-clic → tout
   déplié ; la section DOSSIERS reste ouverte (stopPropagation).
4. Invités rendu en **dernier** des racines, filet présent, hors compteur ; son chevron déplie son enfant ;
   un D&D de dossier ne le déplace pas.
5. Panneau mobile 412 px : Invités aussi en dernier ; replier un dossier via ⇅ desktop puis ouvrir le panneau
   → replié (clé partagée).
6. Tuile « En cours » : n'affiche plus `📥` ; Inbox l'affiche toujours.
7. Tuile Carte : `title` « … points géolocalisés » présent.
8. Zéro erreur console.

**Mutations (≥ 5)** : Inbox masquée au repli (2) · compteur incluant Invités (2) · ⇅ qui bascule aussi
la section (3) · Invités trié comme les autres (4) · clé `sbSection:dossiers` non persistée (2).

## 4. Livraison

`templates/index.html`, `tests/front/test_sidebar_collapse.py`, `REALISATION.md` `[V28.3.270]`, `IDEAS.md`
(retirer [SIDEBAR-COLLAPSE]), ce brief commité. Cycle : tests rouges → code → rebuild LOCAL → `make test` →
journal + handoff → **STOP**. Passe Cowork desktop + mobile (avec Fabien), puis GO.
