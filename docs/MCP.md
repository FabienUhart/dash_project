# Brancher Claude sur le dashboard — serveur MCP ([DASH-MCP], V30.1.283)

Le dashboard expose un **serveur MCP distant** (`/mcp/`), façade de son API v1 : Claude lit et écrit
dossiers et mémos **sans passer par Chrome**. Vingt-deux outils (`get_context`, `get_counts`, `get_notifications`, `list_memos`,
`create_memo`, `append_to_memo`, `complete_memo`, `delete_memo` = corbeille…), tous décrits en français ;
aucune suppression définitive, aucun accès aux partages, invités ou jetons. Chaque appel passe par
`/api/v1` avec **ton jeton**, donc par l'audit et les quotas de l'API (invariant 10).

**1. Un jeton dédié.** Paramètres › 🔌 Appareils connectés › Créer : nom « Claude chat », source *Claude
(chat)*, droits *lecture + écriture* (ou *lecture seule* pour un connecteur de consultation). Le jeton
`dash_…` n'est montré **qu'une fois** : copie-le. Un jeton par client (chat, Claude Code, mobile) : on révoque
l'un sans toucher aux autres.

**2. Dans claude.ai (connecteur personnalisé).** Paramètres › Connecteurs › *Ajouter un connecteur
personnalisé* → URL **`https://dash.fabnode.dev/mcp/<jeton>/`** (le jeton est dans le chemin : le connecteur
ne sait pas envoyer d'en-tête), pas d'OAuth. Puis, dans une conversation, active le connecteur « dash » et
demande par exemple « qu'est-ce que j'ai sur l'iPad ? » (Claude appelle `get_context("ipad")`), « qu'est-ce qu'on
m'a écrit ? » (`get_notifications("me")`) ou « ajoute une sous-tâche “appeler Apple” au mémo 403 ». **Dans Claude Code** :
`claude mcp add --transport http dash https://dash.fabnode.dev/mcp/ --header "Authorization: Bearer dash_…"`
(là, le jeton voyage en en-tête, pas dans l'URL). En local : `http://localhost:8100/mcp/<jeton>/`.

**3. Révoquer, surveiller.** Paramètres › Appareils connectés : la ligne du jeton montre la source, les
droits, le dernier usage et le **client vu** (`mcp 1.0.0`) ; *Révoquer* (deux clics) coupe l'accès
immédiatement — le connecteur répond alors « jeton invalide ou révoqué ». Le journal d'audit (50 derniers
appels, filtrable par jeton) montre chaque lecture et écriture, jamais le contenu. Hors périmètre pour
l'instant : fichiers et images (lot A2), ressources `memo://`, templates.
