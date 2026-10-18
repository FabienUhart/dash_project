#!/bin/bash
# [DASH-MCP] Deux workers dans le même conteneur : gunicorn (Flask, 8099) ET uvicorn (MCP, 8100).
# Si l'un meurt, le script sort non-nul → `restart: unless-stopped` du compose relance le conteneur
# entier (les deux repartent ensemble, jamais un seul à moitié mort).
# uvicorn SANS access log : le chemin contient le jeton (/mcp/<jeton>/) ; le MCP journalise lui-même
# le chemin masqué (/mcp/***/).
set -u
cd /app
gunicorn --bind 0.0.0.0:8099 --workers 2 --timeout 300 --access-logfile - --error-logfile - app:app &
GUNI=$!
uvicorn dash_mcp.server:app --host 0.0.0.0 --port 8100 --no-access-log --proxy-headers --forwarded-allow-ips='*' &
UVI=$!
trap 'kill -TERM $GUNI $UVI 2>/dev/null; wait; exit 0' TERM INT
wait -n $GUNI $UVI
RC=$?
echo "[start.sh] un worker s'est arrêté (rc=$RC) → arrêt du conteneur pour redémarrage propre" >&2
kill -TERM $GUNI $UVI 2>/dev/null
wait
exit 1
