import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
import urllib3
from flask import Flask, g, jsonify, render_template, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PATH = os.environ.get("DB_PATH", "/app/data/dashboard.db")

app = Flask(__name__)


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            descr TEXT DEFAULT '',
            url_public TEXT DEFAULT '',
            url_local TEXT DEFAULT '',
            memo TEXT DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(links)").fetchall()}
    if "memo" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN memo TEXT DEFAULT ''")
    if "category" in cols:
        conn.execute("ALTER TABLE links DROP COLUMN category")
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/links", methods=["GET"])
def list_links():
    rows = (
        get_db()
        .execute(
            "SELECT id, name, descr, url_public, url_local, memo, position "
            "FROM links ORDER BY position, id"
        )
        .fetchall()
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/links", methods=["POST"])
def create_link():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM links").fetchone()[0]
    cur = db.execute(
        "INSERT INTO links (name, descr, url_public, url_local, memo, position) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            name,
            data.get("descr", ""),
            _normalize_url(data.get("url_public", "")),
            _normalize_url(data.get("url_local", "")),
            data.get("memo", ""),
            max_pos + 1,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM links WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/links/<int:link_id>", methods=["PUT"])
def update_link(link_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    db.execute(
        "UPDATE links SET name=?, descr=?, url_public=?, url_local=?, memo=? WHERE id=?",
        (
            data.get("name", existing["name"]),
            data.get("descr", existing["descr"]),
            _normalize_url(data.get("url_public", existing["url_public"])),
            _normalize_url(data.get("url_local", existing["url_local"])),
            data.get("memo", existing["memo"]),
            link_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/links/<int:link_id>", methods=["DELETE"])
def delete_link(link_id):
    db = get_db()
    db.execute("DELETE FROM links WHERE id = ?", (link_id,))
    db.commit()
    return "", 204


@app.route("/api/links/reorder", methods=["POST"])
def reorder_links():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    db = get_db()
    for pos, lid in enumerate(ids):
        db.execute("UPDATE links SET position=? WHERE id=?", (pos, lid))
    db.commit()
    return jsonify({"ok": True})


def _normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    return url if urlparse(url).scheme else "http://" + url


def _check_url(url, timeout=3):
    if not url:
        return "unknown"
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, verify=False)
        return "online" if r.status_code < 500 else "offline"
    except Exception:
        return "offline"


@app.route("/api/links/status", methods=["GET"])
def links_status():
    rows = get_db().execute("SELECT id, url_public, url_local FROM links").fetchall()
    tasks = []
    for r in rows:
        tasks.append((r["id"], "public", r["url_public"]))
        tasks.append((r["id"], "local", r["url_local"]))
    with ThreadPoolExecutor(max_workers=20) as ex:
        statuses = list(ex.map(_check_url, [u for _, _, u in tasks]))
    result = {}
    for (lid, kind, _), st in zip(tasks, statuses):
        result.setdefault(str(lid), {})[kind] = st
    return jsonify(result)


init_db()
