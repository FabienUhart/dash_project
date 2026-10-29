# Brief CC — [MEMO-PRINT] : la vue imprimable d'un dossier (et d'un mémo) — v1 de [MEMO-PDF]

> **Back léger (2 routes de LECTURE owner + 1 gabarit Jinja) + 1 bouton front.** Zéro migration,
> **export 30 inchangé**, aucune route `/share/*` (invariant 5), aucune dépendance nouvelle (pas de
> WeasyPrint : c'est le navigateur qui fait le PDF — v2 serveur + cache à part, graine [MEMO-PDF]).
> Cible **V30.4.286**. Contexte : Fabien part au Japon le 1er nov., 12 h d'avion sans réseau ;
> Cowork lui a généré à la main un PDF du dossier Voyage Japon (79 mémos) le 29/10 — ce lot rend ce
> geste **répétable depuis l'app**. Doctrine TDD. **Gabarit de référence** (structure, ordre, CSS) :
> `docs/maquettes/maquette-print-folder.html` + le générateur `docs/maquettes/print-folder-generator.py`
> (Python, lit le JSON de l'API ; à transposer en Jinja, ne pas l'exécuter en prod).

## 0. Ce que voit Fabien

Sur le board d'un dossier, un bouton **🖨 Imprimer / PDF** dans la barre d'actions (gabarit `hdr-btn`,
icône trait, Luciole). Clic → **nouvel onglet** `/print/project/<id>` : une page autonome, sans JS, lisible
telle quelle et propre à l'impression (Pixel : Partager/Imprimer → Enregistrer en PDF ; Mac : ⌘P).
Même bouton dans la fiche d'un mémo → `/print/memo/<id>`.

## 1. Routes (owner, derrière Authelia — AUCUNE sous `/share/*`)

- `GET /print/project/<int:id>` → 200 HTML ; 404 si dossier inconnu. Sous-arbre via `_project_descendants`
  (~l.3812) ; mémos hors corbeille (`deleted_at` vide) uniquement.
- `GET /print/memo/<int:id>` → 200 HTML ; 404 si inconnu ou en corbeille.
- `Cache-Control: no-store`. Pas de JS dans la page. Rendu Jinja `templates/print.html` (un seul gabarit,
  deux modes). Les données passent par `_memo_dict` (même sérialisation que l'API : `content`,
  `subtasks`, `urls`, `assignees`, `location`, `due_*`, `images`, `attachments`, `link_refs`).

## 2. Le gabarit `templates/print.html` (= la maquette, en Jinja)

1. **En-tête** : emoji + nom du dossier, ligne grise « Mémos du dashboard — export du <date> — N mémos,
   M dossiers ». Mode mémo : titre du mémo seul.
2. **Sommaire** (dossier) : « 1 · Jour par jour » puis une entrée par dossier du sous-arbre **qui a des
   mémos**, dans l'ordre de l'arbre (parent avant enfants, `position`), avec le compte.
3. **Section « Jour par jour »** : tous les mémos **datés** du sous-arbre, triés `due_date` puis
   `due_time` ; un intertitre par jour (« mar. 3 nov. », jour en français) ; chaque mémo porte en méta
   📅 (plage « 3 nov. → 6 nov. » si `due_end`, heure si `due_time`), 📁 dossier, 📍 `location.label`,
   👤 assignés, P<prio>.
4. **Une section par dossier** (saut de page avant chaque) : chemin complet en méta (« Voyage Japon ›
   Activités Kyoto »), mémos triés date d'abord puis `position` ; mêmes blocs sans le 📁.
5. **Bloc mémo** : `<h3>` emoji + titre (ou « (sans titre) »), méta, **contenu HTML tel quel**
   (`|safe` — c'est le HTML Quill déjà assaini à l'écriture ; **retirer les `<img>`**), sous-tâches
   « ☐ / ☑ », liens attachés (`urls` : titre + URL en petit), puis « 📎 n fichier(s) sur le dashboard
   (non inclus) » si images/PJ.
6. **CSS** (recopier celui de la maquette) : `@page { size: A5; margin: 12mm 11mm }`, police système
   + `"Noto Sans CJK JP"` en repli (kanji du dossier « Kanji utiles »), `.memo { page-break-inside:
   avoid }`, `h2 { page-break-before: always }` sauf le sommaire, tableaux Quill bordés, `pre` en
   `pre-wrap`. **Aucune** couleur d'accent : du noir, du gris, c'est du papier.

## 3. Front (owner)

- `templates/index.html`, barre d'actions du board ([HEADER-TOOLBAR] ~l.9848, gabarit `tb.add({icon,
  label})`) : bouton `icon: 'printer'`, `label: 'Imprimer'`, `window.open('/print/project/' + id,
  '_blank', 'noopener')`. Icône trait `#ic-printer` à ajouter au sprite si absente (monochrome).
- Fiche mémo (👁) : même bouton → `/print/memo/<id>`.
- **Pas** côté share/hub en V1.

## 4. Tests (TDD — rouges avant)

Back `tests/back/test_print.py` : (1) `/print/project/<id>` 200 et contient **tous** les titres du
sous-arbre et **aucun** titre d'un autre dossier ; (2) un mémo en corbeille absent ; (3) ordre : les
intertitres de jour sont croissants et un mémo à plage apparaît sous son **premier** jour ; (4) kanji
« 入口 » et « Déménagement » intacts (`charset=utf-8`) ; (5) `<img` absent, mention « 📎 » présente pour
un mémo avec image ; (6) `/print/memo/<id>` 200, 404 en corbeille ; (7) **aucune route `/share/**/print`**
et `/print/*` sans session en prod = 302 Authelia (contrôle externe au deploy, pas un test pytest) ;
(8) `<script` absent de la page. E2E : bouton 🖨 sur un board → nouvel onglet dont le `<title>` = nom
du dossier ; page sans erreur console. Mutations : retirer le filtre corbeille (2 rougit) ; trier par
id au lieu de la date (3 rougit) ; laisser les `<img>` (5 rougit).

## 5. Livraison

`app.py` (2 routes + helper de sous-arbre), `templates/print.html`, `templates/index.html` (bouton),
tests, `REALISATION.md` `[V30.4.286]`, `IDEAS.md` (graine [MEMO-PDF] : v1 faite, reste v2 + cache),
`docs/HISTORIQUE.md` si tu y journalises. Cycle : tests rouges → code → rebuild LOCAL → `make test` →
journal + handoff → **STOP**. Passe Cowork (desktop + Pixel 412 : la page imprimable + « Enregistrer en
PDF »), puis GO. **Deploy souhaité avant le 31/10 au soir** ; si ça ne tient pas, on ne force pas — le PDF
du 29/10 existe déjà.
