# Vision — l'éditeur et le rendu des mémos, façon Medium

Réflexion Fabien + Cowork du 30 septembre 2026. Pas un brief : un cap pour les lots à venir.
Références : un article Medium exporté en PDF (colonne unique, titre fort, image de couverture,
séparateurs, citations) et la page d'écriture Medium (barre flottante à la sélection, bouton ⊕
en marge pour insérer un bloc).

## Ce que Fabien veut, dans ses mots

1. Des **templates** comme Evernote, mais pas statiques : à terme des **formulaires**.
2. Des **rendus PDF** générés à partir des mémos.
3. Du **glisser-déposer d'éléments** (espaces pour images) pour produire du HTML et avoir un vrai
   visuel.
4. Un rendu de lecture **clair comme Medium**, et une page d'écriture qui lui ressemble.

## Ce qu'on a déjà

- Contenu des mémos = HTML Quill 2.0.3 (thème `snow`, barre fixe, tableaux via quill-table-better).
- Photos, fichiers, vocaux, liens reliés : **à côté** du texte, jamais dedans (aucune image inline,
  choix volontaire : pas de base64 dans le contenu, export léger).
- Fiche de lecture 👁 (dialog), card compacte/immersive, mode Compact/Immersif du board.
- Graine [MEMO-TEMPLATES] : champs typés → formulaire à la création (maquette validée le 29 sept.,
  reportée « quand je saurai vraiment ce que je veux »).
- Graine [EXPORT-MEDIA-BUNDLE] : export zip JSON + binaires.

## Le fil conducteur : le mémo devient un document à blocs

Un mémo Medium-like, c'est une suite de **blocs** : paragraphe, titre, image en figure avec
légende, séparateur, citation, encadré, checklist, tableau, carte de lien, pièce jointe. Quill sait
déjà représenter la plupart (blots). Ce qui change : on **autorise l'image dans le texte**, mais
**par référence** (`<img src="/uploads/<nom>">` vers une photo du mémo), jamais en base64. Le mémo
garde ses Photos comme galerie ; le texte peut en afficher certaines à l'endroit voulu.

Une fois le document à blocs en place, les quatre souhaits en découlent :
- **Lecture Medium** = un rendu de ces blocs dans une page dédiée, typographie soignée.
- **PDF** = ce même rendu passé à l'impression (CSS `@media print`) puis, si besoin, rendu serveur.
- **Glisser-déposer** = déposer une photo (ou un lien, un fichier) dans le texte crée le bloc.
- **Templates / formulaires** = un modèle est un document à blocs + des champs ; les champs
  remplissent des blocs (titre, fiche 2 colonnes, corps). C'est la graine MEMO-TEMPLATES, posée sur
  une base plus solide.

## Lots proposés, dans l'ordre (chacun livrable seul)

### 1. [MEMO-READ] — la page de lecture
Une vue `state.view = 'read'` (pas un dialog) : une colonne 680 px, titre H1, sous-titre = première
ligne, méta (dossier, dates, assignés) discrète, photos en figures pleine largeur si le mémo en a,
séparateurs, citations, checklists cochables, pièces jointes en cartes en bas, commentaires sous
l'article. Bouton « Modifier » → éditeur. Owner + invité + hub (composant partagé, ADR-001).
**PDF v1** : feuille `@media print` propre + bouton « Imprimer / PDF » = `window.print()`. Zéro
dépendance, marche sur iPhone (Partager → Enregistrer en PDF). Le rendu papier devient le premier
test du rendu écran.

### 2. [EDITOR-BUBBLE] — la page d'écriture
Quill passe au thème **bubble** (barre flottante à la sélection : B, I, lien, H1/H2, citation,
code), et un bouton **⊕ en marge** du paragraphe vide ouvre le menu de blocs : Image (depuis les
Photos du mémo ou upload), Séparateur, Encadré, Checklist, Tableau, Lien relié (card), Fichier.
Plein écran optionnel, largeur de lecture identique à MEMO-READ (ce qu'on écrit = ce qu'on lit).
Quill 2.0.3 inclut le thème ; il faut vendoriser `quill.bubble.css` et garder quill-table-better.
Mobile : la barre flottante est native chez Quill ; le ⊕ devient un bouton fixe en bas.

### 3. [IMAGE-INLINE] — l'image dans le texte
Blot `figure` (img + légende), source = nom de fichier dans `/uploads/` du mémo, **drag & drop**
d'une vignette Photos vers le texte, coller une image dans le texte = upload dans Photos puis
figure (réutilise PASTE-IMAGE). Règles : pas de base64 (validation serveur : un `<img src="data:`
est refusé), une image inline reste dans Photos (supprimer la photo retire la figure), l'export
JSON ne change pas (les noms sont déjà exportés) ; l'export média ([EXPORT-MEDIA-BUNDLE]) devient
la vraie sauvegarde. Share/hub : même blot en lecture ; en édition selon droits.

### 4. [MEMO-TEMPLATES] — modèles puis formulaires
Reprise de la graine sur cette base : un modèle = document à blocs + champs typés ; « Depuis un
modèle » ouvre le formulaire, les réponses remplissent les blocs (titre, fiche 2 colonnes, corps,
dates, assignés). V2 : lien mémo → modèle pour re-remplir, vues par modèle. À lancer quand Fabien
aura arrêté ce qu'il veut ; la maquette du 29 sept. reste valable.

### 5. [MEMO-PDF] — PDF côté serveur (si v1 ne suffit pas)
WeasyPrint sur le Zimaboard (HTML + CSS print → PDF, pièces jointes images incluses), route
`GET /api/memos/<id>.pdf` et export d'un dossier en un PDF. À décider après usage de la v1.

## Ce qu'on ne fait pas

- Pas de nouveau moteur d'édition (Editor.js, TipTap…) : Quill 2 couvre le besoin, tout le code et
  les tests s'appuient dessus.
- Pas de « page builder » libre (colonnes, positions absolues) : Medium n'en a pas, et c'est ce qui
  rend le rendu clair. Le glisser-déposer place des blocs dans un flux, pas des objets sur une toile.
- Pas de base64 dans le contenu, jamais.

## Arbitrages Fabien (30 sept., 17:29)

1. La page de lecture **remplace la fiche 👁 partout** (desktop + mobile, owner + invité + hub).
2. Thème bubble pour **owner et invité d'un coup**.
3. **Le type du mémo se choisit à la création.** Créer un mémo = choisir d'abord ce qu'il est :
   Note (défaut, l'actuel), Rédaction code, Mission client, Compte-rendu de réunion, Étape de
   voyage, Fiche resto… Chaque type est un **template** : des blocs pré-posés, des champs, et un
   menu ⊕ / une barre adaptés. Exemple acté : **Rédaction code** = fenêtres de code faciles à
   coller (bloc code avec langage, coloration, bouton copier, police mono, collage qui détecte le
   code), titres, encadrés « note » / « attention ».
4. **PDF = un must**, pour télécharger et lire hors ligne. Ce n'est plus un « si besoin ».

## Conséquences sur les lots

- Le **type** est porté par le mémo (colonne additive `kind` ou `template_uid`, valeur par défaut
  `note`) → **export v29** (bump X), à embarquer avec le premier lot qui l'écrit. Un mémo sans type
  reste une Note : rien ne casse à la migration.
- [MEMO-TEMPLATES] remonte : il devient **[MEMO-TYPES]**, le socle « choisir le type à la
  création », livré avec deux types (Note, Rédaction code) et le formulaire de champs de la
  maquette du 29 sept. pour Mission client. Les autres types s'ajoutent un par un.
- [MEMO-PDF] passe en lot ferme après MEMO-READ : v1 impression navigateur (immédiate, hors ligne
  sur iPhone via Partager → PDF), v2 route serveur `GET /api/memos/<id>.pdf` (WeasyPrint sur le
  Zimaboard) pour un vrai fichier téléchargeable, images incluses, et un dossier → un PDF.
- Ordre révisé : **MEMO-READ (+ print) → EDITOR-BUBBLE → MEMO-TYPES (Note + Rédaction code +
  champs) → IMAGE-INLINE → MEMO-PDF serveur**. Chaque lot garde une maquette cliquable avant brief.

## Ce que « choisir le type à la création » change dans l'interface

- Le « ＋ » (board, colonne MÉMOS, Note rapide, dock invité) ouvre un **choix de type** : une rangée
  de tuiles (📝 Note · 💻 Code · 💼 Mission · 📋 Réunion · …), Note pré-sélectionnée, Entrée = Note
  pour ne pas ralentir la capture rapide. La Note rapide reste Note sans question.
- Le type s'affiche sur la card (petit glyphe) et filtre : tuile « Code » dans les filtres du board,
  `t#code` dans la grammaire de recherche.
- Un type peut se changer après coup (Note → Code) sans perte : les blocs restent, seuls le menu ⊕
  et les champs changent.
