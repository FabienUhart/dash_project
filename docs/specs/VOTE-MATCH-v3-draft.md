# BROUILLON — [VOTE-MATCH] Sondage live d'événement (V3, à scoper)

**Statut : BACKLOG — À SCOPER. Toujours AUCUN build.** Les **décisions RGPD/identité**
sont désormais **figées** (Fabien, juil. 2026 — voir §4bis) ; les **bloquants restants
du §5** (anti-abus jeton anonyme, push live + charge, contenu e-mails, bornage délégué,
clôture/anonymisation post-purge) restent **ouverts** → pas de spec verrouillable.
Position : **après** [VOTE-DECISION] V1 (mode `single`) et **coordination avec**
[VOTE V2] (multi-intérêts). C'est un **3e axe** du chantier vote, distinct : vote
**public, live, éphémère** — pas la même population ni le même cycle de vie que V1/V2.

---

## 1. Concept

**Sondage live d'un événement** (match de foot, émission TV, remise de prix…),
**généralisable hors foot**. Un **dossier dédié par événement**. Pendant l'événement,
l'owner pousse un **flux de micro-votes en direct** ; le public vote « à chaud ».

- **Identité à deux profils** (e-mail **optionnel**, choix du votant — §4bis) :
  **A = e-mail** (double opt-in) ou **B = jeton d'appareil anonyme** (repli). Identité
  = **hash e-mail OU jeton** (jamais l'e-mail en clair persisté). Auto-inscription
  publique, pas l'approbation owner du modèle invité actuel.
- **Une voix par personne**, **vote IMMUABLE** : une fois soumis, **pas de
  changement** (⚠️ **diffère de V1** où la voix est modifiable jusqu'à la deadline).
- **Chaque micro-vote a un délai** (fenêtre courte). **E-mail de confirmation /
  résultat** au participant.
- **Compteur de votants visible**, **PAS de liste nominative** (⚠️ diffère de V1 qui
  affiche « qui a voté » — ici volume seul, contrainte vie privée).
- **Flux de micro-votes** : pré-match, mi-temps, + **ajouts « à chaud » par l'owner**
  (« tir au but », « va-t-il marquer ? ») créés en direct.
- **Partage viral** gaté par un **droit d'inviter délégué** (un « admin »/délégué
  peut faire entrer d'autres votants, pas juste l'owner).
- **Cohorte éphémère taguée** (ex. `#match_FrMc`) → **purge en masse** après
  l'événement.

## 2. Ce que ça réutilise (existant)

- **SMTP `.env`** déjà en place (invitations hub, `_send_hub_invite`,
  [HUB-EMAIL-INVITE]/[GUEST-RESEND-LINK]) → confirmations / résultats / invitations.
- **Tags + suppression en masse** (tags normalisés existants) → cohorte `#match_FrMc`
  et purge groupée.
- **Primitive `(personne, option)`** du modèle [VOTE-DECISION] (table `memo_votes`)
  — même brique de base, avec des règles différentes (immuable, identité e-mail).
- **Dossier-par-événement + mémos-options** : même structure que V1 (dossier au vote,
  mémos directs = options), déclinée par micro-vote.
- Routes publiques sous **`/share/*`** (invariant 5) pour la surface votant.

## 3. Écarts majeurs vs V1/V2 (pourquoi c'est un axe à part)

| Axe | V1 (`single`) | V3 (`match`) |
|---|---|---|
| Population | invités **approuvés par l'owner** | **auto-inscription publique** (e-mail double opt-in **ou** jeton anonyme) |
| Identité stockée | nom + e-mail en clair (invité) | **hash salé** (e-mail) **ou** jeton d'appareil — jamais l'e-mail en clair |
| Voix | **modifiable** jusqu'à deadline | **immuable** dès soumission |
| Granularité | 1 vote par dossier | **flux** de micro-votes horodatés |
| Visibilité votants | noms/avatars | **compteur seul**, jamais de noms |
| Invitation | owner | **délégable** (droit d'inviter) |
| Durée de vie | persistant | **éphémère** (cohorte taguée, purge masse) |

→ V3 n'est **pas** une simple option de V1 : nouvelle **identité e-mail auto-inscrite**
et nouveau **cycle live**. À concevoir comme extension, en réutilisant la primitive
mais avec son propre gating et sa propre rétention.

## 4. Modèle pressenti (à valider, PAS figé)

- **Micro-vote** = une « question » horodatée rattachée au dossier-événement, avec sa
  **fenêtre** (ouverture/fermeture courte) et ses **options** (mémos ou options
  légères inline — à trancher).
- **Participant** = **hash salé d'e-mail** (profil A, double opt-in) **ou jeton
  d'appareil** (profil B), rattaché à la **cohorte** de l'événement (tag). Voix =
  `(personne_hash, option, micro_vote_id)`, **INSERT once, jamais d'UPDATE**
  (immuabilité en base : pas de retarget, contrainte d'unicité
  `(micro_vote_id, personne_hash)`). **Jamais d'e-mail en clair en base** (§4bis).
- **Cohorte éphémère** : tag d'événement + **rétention bornée** → job de purge
  (voix + e-mails + confirmations) à l'expiration.
- **Droit d'inviter délégué** : un flag/rôle « peut inviter » distinct de
  l'owner et du `can_edit` (nouveau niveau, à cadrer sous invariant 5).

## 4bis. Décisions figées — identité & RGPD (Fabien, juil. 2026)

Ces choix sont **tranchés** et servent de contrainte à toute spec future. Ils ne
lèvent PAS tous les bloquants du §5 (voir §5 pour ce qui reste ouvert).

- **Identité à deux profils, e-mail optionnel** (choix du votant) :
  - **Profil A — e-mail + double opt-in** : à l'inscription, **mail de validation** ;
    la voix ne compte qu'après clic du lien de confirmation (adresse prouvée).
  - **Profil B — jeton d'appareil anonyme** : **repli** sans e-mail.
  - Primitive de voix inchangée : `(personne, option)`, où **`personne` = hash e-mail
    OU jeton**.
- **Stockage — e-mail JAMAIS persisté en clair** :
  - L'e-mail est manipulé **en clair uniquement le temps du flux d'inscription** (pour
    envoyer le mail de validation), puis **on ne conserve que le hash salé**.
  - **Sel PAR ÉVÉNEMENT** (un e-mail est peu entropique → sel global rendrait le hash
    attaquable par dictionnaire ; sel par cohorte cloisonne et casse la corrélation
    inter-événements).
  - **Conséquence actée** : **mail possible à l'inscription seulement**. **Pas de
    ré-e-mail ultérieur** (ex. résultats) — l'adresse est **irrécupérable** après
    hachage. Si un besoin de mail de résultat émerge, il devra être **envoyé pendant le
    flux d'inscription** (ex. « tu recevras le résultat » impossible tel quel) **ou
    remettre en cause ce choix** de stockage.
- **Transparence — note de confidentialité à l'inscription** (visible avant de voter) :
  - **finalité unique** = ce vote / cet événement ;
  - **« jamais revendu »** ;
  - **suppression après l'événement** (purge de cohorte) ;
  - **point de contact** pour demander la suppression.
- **Suppression sur demande** : la personne **fournit son e-mail** → **re-hash** (même
  sel d'événement) → **DELETE** de la ligne correspondante. (Simple et cohérent avec le
  stockage haché : pas besoin de conserver l'e-mail pour honorer un droit à l'effacement.)

**Ce que ces décisions RÉSOLVENT** (au §5) :
- **§5.1 RGPD / rétention / revente** : traité par **hash salé + purge de cohorte +
  effacement sur demande** (plus de stockage d'e-mails de tiers en clair).
- **§5.2 anti-abus — partie e-mail** : le **double opt-in** couvre l'exigence « adresse
  prouvée » (une voix ne compte qu'après confirmation).

## 5. À SCOPER (questions ouvertes — bloquantes avant toute spec)

> **MAJ juil. 2026** : §5.1 (RGPD) et la **partie e-mail** de §5.2 sont **tranchées**
> par les décisions du **§4bis**. Ce qui reste **ouvert** ci-dessous est signalé.

1. ✅ **TRANCHÉ (§4bis) — RGPD / rétention des e-mails** : consentement + note de
   confidentialité à l'inscription ; **jamais d'e-mail en clair persisté** (hash salé
   par événement) ; **purge de cohorte** à l'expiration ; **effacement sur demande**
   (re-hash → DELETE). Reste à préciser à la spec : durée de rétention chiffrée (jours)
   et déclencheur exact de la purge.
2. **Anti-abus** — **partie e-mail ✅ tranchée** (double opt-in, §4bis : la voix ne
   compte qu'après confirmation de l'adresse). **RESTE OUVERT** : (a) **anti-abus du
   profil B (jeton anonyme)** — un même humain sur **plusieurs appareils/navigateurs**
   génère plusieurs jetons = plusieurs voix ; borner (rate-limit IP, preuve de travail,
   plafond par événement… ?) sans casser l'anonymat ; (b) e-mails **jetables** / alias
   (`+tag`, points Gmail…) qui contournent le « une voix par e-mail » **malgré** le
   double opt-in ; (c) rate-limiting global inscription/vote.
3. **UI push live** : comment le votant reçoit un nouveau micro-vote « à chaud »
   (poll court ? SSE ? rechargement ?), charge sur le **Zimaboard** avec beaucoup de
   votants simultanés (le reste du produit est mono-utilisateur — c'est un pic de
   charge inédit). Dégradation propre si trop de monde.
4. **Contenu des e-mails** — **OUVERT**, mais **borné par §4bis** : l'adresse étant
   hachée après le flux, **le seul e-mail possible est celui envoyé pendant
   l'inscription** (validation double opt-in). **Pas de résultat/récap par e-mail
   ultérieur** (adresse irrécupérable) — sauf à envoyer un contenu **dans le mail de
   validation** ou à rouvrir le choix de stockage. À cadrer : gabarit du mail de
   validation (finalité, note de confidentialité, lien de confirmation, opt-out), et
   **où** vivent les résultats à défaut d'e-mail (page publique de l'événement ?).
5. **Droit d'inviter délégué** : modèle de rôle (qui peut promouvoir un délégué,
   révocation), **partage viral borné** (un lien d'invitation ne doit pas ouvrir un
   accès illimité au reste du dashboard — strict scope événement, invariant 5).
6. **Immat. des options / micro-votes** : options = mémos réutilisés, ou entités
   légères inline (« Oui / Non », « joueur A/B/C ») créées à la volée par l'owner ?
7. **Résultat & clôture** : chaque micro-vote se clôt à sa fenêtre ; agrégation
   finale de l'événement ; que garde-t-on après purge (résultats agrégés anonymisés
   vs tout supprimé) ?

## 6. Risques / tensions à trancher

- **Nouvelle surface publique auto-inscrite** = rupture avec le modèle actuel
  (« invités approuvés par l'owner »). Doit rester **strictement scopée** à
  l'événement sous `/share/*` (invariant 5), sans jamais exposer le reste du
  dashboard ni les autres données.
- **Charge live** sur un Zimaboard pensé mono-utilisateur : à mesurer/plafonner.
- **Coût RGPD** d'un stockage d'e-mails de tiers : ✅ **adressé** par le §4bis (aucun
  e-mail en clair persisté — hash salé par événement, purge, effacement sur demande).
  Le facteur limitant restant est l'**anti-abus du jeton anonyme** (§5.2) et la
  **charge live** (§5.3), pas la rétention.

## 7. Hors périmètre V3 (renvois)

- **V1** [VOTE-DECISION] : vote privé entre invités approuvés, voix modifiable
  (spec verrouillée).
- **V2** [VOTE] multi-intérêts (festival) : extension de V1 par échange d'index.
- **V1.1** : event agenda auto du gagnant.
- **[COMMENT-REACTIONS]** : réactions emoji (spec séparée).

## 8. Prochaine étape

§5.1 (RGPD) et la partie e-mail de §5.2 sont **tranchés** (§4bis). **Bloquants
restants** avant toute spec : **§5.2 anti-abus du jeton anonyme** (multi-appareils),
**§5.3 push live + charge Zimaboard**, **§5.4 contenu e-mail** (borné mais à cadrer),
**§5.5 bornage du droit d'inviter délégué**, **§5.7 résultat/clôture/anonymisation
post-purge**. Session de scoping dédiée sur ces points. **Aucun build tant qu'ils ne
sont pas tranchés.**
