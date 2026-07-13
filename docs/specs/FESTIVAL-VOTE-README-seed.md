# [FESTIVAL-VOTE] — Rejouer le seed (local puis prod)

Ordre exact des commandes/clics. **Idempotent** : rejouable sans doublon (mémos matchés par
`uid` déterministe). Aucun SQL direct, aucun SSH — tout passe par le flux d'import existant.

## 0. (Re)générer le fichier d'import (si le seed JSON a changé)

```bash
python3 scripts/seed_charrues.py
# → docs/specs/festival-vote-charrues-import-v23.json  (1 racine + 6 scènes + 83 passages)
```

## 1. Importer les données

- **UI (recommandé, local ET prod)** : Paramètres → onglet **Sauvegardes** → **Importer** →
  choisir `docs/specs/festival-vote-charrues-import-v23.json`. Ré-import = 0 doublon.
- **API** (local direct) :
  ```bash
  curl -s -X POST http://localhost:8099/api/import \
       -H 'Content-Type: application/json' \
       --data-binary @docs/specs/festival-vote-charrues-import-v23.json
  ```

Contrôle : le dossier **Vieilles Charrues 2026** apparaît avec 6 sous-dossiers scènes ;
la carte du dossier montre **exactement 6 pins** (les scènes) ; échantillons horaires :
KATY PERRY jeu 22:30→00:00 (Glenmor), INTERPOL sam 00:15→01:30 (Kerouac),
FEST NOZ sam 23:00→02:00 (Gwernig).

## 2. Créer le scrutin « Envies » (multi, sans deadline)

Le scope d'un vote nommé porté par la racine couvre déjà **tous les descendants** (les 83
passages) — vérifié. Créer via l'UI (bouton de gestion des scrutins du dossier racine) en
mode **plusieurs choix**, ou en API (local) — remplacer `<ROOT_ID>` par l'id du dossier racine
(visible dans `GET /api/projects`) et fournir tous les `memo_ids` du dossier :

```bash
ROOT_ID=<id du dossier racine>
IDS=$(curl -s http://localhost:8099/api/memos | python3 -c "import sys,json;\
print(json.dumps([m['id'] for m in json.load(sys.stdin) if m.get('content','').split(' · ')[0] in \
['Glenmor','Kerouac','Grall','Gwernig','Guinguette','Esplanade']]))")
curl -s -X POST http://localhost:8099/api/projects/$ROOT_ID/votes \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"Envies\",\"vote_mode\":\"multi\",\"memo_ids\":$IDS}"
```

## 3. Attacher les plans au dossier racine (pièces jointes de dossier)

Fichiers prêts dans `docs/specs/assets/` :
- `plan-festival-2026-1.png`, `plan-festival-2026-2.png` — plan illustré 2026 (fournis).
- `plan-acces-2026.png` — plan d'accès officiel (téléchargé au seed).

- **UI** : ouvrir le dossier racine → pièces jointes → déposer les 3 images.
- **API** (local) :
  ```bash
  for f in plan-festival-2026-1.png plan-festival-2026-2.png plan-acces-2026.png; do
    curl -s -X POST http://localhost:8099/api/projects/$ROOT_ID/attachments \
         -F "file=@docs/specs/assets/$f"
  done
  ```

Aperçu inline (image) côté owner ET invité.

## 4. Partager aux amis

Créer un partage du dossier racine avec **`can_edit:1`** (nécessaire pour l'inscription
invité ; le ❤️ et le vote ne requièrent PAS `can_edit`, mais l'inscription si). Envoyer
lien + PIN. Un invité approuvé peut poser ses coups de cœur ❤️ (contrôle anti-chevauchement
serveur) et voter ses envies ; l'écran **🏆 Résultats** est visible par tous.

## 5. Sonde bypass Authelia (prod, après déploiement)

```bash
# doivent atteindre l'app (403/404/405 applicatif), JAMAIS une redirection SSO Authelia :
curl -si https://<prod>/share/<token>/festival-results | head -1
curl -si -X POST https://<prod>/share/<token>/memo/1/heart | head -1
```
