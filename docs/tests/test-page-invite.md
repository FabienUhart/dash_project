# Test de la page invité

Passe faite le 30 septembre 2026 sur la base locale (localhost:8099, V28.6.273), en desktop. Deux
entrées : le partage `uhart_f` (rôle administrateur, avec un sous-dossier « test dossier ») et le hub
« Vos dossiers partagés » (invité Fabien, dossiers Fabien et Jardin). J'ai passé le bandeau, la barre
latérale, les tuiles, les deux barres d'outils, la création, l'éditeur, la fiche de lecture, les
commentaires, la recherche, Plan, Agenda, Fichiers, Photos, Paramètres et « Gérer les accès ».

En une phrase : l'invité a presque tout ce qu'il faut pour **agir** (créer, éditer, commenter,
voter, joindre, coller une image, relier), mais très peu pour **voir** : pas de colonne mémos, pas
de tri, un éditeur à une seule date, une recherche sans grammaire. Et un bug de dossier à la
création, déjà briefé.

## Ce qui marche bien

Le bandeau vert « Connecté·e en tant que … — tes modifications sont signées » lève tout doute sur
qui écrit. Les deux barres d'outils (Photos · Fichiers · Agenda · Modifier, puis Mémo · Fichier ·
Vocal · Dossier) sont les mêmes qu'en owner, repliables en icônes.

L'éditeur invité est riche : Quill complet (14 outils, tableaux), assignés @, dossier, date,
priorité, position, Photos avec « Ajouter » **et** « Coller une image » (le lot d'hier est bien
passé côté invité), Fichiers, Vocal, « Relié à ». La fiche de lecture 👁, les commentaires (texte +
vocal, @mention), les votes, « Gérer les accès » (nommer jusqu'à Administrateur, borné au
sous-arbre) sont là.

Le hub a déjà des choses que le partage simple n'a pas : le filtre de sous-dossiers (Tous / Aucun /
Inverser, masquer par dossier), Immersif / Compact, ⭐ Favoris, Télécharger en zip, la tuile Carte.

## Ce qui manque, du plus lourd au plus léger

### 1. Pas de colonne MÉMOS à droite

Le milieu porte tout ; dès qu'on ouvre l'agenda, le plan ou les fichiers, la liste des mémos
disparaît. En owner, la colonne de droite reste et sert de fil conducteur, avec la note rapide en
bas. C'est ce que tu as demandé aujourd'hui : lot **[GUEST-MEMO-COLUMN]**, sur le partage **et** le
hub, à extraire en composant partagé (la colonne n'existe que dans `index.html`).

### 2. Le mémo se crée dans le mauvais dossier

Dans « test dossier », la barre de création et la note rapide envoient le mémo à la racine de
l'espace. Cause trouvée (sélecteur qui restaure l'ancienne valeur), brief **[GUEST-ADD-FOLDER]**
écrit, n°1 de la file.

### 3. Aucun tri, aucune grammaire de recherche

Ni « Manuel · Plus récents · Modifiés · Échéance », ni `d#` / `c#` / `m#` / `p#` / `#tag`, ni aide
`/`. `d#2026-09` renvoie « Aucun » alors qu'un mémo est daté du jour ; `m#teste` marche par
accident (le préfixe est ignoré et « teste » matche). Le partial `parseSearchPrefix` existe déjà
avec `dates:true` (lot MEMO-SORT-DATES) : c'est du branchement, pas du nouveau code. À mettre avec
**[SEARCH-ALL]** ou juste après.

### 4. L'éditeur invité s'arrête à une date

Une seule date, pas de fin (plage), pas d'heure, pas de récurrence, pas d'emoji, pas de sous-tâches,
pas de « Voir les versions ». Un invité contributeur d'un dossier de voyage ne peut donc pas poser
« Rome 3 → 5 nov. 19:30 ». Les routes acceptent déjà `due_end`, `due_time`, `subtasks` côté
`/share/*` ? À vérifier chez CC ; sinon c'est le point le plus coûteux de la liste.

### 5. Le partage simple n'a pas ce que le hub a

Pas de filtre de sous-dossiers, pas d'Immersif / Compact, pas de ⭐ Favoris, pas de Télécharger en
zip, pas de tuile Carte, pas de tuile Historique. Deux pages, deux niveaux d'équipement : un invité
qui reçoit un lien direct est moins bien loti que celui qui passe par le hub. Lot de convergence
**[SHARE-HUB-PARITY]**, ou décision de toujours envoyer vers le hub.

### 6. Rien ne dit qu'il s'est passé quelque chose

Pas de cloche, pas de compteur de nouveautés dans le bandeau ; l'invité doit ouvrir chaque mémo pour
voir un commentaire de l'owner. L'owner, lui, a ses notifications. Une pastille « n nouveaux
commentaires depuis ta dernière visite » suffirait (le `seen` par mémo existe déjà).

### 7. Détails

- Le bandeau « Connecté·e … » prend une ligne pleine en permanence ; une fois lu, il pourrait se
  replier en pastille.
- Les languettes ✏️ ¥€ ⏱ (pomodoro, convertisseur, note) sont présentes côté invité alors que la
  note rapide ✏️ écrit… où ? À confirmer, sinon les retirer du partage.
- Paramètres invité = uniquement le thème. Un nom d'affichage / avatar ([GUEST-PROFILE], déjà en
  file) manque pour signer plus lisiblement que par l'e-mail.
- Pas d'horloge ni de météo dans l'en-tête : logique, mais l'espace vide à droite du champ de
  recherche est grand.

## Ce que je propose de faire

Dans l'ordre : **[GUEST-ADD-FOLDER]** (bug, n°1), puis **[SEARCH-ALL]** en y ajoutant la grammaire
côté invité (point 3), puis **[GUEST-MEMO-COLUMN]** (point 1, le gros morceau). Les points 4 et 5
méritent chacun un lot après, une fois qu'on aura vu si les invités s'en servent. Les points 6 et 7
sont du polish à glisser dans un lot existant.

Captures écran à ajouter quand l'onglet sera au premier plan (les animations étaient gelées pendant
la passe).
