# REALISATION

Journal des réalisations livrées, versionnées en SemVer projet **`VX.Y.Z`**.

- **X** = version du **format d'export** (invariant 1 de `CLAUDE.md`). Ne bouge **que** lors d'un changement de format de données (compat des sauvegardes). Aujourd'hui : **19**.
- **Y** = **mineure** : incrémentée à chaque nouvelle fonctionnalité ou lot cohérent, même si le format d'export ne change pas.
- **Z** = **build / identifiant de réalisation** : **compteur continu global**, incrémenté à chaque entrée ci-dessous et **jamais remis à 0** (un Z = une réalisation unique et traçable).

Règle : toute réalisation est consignée ici avec son tag `[VX.Y.Z]` au moment de sa complétion/livraison. La planification (cible `V19.1`, etc.) vit dans `IDEAS.md`. Voir `CLAUDE.md` § Versionnage.

---

## V19 — format d'export v19

- [V19.2.5] refactor(memo) : **réorganisation du détail déplié du mémo** [EXPAND-DETAIL-REORG] — fin de la rangée unique qui débordait. En-tête (fil d'Ariane « 📁 Projet › Sous-projet » + « 👤 Créé par … le … »), assignés pleine largeur, ligne principale **[📅 date] · [Aucune/P1/P2/P3] · [🎨 Style / Options ▾]** (le repli `card-menu` regroupe emoji, couleur du point, récurrence, projet), ligne d'actions [📎 Image][🔗 Partager][📜 Versions][📍 Ma position], puis adresse / sous-tâches / commentaires. Aucun contrôle retiré (mêmes `patchMemo()`), classes/tokens existants. Parité invité (`memo-tools` rangé en blocs, scope respecté). Frontend pur, export inchangé. `templates/index.html` + `templates/share.html`.
- [V19.2.4] feat(memo) : **refonte visuelle des cards de mémo** [CARD-REDESIGN] — extrait tronqué à 3 lignes (`.task-clamp`, `-webkit-line-clamp`), chip de priorité visible (`.prio-chip`, couleur de la priorité + `textOn()`), bordure gauche = priorité **sinon couleur du projet** (`usableProjColor`), assignés en **pastilles d'initiales** (`.asg-av`/`initials()`, ⚠ ambre conservé), miniature normalisée + overlay **« +N »** (repliée = 1 image), lift+ombre au survol, actions révélées au survol desktop, **Dupliquer** déplacé dans un menu **⋯** (`.task-more` + `card-menu`). Parité invité. Frontend pur, export inchangé. `templates/index.html` + `templates/share.html` + helper `initials()` dans `templates/partials/_shared.js.html`.
- [V19.1.3] feat(memo) : **en-tête contextuel de la pop-in mémo** [MEMO-CONTEXT] (fil d'Ariane « 📌 Projet : A › B › C », ligne « 🕒 Créé par @… le … »), commentaires en accordéon repliable, bouton **« 📜 Voir les versions »**. Colonne additive `memos.created_by` (`''` = propriétaire résolu par `_owner_name`, sinon invité « Nom <email> ») → format d'export **v19** (compat v1→v18, upsert non destructif ; `created_by_display` runtime-only, jamais exporté ; owner-only côté partage). Parité invité (fil d'Ariane + date de création en lecture). `app.py` + `templates/index.html` + `templates/share.html`.

## V18 — format d'export v18

- [V18.1.2] feat(memo) : le champ d'ajout rapide « + Nouveau mémo » crée le mémo avec le texte saisi comme **titre** (création « titre d'abord »), plus le placeholder mis à jour. [MEMO-CREATE-TITLE] — `templates/index.html`.
- [V18.1.1] fix(memo) : **alignement case/texte des listes à cocher** sur la card — passage des `li[data-list]` en flex, fin du hack `position:absolute` + marge négative, plus `overflow-wrap` pour les tokens collés. `templates/index.html` + `templates/share.html`.
