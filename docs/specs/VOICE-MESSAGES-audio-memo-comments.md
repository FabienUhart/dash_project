# [VOICE-MESSAGES] — Mémos vocaux + commentaires vocaux (façon WhatsApp, sans bump d'export)

**Brief pour Claude Code — rédigé le 23 juil. 2026 (Cowork). Idée + architecture de Fabien : le vocal est TOUJOURS une pièce jointe v22 (fichier importé) ; côté commentaire, seul un MARQUEUR texte le référence → aucun changement de format d'export.**

## Architecture (la subtilité qui évite le bump v24)

- L'audio enregistré est uploadé comme **pièce jointe de mémo v22 standard** (`attachments`, signature binaire, `preview`, export par noms de fichiers, purge en cascade existante). RIEN de nouveau en base.
- Un **commentaire vocal** = un commentaire dont le texte contient le marqueur **`[audio:<filename>]`** (filename = nom `uuid4().hex.ext` de la PJ). Le rendu détecte le marqueur → **bulle vocale** (lecteur) au lieu du texte. Le texte du commentaire est déjà exporté (v14), la PJ l'est déjà (v22) → **export v23 strictement inchangé**, ré-import = le marqueur se résout à nouveau.
- Marqueur pointant vers un fichier absent (import partiel) → bulle « 🎤 audio indisponible », jamais d'erreur.

## Spécification

### Enregistrement (helper partagé `_shared.js.html`, 3 pages)

- `initVoiceRecorder(cfg)` : bouton **🎤** → MediaRecorder (permission micro au geste), UI minimale : durée qui défile, **■ Stop**, **✕ Annuler**, ré-écoute avant envoi, **Envoyer**. Limite **5 min / ~15 Mo** (garde client ; serveur déjà borné par v22).
- Formats produits par les navigateurs : **webm/opus** (Chrome/Firefox), **mp4/m4a AAC** (Safari/iOS) — enregistrer avec le mimeType supporté (`MediaRecorder.isTypeSupported`), nom `vocal-<horodatage>.<ext>`.
- **HTTPS requis** par l'API (prod OK, localhost OK). Micro refusé/indisponible → message doux, pas d'erreur console.
- Dégradation : MediaRecorder absent → le bouton 🎤 n'apparaît pas (rien de cassé).

### Côté serveur (petite retouche, pas de route nouvelle)

- **Vérifier/étendre les signatures audio** du validateur `preview` v22 pour couvrir **webm (EBML), ogg/opus, mp4/m4a (ftyp)** → `preview=audio` = lecteur inline autorisé ; tout le reste inchangé (anti-XSS : jamais de rendu inline non validé).
- Upload par les routes v22 EXISTANTES : owner `/api/memos/<id>/attachments`, invité `/share/<token>/memo/<id>/attachments` (approuvé + `can_edit`, scope revalidé — invariant 5).

### Mémo vocal

- Bouton **🎤 Vocal** dans la section Fichiers/Photos de la pop-in mémo (owner + invité `can_edit`) → enregistre → PJ audio du mémo → visible comme les autres PJ, **lecteur `<audio controls preload=none>` inline** (bulle : durée + date).

### Commentaire vocal

- Bouton **🎤** à côté du champ « Commenter… » (owner + invité **approuvé `can_edit`**, comme poster un commentaire) → enregistre → upload PJ v22 sur le mémo → poste un commentaire `[audio:<filename>]` via la route commentaire EXISTANTE.
- Rendu du fil (3 pages) : marqueur → **bulle vocale** (lecteur + durée, auteur/date/réactions/réponses = mécanique commentaire inchangée). Un commentaire mixte (texte + marqueur) affiche les deux.
- **Suppression** : supprimer le commentaire ne supprime PAS la PJ (non destructif — elle reste listée dans Fichiers du mémo) ; la purge définitive du mémo emporte tout (cascade v22 existante). Choix assumé, documenter dans la spec du lot.
- La PJ vocale reste une PJ normale : listée dans les vues Fichiers ([FILES-VIEW]), téléchargeable.

## Contraintes

- **Export v23 inchangé** (aucun champ nouveau, aucun bump — c'est le cœur du design). Lot = **V23.9.Z** (après [WEB-CAPTURE] ; Z = dernier `REALISATION.md` + 1).
- Invariants : **5** (routes existantes, scope revalidé, droits identiques aux commentaires/PJ actuels), **6** (MediaRecorder natif, zéro lib), **8**, **9** (bulle aux tokens existants, boutons ronds `.task-actions`).
- `_data_version` : déjà couvert (attachments + commentaires).

## Tests avant fin

1. `python3 -m py_compile app.py` + upload d'un webm ET d'un m4a réels → `preview=audio`, lecture inline ; un `.html` renommé `.webm` → REJETÉ (signature).
2. Owner desktop (Chrome) : mémo vocal + commentaire vocal → bulles lisibles ; ré-écoute avant envoi ; annuler = aucun upload.
3. Invité `can_edit` (page share) : commentaire vocal posté, attribué, visible owner avec 🔔 ; invité lecture seule : PAS de bouton 🎤, bulles lisibles.
4. Export → ré-import sur base vierge : les vocaux réapparaissent (marqueur résolu) ; fichier manquant → bulle « indisponible ».
5. Mobile (le vrai test : iPhone Safari si possible) : permission micro, enregistrement m4a, lecture.
6. Suppression commentaire vocal → PJ toujours dans Fichiers ; purge mémo → tout part.

## Fin de réalisation (process CLAUDE.md)

Journaliser (`REALISATION.md` [V23.9.Z] + `IDEAS.md` [VOICE-MESSAGES] → Fait) → rebuild (hook → handoff) → **PAS de commit/tag/push sans feu vert explicite de Fabien**. Validation Cowork : parcours owner + invité, signatures, export/ré-import ; le test iPhone réel sera fait par Fabien.
