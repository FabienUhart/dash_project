# Trace — une écriture invitée à travers les trois couches

**[GUEST-ROLES-T1-AUDIT] — analyse seule, 8 août 2026 (post V27.29.209). Aucun code modifié.**
Compagnon de [`ROUTE-CAPS.md`](ROUTE-CAPS.md) et de [`GUEST-ROLES-V2.md`](GUEST-ROLES-V2.md).

Cas choisi : **un invité poste un commentaire** depuis la page de partage. C'est l'écriture la plus
courte du repo (une route, un corps JSON) et pourtant elle traverse **toutes** les gardes : jeton de
partage, approbation, périmètre, capacité, contexte projet, overrides. Tout ce qui suit vaut, à la
capacité près, pour les 24 autres routes d'écriture recensées dans `ROUTE-CAPS.md`.

---

## 0. Vue d'ensemble

```
share.html                    _shared.js.html                app.py
──────────                    ───────────────                ──────
canCommentMemo(memo) ────────────────────────────────────────► sert m.can_comment
   │                                                            (_memo_guest_caps)
   ▼
shareCommentInput(memo, parent)
   ├─ cmtPrioSelect(DATA.priorities) ◄── helper partagé
   ├─ attachInputMention(ci, …)      ◄── helper partagé
   ├─ attachCmdHint(ci)              ◄── helper partagé  [COMMENT-VOTE]
   ├─ voiceCommentButton({…})        ◄── helper partagé  [VOICE-MESSAGES]
   │
   └─ keydown Entrée
        ├─ cmdGuardBlocks(ci)        ◄── helper partagé  (confort, ZÉRO valeur de sécurité)
        └─ fetch POST /share/<token>/memo/<id>/comments   (X-Guest-Token)
                                                     │
                                                     ▼
                                            share_add_comment()
                                              1. _share_by_token       → 404
                                              2. _guest_from_request   → 403 (approuvé ?)
                                              3. _share_scope_memos    → 404 (périmètre)
                                              4. _role_allows('comment') → 403  ◄── LA PORTE
                                              5. validation du corps   → 400
                                              6. écriture + commit
                                              7. _comment_dict → 201
                                                     │
        await load() ◄───────────────────────────────┘
        └─ GET /share/<token>/data → render() complet
```

---

## 1. Couche page — `templates/share.html`

| Ligne | Rôle |
|---|---|
| `1187` | `canCommentMemo(m)` = `!!m.can_comment && approved()` — **le booléen vient du serveur**, la page ne le calcule jamais. |
| `3633` | Le composeur n'est ajouté au fil **que** si `canCommentMemo(memo)`. |
| `3595` | L'action « ↩ Répondre » n'est proposée que sous la même condition. |
| `3613` | La rangée de réactions n'est cliquable que sous la même condition (réagir = `commenter`). |
| `1424` | `shareCommentInput(memo, parentId)` construit le composeur. |
| `1443` | `if (cmdGuardBlocks(ci)) return;` — commande inconnue retenue (rien n'est posté). |
| `1446` | `fetch(API + '/memo/' + memo.id + '/comments', …)` avec l'en-tête `X-Guest-Token`. |
| `1451` | `if (r.ok) await load()` — **rechargement complet**, jamais d'insertion optimiste. |

**Ce que la page NE fait pas** : elle ne décide rien. `m.can_comment` est produit par
`_memo_guest_caps()` (`app.py:4983`) et posé sur chaque mémo par `share_data` (`app.py:7502`) et par
`hub_data` (`app.py:7223`). Masquer le champ n'est qu'une politesse : forger le `fetch` à la main
retombe sur la garde 4 côté serveur.

## 2. Couche partagée — `templates/partials/_shared.js.html`

Quatre helpers s'intercalent, tous **purs** (ni `state`, ni `DATA`, ni réseau — règle du partial,
ADR-001) :

| Helper | Ligne | Ce qu'il apporte | Rapport aux droits |
|---|---|---|---|
| `cmtPrioSelect` | `614` | menu des priorités configurées | aucun — le serveur revalide via `_valid_comment_priority` |
| `attachInputMention` | — | menu `@` des personnes du partage | aucun — les `@` partent en **texte** |
| `attachCmdHint` | `730` | panneau d'aide « / » + garde commande inconnue | **aucune valeur de sécurité** |
| `voiceCommentButton` | — | vocal → PJ v22 + commentaire `[audio:…]` | passe par **deux** routes (`/attachments` puis `/comments`), donc **deux** gardes |
| `cmdGuardBlocks` | `814` | `true` = on retient le 1er Entrée | confort de saisie, pas un droit |

Point d'entrée exact du garde-fou : `attachCmdHint` pose `input._cmdApi.blocks()`, et la page
l'appelle **avant** le `fetch` (share.html:1443). Sans composeur outillé, `cmdGuardBlocks` ne bloque
jamais rien — c'est voulu.

⚠️ Conséquence pour T2/T3 : **le vocal invité franchit deux capacités différentes** — `creer`
(upload de la PJ) puis `commenter` (le message). Un futur « Commentateur » au sens strict de la spec
V2 (commenter mais pas créer) **perdrait le micro** sans qu'aucune ligne de la spec ne le dise.

## 3. Couche serveur — `app.py:8257 share_add_comment()`

Quatre gardes, dans cet ordre exact :

1. **Jeton** — `_share_by_token(db, token)` (`4692`) : longueur ≥ 16 + existence en base. Sinon `404`
   (jamais `400` : on ne confirme pas l'existence de la route).
2. **Approbation** — `_guest_from_request(db, share)` (`7562`) lit `X-Guest-Token` et exige
   `status == 'approved'`. Sinon `403 guest_required`. *(Le statut `pending` n'existe plus depuis
   [GUEST-AUTO-APPROVE] — `app.py:502` ; restent `approved` et `rejected`.)*
3. **Périmètre** — `memo_id ∈ _share_scope_memos(db, share)` (`5288`), recalculé **à chaque appel**,
   jamais déduit du front. Sinon `404`. C'est l'invariant 5 en une ligne.
4. **Capacité** — `_role_allows(db, share, "comment", guest, memo_row=memo)` (`4843`). C'est **la
   porte unique** de la spec V2 §1, et elle existe déjà. Elle enchaîne :
   - `_effective_rank` (`4830`) = rang du lien (`_share_role`, `4722`) **élevé** — jamais abaissé —
     par `_resolve_role_floor` (zone héritable, `4792`) puis par `_owns_guest_space_folder`
     (propriété d'un dossier perso → éditeur plein, `4810`) ;
   - `_min_role_for` (`4767`) = rang minimal de l'action selon `_ACTION_MIN_ROLE` (`4706`),
     **abaissé** à `viewer` si le mémo ou un de ses dossiers ancêtres porte `perm_comment='all'`
     (`_resolve_memo_perm`, `4755`).

Puis, seulement, la validation du contenu : `_clean_comment_body`, `_valid_parent_comment`,
`_valid_comment_priority`, et la bifurcation `_parse_poll_command` → scrutin (`kind='poll'` +
`_create_poll`) ou message simple. Commit, `_comment_dict(...)`, `201`.

**Ce que ça dit pour T1** : il n'y a **rien à ajouter comme garde**. `can(invité, capacité, dossier)`
existe, s'appelle `_role_allows`, et les 25 routes d'écriture y passent déjà. T1 consiste à
**remplacer son intérieur** (table `guest_roles` par (invité × dossier), capacités atomiques,
surcharges) — pas à instrumenter les routes une par une. C'est une bonne nouvelle : le risque de
T1 est concentré en un point, pas dispersé sur 49 routes.

## 4. Retour et re-render

`await load()` refait un `GET /share/<token>/data` **entier** et re-rend le board. Deux
conséquences déjà rencontrées :

- **[SHARE-REFRESH-GUARD] (V27.29.209)** : le tick de 15 s est retenu si une pop-in est ouverte, si
  le curseur est dans un champ, ou si un brouillon non envoyé traîne. Le `load()` **explicite** de
  la ligne 1451, lui, rend toujours. Une sonde qui compte les renders juste après un envoi doit
  attendre le fetch (piège journalisé le 8/08).
- **La bulle se re-crée à chaque render** : toute référence DOM gardée en variable est morte au
  render suivant (piège de sonde relevé par Cowork le 8/08). À re-résoudre systématiquement.

## 5. Arêtes pendantes du graphe

Le graphe livré (`graphify-out/graph.json`, 2012 nœuds / 4434 arêtes) contient **0 arête pendante**
telle que livrée — les 65 signalées au run ont été réconciliées ou écartées à la construction.
Vérification faite sur le chemin exact ci-dessus (`share_add_comment`, `_role_allows`,
`_share_by_token`, `_guest_from_request`, `_insert_comment`, `shareCommentInput`, `attachCmdHint`,
`cmdGuardBlocks`, `_role_gate`, `_effective_rank`) : **aucune arête pendante ne tombe sur le chemin
d'écriture**. La marge d'incomplétude annoncée ne concerne donc pas cette tranche ; le tableau de
`ROUTE-CAPS.md` a malgré tout été établi par lecture directe des 49 décorateurs `@app.route`, pas
depuis le graphe seul.
