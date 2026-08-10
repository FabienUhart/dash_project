# Brief CC — [HUB-COMMENTS-POPIN] : commentaires en pop-in dans le HUB invité (la vraie surface)

> **Front only, doctrine TDD.** Suite/complément de [GUEST-COMMENTS-POPIN]. **Vérifié en live par
> Cowork** (Claude in Chrome, localhost:8099) : les invités passent par le **hub** (`/share/hub/…`,
> `hub.html`, « Mes dossiers »), et là le 💬 d'une card appelle `openEditor(m)` → **l'éditeur complet
> du mémo** (titre, contenu, échéance, priorité, assigné·es, images, fichiers, puis les commentaires
> tout en bas). C'est le « tous les paramètres » signalé par Fabien. [GUEST-COMMENTS-POPIN] a corrigé
> `share.html` (partage **direct**), mais **le hub n'a pas été touché** — c'est pourtant la surface
> réelle. On le corrige ici.
>
> **Les deux lots partent ensemble** (rien n'est commité) : `share.html` (fait) + ce hub → un seul tag.

---

## 1. Le correctif (hub.html)

Le 💬 d'une card doit ouvrir une **pop-in de commentaires propre** (juste le fil + composeur),
**comme chez le propriétaire** — pas l'éditeur complet. La **vue complète du mémo reste** accessible
par le 👁 / le clic sur la card (`openEditor`, inchangé).

1. **Coquille pop-in** : ajouter dans `hub.html` un `#comments-dialog` avec `.cp-head`/`.cp-body`/`.cp-x`,
   **CSS reprise à l'identique** de l'owner/`share.html` (invariant 9 — même composant, même look). Ne
   pas inventer un style neuf.
2. **`openHubCommentsPopin(m)`** : en-tête (icône `message` + **titre du mémo**, sinon 1re ligne, sinon
   « Commentaires » + ✕), corps = **le fil de commentaires**. Réutiliser le rendu existant
   `renderEdComments` (déjà utilisé dans l'éditeur) : soit en lui passant un **conteneur cible**, soit
   en extrayant la construction du fil dans une fonction qui renvoie le nœud, appelée par l'éditeur
   **et** par la pop-in. **Aucune duplication du fil** — juste la coquille.
3. **Câblage** : `onComments: cmtHumanCount(m.comments) ? () => openHubCommentsPopin(m) : null`
   (remplace `openEditor(m)`, l.~1299). Le compteur reste `cmtHumanCount` (humains seuls).
4. **Rafraîchissement** (leçon [GUEST-COMMENTS-POPIN]) : après un envoi/réaction/vote depuis la
   pop-in, le fil doit se **re-render dans la pop-in ouverte** (pas seulement dans l'éditeur fermé) —
   prévoir un `refreshHubCommentsPopin()` appelé en fin de `reload()`/rendu, qui reconstruit le fil du
   mémo ouvert en conservant la position de lecture. Sans ça, un message posté part en base et
   n'apparaît nulle part (exactement le trou déjà rencontré côté share).
5. **Droits inchangés** (invariant 5) : composeur/réactions/votes gatés comme aujourd'hui par
   `renderEdComments` (lecture seule → fil consultable, pas de composeur). Le serveur reste juge.

## 2. Ce qui ne change pas

- `openEditor` (vue/édition complète du mémo) reste, accessible par le 👁 et le clic de card.
- Owner (`index.html`) et `share.html` : **non touchés** ici (share.html est déjà fait dans l'autre lot).
- Pas de nouvelle route, pas de serveur.

## 3. Tests (TDD) — hub e2e (la couverture hub existe depuis [CARD-ACTIONS-FIXED])

1. **`test_hub_comment_opens_popin_not_editor`** — dans le hub, cliquer le 💬 d'une card **ouvre une
   pop-in de commentaires** (`#comments-dialog[open]` avec le fil) et **PAS** l'éditeur complet
   (pas de champ Titre/Échéance/Priorité visible). Rouge avant (aujourd'hui c'est l'éditeur) / vert après.
2. **`test_hub_comment_popin_posts`** — rôle commentateur : composeur présent dans la pop-in, un envoi
   ajoute la bulle **dans la pop-in** (prouve le rafraîchissement). Rôle lecture seule : fil visible,
   pas de composeur.
3. **`test_hub_full_view_still_available`** — le 👁 / clic de card ouvre toujours l'éditeur complet
   (non-régression).
4. **Mutation** : re-brancher `onComments` sur `openEditor` → #1 rougit ; retirer le
   `refreshHubCommentsPopin` → #2 rougit.

## 4. Definition of Done

1. Hub : 💬 → pop-in de commentaires (coquille commune, `renderEdComments` réutilisé, rafraîchissement
   dans la pop-in), 👁/clic → éditeur complet inchangé, droits inchangés.
2. `make test` **entièrement vert** ; tests §3 rouges avant / verts après ; mutations tuées.
3. `git status` : `templates/hub.html` (+ `_shared.js.html` si extraction du rendu de fil partagée),
   `tests/…`, `REALISATION.md`. Pas de `.idea`. Rebuild local.
4. **Vérif à l'œil Fabien** (le juge, dans le **hub** cette fois) : une card avec commentaires → 💬 →
   pop-in propre (comme chez l'owner), poster/réagir marchent, **plus** l'éditeur complet ; le 👁
   ouvre toujours la fiche complète.
5. Journal + `handoff.json`, **STOP**. Commit après passe Cowork + **GO** — **avec** [GUEST-COMMENTS-POPIN]
   (share.html) dans le même tag + Deploy (prod actuelle V27.41.249).

## 5. Portée

Uniquement : le 💬 du hub ouvre le fil en pop-in au lieu de l'éditeur complet. Pas de refonte de
l'éditeur, pas de nouvelles capacités. Une intention : commenter dans le hub se fait dans la même
pop-in soignée que partout ailleurs.
