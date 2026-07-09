# CI/CD — infra de déploiement (reference)

**Type :** reference · **Ajouté :** 9 juillet 2026 ([CI-CD], V20.6.40)
Décrit le montage CI/CD pour qu'une prochaine session ne le re-découvre pas. Source canonique du process : `README.md` § « Release (CI/CD) » ; détail du lot : `REALISATION.md` [V20.6.40].

## Runner GitHub Actions (self-hébergé)

- **Nom :** `zimaboard` · **Labels :** `self-hosted`, `Linux`, `X64`, `zimaboard`.
- **Service systemd :** `actions.runner.FabienUhart-dash_project.zimaboard.service` (loaded/active/running, redémarre au boot).
- **Utilisateur :** `casaos` (dans le groupe `docker`, pas root).
- **Dossier du runner :** `~/actions-runner` = `/mnt/StorageNaN/home_casaos/actions-runner` — **séparé** du dossier de déploiement.
- Machine : Zimaboard, `x86_64`, joignable en LAN `casaos@192.168.1.39` (SSH par clé OK ; **`sudo` demande un mot de passe** → les commandes `sudo`, ex. `svc.sh install/start`, doivent être lancées par Fabien en interactif, pas en SSH non-interactif).
- Ré-enregistrement si besoin : `cd ~/actions-runner && ./config.sh --url https://github.com/FabienUhart/dash_project --token <TOKEN_COURT> --name zimaboard --labels zimaboard --unattended --replace` (token généré côté GitHub → Settings → Actions → Runners, courte durée, consommé par `config.sh` — **ne jamais committer**).

## Dossier de déploiement (persistant)

`/mnt/StorageNaN/home_casaos/Documents/projects/dash_project` — clone git du repo, contient **`.env`** (secrets SMTP, jamais dans GitHub) + **`./data`** (SQLite + uploads). C'est ici que tourne `docker compose` (port 8099). `.env` et `./data` sont gitignorés → `git checkout -f <tag>` ne les touche pas.

## Workflows (`.github/workflows/`)

- **`ci.yml`** — déclencheurs : push `main` + toute PR. Runner **cloud `ubuntu-latest`**. Étapes : `py_compile app.py` ; validation syntaxe JS des templates (extraction Python des blocs `<script>` attr-less des 4 fichiers + neutralisation Jinja + `node --check`) ; `docker build -t dashboard:ci .`. **Pas de déploiement.**
- **`deploy.yml`** — déclencheur : push d'un tag `V*.*.*` / `v*.*.*`. `runs-on: [self-hosted, zimaboard]`, `concurrency: zimaboard-deploy` (file d'attente, pas d'annulation). **NE fait PAS `actions/checkout`** : il `cd $DEPLOY_DIR` (le dossier persistant, PAS le workspace du runner), `git fetch --tags` + `git checkout -f <tag>` + `docker compose up -d --build`, puis **smoke test** : `curl -fsS localhost:8099/api/version`, assert **HTTP 200** ET **`version == tag`** (tag sans le `V`), échec du job sinon.

## Process de release

1. Journaliser `[VX.Y.Z]` **en tête** de `REALISATION.md` (c'est la 1re occurrence `[VX.Y.Z]` qui alimente `BUILD_VERSION` → `/api/version`, cf. `_build_version()` dans `app.py` [VERSION-VISIBLE]).
2. Commit + `git push origin main` → déclenche la CI.
3. `git tag VX.Y.Z && git push origin VX.Y.Z` → déclenche le déploiement + smoke test sur le runner `zimaboard`.

**Le tag DOIT correspondre à l'entrée de tête de `REALISATION.md`**, sinon `version != tag` → le smoke test échoue et le job est rouge (déploiement quand même appliqué au conteneur, mais job en échec — corriger REALISATION.md et re-tag).

## Rollback

Sur le Zimaboard, dans le dossier de déploiement :
```bash
git checkout <tag_précédent> && docker compose up -d --build
```
(ou re-taguer un ancien commit avec `git tag -f` + `git push -f` pour repasser par le pipeline).

## Gotcha

**Un tag poussé sur un commit qui ne contient PAS les workflows ne déclenche rien.** `deploy.yml` doit exister *dans le commit tagué*. Vécu au 1er déploiement (V20.6.40 taggé d'abord sur un commit sans `.github/` → supprimer le tag remote+local, commit/push les workflows sur main, **re-taguer sur le nouveau commit**, re-push le tag). Voir aussi [[MEMORY]] § État actuel.

## Ce qui n'est PAS dans GitHub

Aucun secret GitHub (runner local). Les secrets SMTP restent dans `.env` sur le Zimaboard.
