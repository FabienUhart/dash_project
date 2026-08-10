# Addendum CC — [HUB-COMMENTS-POPIN] : afficher le 💬 pour un commentateur SANS message (parité share.html)

> **Petit ajout au lot hub déjà livré (V27.42.252), à glisser AVANT le tag** (mêmes 3 lots : 250 share
> + 251 banc + 252 hub). Front only, doctrine TDD. Décision Fabien : cohérence totale — dans le hub,
> le 💬 doit apparaître **dès qu'on peut commenter**, même sans message existant, comme sur `share.html`.

---

## 1. L'intention

Aujourd'hui, dans le hub, le 💬 n'apparaît que s'il y a **déjà** un message (`cmtHumanCount`). Un
commentateur sans message doit passer par la fiche pour lancer la discussion. On aligne sur
`share.html`, où la règle est **« il y a des messages OU la personne peut commenter »** :

- Référence share.html (l.~3762) : `if (nCmt || canCommentMemo(memo)) { …bouton 💬… }`, et le nombre
  n'est ajouté que **s'il y en a** (`if (nCmt) cBtn.appendChild(nombre)`). Donc : icône seule quand 0,
  icône + compteur quand ≥ 1.

## 2. Le point d'attention (composant PARTAGÉ)

Le 💬 du hub est dessiné par `memoPictosRow` (`templates/partials/_shared.js.html`) :

- l.4517 : `const nCom = cfg.comments || 0;`
- l.4533 : `if (nCom) chip('💬 ' + nCom, …, cfg.onComments || null);`

La pastille est donc gatée sur **`nCom > 0` uniquement** — même si `onComments` est fourni, rien ne
s'affiche à 0. `memoPictosRow` est **partagé** (hub et potentiellement d'autres appelants) : il ne faut
**pas** faire apparaître un 💬 vide partout par effet de bord.

**Voie recommandée (à toi de trancher, documente au journal)** : rendre l'affichage **opt-in** sans
changer le défaut. Par ex. un drapeau `cfg.commentsShowWhenEmpty` (ou équivalent) : la pastille
s'affiche si `nCom > 0` **ou** (`cfg.onComments` **et** ce drapeau). Icône seule quand `nCom === 0`
(pas de « 💬 0 »), compteur seulement si `nCom > 0` — exactement le comportement share.html. Les
appelants qui ne passent pas le drapeau gardent le comportement actuel (aucune régression owner/autres).

Puis, côté hub (`templates/hub.html`, l.~1322), passer le 💬 « toujours si on peut commenter » :

- `onComments: (cmtHumanCount(m.comments) || m.can_comment) ? () => openHubCommentsPopin(m) : null`
- et activer le drapeau d'affichage-à-vide sur cet appel `memoPictosRow`.

(Le hub gate déjà le composeur sur `m.can_comment`, l.2467 — la pop-in reste en lecture seule pour qui
ne peut pas commenter : ouvrir un 💬 sans droit d'écrire n'a de sens que s'il y a des messages à lire,
donc bien conditionner l'apparition-à-vide sur `m.can_comment`, pas sur la simple présence du handler.)

## 3. Tests (TDD)

1. `test_hub_comment_icon_shows_for_commenter_without_message` — carte hub, rôle **commentateur**,
   mémo **sans** message → un 💬 (icône, **sans** compteur) est présent au pied ; clic → pop-in avec
   composeur. **Rouge avant** (aujourd'hui pas de 💬 à 0) / vert après.
2. `test_hub_comment_icon_absent_for_viewer_without_message` — rôle **lecture seule**, mémo sans
   message → **pas** de 💬 (rien à lire, pas le droit d'écrire). Non-régression du bon sens.
3. `test_hub_comment_count_still_shown` — mémo avec messages → 💬 **avec** compteur (`cmtHumanCount`),
   inchangé.
4. **Non-régression composant partagé** : un appelant de `memoPictosRow` **sans** le drapeau n'affiche
   toujours **pas** de 💬 à 0 (prouve l'opt-in). Owner non touché.
5. **Mutation** : retirer le drapeau côté hub → #1 rougit ; gater l'apparition-à-vide sur le handler
   au lieu de `can_comment` → #2 rougit.

## 4. Definition of Done

1. Hub : 💬 visible dès que `cmtHumanCount > 0` **ou** `m.can_comment` ; icône seule à 0, compteur si
   ≥ 1 — parité exacte avec share.html. Lecteur sans message : pas de 💬.
2. `memoPictosRow` : affichage-à-vide **opt-in**, aucun autre appelant régressé (owner intact).
3. `make test` **entièrement vert** ; tests §3 rouges avant / verts après ; mutations tuées.
4. `git status` : `templates/hub.html`, `templates/partials/_shared.js.html`, `tests/…`,
   `REALISATION.md`. Pas de `.idea`. Rebuild local.
5. **Vérif à l'œil Fabien** (le juge, dans le hub) : un mémo où Marie peut commenter mais sans message
   → le 💬 est là → clic → pop-in avec composeur ; un mémo en lecture seule sans message → pas de 💬.
6. Journal + `handoff.json`, **STOP**. Ce lot **rejoint le tag** avec share (250) + banc (251) + hub
   (252) : un seul tag + Deploy après ta passe et **GO** (prod actuelle : V27.41.249).

## 5. Portée

Uniquement : rendre le 💬 du hub visible pour qui peut commenter, même sans message, comme share.html.
Pas d'autre changement de la pop-in, pas de nouvelle capacité, pas de régression du composant partagé.
