# SPEC — [MEMO-TABLES] Tableaux dans les mémos (éditeur Quill)

**Statut : VERROUILLÉE — décisions validées par Fabien (6 juil. 2026).**
Cible : **V20.5** (avant [COMMENT-REACTIONS] V21.0 — ce lot ne bump pas, l'autre oui).
**Frontend + vendoring uniquement — AUCUN changement de schéma, de route, ni du
format d'export** (le contenu HTML des mémos est déjà exporté tel quel dans
`content`, un tableau est du HTML comme un autre → reste **v20**).

---

## 1. Décisions figées

1. **Édition complète** : insérer un tableau, ajouter/supprimer lignes et colonnes,
   supprimer le tableau — pour l'owner ET les invités `can_edit` (approuvés).
2. **Module communautaire vendorisé** (Quill 2 n'a pas de module tableau complet
   natif) : cible = **`quill-table-better`** (compatible Quill 2). JS + CSS
   committés dans `static/` comme leaflet/gsap/markercluster — **aucun CDN,
   aucun build** (invariant 6).
3. **Dégradation propre** : si le fichier du module manque ou si
   l'enregistrement échoue → l'éditeur fonctionne comme aujourd'hui (pas de
   bouton tableau), et les tableaux déjà présents dans `content` restent rendus
   en HTML statique (lecture intacte).
4. **Pas de bump d'export**, pas de sanitisation nouvelle : même modèle de
   confiance que le contenu Quill existant (HTML stocké tel quel).

## 2. Vérification préalable OBLIGATOIRE (avant d'écrire une ligne)

- Identifier la version exacte du Quill vendorisé (`static/quill.min.js`) et
  vérifier la compatibilité du module (`quill-table-better` vise Quill ≥ 2).
- Vendoriser une version précise (noter la version dans l'en-tête du fichier
  comme pour markercluster 1.5.3), licence compatible (MIT attendu).
- **Si incompatibilité réelle découverte au POC** (conflit avec nos modules :
  mentions, `list: check`) → **STOP et remonter à Fabien** avec les options
  (autre module, fork minimal, report). Pas de bricolage silencieux.

## 3. Intégration

### Fichiers statiques
- `static/quill-table-better.js` + `static/quill-table-better.css` (noms selon
  la distribution du module).
- **Whitelist `SHARE_ASSETS`** (les invités chargent via `/share/assets/<nom>`,
  `/static/` étant derrière Authelia — invariant 5, même pattern que Quill/GSAP).

### Pages (les 3, parité complète)
- `index.html` : éditeur du détail mémo (owner).
- `share.html` : pop-in « Modifier le mémo » (invité `can_edit` approuvé).
- `hub.html` : éditeur inline [HUB-INLINE-EDIT] (mêmes assets, mêmes modules).
- Enregistrement conditionnel : `if (window.QuillTableBetter) Quill.register(...)`
  + module dans la config seulement si présent (décision 3). Lecture seule
  (Quill `enable(false)`) : le tableau s'affiche, aucune poignée d'édition.

### Barre d'outils
- Bouton « ⊞ » (insertion tableau) ajouté aux toolbars existantes des 3 pages ;
  opérations lignes/colonnes via le menu contextuel du module.
- Mobile : la barre Quill est déjà une ligne défilable — le bouton s'y ajoute ;
  vérifier que la règle tactile `min-height:44px` ne déforme pas les menus du
  module (même gotcha que [PHOTO-VIEWER-MOBILE] : dimensions explicites si besoin).

## 4. Rendu / CSS (tokens existants — invariant 9)

- Styles des tableaux **aux tokens** : bordures `var(--border)`, en-tête éventuel
  `var(--panel-2)`, texte courant — valides en thème sombre ET clair
  (`:root[data-theme="light"]`).
- **Card (extrait)** : `stripHTML` aplatit le tableau en texte — assumé, pas de
  rendu de tableau sur la card (le clamp 3 lignes [CARD-REDESIGN] fait le reste).
- **Mobile** : tableau plus large que la colonne → défilement horizontal
  (`overflow-x:auto` sur le conteneur du tableau dans `.ql-editor` et dans le
  rendu lecture), jamais d'écrasement des colonnes. Overrides placés en FIN de
  `<style>` (gotcha cascade).
- CSS du module aligné sur les tokens si ses couleurs par défaut jurent
  (surcharge locale, pas de fork du CSS vendorisé).

## 5. Sécurité / périmètre

- Aucune route nouvelle. Écritures invité = `PUT /share/<t>/memo` existant,
  revalidé serveur (scope + can_edit + approuvé) — le tableau n'est que du
  contenu (invariant 5).
- Uploads/images/commentaires : non concernés.

## 6. Tests

1. `python3 -m py_compile app.py` (app.py ne devrait pas bouger, sauf
   `SHARE_ASSETS`) ; rendu Jinja des 3 pages + `node --check` des blocs script.
2. Owner : insérer un tableau 3×3, taper du texte, ajouter/supprimer
   ligne/colonne, enregistrer → rouvrir : tableau intact ; card = extrait texte.
3. Invité `can_edit` (share ET hub) : mêmes opérations via sa pop-in ; invité
   lecture : tableau visible, non éditable.
4. **Non-régression** : mentions `@` et listes à cocher (`list: check`, clic sur
   la card owner + share) fonctionnent dans un mémo contenant un tableau.
5. **Dégradation** : renommer temporairement le fichier du module → éditeur OK
   sans bouton, mémo à tableau existant rendu en lecture.
6. Export → import sur copie de base : ré-import complet = 0 ajout, le `content`
   avec tableau passe verbatim (aucun changement de version).
7. Thème clair + mobile (barre défilante, scroll horizontal du tableau).

## 7. Hors périmètre (volontaire)

- Tri/formules/fusion de cellules, redimensionnement fin des colonnes au-delà de
  ce que le module offre nativement.
- Rendu tableau sur les cards, dans la vue Plan, l'agenda ou la carte.
- Sanitisation HTML serveur (chantier séparé si un jour multi-utilisateur réel).

## 8. Invariants touchés

- **6** : lib vendorisée `static/` + dégradation propre → à AJOUTER à la liste
  des dépendances autorisées dans `CLAUDE.md` (comme markercluster).
- **5** : whitelist `SHARE_ASSETS` limitée aux 2 fichiers du module.
- **9** : tokens existants, aucun langage visuel nouveau.
- Export : **inchangé (v20)** — le § Versionnage ne bouge pas.
