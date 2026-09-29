# Brief CC — [RAIL-LABELS] : le rail d'icônes devient lisible, et l'œil masque vraiment la barre

> **Front pur, owner desktop (> 900 px), zéro route, `app.py` intact, export 28 inchangé.** Demande Fabien
> du 29 sept. 2026 (« en icône réduit on n'a pas l'intitulé clairement au survol » ; « quand la colonne
> n'est pas visible il faut faire disparaître l'icône hamburger »), maquette injectée dans localhost:8099
> validée (« j'aime bien clairement »). Doctrine TDD. Cible **V28.4.271**.

## 0. Ce qui change, en une phrase

En mode rail (`nav#sidebar.sb-rail`, 64 px), chaque icône reçoit une **infobulle maison instantanée**
(nom + compteur), les dossiers sans emoji montrent leur **initiale** sur la pastille couleur, le rail
**respecte les replis** de l'arbre au lieu d'aplatir les 47 sous-dossiers ; et le bouton « œil » **masque
réellement** la barre même en rail, en escamotant le hamburger.

## 1. Constats (mesurés le 29 sept., V28.3.270 local)

- Rail : seuls les `title` natifs servent d'étiquette. Absents sur Fichiers-vue, Inbox, Mémos, 📦 ; verbeux
  ailleurs (« Vue Plan : toute la hiérarchie… », « Serveur — double-clic ou clic droit pour modifier »).
- `renderSidebar` (~l.3674) : `flat = rail || mobile` → `projOpen`/`secOpen` forcés à vrai, et CSS l.746
  `.sb-rail .sb-kids { display: contents }` → 47 pastilles sans nom, dont 20 `●` de couleur seule.
- **Bug** : `nav#sidebar.sb-rail { width: 64px }` (l.790) est déclaré APRÈS `nav#sidebar.sb-hidden { width: 0 }`
  (l.789), même spécificité → avec `sb-rail sb-hidden` la barre reste à 64 px. L'œil ne fait rien en rail.

## 2. Décisions (fermes — maquette validée)

1. **Infobulle rail** : UN élément `#rail-tip` (position fixed, `left: 72px`, `top` aligné sur l'item),
   rempli au `mouseenter` / `focusin` d'un `.cat-item` du rail, vidé au `mouseleave` / `focusout`.
   Contenu : `.cat-label` de l'item + `.count` s'il existe (ex. « newss 2 »), en atténué pour le compteur.
   Style **Luciole** : fond `--panel`, bordure 1 px `--accent`, rayon 8 px, ombre douce, petite flèche à
   gauche, `pointer-events: none`, apparition 120 ms (opacity + translateX 4 px, GSAP inutile — CSS
   transition ; reduced-motion → instantané). Actif **uniquement** si `sb-rail` et > 900 px.
   Les `title` natifs des `.cat-item` sont **retirés en rail** (`removeAttribute` au rendu) pour éviter la
   double bulle ; ils restent en mode normal.
2. **Initiale sur la pastille** : en rail, `.cat-dot` d'un dossier sans emoji passe à 22 px et affiche la
   première lettre du nom en majuscule (`font: 600 11px system-ui`, couleur `#0b0f14` sur le fond couleur).
   Hors rail : pastille 0.7 rem inchangée (CSS scoped `.sb-rail .cat-dot`). Pas d'initiale sur les entrées
   qui ont un emoji.
3. **Le rail respecte les replis** : dans `renderSidebar`, `projOpen = mobile || sbProjOpen(id)` (le rail
   ne force plus). Un dossier replié n'affiche pas ses enfants ; le ⇅ de [SIDEBAR-COLLAPSE] et
   `sbProjOpen:<id>` s'appliquent donc au rail. La section DOSSIERS reste sans en-tête en rail (comme les
   autres en-têtes, l.747) : **`secOpen` reste forcé** en rail — un rail avec tout replié serait vide.
   Supprimer `.sb-rail .sb-kids { display: contents }` → remplacer par `margin/padding/border: 0` pour
   garder la structure DOM sans indentation.
4. **Œil en rail** : `nav#sidebar.sb-hidden` doit gagner : déplacer la règle après `.sb-rail`, ou
   `nav#sidebar.sb-hidden, nav#sidebar.sb-rail.sb-hidden { width: 0 … }`. Quand `hidden` est vrai, le
   hamburger `#sidebar-rail-btn` est **masqué** (`hidden` attribut ou classe existante), rétabli quand
   l'œil rouvre ; l'état rail est conservé en mémoire (`sbRail`) et retrouvé à la réouverture. `syncBtns`
   gère les deux. Le GSAP d'ouverture/fermeture (l.11123) reste ; en rail, animer de 64 → 0.
5. **Hors périmètre** : mobile (≤ 900 px : rail et œil déjà masqués l.806), share/hub, panneau Dossiers
   mobile, sections FAVORIS/LIENS/ÉTIQUETTES.

## 3. Ce qui NE bouge PAS

`renderSidebar` garde son contrat et ses clés (`sbSection:*`, `sbProjOpen:*`, `treeOpen:*`) ; mode
normal (labels visibles) rendu pixel-identique ; D&D ; `app.py` ; export 28 ; invariant 9 (aucune classe
de bouton nouvelle : `#rail-tip` est un composant unique, pas un bouton).

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_rail_labels.py` (viewport 1280×800, décor : 3 dossiers racine dont 1 avec emoji, 1 sans
emoji nommé « Maison » avec un enfant « Cuisine », 1 replié ; localStorage `sbRail=1`).

1. Rail actif → survol de « Maison » : `#rail-tip` visible, texte commence par « Maison », contient le
   compteur ; sortie → masqué. Les `.cat-item` du rail n'ont **pas** d'attribut `title`.
2. `.cat-dot` de « Maison » affiche « M » ; en mode normal (sbRail=0) la pastille est vide.
3. « Maison » replié (`sbProjOpen:<id>=0`) → « Cuisine » absent du rail ; ouvert → présent. Le ⇅ de la
   section DOSSIERS (mode normal) puis passage rail → replis respectés.
4. Rail + clic œil → `nav#sidebar` largeur 0, `#sidebar-rail-btn` masqué, `sbHidden=1` ; rechargement →
   même état ; re-clic œil → barre à 64 px (rail conservé), hamburger visible.
5. Focus clavier (Tab) sur un item du rail → infobulle visible (`focusin`).
6. Mode normal : aucune infobulle `#rail-tip` au survol.

Mutations à poser puis tuer : (a) `title` non retiré en rail ; (b) `projOpen` forcé en rail ; (c) règle
`.sb-hidden` avant `.sb-rail` ; (d) hamburger non masqué quand hidden.

## 5. Livraison

`templates/index.html`, `tests/front/test_rail_labels.py`, `REALISATION.md` `[V28.4.271]`, `IDEAS.md`
(retirer [RAIL-LABELS] de la file), ce brief commité. Cycle : tests rouges → code → rebuild LOCAL →
`make test` → journal + handoff → **STOP**. Passe Cowork desktop, puis GO de Fabien.
