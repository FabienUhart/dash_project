# Brief CC — [MEMO-PDF] v2 : le PDF fabriqué par le Zimaboard, rangé dans le dossier, à jour tout seul

> **Back (WeasyPrint + cache + sweep) + front (bouton 📄, entrée dans Fichiers).** S'appuie sur
> [MEMO-PRINT] V30.4.286 : **même gabarit `templates/print.html`**, rien à redessiner. Export 30
> **inchangé** (le PDF est une donnée dérivée, comme `derived/`), **aucune migration**, **une dépendance
> nouvelle** (WeasyPrint + Noto Sans CJK dans l'image Docker). Cible **V30.5.287** ([TRIP-VIEW] glisse en
> V30.6.x — à renuméroter). Décision Fabien 30/10 : « va pour lancer la v2, avec icône de PDF, et le PDF
> généré automatiquement dans le dossier ou le mémo ». Doctrine TDD.
>
> **⚠ Calendrier** : Fabien part le 1er nov. Ce lot se déploie **seulement si** la passe Cowork est verte
> ET le test kanji en prod passe ; sinon il reste en local jusqu'au retour (~18/11). La v1 (Imprimer)
> reste en place quoi qu'il arrive : **le bouton Imprimer n'est pas retiré**, le 📄 s'ajoute à côté.

## 0. Ce que voit Fabien

- Sur le board d'un dossier et au pied de la fiche 👁 d'un mémo, un bouton **📄 PDF** (icône trait
  « document », gabarit `hdr-btn`, à côté de 🖨 Imprimer). Clic → le PDF **se télécharge** (A5,
  `Content-Disposition: attachment; filename="<nom>.pdf"`). Si le fichier est **à jour** c'est immédiat ;
  s'il est **périmé** ou absent, il est généré à la volée (quelques secondes) puis servi.
- Dans **Fichiers** du dossier (vue [FILES-VIEW]) et dans la liste des fichiers de la fiche mémo, une
  entrée **« 📄 PDF du dossier — généré le 30/10 14:02 · à jour »** (ou « périmé », en muted), avec
  ⤓ (télécharge, régénère si périmé) et ↻ (force). Pas d'upload possible, pas de ✕ : c'est dérivé.
- **« Automatiquement »** : le PDF existe sans qu'on le demande. Un **sweep** (thread daemon, comme
  `_og_sweep`/`_backfill_derived`) repasse toutes les **10 min** sur les dossiers et mémos dont le PDF est
  **périmé ou absent** et les régénère, un à la fois, avec une pause. Après une modification, le PDF
  est donc à jour dans les 10 min sans action ; et un clic sur 📄 n'attend jamais si le sweep est passé.

## 1. Moteur : WeasyPrint

- `requirements.txt` : `weasyprint==63.1` (ou la dernière stable compatible Python 3.12 — **épingler**).
- `Dockerfile` : avant `pip install`, `apt-get install -y --no-install-recommends libpango-1.0-0
  libpangoft2-1.0-0 libharfbuzz0b libffi8 fonts-noto-cjk fonts-dejavu-core && rm -rf /var/lib/apt/lists/*`
  — `fonts-noto-cjk` apporte **Noto Sans CJK** (kanji du dossier « Kanji utiles »). Mesure la taille de
  l'image avant/après et note-la (attendu : +~150 Mo ; si « fonts-noto-cjk » pèse trop, prendre
  `fonts-noto-cjk-extra` NON, et vérifier que la variante JP est bien dedans).
- Génération : `weasyprint.HTML(string=html, base_url=...).write_pdf()` sur le **même rendu Jinja** que
  `/print/…` (factoriser `_render_print_html(kind, id)` utilisé par les deux routes). Le CSS de
  `print.html` reste la référence ; ajouter dans son `font-family` `"Noto Sans CJK JP", "Noto Sans",
  "DejaVu Sans"` **avant** le repli système, pour que WeasyPrint trouve la police.
- **Import paresseux** (`import weasyprint` dans la fonction) : si le module ou ses libs manquent
  (dev sans Pango), la route 📄 répond **503 « PDF indisponible sur cette installation »** et l'UI
  masque le bouton (drapeau `pdf_enabled` dans `/api/version` ou le payload initial) — **la v1
  Imprimer continue de marcher**. Un test vérifie ce repli (monkeypatch de l'import).
- Garde-fou mémoire : un seul rendu WeasyPrint à la fois (verrou de processus `threading.Lock` +
  **claim multi-worker** comme [LINK-OG] 258 : 2 workers gunicorn ne doivent pas générer le même
  fichier en même temps — réserver via une ligne `pdf_jobs` ou un fichier `.lock` avec TTL 120 s).

## 2. Cache : où, quand, quoi

- Fichiers : `data/uploads/pdf/project-<uid>.pdf` et `data/uploads/pdf/memo-<uid>.pdf` (un seul fichier
  par cible, **écrasé** ; écriture atomique temp + `os.replace`). Dossier **jamais exporté, jamais commité**
  (`data/` est déjà gitignoré). Purge à la suppression du dossier / purge définitive du mémo.
- **Empreinte** (`_pdf_fingerprint(kind, id)`) = sha256 de : liste triée des ids du sous-arbre (mémo seul :
  son id) + `max(updated_at)` des mémos + nombre de mémos + structure des sous-dossiers (ids, parents,
  noms, positions) + nom/emoji du dossier + **`PRINT_TEMPLATE_VERSION`** (constante à incrémenter quand
  `print.html` change → tout se régénère). Les sous-tâches, urls, assignés sont dans `updated_at` du mémo
  (vérifier que `PUT` sur sous-tâches/urls touche bien `updated_at` ; sinon l'inclure dans l'empreinte).
- Table additive **`pdf_cache (kind TEXT, target_id INTEGER, fingerprint TEXT, generated_at TEXT,
  size INTEGER, PRIMARY KEY(kind, target_id))`**, `CREATE TABLE IF NOT EXISTS`. `à jour` =
  `fingerprint == _pdf_fingerprint()` ET fichier présent. Jamais exportée.
- `GET /api/projects/<id>/pdf` et `GET /api/memos/<id>/pdf` (owner) : si à jour → fichier ; sinon
  générer (synchrone, verrou) puis fichier. `ETag` = fingerprint ; `Cache-Control: private, no-store`.
  `?force=1` régénère. `HEAD`/`GET /api/projects/<id>/pdf/status` → `{generated_at, fresh, size}` pour
  l'entrée Fichiers.
- **Sweep** `_pdf_sweep()` : toutes les 10 min (sommeil initial 60 s, comme `_backfill_og` : jamais
  pendant les tests), parcourt les dossiers **qui ont au moins un mémo** et les mémos **modifiés
  depuis 24 h** ; pour chacun, si périmé/absent → génère ; `pause=1 s` entre deux ; plafond **20
  générations par passage** ; claim multi-worker. Journalise en `info` le nombre généré.
  **Pas** de génération pour les mémos jamais ouverts/anciens : un mémo seul n'a son PDF
  automatique que s'il a été modifié dans les 24 h **ou** si on l'a demandé une fois (ligne dans
  `pdf_cache`). Les dossiers, eux, l'ont tous.

## 3. Invités : projection, pas le PDF de l'owner

- `GET /share/<token>/project/<id>/pdf` et `/share/<token>/memo/<id>/pdf` (sous `/share/*`, invariant 5) :
  **seulement** si la cible est dans le périmètre du jeton ; le HTML est rendu avec la **projection
  invitée** (`_share_memo_dict`, pas `_memo_dict` : pas de `created_by`, pas de liens hors scope, pas
  d'étiquettes de dossier) → fichiers **séparés** `pdf/share-<share_id>-project-<uid>.pdf`, empreinte
  qui inclut le `share_id` + le rôle. Pas de sweep pour les invités : génération à la demande seulement,
  même verrou. Bouton 📄 côté share/hub dans la barre d'actions (même gabarit). Test : l'invité ne reçoit
  **jamais** un PDF contenant un titre hors de son périmètre ni un champ owner-only.

## 4. Front

- Owner : bouton 📄 `icon: 'file-pdf'` (nouveau glyphe trait dans le sprite : document + coin plié),
  `label: 'PDF'`, `href` direct vers `/api/projects/<id>/pdf` (ouverture = téléchargement). Pendant une
  génération à la volée, le bouton passe en « … » (désactivé) jusqu'à la réponse — pas de spinner Luciole
  permanent. Masqué si `pdf_enabled` est faux.
- Fichiers ([FILES-VIEW]) : `_collect_files` (~l.5701) ajoute une **entrée virtuelle** de `kind:'pdf'` en
  **première position** (jamais dans `attachments`), avec `fresh`, `generated_at`, `size`, `url`.
  Rendu : ligne grisée si périmé, ↻ à droite.
- Fiche 👁 : bouton 📄 à côté de 🖨.

## 5. Tests (TDD — rouges avant)

Back `tests/back/test_pdf.py` (WeasyPrint **réel** dans la CI — l'image de test doit avoir Pango + Noto ;
si la CI ne l'a pas, installer dans `ci.yml` **et** `Makefile install`) :
1. `/api/projects/<id>/pdf` → 200, `application/pdf`, commence par `%PDF-`, `Content-Disposition`
   avec le nom du dossier ; **le texte extrait** (pypdf **n'est pas** autorisé → utiliser
   `pdfminer.six` en dev-dep, ou vérifier via WeasyPrint `Document.pages`) contient tous les titres du
   sous-arbre et **« 入口 »** (police CJK effectivement embarquée — c'est LE test qui conditionne le deploy).
2. Cache : 2e appel → même fichier (mtime inchangé), `fresh: true` ; modifier un mémo → `fresh: false`,
   appel → régénéré ; `?force=1` régénère même à jour.
3. Empreinte : ajouter/supprimer un mémo, renommer un sous-dossier, bumper `PRINT_TEMPLATE_VERSION` →
   périmé. Corbeille : mémo en corbeille → absent du PDF et empreinte changée.
4. Sweep : 2 dossiers périmés → un passage génère les 2, un 2e passage ne génère rien ; plafond 20
   respecté ; claim : deux appels concurrents ne produisent qu'une génération (comme le test 258).
5. Purge : supprimer le dossier → fichier et ligne `pdf_cache` partis.
6. Invité : PDF du dossier partagé = projection (pas de `created_by_display`, pas de titre hors scope) ;
   dossier hors périmètre → 404 ; fichiers owner/invité distincts.
7. Repli : WeasyPrint absent (monkeypatch import) → 503 + `pdf_enabled: false`, **`/print/…` toujours 200**.
8. Invariants : export inchangé (`pdf_cache` et `pdf/` absents), round-trip OK.
E2E owner : bouton 📄 → réponse `application/pdf` ; entrée « PDF du dossier » dans Fichiers avec son
état. Mutations : retirer l'empreinte du template (3 rougit) ; retirer le claim (4 rougit) ; servir le
PDF owner à l'invité (6 rougit) ; `import weasyprint` au niveau module (7 rougit).

## 6. Deploy — règle spéciale avant le départ

Après le GO et le tag : contrôle Cowork **en prod** via `192.168.1.39:8099` (VPN) — `/api/projects/3/pdf`
→ `%PDF-`, taille cohérente (~1–3 Mo), **kanji visibles** (Cowork ouvre le PDF). Si un seul point rouge :
**pas de deuxième tentative avant le 1er nov.** ; on laisse la prod avec le lot (la v1 Imprimer couvre),
et on corrige au retour. Fabien part avec le PDF v1 (Opera/Mac) de toute façon.

## 7. Livraison

`app.py`, `templates/print.html` (font-family), `templates/index.html`, `share.html`, `hub.html`,
`_shared.js.html` (glyphe), `Dockerfile`, `requirements.txt` (+ `requirements-dev.txt` pdfminer.six),
`.github/workflows/ci.yml` (deps Pango/Noto), `Makefile`, tests, `REALISATION.md` `[V30.5.287]`,
`IDEAS.md` (graine MEMO-PDF → v2 faite ; TRIP-VIEW → V30.6.x), `README` (nouvelles routes + `pdf/`).
Cycle habituel : tests rouges → code → rebuild LOCAL (**mesurer la taille de l'image**) → `make test` →
journal + handoff → **STOP**. Passe Cowork (owner, invité, Fichiers) puis GO.
