# BROUILLON — [VOTE-MATCH] Sondage live d'événement (V3, à scoper)

**Statut : BACKLOG — À SCOPER. NON verrouillé, aucune décision figée.**
Position : **après** [VOTE-DECISION] V1 (mode `single`) et **coordination avec**
[VOTE V2] (multi-intérêts). C'est un **3e axe** du chantier vote, distinct : vote
**public, live, éphémère** — pas la même population ni le même cycle de vie que V1/V2.
Ce fichier fige le **cadrage à discuter**, pas des choix.

---

## 1. Concept

**Sondage live d'un événement** (match de foot, émission TV, remise de prix…),
**généralisable hors foot**. Un **dossier dédié par événement**. Pendant l'événement,
l'owner pousse un **flux de micro-votes en direct** ; le public vote « à chaud ».

- **Inscription par e-mail** → **identité = e-mail** (auto-inscription publique, pas
  forcément l'approbation owner du modèle invité actuel).
- **Une voix par e-mail**, **vote IMMUABLE** : une fois soumis, **pas de
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
| Population | invités **approuvés par l'owner** | **auto-inscription publique par e-mail** |
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
- **Participant** = e-mail vérifié (double opt-in ?), rattaché à la **cohorte** de
  l'événement (tag). Voix = `(e-mail, option, micro_vote_id)`, **INSERT once, jamais
  d'UPDATE** (immuabilité en base : pas de retarget, contrainte d'unicité
  `(micro_vote_id, e-mail)`).
- **Cohorte éphémère** : tag d'événement + **rétention bornée** → job de purge
  (voix + e-mails + confirmations) à l'expiration.
- **Droit d'inviter délégué** : un flag/rôle « peut inviter » distinct de
  l'owner et du `can_edit` (nouveau niveau, à cadrer sous invariant 5).

## 5. À SCOPER (questions ouvertes — bloquantes avant toute spec)

1. **RGPD / rétention des e-mails** : base légale (consentement à l'inscription),
   **durée de rétention** explicite, **purge** (à l'expiration de la cohorte + sur
   demande de retrait), pas de conservation au-delà de l'événement. Où sont stockés
   les e-mails, chiffrement au repos ? Mention légale à l'inscription.
2. **Anti-abus** : **e-mails jetables** (blocage domaines temporaires ?),
   **double opt-in** (lien de confirmation avant que la voix compte),
   rate-limiting par IP/e-mail, un vote par e-mail réellement garanti malgré les
   alias (`+tag`, points Gmail…). Sans ça, « une voix par e-mail » est trivialement
   contournable.
3. **UI push live** : comment le votant reçoit un nouveau micro-vote « à chaud »
   (poll court ? SSE ? rechargement ?), charge sur le **Zimaboard** avec beaucoup de
   votants simultanés (le reste du produit est mono-utilisateur — c'est un pic de
   charge inédit). Dégradation propre si trop de monde.
4. **Contenu des e-mails** : gabarits (invitation, confirmation double opt-in,
   résultat par micro-vote / récap final), fréquence (un e-mail par micro-vote =
   spam ? digest ?), désinscription (lien opt-out obligatoire).
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
- **Coût RGPD** d'un stockage d'e-mails de tiers non-invités : peut être le vrai
  facteur limitant — à valider avant tout code.

## 7. Hors périmètre V3 (renvois)

- **V1** [VOTE-DECISION] : vote privé entre invités approuvés, voix modifiable
  (spec verrouillée).
- **V2** [VOTE] multi-intérêts (festival) : extension de V1 par échange d'index.
- **V1.1** : event agenda auto du gagnant.
- **[COMMENT-REACTIONS]** : réactions emoji (spec séparée).

## 8. Prochaine étape

Session de **scoping dédiée** sur les 7 questions du §5 (RGPD et anti-abus en
premier — ce sont les vrais bloquants). Ensuite seulement : décider si V3 se fait, et
rédiger une spec verrouillable. **Aucun build tant que le §5 n'est pas tranché.**
