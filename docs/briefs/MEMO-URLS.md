# Brief CC — [MEMO-URLS] : des liens attachés au mémo, comme les fichiers

> **Back + front 3 pages, table additive `memo_urls`, BUMP export v28 → v29 (`APP_VERSION="29"`,
> tags `V29.x`).** Cible **V29.0.279**. Doctrine TDD. Demande Fabien du 15 oct. 2026 (mémo prod 403) :
> « je viens de recevoir un lien de suivi pour la réparation de mon iPad et je veux, comme les dates
> et les fichiers, rajouter l'URL au mémo ; et aussi lister celles qui sont dans le texte ». Pas de
> maquette (Fabien : « va pour se lancer »), on reprend **le gabarit des Fichiers** (`renderAttachments`)
> et **les chips de [LINK-REFS]** (`linkRefsRow`) — rien de visuel nouveau.

## 0. Contexte — à relire

- Aujourd'hui une URL n'a que deux places : **dans le texte** (cliquable via `linkifyTextNodes`/`dressLinks`,
  [EDITOR-AUTOLINK]) ou **dans la vue Liens** reliée au mémo par `link_refs` ([LINK-REFS] v28, chips 🔗 sur la
  card). Un lien de suivi de colis/réparation n'est ni l'un ni l'autre : il appartient **au mémo**, il n'a
  rien à faire dans la curation de la vue Liens, et le noyer dans le texte le rend introuvable.
- Modèle : exactement ce qu'on a fait pour les pièces jointes ([ATTACHMENTS] v22) — une **table additive
  par mémo**, une section dans l'éditeur, une rangée en pied de card, parité invités. Ici sans binaire.
- Deux sources **fusionnées à l'affichage** : (a) les URL **attachées** (table) ; (b) les URL **détectées
  dans le contenu** (runtime, jamais stockées). Dédup par URL normalisée ; une URL détectée qu'on
  « épingle » devient attachée.

## 1. Modèle & API

### 1.1 Table (additive, `CREATE TABLE IF NOT EXISTS`, jamais destructive)
```
memo_urls (id INTEGER PK, memo_id INTEGER NOT NULL, memo_uid TEXT, url TEXT NOT NULL,
           label TEXT DEFAULT '', position INTEGER DEFAULT 0, created_at TEXT, created_by TEXT DEFAULT '',
           og_title TEXT DEFAULT '', og_domain TEXT DEFAULT '', og_fetched_at TEXT,
           UNIQUE(memo_id, url))
```
- `url` validée par `_clean_url()` : **`http://` ou `https://` uniquement** (jamais `javascript:`/`data:`),
  longueur ≤ 2048, espaces trimés, **pas de normalisation agressive** (on garde la query — les liens de suivi
  en dépendent) ; dédup sur `url` exact par mémo. `label` ≤ 120 car., texte brut (jamais de HTML).
- `og_*` = **dérivées**, remplies par `_fetch_og` existant (SSRF-safe de [LINK-OG]) à la création, **hors
  export** comme pour les liens ; échec → vides, l'UI retombe sur le domaine.
- Plafond **20 URL par mémo** (400 explicite). `created_by` = pattern v19 (`''` owner, sinon « Nom <email> »).
- Corbeille : mémo en corbeille → URL masquées partout mais conservées ; **purge définitive** →
  `_purge_memo_row` supprime les lignes (cascade, comme attachments).

### 1.2 Routes
- Owner (derrière Authelia) : `GET /api/memos/<id>/urls`, `POST /api/memos/<id>/urls {url, label}` → 201 +
  objet, `PUT /api/memos/<id>/urls/<uid>` `{label, position}`, `DELETE /api/memos/<id>/urls/<uid>`.
  `_memo_dict` émet `urls: [{id, url, label, position, og_title, og_domain, created_by_display}]`
  (donc présent dans `/api/memos` sans appel de plus).
- Invités (invariant 5, bypass `/share/*`) : lecture dans `_share_memo_dict` (projection `{url, label,
  og_title, og_domain}` — pas d'id, pas de `created_by`) ; écriture `POST/DELETE /share/<token>/memo/<id>/urls`
  pour invité **approuvé + `can_edit`**, scope revalidé — même matrice que les pièces jointes.

### 1.3 Export v29
- `urls` niché dans chaque mémo : `[{url, label, position, created_at, created_by}]` (**jamais `og_*`**).
- Import **uid-d'abord tolérant** : URL invalide ignorée (jamais de 400), `INSERT OR IGNORE` sur
  `UNIQUE(memo_id, url)` (ré-import v29 = 0 doublon), **additif non destructif** (une URL locale n'est jamais
  retirée ; un `label` local non vide n'est pas écrasé par un vide). Absent à l'import (v1→v28) = aucune URL
  = rendu identique, compat ascendante garantie (invariant 2). Compteur `imported_memo_urls`.
- `APP_VERSION="29"`, entrée v29 dans `docs/EXPORT-FORMAT.md`, index `CLAUDE.md`. **[MEMO-TYPES] visera v30.**

## 2. UI (3 pages, helpers dans `_shared.js.html` — ADR-001)

### 2.1 Détection dans le texte — helper pur `extractUrls(html)`
Déshabille le HTML (`<template>`), applique **la même regex que `linkifyTextNodes`** (une seule source :
sortir la regex en constante partagée `URL_RE` si elle est inline), retire la ponctuation finale `.,;:)]`,
dédoublonne, garde l'ordre d'apparition, max 50. Zéro état.

### 2.2 Section « Liens » de l'éditeur — `renderMemoUrls(cfg)`
Même squelette que `renderAttachments` (`attach-sec`, `secHeadIcon('link')`, titre « Liens (n) ») posée
**juste sous `#me-attachments`** (owner `#me-urls`, share/hub idem à côté de leur bloc Fichiers).
- Liste : une ligne par URL = chip `linkRefChip`-like (favicon via `og_domain`, libellé = `label` ||
  `og_title` || domaine, `↗` ouvre dans un nouvel onglet `noopener`), `×` retire (canEdit), **drag léger
  ou flèches ↑↓** pour `position` (comme les sous-tâches — réutiliser ce qui existe, pas de nouveau D&D).
- Ajout : champ `url` + champ `label` (placeholder « Libellé (optionnel) ») + bouton Luciole « Ajouter »
  ; Entrée dans le champ url = ajout ; coller une URL **dans le champ url** suffit. Validation côté client
  miroir de `_clean_url` (message « Seules les adresses http(s) sont acceptées »).
- Sous la liste, si `extractUrls(content)` renvoie des URL **non déjà attachées** : sous-titre discret
  « Dans le texte » + chips grisées avec un bouton **« Épingler »** (= POST avec `label` vide). Pas de
  `×` sur celles-là (elles vivent dans le texte).

### 2.3 Pied de card (board + colonne + share/hub) et fiche 👁
- Nouvelle rangée `urlsRow(memo.urls, detected)` **juste après `linkRefsRow`** (même style `lrefs-row`,
  mêmes chips) : attachées d'abord (ordre `position`), puis détectées (grisées, `title` « dans le texte »).
  Clic = ouvre l'URL (`noopener`), pas de `×` sur la card (on retire depuis l'éditeur).
- Compact/Immersif : la rangée suit les mêmes règles que `linkRefsRow` (rien de spécial).
- Fiche 👁 (`openMemoView`) : même rangée en pied, avant les commentaires. (La future page [MEMO-READ]
  la reprendra telle quelle.)
- Recherche : `visibleMemos` et share/hub cherchent aussi dans `label` et `url` (texte), comme les
  sous-tâches en [GUEST-SEARCH-GRAMMAR].

## 3. Tests (TDD — rouges d'abord)

**Back** `tests/test_memo_urls.py` : (1) POST valide → 201, `GET /api/memos` porte `urls` ; (2) `javascript:`,
`ftp:`, URL vide, > 2048 → 400 ; (3) doublon exact → 409 ; (4) 21ᵉ → 400 ; (5) corbeille → `urls` absentes
du payload, restauration → reviennent, purge → lignes supprimées ; (6) export v29 porte `urls` sans `og_*`,
`version == 29` ; ré-import = 0 doublon, label local conservé ; import d'un export v28 → OK, 0 URL ;
(7) invité lecteur voit `{url,label,og_title,og_domain}` et rien d'autre, POST invité non `can_edit` → 403,
`can_edit` → 201, token d'un autre scope → 404 ; (8) `_fetch_og` mocké : `og_title/og_domain` remplis,
échec réseau → vides et 201 quand même.
**Front** `tests/front/test_memo_urls.py` (owner + share + hub, desktop + 412 px) : (9) éditeur : ajouter
une URL + libellé → chip en pied de card avec le libellé, `↗` ouvre un nouvel onglet (`context.expect_page`) ;
(10) texte contenant `https://exemple.test/suivi?x=1` → chip « dans le texte » sur la card **sans** rien en
base ; « Épingler » → passe en attachée (GET urls = 1) ; (11) `×` retire ; (12) recherche « suivi »
trouve le mémo par le label ; (13) share `can_edit` ajoute, lecteur ne voit pas le bloc d'ajout ;
(14) zéro erreur console.
**Mutations** : `_clean_url` acceptant `javascript:` → 2 ; `UNIQUE` retiré → 3/6 ; `og_*` exporté → 6 ;
`_share_memo_dict` fuitant `created_by` → 7 ; `extractUrls` sans dédup → 10 ; purge sans cascade → 5.
Non-régression : `test_link_refs.py`, `test_attachments*.py`, `test_export_import*.py` verts ; le
**scénario d'import de TOUS les exports v1→v28 de `tests/fixtures`** reste vert.

## 4. Livraison
`make test` vert ; `REALISATION.md` `[V29.0.279] feat(mémos) : **[MEMO-URLS]…**` (bump v29 explicite) ;
`docs/EXPORT-FORMAT.md` + `CLAUDE.md` index ; IDEAS.md : retirer de la file, graine [MEMO-TYPES] → v30 ;
rebuild local complet ; **STOP avant push** : passe Cowork owner (desktop + mobile) et invité, puis GO Fabien.
