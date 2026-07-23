# [WEB-CAPTURE] — Capturer une page ou une sélection depuis le navigateur (bookmarklets)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Décisions Fabien : phase 1 en bookmarklets (zéro extension) ; l'extension navigateur (badge 🔔, mini-lanceur) = phase 2 [BROWSER-EXTENSION], non planifiée.**

## Objectif

Depuis n'importe quel onglet : un clic sur un favori « magique » envoie la page courante (ou le texte sélectionné) vers le dashboard, pré-rempli. Façon web clipper de Trilium/SiYuan, sans rien installer.

## Spécification

### Côté app (owner, `index.html` — c'est le seul vrai travail)

- Au chargement, lire les **query params de capture** puis les **nettoyer** de l'URL (`history.replaceState`) pour ne pas polluer reload/favoris :
  - `?capture=link&url=…&title=…` → ouvrir `openDialog()` pré-rempli : Nom = title, URL publique = url (l'utilisateur choisit catégorie/tags et enregistre — flux existant, la catégorie active pré-remplie s'applique comme d'habitude).
  - `?capture=memo&url=…&title=…&text=…` → créer l'éditeur de **nouveau mémo Inbox** pré-rempli : contenu = text (échappé — jamais injecté en HTML) + ligne source « 🔗 title — url » ; l'utilisateur valide (pas de création silencieuse).
- **Aucune route ni schéma nouveau** : tout passe par la page owner (derrière Authelia — si pas de session, Authelia fait son travail avant, comportement normal). Valeurs traitées comme TEXTE brut (attributs/valeurs de formulaire uniquement, aucune interpolation HTML — pas de XSS par titre de page piégé).
- Bornes : `title` ~200 car., `text` ~2000 car., `url` validée http(s) sinon champ vide.

### Côté navigateur : les 2 bookmarklets (générés par l'app)

- Paramètres → nouvel onglet **« 🔖 Capture »** (pattern [SETTINGS-TABS]) : deux liens **à glisser dans la barre de favoris**, générés avec l'origin courant :
  - **« ➕ Capturer la page »** : `javascript:location.href='<origin>/?capture=link&url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title)`
  - **« 📝 Note depuis la page »** : idem avec `capture=memo` + `&text='+encodeURIComponent(String(getSelection()).slice(0,2000))`
  - Sous chaque lien : une ligne d'explication + bouton 📋 copier le code (pour créer le favori à la main si le drag ne marche pas).
- Variante « nouvel onglet » : les bookmarklets ouvrent le dash dans l'onglet courant (simple, fiable). Pas de `window.open` (bloqueurs de popup).

## Contraintes

- **Frontend pur, export inchangé (v23)**. Lot = **V23.8.Z** (Z = dernier `REALISATION.md` + 1 — après [TAG-NAV] V23.7.x).
- Invariants 5 (rien de public nouveau — tout est derrière Authelia), 6, 8, 9. Pages invité non concernées.
- Le param `capture` inconnu/malformé = ignoré silencieusement (page normale).

## Tests avant fin

1. `python3 -m py_compile app.py` (sanité).
2. `/?capture=link&url=https://example.com&title=Exemple` → pop-in lien pré-remplie, URL nettoyée de la barre, enregistrement OK ; param absent après reload.
3. `/?capture=memo&…&text=Bonjour` → éditeur mémo Inbox pré-rempli avec texte + source ; validation manuelle requise.
4. Titre de page piégé (`<img onerror=…>`) → affiché comme texte brut, aucun script exécuté.
5. `?capture=zzz` ou params tronqués → page normale, zéro erreur console.
6. Onglet Capture des Paramètres : drag des 2 favoris vers la barre → test réel sur un site tiers.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.8.Z] + `IDEAS.md` [WEB-CAPTURE] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**.

## Phase 2 — [BROWSER-EXTENSION] (backlog, non planifié)

Extension Chrome MV3 chargée en mode développeur (desktop only) : badge d'activité 🔔 sur l'icône (poll `GET /api/activity` avec la session Authelia du navigateur), popup mini-lanceur (recherche instantanée des liens → ouverture clavier), et reprise des deux captures en un clic sans changer d'onglet. Nouveau sous-dossier `extension/` dans le repo. À cadrer quand l'usage des bookmarklets sera validé.
