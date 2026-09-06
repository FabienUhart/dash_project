# Audit des droits invités — la matrice expliquée

> **Lecture seule.** Rien n'a été modifié dans le code. Ce document décrit ce que le
> système **fait aujourd'hui** (relevé dans `app.py`), en français clair, pour que tu
> décides ensuite quelle politique tu veux. Les questions à trancher sont à la fin.

---

## 0. Les mots, en clair (à lire d'abord)

Avant la matrice, le vocabulaire — parce que le code raisonne avec ces mots et que tu
dois les avoir en main pour répondre aux questions.

**Rôle** = une étiquette posée sur un invité (ou sur un dossier partagé). Il y en a
quatre que tu peux donner en partageant, et deux « hauts » réservés :

- **lecteur** (*viewer*) : il voit, point.
- **commentateur** (*commenter*) : il voit, **commente**, **vote** dans les commentaires.
- **contributeur** (*contributor*) : commentateur **+ il peut créer** des mémos.
- **éditeur** (*editor*) : contributeur **+ il modifie** les mémos, **coche** les
  checklists, **crée des scrutins** de vote.
- **modérateur** (*moderator*) : réservé (existe dans le code, peu utilisé aujourd'hui).
- **admin** : le plus haut — il **gère** le dossier, **invite** du monde et **donne des
  rôles**.

**Capacité** = une **action précise** autorisée ou non. C'est le point clé de tout le
système : **le serveur ne regarde jamais le nom du rôle pour décider, il regarde la
capacité.** Le rôle n'est qu'un raccourci qui « allume » un paquet de capacités. Les
capacités sont : voir, commenter, voter, cocher, créer (un mémo), éditer, créer un
scrutin, **modérer**, et **administrer** (inviter + donner des rôles).

Correspondance rôle → capacités (ce que chaque étiquette allume) :

| Rôle | voir | commenter | voter | créer mémo | cocher | éditer | créer scrutin | **administrer** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| lecteur | ✅ | — | — | — | — | — | — | — |
| commentateur | ✅ | ✅ | ✅ | — | — | — | — | — |
| contributeur | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| éditeur | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **✅** |

**Surface** = *où* on est. Un même invité n'a pas les mêmes droits partout. Il y a
quatre endroits qui comptent :

- **Sa maison invité (🏠)** : son espace à lui.
- **Un dossier qu'il a créé lui-même** : sous-partie qu'il a fabriquée.
- **Ton contenu à toi qu'il consulte** : les dossiers/mémos que **tu** as partagés.
- **Le hub** : la page « Mes dossiers » par laquelle il navigue (c'est une vue, pas un
  lieu de droits différent — les mêmes règles s'y appliquent).

**Le principe qui surprend — « Créateur = Admin de naissance ».** Le code contient une
règle (fonction `_owns_guest_space_folder`) : **si un invité a créé un dossier lui-même,
il devient automatiquement admin de ce dossier** (et de tout ce qu'il y range), sans que
tu aies à le lui accorder. Idem dans sa maison invité. **C'est la source de ce que tu as
observé** : « il a les mêmes droits que moi dans son dossier ».

---

## 1. La matrice : qui peut quoi, et *où*

C'est le cœur. On lit une ligne = une action ; les colonnes = les quatre surfaces.

| Action de l'invité | Ta maison / ton contenu partagé | Un dossier **qu'il a créé** | Sa maison invité 🏠 |
|---|---|---|---|
| **Voir** | Selon le rôle que tu donnes (dès lecteur) | Oui | Oui |
| **Commenter / voter** | Si tu l'as mis commentateur ou + | Oui | Oui |
| **Créer un mémo** | Si contributeur ou + | Oui | Oui |
| **Éditer / cocher / créer un scrutin** | Si éditeur | Oui | Oui |
| **Créer un sous-dossier** | Si son rôle le permet (éditeur/contributeur selon config) | Oui | Oui |
| **Inviter d'autres personnes** | **Non** | **Oui (admin de naissance)** | **Oui** |
| **Donner/changer des rôles** | **Non** | **Oui, jusqu'à admin** | **Oui** |
| **Créer un nouveau lien de partage** | **Non** (réservé au propriétaire) | **Non** | **Non** |
| **Toucher TON contenu à toi** | Selon le rôle, jamais admin | **Non** (son admin ne déborde pas chez toi) | **Non** |
| **S'auto-promouvoir** | **Non** | **Non** | **Non** |
| **Retirer/rétrograder le propriétaire** | **Non** | **Non** | **Non** |

**En une phrase :** un invité est **admin — donc peut inviter et distribuer des rôles —
uniquement dans les dossiers qu'il a fabriqués lui-même et dans sa maison invité.** Sur
**ton** contenu, il reste borné entre lecteur et éditeur, **sans jamais** pouvoir inviter
ni donner de rôle.

---

## 2. Les garde-fous déjà en place (ce qui te protège aujourd'hui)

Même quand un invité est admin dans son coin, le code l'encadre. Vérifié dans la route de
délégation (`share_set_guest_role`) :

1. **Périmètre borné.** Son pouvoir d'admin ne vaut **que sur le sous-arbre qu'il a
   créé**. Il ne remonte pas vers tes dossiers.
2. **Cible restreinte.** Il ne peut donner un rôle qu'à une personne **déjà invitée sur
   le même lien** — pas à un inconnu venu d'ailleurs.
3. **Plafond à admin.** Il ne peut pas créer un rôle plus haut que le sien.
4. **Pas d'auto-promotion.** Il ne peut pas se donner un rôle à lui-même.
5. **Propriétaire intouchable.** Il ne peut ni te rétrograder ni te retirer.
6. **Tout est journalisé (🔔).** Chaque changement de rôle laisse une trace.
7. **Créer un lien de partage neuf reste à toi.** La route qui fabrique un lien
   (`create_share`) est réservée au propriétaire (`/api/…`). Un invité ne peut
   qu'**attribuer un rôle** à quelqu'un déjà présent — pas ouvrir une nouvelle porte
   d'entrée vers l'extérieur.

**Ce qui reste réellement « gros »**, et qui est le nœud que tu pointes : dans **son**
dossier, l'invité peut faire **entrer d'autres personnes** (parmi les invités du lien) et
**leur distribuer des rôles jusqu'à admin**, **sans te demander**. C'est voulu par la
règle « créateur = admin », mais c'est exactement la délégation que tu veux peut-être
resserrer.

---

## 3. Les questions à trancher (c'est ici que j'ai besoin de toi)

Je te les pose en clair, avec ce que chaque choix implique. Rien ne bouge dans le code
tant que tu n'as pas décidé.

**Q1 — La délégation par l'invité : on la garde, on l'encadre, ou on la coupe ?**
Aujourd'hui : un invité qui crée un dossier peut y inviter et distribuer des rôles seul.
- *Garder* : autonomie maximale, tu ne fais rien. Contrepartie : des gens peuvent entrer
  dans un sous-dossier sans ton feu vert.
- *Encadrer* : il peut proposer/inviter, mais tu valides (voir Q2).
- *Couper* : seul toi distribues les rôles et invites, partout. L'invité crée et gère du
  contenu mais n'ouvre plus la porte à personne.

**Q2 — « Propriétaire dans la boucle » : une nouvelle personne amenée par un invité doit-elle
attendre ton approbation ?**
Utile surtout si tu réponds « encadrer » à Q1. Ça veut dire : l'invité propose un accès,
la personne n'entre vraiment qu'après ton OK. Plus sûr, un peu plus de friction pour toi.

**Q3 — Faut-il plafonner un invité-admin *plus bas* que « admin » quand il donne des rôles ?**
Aujourd'hui il peut nommer quelqu'un jusqu'à admin (donc créer d'autres délégués comme
lui). On pourrait le limiter à « éditeur maximum » : il fait travailler des gens dans son
dossier, mais **il ne fabrique pas d'autres administrateurs**. La chaîne de délégation
s'arrête à lui.

---

*Prochaine étape : tu réponds Q1/Q2/Q3, je traduis ta décision en brief CC (avec tests),
et on l'applique. D'ici là, rien n'est modifié.*
