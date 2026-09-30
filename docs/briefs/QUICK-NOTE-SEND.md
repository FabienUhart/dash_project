# Brief CC — [QUICK-NOTE-SEND] : la note rapide dit qu'elle est partie

> **Front pur, owner desktop + mobile, zéro route, `app.py` intact, export 28 inchangé.** Demande
> Fabien du 30 sept. 2026 (« sur mobile la note rapide n'a pas de bouton pour sauvegarder, on se
> demande si la sauvegarde a bien été envoyée »). Pas de maquette (Fabien fait confiance). Doctrine
> TDD. Cible **V28.6.273** (passe avant [SEARCH-ALL], qui devient V28.7.274 — arbitrage Fabien 30 sept.
> 14:40).

## 0. Ce qui change, en une phrase

Le champ « + Note rapide… » gagne un bouton **Ajouter**, un retour visuel après l'envoi (toast +
card surlignée, défilement jusqu'à elle en mobile), un clavier mobile qui affiche « Envoyer », et
il ne passe plus sous les languettes ✏️ ¥€ ⏱.

## 1. Constats (30 sept., V28.5.272)

- `#memo-quick` (`textarea`, ~l.2375 ; handler `keydown` ~l.10462) : Entrée envoie, Maj+Entrée
  = saut de ligne. Sur téléphone la touche s'affiche « retour »/⏎ : rien ne dit qu'elle envoie.
- Après envoi : `value=''` + `loadAll()`. **Aucun message**, et le mémo neuf arrive en **haut** de la
  colonne (tri Plus récents) alors que l'utilisateur est en bas, collé au champ. Hors ligne :
  `enqueueNote` + `renderPendingNotes()` sans autre signal.
- Mobile : les lanceurs fixes `#qm-reshow / #fx-reshow / #pomo-reshow` recouvrent le bord gauche
  du champ (capture Fabien 30 sept.).

## 2. Décisions (fermes)

1. **Bouton « Ajouter »** dans `#memo-quick-wrap`, à droite du textarea (flex, même cadre), classe
   existante Luciole (`prio-btn` / gabarit du « Ajouter » du board, invariant 9), `type=button`,
   **masqué tant que le champ est vide** (`hidden` togglé sur `input`), visible desktop et mobile.
   Clic = **même fonction** que Entrée : extraire `quickAddNote()` du handler, appelée par les deux ;
   une seule implémentation (file hors ligne comprise).
2. **Clavier mobile** : `enterkeyhint="send"` sur le textarea ; Entrée garde son rôle actuel
   (envoi, Maj+Entrée = retour à la ligne) sur tous les supports. Placeholder : « + Note rapide… »
   (le « (Entrée pour ajouter) » disparaît, le bouton le remplace).
3. **Retour visuel** après envoi réussi : `notify('Note ajoutée dans Inbox')` (helper existant, pas
   d'erreur) ; la card du mémo créé reçoit la classe `.memo-note.is-new` (liseré accent, fondu 2 s,
   CSS seul, pas de GSAP) ; en mobile (≤ 900 px) `scrollIntoView({block:'nearest'})` sur cette card.
   L'id vient de la réponse du `POST /api/memos` (déjà renvoyée). Hors ligne :
   `notify('Note en attente — envoyée au retour du réseau')`, rien d'autre ne change.
4. **Languettes** (≤ 900 px) : `#memo-quick-wrap` reçoit `padding-left` égal à la largeur des
   lanceurs + 6 px (mesurée en CSS : leur largeur est fixe, 28 px selon l'audit) **ou**, si CC juge
   plus propre, les lanceurs remontent au-dessus du champ quand la colonne est ouverte. Un seul des
   deux, documenté dans REALISATION. Desktop : rien ne bouge.
5. **Hors périmètre** : la Note rapide du board (« + Titre du nouveau mémo… », qui a déjà son
   bouton), le widget note du dock (✏️), share/hub.

## 3. Ce qui NE bouge PAS

Route `POST /api/memos`, file hors ligne idempotente ([OFFLINE] D5), tri de la colonne, sticky du
champ ([MEMO-QUICK-STICKY]), `app.py`, export 28.

## 4. Tests (TDD — rouges d'abord)

`tests/front/test_quick_note_send.py`.

1. Desktop : champ vide → bouton absent ; taper → bouton visible ; clic → `POST /api/memos` une
   fois, champ vidé, toast « Note ajoutée dans Inbox », card `.is-new` présente dans la colonne.
2. Entrée → même effet, un seul POST (pas de double envoi bouton + touche).
3. Maj+Entrée → pas de POST, retour à la ligne dans le champ.
4. Mobile 412 px : `enterkeyhint === 'send'`, clic bouton → POST, card `.is-new` **visible dans le
   viewport** après défilement ; le champ ne chevauche aucun lanceur (rects disjoints).
5. Hors ligne simulé (`context.set_offline(True)`) : clic → aucun POST, toast « en attente », note
   dans la file locale ; retour en ligne → POST rejoué.
6. Zéro erreur console.

Mutations à poser puis tuer : (a) bouton et touche appelant deux fonctions distinctes (2 rougit si
l'une oublie de vider le champ) ; (b) `.is-new` jamais posée (1) ; (c) padding mobile retiré (4) ;
(d) toast hors ligne remplacé par le toast succès (5).

## 5. Livraison

`templates/index.html`, `tests/front/test_quick_note_send.py`, `REALISATION.md`, `IDEAS.md`
(retirer [QUICK-NOTE-SEND]), ce brief commité. Cycle : tests rouges → code → rebuild LOCAL →
`make test` → journal + handoff → **STOP**. Passe Cowork desktop + mobile, puis GO.

## 6. Précision (Cowork, 30 sept. 14:42) — « toast », pas pop-in

`notify()` ouvre une pop-in modale : **interdit ici** (une fenêtre à fermer à chaque note serait
pire que le silence actuel). Utiliser le **toast discret existant** (`announce` / gabarit
`undoToast`, `_shared.js` ~l.2755), non bloquant, auto-fermeture ~2,5 s, sans bouton sauf le cas
hors ligne. S'il n'existe pas de variante « info sans action », en dériver une dans le même
composant (invariant 9, pas de nouveau composant). Même règle pour le message hors ligne.
