# [CARD-PREVIEW] — Aperçu du contenu sur les cards : extrait + pictos de signature

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Maquette variante B validée par Fabien. Complète [LESS-BUTTONS] : les cards compactes ne montrent plus que le titre, on leur redonne un aperçu passif du contenu.**

## Décision

Sous le titre de chaque card mémo : **un extrait du contenu (2 lignes max)** + **une rangée de pictos-compteurs** qui donne la « signature » du mémo. De l'information passive uniquement — zéro bouton d'action en plus (esprit [LESS-BUTTONS]).

## Spécification

### Extrait

- 2 lignes max (`-webkit-line-clamp: 2` + fallback), `stripHTML(content)`, style muted (`var(--muted)`), sous la ligne de titre.
- **⚠️ Cas sans titre** (interaction avec [MEMO-TITLE-FALLBACK] V23.3.93) : le « titre » affiché est déjà le début du contenu → l'extrait doit reprendre **après** la partie promue en titre ; si le contenu ne dépasse pas ce qui est déjà affiché, **pas d'extrait** (jamais la même phrase deux fois).
- Mémo à contenu vide (titre seul, valide depuis v14) : pas d'extrait, pas de ligne vide.

### Rangée de pictos (masquer chaque picto à zéro ; rangée absente si tout est à zéro)

- **☑ n/m** sous-tâches (cochées/total) — passif.
- **📷 n** images — clic = visionneuse du mémo (comportement existant des miniatures).
- **📎 n** fichiers — conserve le clic `attachQuickView` existant ([ATTACHMENTS-QUICKVIEW]).
- **💬 n** commentaires — conserve le clic existant (ouverture du fil).
- **Règle anti-doublon** : ces compteurs remplacent/absorbent les badges 📎 n et 💬 n actuels de la card — UNE seule rangée d'indicateurs, aucun compteur affiché deux fois. Les handlers de clic existants sont conservés tels quels, juste re-logés.
- Style : petits chips muted au gabarit `.badge` (tokens existants, invariant 9), sur leur propre ligne en mobile (pattern badges pleine largeur existant).

### Données

- Tout est déjà côté front (`state.memos` / `DATA.memos` : subtasks JSON, images, attachments, compteur commentaires) — **aucun appel réseau ni route en plus**.

### Périmètre

- **3 pages** (owner `index.html`, `share.html`, `hub.html`) — cohérent avec [LESS-BUTTONS]. Helper partagé dans `_shared.js.html` **seulement si** le corps est strictement identique entre pages (règle ADR-001), sinon dupliqué proprement.
- Vues Plan / Agenda / carte : **hors périmètre** (elles ont leurs propres formats compacts).

## Contraintes

- **Frontend pur, export inchangé (v23)**. Lot = **V23.6.Z** (Z = dernier `REALISATION.md` + 1).
- Invariants 5 (rien de nouveau exposé aux invités), 6, 8, 9. Les miniatures d'images profitent de `?size=t` ([IMAGE-THUMBS]) — ne rien charger de nouveau : les pictos sont du texte.
- Ne pas alourdir : la card reste scannable, l'extrait et les pictos sont discrets (muted), le titre reste l'élément dominant.

## Tests avant fin (3 pages, desktop + mobile)

1. Mémo avec titre + contenu long → titre gras, extrait 2 lignes, ellipsis.
2. Mémo **sans titre** → titre-fallback + extrait qui reprend après (ou absent) — jamais de duplication de phrase.
3. Mémo titre seul (contenu vide) → pas de ligne d'extrait.
4. Pictos : mémo avec 9/13 sous-tâches + 4 photos + 2 fichiers + 1 commentaire → les 4 chips ; mémo nu → aucune rangée ; clics 📷/📎/💬 = comportements existants.
5. Aucun compteur en double sur la card (anciens badges 📎/💬 absorbés).
6. Invité (share/hub) : idem, lecture seule intacte.
7. `python3 -m py_compile app.py` (sanité — aucun changement backend).

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.6.Z] + entrée `IDEAS.md`) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : les 7 tests ci-dessus, owner + invité.
