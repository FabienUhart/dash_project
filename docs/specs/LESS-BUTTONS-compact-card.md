# [LESS-BUTTONS] — Cards mémo allégées : barre compacte + menu, la pop-in devient le lieu d'édition

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Maquette variante A validée par Fabien, décisions figées le même jour.**

## Problème (idée d'origine de Fabien, IDEAS.md § Confort)

La card mémo dépliée aligne ~15 contrôles (date, P1-P4, emoji, pin couleur, sélecteur projet, Image, Partager, Versions, Ma position, adresse, sous-tâche, commentaire, récurrence…). « La profusion de boutons n'a de sens qu'à la création ; en consultation, ne montrer que l'essentiel. »

## Décisions figées

1. **Variante A** : en consultation, la card porte une **barre compacte** de boutons ronds + un menu **⋯** ; la **pop-in « Éditer le mémo » devient l'unique lieu d'édition riche** (elle contient déjà titre, contenu, assignés, position, 📷 Photos [MEMO-EDITOR-IMAGES], fichiers, commentaires, versions).
2. **Restent sur la card dépliée** : les sous-tâches cochables + champ « + sous-tâche », et le fil / champ « Commenter… » (gestes de consultation active).
3. **Périmètre : les 3 pages d'un coup** (owner `index.html` + `share.html` + `hub.html`) — une seule philosophie de card partout, une seule passe de validation.

## Spécification

### Card (repliée)

- Contenu : titre gras (ou fallback extrait [MEMO-TITLE-FALLBACK]) + extrait + badges existants (échéance, @assignés, projet, lieu, 💬 n, 📎 n, vignettes images, vote…). **Aucun changement des badges.**
- **Barre compacte** (gabarit `.task-actions`, boutons ronds) : **✓** (done), **✎** (ouvre la pop-in), **⋯** (menu). C'est tout.

### Card (dépliée)

- En plus : sous-tâches cochables + « + sous-tâche (Entrée) », fil de commentaires + champ « Commenter… » (avec mentions @, inchangés).
- **Partent dans la pop-in** (et disparaissent de la card) : champ date/heure inline, chips P1-P4, emoji, couleur de point 📍, sélecteur de projet, boutons Image / Ma position / adresse, Récurrence. ⚠️ Vérifier que CHAQUE contrôle retiré existe bien dans la pop-in de la page concernée **avant** de le retirer — s'il manque (notamment côté invité), **l'ajouter à la pop-in dans ce même lot** (date/priorité/récurrence côté share/hub le cas échéant).

### Menu ⋯ de la card

- Actions rares mais utiles hors édition : **Partager**, **Dupliquer**, **Supprimer** (style danger `var(--red)`). Réutiliser le pattern `card-menu` existant. (« Déplacer vers… » : seulement s'il est trivial ici, sinon il reste au backlog [MOVE-MENU].)

### Invités

- `can_edit` : même card compacte, mêmes règles (leur pop-in « Modifier le mémo » doit couvrir tout ce qu'on retire — auditer, compléter si besoin).
- Lecture seule / anonyme : card = lecture pure (badges + sous-tâches NON cochables), comportement actuel conservé, pas de barre d'action.

## Contraintes

- **Frontend pur, export inchangé (v23)** — `APP_VERSION` reste "23". Lot = **V23.5.Z** (après [IMAGE-THUMBS] V23.4.x ; Z = dernier `REALISATION.md` + 1).
- Invariants : **5** (rien de nouveau exposé aux invités, routes inchangées), **6** (zéro lib), **8** (pas de GSAP sur dialog, menu = `card-menu` natif), **9** (uniquement les classes/tokens existants — `.task-actions`, `.prio-btn`, `.badge`).
- Mobile : boutons ronds NON ovalisés (fix `min-height:0` + carré, cf. gotcha connu), zone de tap ≥ 36 px, overrides ≤ 900 px en fin de `<style>`.
- Ne PAS toucher : drag & drop des cards, recherche/filtres, tuiles, [BOARD-SUBHIDE], votes (le bouton Voter des dossiers-scrutin reste sur la card — c'est de la consultation).

## Tests avant fin (3 pages, desktop + mobile)

1. Consultation : cocher done, cocher une sous-tâche, ajouter une sous-tâche, commenter — sans ouvrir la pop-in.
2. Chaque contrôle retiré est accessible dans la pop-in de SA page (owner, share can_edit, hub) — liste de correspondance dans le message de fin.
3. Menu ⋯ : Partager / Dupliquer / Supprimer opérationnels ; Supprimer = corbeille + undoToast (comportements existants).
4. Invité lecture seule : aucune barre, rien de cliquable en écriture. Vote sur dossier-scrutin intact.
5. Mobile : barre compacte ronde, pas d'ovale, D&D intact.
6. `python3 -m py_compile app.py` (sanité — aucun changement backend attendu).

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.5.Z] + `IDEAS.md` [LESS-BUTTONS] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : parcours consultation + audit de correspondance card→pop-in, owner + invité, desktop + mobile.
