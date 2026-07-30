# Style « Luciole » — boutons du dashboard

**Nom d'usage : dire « bouton Luciole » (ou juste « Luciole ») dans un brief suffit.**
Baptisé le 30 juillet 2026 après une journée d'itérations Fabien × Cowork (comparatifs
uiverse — glow button d'Aaron Iker, dock `little-mole-12` — et prototypes injectés dans
le vrai dashboard). Première implémentation : boutons « Détails » / « Ajouter » de la
barre d'ajout de la vue Mémos owner (`.mab-btn`, `templates/index.html`, V26.6.142 →
V26.7.146) ; cousin partiel : lueur suiveuse de la barre d'actions du board
(`[HDR-GLOW]`, `hdrAttachGlow` dans `_shared.js.html`, V26.7.144).

## Philosophie (le pourquoi des règles)

1. **Jamais d'aplat accent plein.** Ni au repos, ni au survol, ni pour un état. Le
   remplissage accent intégral est l'anti-pattern « inverted toggle » (UX Movement) —
   il aimante l'œil en permanence. La couleur pleine est réservée aux DONNÉES
   (pastilles de compteur, priorités), jamais au chrome.
2. **Le mouvement n'appartient qu'au geste.** Les micro-animations (lueur, lift)
   n'existent que pendant le survol/clic. Un ÉTAT persistant (déplié, sélectionné) est
   marqué par la MATIÈRE (bordure, fond, creux) et par le LIBELLÉ — jamais par une
   animation permanente. Zéro coût GPU au repos.
3. **L'état se dit avec des mots.** Un bouton bascule change de libellé
   (« Détails » ⇄ « Réduire » — pattern « More/Fewer options », guide Microsoft de
   divulgation progressive), avec un `min-width` qui évite tout saut de largeur.
4. **Clair et sombre ne sont pas des miroirs pixel.** Chacun est juste dans son monde :
   le sombre parle accent, le clair est monochrome au repos et ne prend l'accent
   qu'au survol (même doctrine que la barre d'actions du board).

## Anatomie (DOM)

```html
<button class="…">            <!-- position:relative ; overflow:hidden -->
  <span class="…-glow"></span> <!-- la luciole : point flouté, suit la souris -->
  <span class="…-btxt">Libellé</span> <!-- z-index:1, net au-dessus de la lueur -->
</button>
```

⚠️ Si le bouton porte des pastilles qui DÉBORDENT (compteur, vignette-menu, cf.
`.hdr-count`) : pas d'`overflow:hidden` sur le bouton — clipper la lueur dans un calque
interne (`.hdr-glowwrap`, `inset:0; overflow:hidden; border-radius:inherit`), gotcha V26.2.136.

## Les 4 états — valeurs de référence

### Repos
- **Sombre** : fond `var(--panel-2)` ; bordure 1 px `color-mix(in srgb, var(--accent) 45%, transparent)`
  (repli `rgba(79,195,247,.45)`) — fine, FIGÉE, aucune animation de contour ; texte `var(--accent)`.
- **Clair** : verre — fond `rgba(255,255,255,.75)` + `backdrop-filter: blur(8px)`
  (+ `-webkit-`) ; bordure `rgba(190,200,212,.8)` ; texte encre `#3b444d` ; ombre douce
  `0 2px 8px rgba(20,30,40,.07)`. Monochrome strict : zéro couleur au repos.

### Survol (la luciole s'allume)
- **Lift commun** : `transform: translateY(-2px)` + ombre portée (sombre
  `0 6px 14px rgba(0,0,0,.35)` ; clair `0 7px 16px rgba(20,30,40,.13)`),
  transition `.2s ease-in-out`.
- **Fond qui s'imprègne** : sombre `color-mix(in srgb, var(--accent) 14%, var(--panel-2))`
  (repli `#2c4557`) ; clair `rgba(79,195,247,.10)` (le verre vire bleu pâle).
- **La luciole** : point flouté qui SUIT la souris avec lissage (voir Mécanique).
  Sombre : 34 px, `blur(18px)`, opacité `.55`, teinte caméléon accent → accent+35 % blanc.
  Clair : 30 px, `blur(12px)` (flou SERRÉ — un bord visible pour voir le mouvement),
  opacité `.55`, teinte `#1e88e5` (bleu profond — le pastel se noie dans le blanc)
  → mélange 70 % vers l'accent selon x.
- Bordure réveillée : sombre `color-mix(accent 80%)` ; clair `#8a97a3`.

### Clic
- `transform: translateY(0) scale(.97)` ; `box-shadow: none`. L'impulsion, puis retour.

### État activé / déplié (persistant — IMMOBILE : `transform:none`, pas de lift au survol)
- **Sombre** : bordure `var(--accent)` pleine + fond dégradé statique
  `linear-gradient(180deg, var(--panel-2) 0%, color-mix(accent 18%, var(--panel-2)) 100%)`.
- **Clair** : pastille grise PLATE `#eef0f3` + bordure `#5f6b76` + texte `#1c2530`
  + creux `inset 0 1px 3px rgba(20,30,40,.08)`. (Pas de dégradé en clair : lecture
  « pressed » datée.)
- **Libellé basculé** (« Réduire »), `aria-expanded`, `min-width: 5.6em`.

## Mécanique JS (zéro lib — invariant 6)

- **Lissage** : la lueur vise la souris et la rattrape à `x += (tx - x) * 0.11` par
  frame (`requestAnimationFrame`). La boucle ne tourne QUE pendant le survol
  (`pointerenter` → `pointerleave`) : zéro coût au repos.
- **Caméléon** : interpolation hex maison (`mabMixHex`/`hdrMixHex`) entre une paire de
  teintes selon `x / largeur` ; couleur posée sur le spot à chaque `pointermove`.
- **Thème suivi** : la paire est choisie à CHAQUE `pointerenter` en lisant
  `data-theme` / `--accent` calculé → la bascule 🌙/☀️ en session est prise en compte.
- Implémentations de référence : `mabGlowButton` (index.html) et
  `hdrMixHex`/`hdrAttachGlow` (partial `_shared.js.html`).

## Gardes obligatoires

- `@media (prefers-reduced-motion: reduce)` : transitions coupées ET `:hover { transform:none }`.
- **Tactile** : pas de survol → luciole inerte, le `scale(.97)` au clic reste le feedback.
- **`color-mix`** : chaque déclaration doublée d'un repli `rgba`/hex sur la ligne
  précédente (déclaration inconnue ignorée = repli naturel, pas d'`@supports`).
- `backdrop-filter` : préfixe `-webkit-` systématique (clair uniquement).
- Libellé/icône au-dessus de la lueur (`position:relative; z-index:1`).

## Variantes (V26.7.147)

La classe de base est `.mab-btn` (nom hérité de la barre d'ajout, première implémentation).
Trois déclinaisons, appliquées à un bouton EXISTANT via `lucioleize(btn, variante)`
(idempotent : enveloppe le contenu dans `.mab-btxt`, injecte la lueur, retire `.primary`) :

- **Luciole action** (par défaut, sans variante) : bordure + texte accent —
  les boutons d'une barre de saisie (« Détails »/« Ajouter »).
- **`.luc-neutral` — secondaire** : repos discret (bordure `var(--border)`, texte
  `var(--muted)` ; clair : `#c9d2da`/`#5f6b76`), le survol Luciole de base fait le
  reste (fond imprégné, lift, lueur ; texte réveillé vers `var(--text)`).
  Usage : « Annuler », « 📜 Voir les versions », secondaires de pieds de pop-in.
- **`.luc-primary` — action principale** : la SEULE à porter de la couleur au repos —
  teinte accent LÉGÈRE (sombre `color-mix(accent 12%, panel-2)`, clair
  `rgba(79,195,247,.12)` + texte `#1565c0` + bordure accent), `font-weight:600`,
  survol = teinte approfondie (24 % / .22). **Remplace l'aplat plein `button.primary`**
  (dégradé accent intégral = exactement ce que Luciole interdit). Une seule
  `.luc-primary` par pop-in. Le gradient `button.primary` survit ailleurs dans l'app —
  à convertir au fil de l'eau, pop-in par pop-in, jamais en masse aveugle.

## Quand l'utiliser / quand s'abstenir

- **Oui** : boutons d'action texte des barres de saisie/formulaires, paires
  action + bascule (le duo « Ajouter »/« Détails » est le cas canonique), et
  **pieds des pop-ins d'ÉDITION** (éditeur de mémo : Versions/Annuler en
  `.luc-neutral`, Sauver en `.luc-primary` — V26.7.147).
- **Non** : cards mémo (`.task-actions` reste le gabarit des boutons ronds d'action),
  petites confirmations Oui/Non (`#confirm-dialog`/`#notify-dialog` — sobriété, et le
  danger reste `button.danger` rouge), et tout contexte où une animation au survol
  distrairait d'une lecture (listes denses). La barre d'actions du board garde son
  propre gabarit (`hdr-btn`) — elle n'a QUE la lueur suiveuse, pas le lift ni le verre.
- Toute nouvelle Luciole = mêmes tokens (`--accent`, `--panel-2`…), invariant 9 ;
  les hex en dur (gris du clair, `#1e88e5`, `#1565c0`) sont l'exception locale
  documentée ici.

## Historique

- V26.5.141 [ADD-BAR-POLISH] (CC) : sortie du `.primary` plein, gabarit card.
- V26.6.142 [ADD-BAR-GLOW] : bordure fine figée + luciole + Détails⇄Réduire (sombre).
- V26.6.143 : passe clair monochrome v1 (gris).
- V26.7.144 [HDR-GLOW] : lueur suiveuse sur la barre du board (partial, 3 pages).
- V26.7.145 : clair « synthèse » (verre + lift 2 thèmes, pastille plate).
- V26.7.146 : fond imprégné au survol (2 thèmes) + luciole bleu profond en clair ;
  baptême « Luciole » + ce document.
- V26.7.147 : helpers généralisés top-level (`attachLuciole`/`lucioleize`) + variantes
  `.luc-neutral`/`.luc-primary` ; premier pied de pop-in converti (éditeur de mémo).
