# SPEC — [BOARD-SUBHIDE] Masquer/afficher les mémos des sous-projets dans le board

**Statut : VERROUILLÉE — décisions validées par Fabien (6 juil. 2026).**
Cible : **V20.7** (après [MEMO-TABLES] V20.5 et le hotfix [DIALOG-STICKY-ACTIONS] V20.6, avant [COMMENT-REACTIONS] V21.0).
**Frontend pur, les 3 pages (index + share + hub) — zéro route nouvelle, zéro
changement de schéma, export inchangé** (reste v20).

Contexte : le board d'un projet parent agrège récursivement les mémos de ses
descendants (ex. « Voyage Japon » noyé par les 8 mémos de « Reservations Alex
Fab »). Besoin : pouvoir replier ces mémos pour la lecture, desktop et mobile.

---

## 1. Décisions figées

1. **Chips par sous-projet** (même pattern éprouvé que [MAP-SUBFILTER]), mais
   sémantique **masquer/afficher** : cliquer un chip masque les mémos de ce
   sous-projet dans le board ; re-cliquer les réaffiche. Tous visibles par défaut.
2. **Les 3 pages d'un coup** : board owner (`index.html`), board du partage
   (`share.html`), board du hub (`hub.html`).
3. **Affichage seul** : les tuiles de filtres (En cours / Planifiés / …), la
   recherche et la **carte** gardent le périmètre COMPLET. Le repli ne fait que
   masquer des cards à l'affichage — même philosophie que le focus de la carte.

## 2. La barre de chips

- **Emplacement** : au-dessus des sections du board (sous les tuiles de filtres
  et la barre « + Nouveau mémo »), rangée `flex-wrap` (défilable en mobile si
  besoin, pattern barre Quill).
- **Un chip par sous-projet descendant PRÉSENT** parmi les mémos affichables
  (récursif — provenance = `memos.project_id`, remontée comme la liste carte),
  **+ un chip « (ce projet) »** pour les mémos propres du projet courant.
- **Apparence** (invariant 9, tokens seuls) : chips `.prio-btn`/`.mfilter` avec
  pastille `provenanceColor(proj)` + emoji + nom + compteur de mémos ;
  état **masqué** = chip estompé (opacité réduite + nom barré ou préfixe « ✕ »),
  jamais de nouveau langage visuel.
- **Règle d'apparition** (identique à [MAP-SUBFILTER]) : seulement sur le board
  d'un **vrai projet** (pas Mémos global / Inbox), et seulement si **au moins un
  mémo provient d'un descendant**. Un projet plat n'affiche pas la barre.
- **Indicateur anti-confusion** : quand ≥1 chip est masqué, un badge discret en
  fin de barre « n mémos masqués · tout afficher » (clic = reset) — évite le
  « où sont passés mes mémos ? ».

## 3. Comportement

- Le masquage s'applique **après** les filtres existants (tuile active,
  recherche) — un mémo est rendu s'il passe les filtres ET si sa provenance
  n'est pas masquée. Les **en-têtes de section** (À VENIR (n)…) comptent les
  mémos affichés ; une section vidée par le repli est omise (comportement
  existant des sections vides).
- **Tuiles de filtres et compteurs sidebar : INCHANGÉS** (totaux réels).
- ⚠️ **La carte n'est PAS affectée** : `boardMapPoints()` réutilise le pipeline
  de filtrage du board ([V15]) — le masquage [BOARD-SUBHIDE] doit être appliqué
  **au rendu des cards uniquement**, jamais dans le pipeline partagé avec la
  carte (elle a déjà son propre filtre [MAP-SUBFILTER], clés distinctes).
- Vue Plan, Agenda, sidebar, D&D, édition : non concernés.
- Sous-projet supprimé/déplacé entre-temps : entrée de persistance orpheline
  ignorée silencieusement (comme `mapSubFilter`).

## 4. Persistance (localStorage, par projet — mêmes conventions que la carte)

- Owner : `boardSubHide:<projId>` (liste JSON d'ids de sous-projets masqués ;
  le projet courant lui-même = token dédié, comme `subToken` carte).
- Share : `shareBoardSubHide:<TOKEN>:<PFILTER>`.
- Hub : `hubBoardSubHide:<FOCUS>`.
- Clés **distinctes** de `mapSubFilter`/`mapFocus` (le repli board et le focus
  carte sont deux états indépendants).

## 5. Invités (invariant 5)

Pur affichage en aval de données déjà scopées (`DATA.memos`/union hub) — aucun
droit nouveau, aucune écriture, aucune route. Les invités lecture seule en
profitent aussi (c'est de la lecture).

## 6. Mutualisation (ADR-001)

Si owner/share/hub aboutissent à un rendu de barre identique, extraire un helper
**pur** dans `_shared.js.html` (ex. `subHideBar(cfg)` : liste des provenances +
état + callbacks — comme `runMapDialog`). Sinon, dupliquer proprement comme les
`renderSidebar` (au choix de l'implémentation, corps identiques vérifiés par
diff avant extraction).

## 7. Tests

1. Rendu Jinja 3 pages + `node --check` ; `py_compile` (app.py intouché).
2. Owner « Voyage Japon » : chips présents (« (ce projet) », « Reservations… »,
   « Réservation T… »), masquer un sous-projet → ses cards disparaissent,
   badge « n masqués », tuiles INCHANGÉES, re-clic → retour ; reload → persisté.
3. **Carte** : masquer un sous-projet dans le board puis ouvrir la carte → les
   points du sous-projet masqué sont TOUJOURS là (indépendance vérifiée).
4. Recherche + tuile filtre actives + repli → cumul correct.
5. Projet plat (aucun mémo de descendant) → pas de barre ; Mémos global/Inbox
   → pas de barre.
6. Share (invité lecture ET can_edit) + hub : mêmes comportements, persistance
   par token/dossier ; scope inchangé (aucun mémo hors partage n'apparaît ni ne
   disparaît côté serveur).
7. Mobile : chips lisibles (règle tactile 44px sans ovales — gotcha connu),
   rangée défilable/enroulée.
8. Sous-projet supprimé après persistance → pas d'erreur, entrée ignorée.

## 8. Hors périmètre (volontaire)

- Repli dans la vue Plan (elle a déjà ses chevrons par nœud) et l'Agenda.
- Regroupement du board par sous-projet (sections par provenance).
- Toute synchronisation avec le focus carte.

## 9. Invariants touchés

- **6** : aucune lib, rien de nouveau. **8** : aucun GSAP sur dialog (pas de
  dialog du tout). **9** : chips aux tokens existants. **5** : lecture pure en
  aval du scope. Export : **inchangé (v20)**.
