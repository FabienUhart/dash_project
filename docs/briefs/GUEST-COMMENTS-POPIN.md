# Brief CC — [GUEST-COMMENTS-POPIN] : le fil de commentaires en pop-in côté invité (parité owner)

> **Front only, doctrine TDD.** Retour Fabien : côté invité, les commentaires « c'est pas ça ». La
> cause, relevée dans le code : l'invité affiche tout le fil **en ligne dans la card**
> (`share.html`, `cwrap` collé à la card, l.~3668-3746), tandis que le **propriétaire** l'ouvre dans
> une **pop-in dédiée** (`openCommentsPopin`, `index.html` l.5661). On amène l'invité à la **parité**.
>
> **Périmètre : `share.html` (invité) uniquement.** Le **hub** ouvre déjà les commentaires dans
> l'éditeur (`renderEdComments` → `#ed-comments`), pas en ligne — il n'est **pas** concerné. Le
> propriétaire a déjà sa pop-in — **ne pas y toucher** (test de non-régression seulement).

---

## 1. Le correctif

Côté invité :

1. **Retirer le fil en ligne** de la card : le bloc `cwrap` (bulles `buildC` + `shareCommentInput`)
   ne s'appende plus à la card `t`.
2. **Ajouter un bouton 💬 au pied de card** (le `.task-foot` posé par [CARD-ACTIONS-FIXED]), avec le
   **compteur de messages humains** (mêmes règles que le hub : `cmtHumanCount`, ni journaux ni
   tombales), visible s'il y a des commentaires **ou** si `canCommentMemo(memo)` (un commentateur
   sans message doit pouvoir en poster). Icône trait monochrome, comme le reste.
3. **Ouvrir le fil dans une pop-in dédiée** au clic sur ce 💬 — même **coquille et même look** que la
   pop-in owner (invariant 9 : c'est le même composant, il doit se ressembler d'une page à l'autre),
   en **réutilisant les composants partagés déjà en place** (`cmtRow`, `reactionRow`,
   `cmtMoreToggle` du partial ; `buildC`, `shareCommentInput` de l'invité). La pop-in doit conserver
   **tout** ce que l'invité avait en ligne : réponses imbriquées, réactions, **scrutins de vote**
   (`cmtPollNode`), et le composer gaté par rôle (`canCommentMemo`).

> **Décision technique (à toi, je recommande)** : plutôt que de dupliquer la coquille pop-in de
> `index.html`, **extraire une coquille commune** (le `<dialog>` + en-tête + zone défilable + pied
> composer) dans le partial `_shared.js.html`, paramétrée par la source de données (API owner vs
> invité, `X-Guest-Token` / routes `/share/*`), et l'appeler des deux côtés. Si l'extraction est trop
> lourde pour ce lot, **construis une pop-in invité dans `share.html` qui réutilise au maximum les
> composants partagés** et **reprend la CSS de la pop-in owner à l'identique** — sans toucher ni
> régresser l'owner. Signale la voie retenue.

## 2. Ce qui ne change pas

- **Droits inchangés** (invariant 5) : le serveur reste seul juge (`can_comment`, périmètre, rôle) ;
  la pop-in ne fait qu'afficher ce qu'il autorise. `canCommentMemo` continue de gater le composer et
  les réponses/réactions/votes.
- **Owner** : `openCommentsPopin` intact. **Hub** : inchangé (déjà dans l'éditeur).
- En **Immersif** (couverture) le fil n'avait déjà pas sa place sur la card — le 💬 du pied de verre
  doit ouvrir la même pop-in ; garder la cohérence avec [CARD-COVER].

## 3. Tests (TDD)

**e2e invité par une vraie porte** (leçon des lots précédents) :

1. **`test_guest_comments_open_in_popin`** — card invité avec ≥ 1 commentaire → le fil **n'est plus
   en ligne** sur la card (le `cwrap` a disparu du DOM de la card) ; un **💬 avec compteur** est au
   pied ; clic → une **pop-in** s'ouvre (`dialog[open]`) contenant les bulles. Rouge avant / vert après.
2. **`test_guest_can_post_from_popin`** — rôle commentateur : le composer est présent dans la pop-in,
   un envoi ajoute la bulle (droits respectés). Rôle lecteur : composer absent, fil consultable.
3. **Non-régression owner** : `openCommentsPopin` s'ouvre toujours, thread + composer OK.
4. Éprouver par **mutation** : remettre le fil en ligne (réappend du `cwrap`) → le test #1 rougit.

## 4. Definition of Done

1. Invité : fil de commentaires **en pop-in** via le 💬 du pied de card, plus en ligne ; compteur
   humain ; réponses/réactions/votes/composer préservés, droits inchangés. Owner et hub non touchés
   (owner : test de non-régression).
2. Réutilisation des composants partagés / coquille owner (invariant 9), icône trait monochrome.
3. `make test` **entièrement vert** ; tests §3 rouges avant / verts après, ancre éprouvée par mutation.
4. `git status` : `templates/share.html` (+ `templates/partials/_shared.js.html` si coquille
   extraite), `tests/…`, `REALISATION.md`. Pas de `.idea`. Rebuild local.
5. **Vérif à l'œil Fabien** : côté invité, une card avec des commentaires → 💬 au pied → pop-in
   propre (comme chez l'owner), poster/réagir/répondre fonctionnent, la card n'est plus encombrée.
6. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO**, puis **tag + Deploy**
   (prod actuelle : V27.41.249).

## 5. Portée

Uniquement le passage du fil invité **en pop-in** (parité owner). Pas de refonte du composer, pas de
nouvelles capacités de commentaire, pas le hub. Une intention : que commenter côté invité se fasse
dans la même pop-in soignée que côté propriétaire.
