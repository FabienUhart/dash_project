# Brief CC — [GUEST-ADD-FOLDER] : côté invité, le mémo se crée dans le dossier affiché

> **Bug, front pur (`_shared.js`), zéro route, `app.py` intact, export 28 inchangé.** Constat Fabien
> du 30 sept. 2026 : connecté en invité (share `qwpW…`, rôle editor, espace `uhart_f` id 93), il
> ouvre le sous-dossier « test dossier » (138), crée un mémo → le mémo atterrit dans `uhart_f` (93)
> (mémo 423 en base locale). Doctrine TDD. Cible **V28.7.274** ([SEARCH-ALL] passe en V28.8.275).

## 1. Cause (mesurée le 30 sept. sur localhost, page share)

En vue « test dossier », `PFILTER === 138` mais les **deux** sélecteurs de dossier restent sur 93 :
- `guestMemoAddBar.updateFolders` (`_shared.js` ~l.7540) : reconstruit les options avec le bon
  `selected`, puis **restaure la valeur précédente** (`if (prev && …) projSel.value = prev`). Le
  « souvenir du choix » écrase la navigation.
- Widget Note rapide invité (`initQuickMemo`, ~l.6781) : `const want = cur || cfg.defaultFolder()` :
  la valeur courante gagne sur le dossier affiché.
Le serveur (`POST /share/<token>/memos`, app.py ~l.10193) honore `project_id` s'il est descendant de
la cible : le front envoie simplement le mauvais id.

## 2. Décision

Le sélecteur **suit le dossier affiché**, sauf si l'utilisateur l'a **changé lui-même depuis la
dernière navigation** : un drapeau `userPicked` posé sur `change` du `<select>`, remis à faux quand
`updateFolders` / `defaultFolder` reçoit un dossier affiché différent du précédent. Même règle dans
les deux composants, une seule petite fonction partagée (`pickFolder(sel, wanted, userPicked)`).
Rien ne change côté owner (composants distincts) ni côté serveur.

## 3. Tests (TDD — rouges d'abord)

`tests/front/test_guest_add_folder.py` (share editor sur un espace avec un sous-dossier) :
1. Aller dans le sous-dossier → barre « + Titre… » : créer → `project_id` du POST = sous-dossier ;
   idem via la Note rapide.
2. Revenir sur « Tous » → créer → `project_id` = racine de l'espace (`DATA.root_id`).
3. Dans le sous-dossier, choisir à la main la racine dans le sélecteur, créer → racine (choix manuel
   respecté) ; naviguer vers un autre dossier → le sélecteur suit à nouveau.
4. Zéro erreur console.
Mutations : `prev` restauré sans condition (1 rougit) ; `userPicked` jamais remis à faux (3 rougit).

## 4. Livraison

`templates/partials/_shared.js.html`, `tests/front/test_guest_add_folder.py`, `REALISATION.md`,
`IDEAS.md`, ce brief. Cycle habituel, **STOP** au rebuild local, passe Cowork (share local), GO.
