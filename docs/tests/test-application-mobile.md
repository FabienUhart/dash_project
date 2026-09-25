# Test de l'application en mobile

Passe faite le 25 septembre 2026 sur la base locale (localhost:8099, V27.45.260), en émulation téléphone à 412 px de large, dans Chrome. J'ai parcouru l'accueil, la colonne mémos, l'éditeur d'un mémo, le board « Tous les mémos », la recherche, la navigation entre dossiers et le tri des liens livré le matin.

Le résumé tient en une phrase : le contenu est bon, c'est l'accès au contenu qui coûte cher sur un petit écran. Trois problèmes pèsent vraiment (la navigation entre dossiers, le formulaire de création ouvert par défaut, l'en-tête qui mange un tiers de l'écran). Le reste est du polish.

## Ce qui marche bien

La feuille de recherche est le meilleur écran de l'app en mobile. Elle prend tout l'écran, propose Tout / Liens / Mémos / Dossiers, et « kyoto » sort six résultats en un geste. Rien à changer.

L'éditeur de mémo est complet et on sait toujours comment en sortir : « Sauver » et « Commentaires » restent collés en bas quel que soit le défilement.

Les tuiles de filtre du board (En cours 179, En retard 96, Planifiés 49...) sont lisibles et réagissent au premier tap.

Le tri des liens ajouté ce matin passe bien en mobile : les quatre boutons se rangent dans l'en-tête du bloc Liens avec des libellés courts, sans rien casser autour.

## Les frictions, de la plus lourde à la plus légère

### 1. Trouver un dossier demande de faire défiler 20 écrans

Sur téléphone, la barre latérale devient une bande horizontale. Elle contient 60 entrées sur 8 236 px de large. Pour atteindre « Voyage Japon », il faut faire glisser l'équivalent de vingt écrans, ou passer par la recherche.

C'est le problème numéro un. Ma proposition : un panneau « Dossiers » qui monte du bas de l'écran (bottom sheet), avec l'arbre replié, les favoris en tête et un champ de recherche. Il s'ouvrirait depuis un bouton dans l'en-tête ou dans la barre du bas. Cela suit ta règle « mobile = bottom sheet ».

### 2. Le formulaire de création est déplié par défaut sur le board

Quand on ouvre « Tous les mémos », le formulaire complet (Quand, deux dates, heure, priorité, récurrence, dossier) occupe la moitié de l'écran avant le premier mémo. Le bouton « Réduire » existe, mais il faut le presser à chaque fois.

Proposition : replié par défaut sur téléphone, et l'état mémorisé. On garderait juste le champ « + Titre » et le bouton « Ajouter », le reste apparaît au tap.

### 3. Trois rangées d'en-tête avant le contenu

Titre + recherche + horloge sur la première ligne, puis les trois icônes (notifications, thème, réglages) sur une deuxième ligne, puis la bande de navigation sur une troisième. Cela fait environ 175 px de chrome sur 921 px d'écran.

Les trois icônes tiennent à droite de la première ligne si l'horloge et la météo passent dans une infobulle. La bande de navigation disparaît si le point 1 est fait. On récupère un tiers de l'écran.

### 4. L'accueil ouvre sur les liens, avec les mémos repliés

Avec 179 mémos dont 96 en retard, c'est l'inverse de ton usage. Proposition : mémoriser l'état ouvert ou replié du bloc MÉMOS, et l'ouvrir par défaut sur téléphone.

### 5. Le titre est répété dans le contenu

Beaucoup de cards affichent « Changer les mots de passe signalés par Google, Changer les mots de passe signalés par Google @Marie... ». Ce sont tes mémos qui commencent par leur titre, mais la card peut masquer la première ligne du contenu quand elle est identique au titre. Petit changement, très visible.

### 6. Trois languettes fixes sur le bord gauche

Le pomodoro, le convertisseur ¥€ et la note rapide sont trois languettes de 28 px collées au bord gauche, en bas. Sur iPhone, c'est la zone du geste « retour » (glisser depuis le bord). Elles vont soit gêner le geste, soit être touchées par erreur. À regrouper dans le dock du bas, ou derrière un seul bouton.

### 7. Les résultats de recherche n'affichent pas le chemin complet

« Kyoto · Sanjo » sort deux fois, chaque fois avec « Reservations Alex Fab » dessous. Ce sont deux dossiers homonymes (ids 12 et 125, tes doublons connus). Afficher le chemin du parent (« Voyage Japon › Reservations Alex Fab ») lèverait le doute, et t'aiderait à faire le ménage.

### 8. Les cards de liens sont très hautes

Chaque lien affiche en permanence les boutons modifier et supprimer, la rangée des statuts, la rangée des tags et le « + ». Résultat : environ 220 px par lien, donc quatre liens par écran. Un mode compact (une ligne avec favicon, nom et statut, les actions au tap long ou derrière « ... ») en ferait tenir dix.

### 9. Détails

La rangée Favoris / Partages / Corbeille est coupée à droite (« Corbeille 0 » tronqué).

La tuile « Carte 69 » est seule sur sa ligne au-dessus des filtres.

Le premier tap sur un mémo de la liste a expiré une fois côté extension (page occupée). À surveiller si ton iPhone montre un délai à l'ouverture d'un mémo quand la liste en contient 179.

## Ce que je propose de faire

Un lot [MOBILE-NAV] qui prend les points 1, 3 et 4 (navigation en bottom sheet, en-tête compacté, bloc MÉMOS ouvert par défaut). C'est le plus gros gain pour un seul lot.

Ensuite un lot plus petit [MOBILE-POLISH] pour les points 2, 5, 6 et 9.

Les points 7 et 8 peuvent attendre [CARD-POLISH-V3], déjà dans la file.

Avant tout brief, je fais une maquette cliquable du panneau Dossiers, comme on l'a fait pour le tri.
