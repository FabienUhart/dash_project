# [PHOTO-ROTATE-DEBUG] Re-test sur localhost:8099 — synthèse

*9 août 2026 — mené par CC à la demande de Fabien. Ce document couvre **deux temps** : le
diagnostic instrumenté (sans toucher au code), puis le correctif qui en découle,
**[PHOTO-ROTATE-MEMCACHE] V27.40.248**, et sa vérification en live.*

---

## Verdict en trois lignes

1. **La sauvegarde n'a jamais échoué.** Tous les `POST /api/images/<name>/rotate` répondent
   **200**, et le fichier original est bien réécrit à chaque fois (dimensions échangées,
   `Orientation` remise à 1, dérivées `t_`/`s_` régénérées dans la même seconde).
2. **Le défaut est un problème d'AFFICHAGE, et il subsiste en 27.40.247.** À la réouverture de
   la galerie dans la même page, la visionneuse montre l'image d'avant — **2 fois sur 3** dans
   mes mesures.
3. **La cause est le cache MÉMOIRE du document**, pas le cache HTTP : à la réouverture,
   **aucune requête ne part**. Ni le réseau ni le service worker ne sont consultés, donc le
   `Cache-Control: no-cache` ajouté en 247 n'a **aucune prise**.

---

## Ce qui marche déjà en 27.40.247

| Point | Résultat |
|---|---|
| Bouton « Enregistrer » présent et **grisé** au repos | ✅ |
| Il **s'active** après ↻ | ✅ |
| **Aucun décalage** de la barre (7 boutons avant / 7 après) | ✅ |
| Il **retombe grisé** après sauvegarde | ✅ |
| Fichier pivoté sur le disque, en < 1 s | ✅ |
| **ETag change** après rotation, `Cache-Control: no-cache`, 304 si inchangé | ✅ |
| Visionneuse à jour **immédiatement après le clic** | ✅ |
| **Rechargement complet** de la page → vignette de la card correcte | ✅ |
| Aucune erreur JS pendant tout le parcours | ✅ |
| **Réouverture de la galerie sans recharger la page** | ❌ **2 échecs sur 3 cycles** |

## La cause, mesurée

À la fermeture puis réouverture, `render()` réassigne
`img.src = "/uploads/<nom>?size=s"` — **exactement l'URL déjà chargée** dans ce document.
Chromium sert alors la ressource depuis son cache mémoire **sans émettre de requête** :

```
CYCLE 1 — ❌ RÉOUVERTURE PÉRIMÉE
   disque (900, 500) -> (500, 900) | après save à l'écran (500, 900) | réouverture (900, 500)
   src à la réouverture : /uploads/afacf742…jpg?size=s
   ⚠ AUCUNE REQUÊTE ?size=s
```

C'est aussi pourquoi le correctif de 247 semblait sans effet : la revalidation ETag règle le
cache **HTTP** (elle fonctionne : le rechargement complet de page donne bien la bonne vignette),
mais elle ne peut rien contre une image que le document n'redemande jamais.

> **Ce que ça dit du correctif précédent** : en retirant le jeton `?v=` de la 245, j'ai supprimé
> la seule chose qui changeait l'URL — donc la seule qui défaisait le cache mémoire. Le tort de
> la 245 n'était pas le principe du jeton, c'était sa **granularité en secondes**.

## Correctif — APPLIQUÉ en V27.40.248 ✅

Jeton de version **par nom de fichier**, en millisecondes, posé à chaque sauvegarde réussie et
appliqué dans **`imgSize`** — l'entonnoir que traversent déjà la visionneuse, les vignettes de
cards, la bande et les grilles photo. Une seule mécanique, un seul endroit :

```js
const _imgVersions = Object.create(null);        // nom de fichier -> jeton ms
function bumpImgVersion(name) { _imgVersions[_imgBaseName(name)] = Date.now(); }
function imgSize(url, sz) {
  const u = url + (url.indexOf('?') < 0 ? '?' : '&') + 'size=' + sz;
  const v = _imgVersions[_imgBaseName(url)];
  return v ? u + '&v=' + v : u;
}
```

**Vérifié en live après correctif** (`09-verif-apres-correctif.txt`) : la *même* sonde qui
donnait 2 anomalies sur 3 cycles en donne **0 sur 6**. Le rechargement forcé ponctuel de la 247
a été retiré : un seul jeton, pas deux paramètres de fraîcheur.

La revalidation ETag de 247 **reste utile et se garde** : c'est elle qui assure la fraîcheur
entre deux chargements de page et pour la vignette des cards. Les deux sont complémentaires —
l'ETag pour le cache HTTP, le jeton pour le cache mémoire.

Le test de non-régression correspondant a été écrit : il ouvre, sauve, **ferme et rouvre sans
recharger**, en attendant le décodage (`img.complete && naturalWidth > 0`) avant de mesurer —
condition indispensable, un `<img>` gardant l'ancien bitmap jusque-là.

## Preuve que ta session a bien subi le défaut

Les logs du conteneur montrent, avant mes propres essais, quatre rotations depuis **Chrome 151**
(ton navigateur, pas mon Chromium headless) — dont **deux sur la même photo à trois secondes
d'intervalle** :

```
18:55:19  POST /api/images/c58e91f5….jpg/rotate  200
18:55:22  POST /api/images/c58e91f5….jpg/rotate  200   ← même photo, 3 s plus tard
18:55:30  POST /api/images/5bc86580….jpg/rotate  200
18:57:20  POST /api/images/c58e91f5….jpg/rotate  200
```

C'est le « il faut cliquer plusieurs fois » : l'écran ne bougeant pas, tu recliques — et chaque
clic **pivote réellement** le fichier. À noter : ces essais tournaient sur le conteneur en
**27.40.246**, avant mon rebuild en 247 (~21:30). Et **la prod est encore en 27.39.245**.

## Deux points annexes relevés

- **Service worker** : `networkFirstMedia` est strictement network-first (le cache n'est qu'un
  repli hors ligne) — il n'est **pas** en cause. Ses caches sont versionnés
  (`dash-media-27.40.247`) et purgés à l'activation. Attention toutefois : après un rebuild,
  l'**ancien** SW garde les onglets déjà ouverts jusqu'à leur fermeture.
- **Reverse-proxy hors de cause** : mêmes en-têtes de cache en prod et en local, Caddy n'ajoute
  que `via: 1.1 Caddy` et ne réécrit rien.
- **Bruit console** : de nombreux `404` sur la page d'accueil pendant les tests (ressources
  absentes). Sans rapport avec la rotation, mais à regarder un jour.

## Fichiers de ce dossier

| Fichier | Contenu |
|---|---|
| `00-etat-avant.txt` | État de la base et des fichiers **avant** le test |
| `01-version.txt` | Version servie par localhost + version du service worker |
| `02-logs-avant-test.txt` | Logs du conteneur juste avant |
| `03-parcours.txt` | Parcours complet A→H (première passe) |
| `04-reouverture.txt` | Zoom sur la réouverture, avec `from_service_worker` |
| `05-verdict-3-cycles.txt` | 3 cycles avec attente du décodage — 1 anomalie |
| `06-cause.txt` | **La cause**, avant correctif : aucune requête à la réouverture |
| `07-etat-apres-nettoyage.txt` | État **après** — identique au 00 |
| `08-logs-serveur.txt` | Tous les `POST /rotate` (dont ceux de ta session) |
| `09-verif-apres-correctif.txt` | La même sonde **après** correctif : 0 anomalie sur 6 cycles |

## Sûreté des données

Aucune de tes photos n'a été modifiée par moi : le test a créé **quatre mémos jetables** avec
des images synthétiques, tous **purgés définitivement** ensuite. L'état de la base est
**identique** avant et après (179 mémos, 15 `image_meta`, 0 corbeille, 24 fichiers, 23
dérivées) — voir `00` vs `07`.

Les rotations subies par les photos de **REVUs** proviennent de ta propre session de 20:55–20:57,
pas de ce test.

---

## Suite : correctif [PHOTO-ROTATE-MEMCACHE] (V27.40.248)

Appliqué le 9 août 2026 au soir, **front only** (le serveur était déjà correct, ce diagnostic
l'avait prouvé). Voir `09-verif-apres-correctif.txt` pour le rejeu de la sonde, et l'entrée
`[V27.40.248]` de `REALISATION.md` pour le détail.

Test de non-régression ajouté : `test_rotation_survives_reopening_without_a_page_reload`
(ouvre par une vraie porte, sauve, ferme, **rouvre sans recharger**, et vérifie la visionneuse
**et** la vignette de la card). Éprouvé par 2 mutations, toutes deux tuées.
