import calendar
import json
import os
import secrets
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import re

import requests
import urllib3
from flask import (
    Flask,
    Response,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PATH = os.environ.get("DB_PATH", "/app/data/dashboard.db")
UPLOAD_DIR = os.path.join(os.path.dirname(DB_PATH), "uploads")
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
SAFE_IMG_NAME = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$")


def _looks_like_image(head, ext):
    if ext in ("jpg", "jpeg"):
        return head[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "gif":
        return head[:6] in (b"GIF87a", b"GIF89a")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def _save_uploaded_image(f, allowed_ext):
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in allowed_ext:
        return None, "format non supporté (" + ", ".join(sorted(allowed_ext)) + ")"
    head = f.stream.read(12)
    f.stream.seek(0)
    if not _looks_like_image(head, ext):
        return None, "le fichier n'est pas une vraie image " + ext.upper()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(UPLOAD_DIR, name))
    return name, None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS priorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    if conn.execute("SELECT COUNT(*) FROM priorities").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO priorities (id, name, color, position) VALUES (?, ?, ?, ?)",
            [
                (1, "P1", "#f44336", 0),
                (2, "P2", "#ffc107", 1),
                (3, "P3", "#4caf50", 2),
            ],
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            can_edit INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS share_guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            name TEXT DEFAULT '',
            guest_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT '',
            approved_at TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memo_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_id INTEGER NOT NULL,
            memo_uid TEXT DEFAULT '',
            editor TEXT NOT NULL,
            share_id INTEGER,
            before TEXT,
            after TEXT,
            edited_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memo_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_uid TEXT DEFAULT '',
            content TEXT NOT NULL,
            project TEXT DEFAULT '',
            done_at TEXT NOT NULL
        )
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(links)").fetchall()}
    if "memo" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN memo TEXT DEFAULT ''")
    if "category_id" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN category_id INTEGER")
    if "tags" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN tags TEXT DEFAULT ''")
    for col in ("uid", "created_at", "updated_at"):
        if col not in cols:
            conn.execute(f"ALTER TABLE links ADD COLUMN {col} TEXT DEFAULT ''")
    mcols = {r[1] for r in conn.execute("PRAGMA table_info(memos)").fetchall()}
    for col in ("uid", "updated_at"):
        if col not in mcols:
            conn.execute(f"ALTER TABLE memos ADD COLUMN {col} TEXT DEFAULT ''")
    if "done" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN done INTEGER NOT NULL DEFAULT 0")
    if "due_date" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN due_date TEXT DEFAULT ''")
    if "priority" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
    if "subtasks" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN subtasks TEXT DEFAULT '[]'")
    if "project_id" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN project_id INTEGER")
    if "images" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN images TEXT DEFAULT '[]'")
    if "recurrence" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN recurrence TEXT DEFAULT ''")
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "color" not in ccols:
        conn.execute("ALTER TABLE categories ADD COLUMN color TEXT DEFAULT ''")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "tags" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN tags TEXT DEFAULT ''")
    scols = {r[1] for r in conn.execute("PRAGMA table_info(shares)").fetchall()}
    if "pin" not in scols:
        conn.execute("ALTER TABLE shares ADD COLUMN pin TEXT DEFAULT ''")
    for row in conn.execute(
        "SELECT id FROM shares WHERE pin = '' OR pin IS NULL"
    ).fetchall():
        conn.execute(
            "UPDATE shares SET pin = ? WHERE id = ?",
            (f"{secrets.randbelow(10000):04d}", row[0]),
        )
    now = datetime.now(timezone.utc).isoformat()
    for row in conn.execute("SELECT id FROM links WHERE uid = '' OR uid IS NULL").fetchall():
        conn.execute(
            "UPDATE links SET uid = ?, created_at = ?, updated_at = ? WHERE id = ?",
            (str(uuid.uuid4()), now, now, row[0]),
        )
    for row in conn.execute("SELECT id, created_at FROM memos WHERE uid = '' OR uid IS NULL").fetchall():
        conn.execute(
            "UPDATE memos SET uid = ?, updated_at = ? WHERE id = ?",
            (str(uuid.uuid4()), row[1] or now, row[0]),
        )
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------- links

LINK_FIELDS = (
    "id, name, descr, url_public, url_local, memo, position, category_id, "
    "uid, created_at, updated_at, tags"
)


def _normalize_tags(value):
    if not value:
        return ""
    parts = re.split(r"[,\s#]+", str(value).lower())
    seen = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return " ".join(seen)


@app.route("/api/links", methods=["GET"])
def list_links():
    rows = (
        get_db()
        .execute(f"SELECT {LINK_FIELDS} FROM links ORDER BY position, id")
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
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO links (name, descr, url_public, url_local, memo, position, category_id, "
        "uid, created_at, updated_at, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            data.get("descr", ""),
            _normalize_url(data.get("url_public", "")),
            _normalize_url(data.get("url_local", "")),
            data.get("memo", ""),
            max_pos + 1,
            _valid_category_id(db, data.get("category_id")),
            str(uuid.uuid4()),
            now,
            now,
            _normalize_tags(data.get("tags", "")),
        ),
    )
    db.commit()
    row = db.execute(
        f"SELECT {LINK_FIELDS} FROM links WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/links/<int:link_id>", methods=["PUT"])
def update_link(link_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    category_id = (
        _valid_category_id(db, data.get("category_id"))
        if "category_id" in data
        else existing["category_id"]
    )
    tags = (
        _normalize_tags(data.get("tags"))
        if "tags" in data
        else (existing["tags"] or "")
    )
    db.execute(
        "UPDATE links SET name=?, descr=?, url_public=?, url_local=?, memo=?, category_id=?, "
        "tags=?, updated_at=? WHERE id=?",
        (
            data.get("name", existing["name"]),
            data.get("descr", existing["descr"]),
            _normalize_url(data.get("url_public", existing["url_public"])),
            _normalize_url(data.get("url_local", existing["url_local"])),
            data.get("memo", existing["memo"]),
            category_id,
            tags,
            datetime.now(timezone.utc).isoformat(),
            link_id,
        ),
    )
    db.commit()
    _favicon_cache.pop(link_id, None)
    row = db.execute(
        f"SELECT {LINK_FIELDS} FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    return jsonify(dict(row))


@app.route("/api/links/<int:link_id>", methods=["DELETE"])
def delete_link(link_id):
    db = get_db()
    db.execute("DELETE FROM links WHERE id = ?", (link_id,))
    db.commit()
    _favicon_cache.pop(link_id, None)
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


# ----------------------------------------------------------- categories


@app.route("/api/categories", methods=["GET"])
def list_categories():
    rows = (
        get_db()
        .execute(
            "SELECT c.id, c.name, c.position, c.color, COUNT(l.id) AS link_count "
            "FROM categories c LEFT JOIN links l ON l.category_id = c.id "
            "GROUP BY c.id ORDER BY c.position, c.id"
        )
        .fetchall()
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM categories WHERE name = ?", (name,)).fetchone():
        return jsonify({"error": "category already exists"}), 409
    max_pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM categories"
    ).fetchone()[0]
    color = (data.get("color") or "").strip()
    cur = db.execute(
        "INSERT INTO categories (name, position, color) VALUES (?, ?, ?)",
        (name, max_pos + 1, color),
    )
    db.commit()
    return (
        jsonify(
            {"id": cur.lastrowid, "name": name, "position": max_pos + 1, "color": color}
        ),
        201,
    )


@app.route("/api/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute(
        "SELECT * FROM categories WHERE id = ?", (cat_id,)
    ).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    name = (data.get("name", existing["name"]) or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    color = (data.get("color", existing["color"]) or "").strip()
    db.execute(
        "UPDATE categories SET name = ?, color = ? WHERE id = ?", (name, color, cat_id)
    )
    db.commit()
    return jsonify({"id": cat_id, "name": name, "color": color})


@app.route("/api/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    db = get_db()
    db.execute("UPDATE links SET category_id = NULL WHERE category_id = ?", (cat_id,))
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    db.commit()
    return "", 204


@app.route("/api/categories/reorder", methods=["POST"])
def reorder_categories():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    db = get_db()
    for pos, cid in enumerate(ids):
        db.execute("UPDATE categories SET position=? WHERE id=?", (pos, cid))
    db.commit()
    return jsonify({"ok": True})


# -------------------------------------------------------------- projects


@app.route("/api/projects", methods=["GET"])
def list_projects():
    rows = (
        get_db()
        .execute(
            "SELECT p.id, p.name, p.color, p.position, p.tags, "
            "COUNT(CASE WHEN m.done = 0 THEN m.id END) AS memo_count "
            "FROM projects p LEFT JOIN memos m ON m.project_id = p.id "
            "GROUP BY p.id ORDER BY p.position, p.id"
        )
        .fetchall()
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM projects WHERE name = ?", (name,)).fetchone():
        return jsonify({"error": "project already exists"}), 409
    max_pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM projects"
    ).fetchone()[0]
    color = (data.get("color") or "").strip()
    tags = _normalize_tags(data.get("tags", ""))
    cur = db.execute(
        "INSERT INTO projects (name, color, position, tags) VALUES (?, ?, ?, ?)",
        (name, color, max_pos + 1, tags),
    )
    db.commit()
    return (
        jsonify(
            {"id": cur.lastrowid, "name": name, "color": color, "position": max_pos + 1, "tags": tags}
        ),
        201,
    )


@app.route("/api/projects/<int:project_id>", methods=["PUT"])
def update_project(project_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    name = (data.get("name", existing["name"]) or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    color = (data.get("color", existing["color"]) or "").strip()
    tags = (
        _normalize_tags(data.get("tags"))
        if "tags" in data
        else (existing["tags"] or "")
    )
    db.execute(
        "UPDATE projects SET name = ?, color = ?, tags = ? WHERE id = ?",
        (name, color, tags, project_id),
    )
    db.commit()
    return jsonify({"id": project_id, "name": name, "color": color, "tags": tags})


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    db = get_db()
    db.execute("UPDATE memos SET project_id = NULL WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.execute(
        "DELETE FROM shares WHERE kind = 'project' AND target_id = ?", (project_id,)
    )
    db.commit()
    return "", 204


@app.route("/api/projects/reorder", methods=["POST"])
def reorder_projects():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    db = get_db()
    for pos, pid in enumerate(ids):
        db.execute("UPDATE projects SET position=? WHERE id=?", (pos, pid))
    db.commit()
    return jsonify({"ok": True})


def _valid_project_id(db, project_id):
    if project_id in (None, "", 0):
        return None
    row = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row["id"] if row else None


def _valid_priority(db, value):
    try:
        p = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if p <= 0:
        return 0
    row = db.execute("SELECT 1 FROM priorities WHERE id = ?", (p,)).fetchone()
    return p if row else 0


# ------------------------------------------------------------ priorities


@app.route("/api/priorities", methods=["GET"])
def list_priorities():
    rows = (
        get_db()
        .execute(
            "SELECT p.id, p.name, p.color, p.position, COUNT(m.id) AS memo_count "
            "FROM priorities p LEFT JOIN memos m ON m.priority = p.id "
            "GROUP BY p.id ORDER BY p.position, p.id"
        )
        .fetchall()
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/priorities", methods=["POST"])
def create_priority():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM priorities WHERE name = ?", (name,)).fetchone():
        return jsonify({"error": "priority already exists"}), 409
    max_pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM priorities"
    ).fetchone()[0]
    color = (data.get("color") or "").strip()
    cur = db.execute(
        "INSERT INTO priorities (name, color, position) VALUES (?, ?, ?)",
        (name, color, max_pos + 1),
    )
    db.commit()
    return (
        jsonify(
            {"id": cur.lastrowid, "name": name, "color": color, "position": max_pos + 1}
        ),
        201,
    )


@app.route("/api/priorities/<int:prio_id>", methods=["PUT"])
def update_priority(prio_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute(
        "SELECT * FROM priorities WHERE id = ?", (prio_id,)
    ).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    name = (data.get("name", existing["name"]) or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    color = (data.get("color", existing["color"]) or "").strip()
    db.execute(
        "UPDATE priorities SET name = ?, color = ? WHERE id = ?",
        (name, color, prio_id),
    )
    db.commit()
    return jsonify({"id": prio_id, "name": name, "color": color})


@app.route("/api/priorities/<int:prio_id>", methods=["DELETE"])
def delete_priority(prio_id):
    db = get_db()
    db.execute("UPDATE memos SET priority = 0 WHERE priority = ?", (prio_id,))
    db.execute("DELETE FROM priorities WHERE id = ?", (prio_id,))
    db.commit()
    return "", 204


# ---------------------------------------------------------------- memos


RECURRENCES = {"daily", "weekly", "monthly", "quarterly", "yearly"}


def _valid_recurrence(value):
    value = (value or "").strip().lower()
    return value if value in RECURRENCES else ""


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _next_due(due_str, recurrence):
    today = date.today()
    try:
        d = date.fromisoformat(due_str) if due_str else today
    except ValueError:
        d = today

    def step(x):
        if recurrence == "daily":
            return x + timedelta(days=1)
        if recurrence == "weekly":
            return x + timedelta(weeks=1)
        if recurrence == "monthly":
            return _add_months(x, 1)
        if recurrence == "quarterly":
            return _add_months(x, 3)
        if recurrence == "yearly":
            return _add_months(x, 12)
        return x

    nxt = step(d)
    while nxt <= today:
        nxt = step(nxt)
    return nxt.isoformat()


def _memo_dict(row):
    d = dict(row)
    try:
        d["subtasks"] = json.loads(d.get("subtasks") or "[]")
    except Exception:
        d["subtasks"] = []
    try:
        d["images"] = json.loads(d.get("images") or "[]")
    except Exception:
        d["images"] = []
    d["done"] = bool(d.get("done"))
    return d


def _images_json(value, check_files=False):
    if not isinstance(value, list):
        return "[]"
    clean = []
    for name in value:
        name = os.path.basename(str(name or "").strip())
        if not SAFE_IMG_NAME.match(name):
            continue
        if check_files and not os.path.isfile(os.path.join(UPLOAD_DIR, name)):
            continue
        clean.append(name)
    return json.dumps(clean)


def _delete_image_files(images_json_str):
    try:
        names = json.loads(images_json_str or "[]")
    except Exception:
        return
    for name in names:
        name = os.path.basename(str(name))
        if SAFE_IMG_NAME.match(name):
            try:
                os.remove(os.path.join(UPLOAD_DIR, name))
            except OSError:
                pass


def _subtasks_json(value):
    if not isinstance(value, list):
        return "[]"
    clean = []
    for st in value:
        if isinstance(st, dict) and (st.get("content") or "").strip():
            clean.append(
                {"content": st["content"].strip(), "done": bool(st.get("done"))}
            )
    return json.dumps(clean, ensure_ascii=False)


@app.route("/api/memos", methods=["GET"])
def list_memos():
    db = get_db()
    rows = db.execute("SELECT * FROM memos ORDER BY position, id").fetchall()
    guest_last = {}
    for r in db.execute(
        "SELECT memo_id, editor, before IS NULL AS created, edited_at "
        "FROM memo_revisions WHERE share_id IS NOT NULL "
        "ORDER BY edited_at DESC, id DESC"
    ).fetchall():
        if r["memo_id"] not in guest_last:
            guest_last[r["memo_id"]] = r
    out = []
    for row in rows:
        d = _memo_dict(row)
        g = guest_last.get(d["id"])
        if g:
            d["guest_editor"] = g["editor"]
            d["guest_action"] = "created" if g["created"] else "edited"
            d["guest_at"] = g["edited_at"]
        out.append(d)
    return jsonify(out)


@app.route("/api/memos", methods=["POST"])
def create_memo():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    db = get_db()
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    uid = str(uuid.uuid4())
    cur = db.execute(
        "INSERT INTO memos (content, position, created_at, uid, updated_at, "
        "done, due_date, priority, subtasks, project_id, recurrence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            content,
            max_pos + 1,
            now,
            uid,
            now,
            1 if data.get("done") else 0,
            (data.get("due_date") or "").strip(),
            _valid_priority(db, data.get("priority")),
            _subtasks_json(data.get("subtasks")),
            _valid_project_id(db, data.get("project_id")),
            _valid_recurrence(data.get("recurrence")),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_memo_dict(row)), 201


def _memo_snapshot(content, done, due_date, priority, subtasks_json, recurrence):
    try:
        subs = json.loads(subtasks_json or "[]")
    except Exception:
        subs = []
    return {
        "content": content,
        "done": bool(done),
        "due_date": due_date or "",
        "priority": priority or 0,
        "subtasks": subs,
        "recurrence": recurrence or "",
    }


def _log_revision(db, memo_row, after, editor, share_id=None):
    before = _memo_snapshot(
        memo_row["content"], memo_row["done"], memo_row["due_date"],
        memo_row["priority"], memo_row["subtasks"], memo_row["recurrence"],
    )
    if before == after:
        return
    db.execute(
        "INSERT INTO memo_revisions (memo_id, memo_uid, editor, share_id, before, after, edited_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            memo_row["id"],
            memo_row["uid"] or "",
            editor,
            share_id,
            json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _perform_memo_update(db, existing, data, editor="moi", share_id=None):
    memo_id = existing["id"]
    content = (data.get("content", existing["content"]) or "").strip()
    if not content:
        return {"error": "content required"}, 400
    done = 1 if data.get("done", existing["done"]) else 0
    due_date = (data.get("due_date", existing["due_date"]) or "").strip()
    priority = _valid_priority(db, data.get("priority", existing["priority"]))
    if "subtasks" in data:
        subtasks = _subtasks_json(data.get("subtasks"))
    else:
        subtasks = existing["subtasks"] or "[]"
    project_id = (
        _valid_project_id(db, data.get("project_id"))
        if "project_id" in data
        else existing["project_id"]
    )
    recurrence = (
        _valid_recurrence(data.get("recurrence"))
        if "recurrence" in data
        else (existing["recurrence"] or "")
    )

    now = datetime.now(timezone.utc).isoformat()
    was_done = bool(existing["done"])
    if done and not was_done:
        proj = None
        if project_id:
            proj = db.execute(
                "SELECT name FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        db.execute(
            "INSERT INTO memo_history (memo_uid, content, project, done_at) "
            "VALUES (?, ?, ?, ?)",
            (existing["uid"] or "", content, proj["name"] if proj else "", now),
        )
        if recurrence:
            done = 0
            due_date = _next_due(due_date, recurrence)
    elif was_done and not done:
        db.execute(
            "DELETE FROM memo_history WHERE id = ("
            "SELECT id FROM memo_history WHERE memo_uid = ? "
            "ORDER BY done_at DESC, id DESC LIMIT 1)",
            (existing["uid"] or "",),
        )

    after = _memo_snapshot(content, done, due_date, priority, subtasks, recurrence)
    _log_revision(db, existing, after, editor, share_id)

    db.execute(
        "UPDATE memos SET content=?, done=?, due_date=?, priority=?, subtasks=?, "
        "project_id=?, recurrence=?, updated_at=? WHERE id=?",
        (
            content,
            done,
            due_date,
            priority,
            subtasks,
            project_id,
            recurrence,
            now,
            memo_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return _memo_dict(row), 200


@app.route("/api/memos/<int:memo_id>", methods=["PUT"])
def update_memo(memo_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    payload, status = _perform_memo_update(db, existing, data)
    return jsonify(payload), status


@app.route("/api/memos/<int:memo_id>", methods=["DELETE"])
def delete_memo(memo_id):
    db = get_db()
    row = db.execute("SELECT images FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if row:
        _delete_image_files(row["images"])
    db.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
    db.execute("DELETE FROM shares WHERE kind = 'memo' AND target_id = ?", (memo_id,))
    db.commit()
    return "", 204


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    name = os.path.basename(filename)
    if not SAFE_IMG_NAME.match(name):
        return "", 404
    return send_from_directory(UPLOAD_DIR, name, max_age=86400)


@app.route("/api/memos/<int:memo_id>/images", methods=["POST"])
def add_memo_image(memo_id):
    db = get_db()
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"error": "image file required"}), 400
    name, err = _save_uploaded_image(f, ALLOWED_IMG_EXT)
    if err:
        return jsonify({"error": err}), 400
    try:
        images = json.loads(existing["images"] or "[]")
    except Exception:
        images = []
    images.append(name)
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row)), 201


@app.route("/api/memos/<int:memo_id>/images/<name>", methods=["DELETE"])
def delete_memo_image(memo_id, name):
    name = os.path.basename(name)
    db = get_db()
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    try:
        images = json.loads(existing["images"] or "[]")
    except Exception:
        images = []
    if name not in images:
        return jsonify({"error": "image not found"}), 404
    images = [n for n in images if n != name]
    if SAFE_IMG_NAME.match(name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row))


@app.route("/api/history", methods=["GET"])
def list_history():
    rows = (
        get_db()
        .execute(
            "SELECT id, memo_uid, content, project, done_at FROM memo_history "
            "ORDER BY done_at DESC, id DESC"
        )
        .fetchall()
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/history", methods=["DELETE"])
def purge_history():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM memo_history").fetchone()[0]
    db.execute("DELETE FROM memo_history")
    db.commit()
    return jsonify({"purged": count})


@app.route("/api/memos/reorder", methods=["POST"])
def reorder_memos():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    db = get_db()
    for pos, mid in enumerate(ids):
        db.execute("UPDATE memos SET position=? WHERE id=?", (pos, mid))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- utils


def _normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    return url if urlparse(url).scheme else "http://" + url


def _valid_category_id(db, cat_id):
    if cat_id in (None, "", 0):
        return None
    row = db.execute("SELECT id FROM categories WHERE id = ?", (cat_id,)).fetchone()
    return row["id"] if row else None


def _check_url(url, timeout=3):
    if not url:
        return "unknown"
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, verify=False)
        return "online" if r.status_code < 500 else "offline"
    except Exception:
        return "offline"


_favicon_cache = {}


@app.route("/api/favicon/<int:link_id>", methods=["GET"])
def link_favicon(link_id):
    if link_id in _favicon_cache:
        cached = _favicon_cache[link_id]
        if cached is None:
            return "", 404
        return Response(
            cached[0], mimetype=cached[1], headers={"Cache-Control": "max-age=86400"}
        )
    row = get_db().execute(
        "SELECT url_local, url_public FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    if not row:
        return "", 404
    for base in (row["url_local"], row["url_public"]):
        if not base:
            continue
        try:
            r = requests.get(
                base.rstrip("/") + "/favicon.ico",
                timeout=3,
                allow_redirects=True,
                verify=False,
            )
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            if r.ok and r.content and ("image" in ctype or "icon" in ctype):
                _favicon_cache[link_id] = (r.content, ctype or "image/x-icon")
                return Response(
                    r.content,
                    mimetype=ctype or "image/x-icon",
                    headers={"Cache-Control": "max-age=86400"},
                )
        except Exception:
            pass
    _favicon_cache[link_id] = None
    return "", 404


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


# ---------------------------------------------------------------- shares


def _text_excerpt(html, n=80):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def _share_by_token(db, token):
    if not token or len(token) < 16:
        return None
    return db.execute("SELECT * FROM shares WHERE token = ?", (token,)).fetchone()


def _share_memo_dict(row):
    d = _memo_dict(row)
    return {
        "id": d["id"],
        "content": d["content"],
        "done": d["done"],
        "due_date": d["due_date"],
        "priority": d["priority"],
        "subtasks": d["subtasks"],
        "images": d["images"],
        "recurrence": d["recurrence"],
    }


def _share_scope_memos(db, share):
    if share["kind"] == "memo":
        row = db.execute(
            "SELECT * FROM memos WHERE id = ?", (share["target_id"],)
        ).fetchone()
        return [row] if row else []
    return db.execute(
        "SELECT * FROM memos WHERE project_id = ? ORDER BY position, id",
        (share["target_id"],),
    ).fetchall()


@app.route("/api/shares", methods=["GET"])
def list_shares():
    db = get_db()
    rows = db.execute("SELECT * FROM shares ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if r["kind"] == "memo":
            t = db.execute(
                "SELECT content FROM memos WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = _text_excerpt(t["content"]) if t else None
        else:
            t = db.execute(
                "SELECT name FROM projects WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = t["name"] if t else None
        d["guests"] = [
            {
                "id": g["id"],
                "email": g["email"],
                "name": g["name"],
                "status": g["status"],
            }
            for g in db.execute(
                "SELECT * FROM share_guests WHERE share_id = ? ORDER BY id",
                (r["id"],),
            ).fetchall()
        ]
        out.append(d)
    return jsonify(out)


@app.route("/api/shares", methods=["POST"])
def create_share():
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip()
    if kind not in ("memo", "project"):
        return jsonify({"error": "kind must be memo or project"}), 400
    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "target_id required"}), 400
    db = get_db()
    table = "memos" if kind == "memo" else "projects"
    if not db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (target_id,)).fetchone():
        return jsonify({"error": "target not found"}), 404
    token = secrets.token_urlsafe(24)
    pin = f"{secrets.randbelow(10000):04d}"
    cur = db.execute(
        "INSERT INTO shares (token, kind, target_id, can_edit, created_at, pin) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            token,
            kind,
            target_id,
            1 if data.get("can_edit") else 0,
            datetime.now(timezone.utc).isoformat(),
            pin,
        ),
    )
    db.commit()
    return (
        jsonify(
            {
                "id": cur.lastrowid,
                "token": token,
                "kind": kind,
                "target_id": target_id,
                "can_edit": bool(data.get("can_edit")),
                "pin": pin,
            }
        ),
        201,
    )


@app.route("/api/shares/<int:share_id>", methods=["PUT"])
def update_share(share_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM shares WHERE id = ?", (share_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    pin = (str(data.get("pin", existing["pin"])) or "").strip()
    if not re.match(r"^\d{4}$", pin):
        return jsonify({"error": "le code doit faire 4 chiffres"}), 400
    can_edit = 1 if data.get("can_edit", existing["can_edit"]) else 0
    db.execute(
        "UPDATE shares SET pin = ?, can_edit = ? WHERE id = ?",
        (pin, can_edit, share_id),
    )
    db.commit()
    return jsonify({"id": share_id, "pin": pin, "can_edit": bool(can_edit)})


@app.route("/api/shares/<int:share_id>", methods=["DELETE"])
def delete_share(share_id):
    db = get_db()
    db.execute("DELETE FROM share_guests WHERE share_id = ?", (share_id,))
    db.execute("DELETE FROM shares WHERE id = ?", (share_id,))
    db.commit()
    return "", 204


def _get_state(db, key, default=""):
    row = db.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set_state(db, key, value):
    db.execute(
        "INSERT INTO app_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


@app.route("/api/guests", methods=["GET"])
def list_guests():
    db = get_db()
    rows = db.execute(
        "SELECT g.*, s.kind, s.target_id FROM share_guests g "
        "JOIN shares s ON s.id = g.share_id ORDER BY g.id DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("guest_token", None)
        if r["kind"] == "memo":
            t = db.execute(
                "SELECT content FROM memos WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = (_text_excerpt(t["content"], 60) if t else "(supprimé)")
        else:
            t = db.execute(
                "SELECT name FROM projects WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = (t["name"] if t else "(supprimé)")
        out.append(d)
    return jsonify(out)


@app.route("/api/guests/<int:guest_id>", methods=["PUT"])
def update_guest(guest_id):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in ("approved", "rejected", "pending"):
        return jsonify({"error": "status invalide"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM share_guests WHERE id = ?", (guest_id,)).fetchone():
        return jsonify({"error": "not found"}), 404
    db.execute(
        "UPDATE share_guests SET status = ?, approved_at = ? WHERE id = ?",
        (
            status,
            datetime.now(timezone.utc).isoformat() if status == "approved" else "",
            guest_id,
        ),
    )
    db.commit()
    return jsonify({"id": guest_id, "status": status})


@app.route("/api/guests/<int:guest_id>", methods=["DELETE"])
def delete_guest(guest_id):
    db = get_db()
    db.execute("DELETE FROM share_guests WHERE id = ?", (guest_id,))
    db.commit()
    return "", 204


@app.route("/api/activity", methods=["GET"])
def activity():
    db = get_db()
    pending = db.execute(
        "SELECT COUNT(*) FROM share_guests WHERE status = 'pending'"
    ).fetchone()[0]
    revisions = db.execute(
        "SELECT r.*, m.content AS memo_content FROM memo_revisions r "
        "LEFT JOIN memos m ON m.id = r.memo_id "
        "WHERE r.share_id IS NOT NULL ORDER BY r.edited_at DESC, r.id DESC LIMIT 50"
    ).fetchall()
    seen_at = _get_state(db, "activity_seen_at", "")
    out_rev = []
    unseen = 0
    for r in revisions:
        d = {
            "id": r["id"],
            "memo_id": r["memo_id"],
            "editor": r["editor"],
            "edited_at": r["edited_at"],
            "memo_content": r["memo_content"],
            "created": r["before"] is None,
            "before": json.loads(r["before"]) if r["before"] else None,
            "after": json.loads(r["after"]) if r["after"] else None,
        }
        if r["edited_at"] > seen_at:
            unseen += 1
        out_rev.append(d)
    return jsonify({"pending_guests": pending, "unseen": unseen, "revisions": out_rev})


@app.route("/api/activity/seen", methods=["POST"])
def activity_seen():
    db = get_db()
    _set_state(db, "activity_seen_at", datetime.now(timezone.utc).isoformat())
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/memos/<int:memo_id>/revisions", methods=["GET"])
def memo_revisions(memo_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memo_revisions WHERE memo_id = ? ORDER BY edited_at DESC, id DESC LIMIT 100",
        (memo_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "editor": r["editor"],
                "edited_at": r["edited_at"],
                "before": json.loads(r["before"]) if r["before"] else None,
                "after": json.loads(r["after"]) if r["after"] else None,
            }
        )
    return jsonify(out)


@app.route("/api/memos/<int:memo_id>/restore", methods=["POST"])
def memo_restore(memo_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    rev = db.execute(
        "SELECT * FROM memo_revisions WHERE id = ? AND memo_id = ?",
        (data.get("revision_id"), memo_id),
    ).fetchone()
    if not rev:
        return jsonify({"error": "revision not found"}), 404
    which = "before" if data.get("which") == "before" else "after"
    snap_raw = rev[which]
    if not snap_raw:
        return jsonify({"error": "pas d'état pour cette version"}), 400
    snap = json.loads(snap_raw)
    after = _memo_snapshot(
        snap.get("content", ""),
        1 if snap.get("done") else 0,
        snap.get("due_date", ""),
        snap.get("priority", 0),
        json.dumps(snap.get("subtasks") or []),
        snap.get("recurrence", ""),
    )
    _log_revision(db, existing, after, "moi (restauration)")
    db.execute(
        "UPDATE memos SET content=?, done=?, due_date=?, priority=?, subtasks=?, "
        "recurrence=?, updated_at=? WHERE id=?",
        (
            after["content"],
            1 if after["done"] else 0,
            after["due_date"],
            after["priority"],
            json.dumps(after["subtasks"], ensure_ascii=False),
            after["recurrence"],
            datetime.now(timezone.utc).isoformat(),
            memo_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row))


@app.route("/share/<token>")
def share_page(token):
    if not _share_by_token(get_db(), token):
        return "Lien de partage invalide ou révoqué.", 404
    return render_template("share.html")


@app.route("/share/<token>/data")
def share_data(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    memos = [_share_memo_dict(r) for r in _share_scope_memos(db, share)]
    payload = {
        "kind": share["kind"],
        "can_edit": bool(share["can_edit"]),
        "memos": memos,
        "priorities": [
            dict(r)
            for r in db.execute(
                "SELECT id, name, color FROM priorities ORDER BY position, id"
            ).fetchall()
        ],
    }
    if share["kind"] == "project":
        proj = db.execute(
            "SELECT name, color FROM projects WHERE id = ?", (share["target_id"],)
        ).fetchone()
        if not proj:
            return jsonify({"error": "invalid"}), 404
        payload["title"] = proj["name"]
        payload["color"] = proj["color"]
    else:
        payload["title"] = "Mémo partagé"
        payload["color"] = ""
    return jsonify(payload)


def _guest_from_request(db, share):
    token = (request.headers.get("X-Guest-Token") or "").strip()
    if not token:
        return None
    return db.execute(
        "SELECT * FROM share_guests WHERE guest_token = ? AND share_id = ?",
        (token, share["id"]),
    ).fetchone()


@app.route("/share/<token>/register", methods=["POST"])
def share_register(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or not share["can_edit"]:
        return jsonify({"error": "invalid"}), 404
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()[:60]
    pin = (str(data.get("pin") or "")).strip()
    if not email or "@" not in email or len(email) > 120:
        return jsonify({"error": "e-mail invalide"}), 400
    if pin != (share["pin"] or ""):
        return jsonify({"error": "code invalide — demande le code à 4 chiffres au propriétaire"}), 403
    now = datetime.now(timezone.utc).isoformat()
    existing = db.execute(
        "SELECT * FROM share_guests WHERE share_id = ? AND email = ?",
        (share["id"], email),
    ).fetchone()
    if existing:
        if existing["status"] != "approved":
            db.execute(
                "UPDATE share_guests SET status = 'approved', approved_at = ? WHERE id = ?",
                (now, existing["id"]),
            )
            db.commit()
        return jsonify(
            {"guest_token": existing["guest_token"], "status": "approved", "email": email}
        )
    if db.execute(
        "SELECT COUNT(*) FROM share_guests WHERE share_id = ?", (share["id"],)
    ).fetchone()[0] >= 30:
        return jsonify({"error": "trop de demandes pour ce lien"}), 429
    gtoken = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO share_guests (share_id, email, name, guest_token, status, created_at, approved_at) "
        "VALUES (?, ?, ?, ?, 'approved', ?, ?)",
        (share["id"], email, name, gtoken, now, now),
    )
    db.commit()
    return jsonify({"guest_token": gtoken, "status": "approved", "email": email}), 201


@app.route("/share/<token>/me")
def share_me(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest:
        return jsonify({"status": "anonymous"})
    return jsonify(
        {"status": guest["status"], "email": guest["email"], "name": guest["name"]}
    )


@app.route("/share/<token>/memo/<int:memo_id>", methods=["PUT"])
def share_update_memo(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"]:
        return jsonify({"error": "lecture seule"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required", "status": guest["status"] if guest else "anonymous"}), 403
    allowed_ids = {r["id"] for r in _share_scope_memos(db, share)}
    if memo_id not in allowed_ids:
        return jsonify({"error": "not found"}), 404
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    raw = request.get_json(silent=True) or {}
    data = {
        k: raw[k]
        for k in ("content", "done", "subtasks", "due_date", "priority", "recurrence")
        if k in raw
    }
    editor = guest["name"] or guest["email"]
    payload, status = _perform_memo_update(
        db, existing, data, editor=f"{editor} <{guest['email']}>", share_id=share["id"]
    )
    if status == 200:
        payload = _share_memo_dict_from_payload(payload)
    return jsonify(payload), status


GUEST_IMG_EXT = {"png", "jpg", "jpeg"}


@app.route("/share/<token>/memo/<int:memo_id>/images", methods=["POST"])
def share_add_image(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"]:
        return jsonify({"error": "lecture seule"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    allowed_ids = {r["id"] for r in _share_scope_memos(db, share)}
    if memo_id not in allowed_ids:
        return jsonify({"error": "not found"}), 404
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"error": "image file required"}), 400
    name, err = _save_uploaded_image(f, GUEST_IMG_EXT)
    if err:
        return jsonify({"error": err}), 400
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    try:
        images = json.loads(existing["images"] or "[]")
    except Exception:
        images = []
    images.append(name)
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_share_memo_dict(row)), 201


@app.route("/share/<token>/memo/<int:memo_id>/images/<name>", methods=["DELETE"])
def share_delete_image(token, memo_id, name):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or not share["can_edit"]:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    allowed_ids = {r["id"] for r in _share_scope_memos(db, share)}
    if memo_id not in allowed_ids:
        return jsonify({"error": "not found"}), 404
    name = os.path.basename(name)
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    try:
        images = json.loads(existing["images"] or "[]")
    except Exception:
        images = []
    if name not in images:
        return jsonify({"error": "image not found"}), 404
    images = [n for n in images if n != name]
    if SAFE_IMG_NAME.match(name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_share_memo_dict(row))


def _share_memo_dict_from_payload(d):
    return {
        "id": d["id"],
        "content": d["content"],
        "done": d["done"],
        "due_date": d["due_date"],
        "priority": d["priority"],
        "subtasks": d["subtasks"],
        "images": d["images"],
        "recurrence": d["recurrence"],
    }


@app.route("/share/<token>/memos", methods=["POST"])
def share_add_memo(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"] or share["kind"] != "project":
        return jsonify({"error": "non autorisé"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required", "status": guest["status"] if guest else "anonymous"}), 403
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    new_uid = str(uuid.uuid4())
    cur = db.execute(
        "INSERT INTO memos (content, position, created_at, uid, updated_at, "
        "done, due_date, priority, subtasks, project_id, recurrence) "
        "VALUES (?, ?, ?, ?, ?, 0, '', 0, '[]', ?, '')",
        (content, max_pos + 1, now, new_uid, now, share["target_id"]),
    )
    editor = guest["name"] or guest["email"]
    db.execute(
        "INSERT INTO memo_revisions (memo_id, memo_uid, editor, share_id, before, after, edited_at) "
        "VALUES (?, ?, ?, ?, NULL, ?, ?)",
        (
            cur.lastrowid,
            new_uid,
            f"{editor} <{guest['email']}>",
            share["id"],
            json.dumps(_memo_snapshot(content, 0, "", 0, "[]", ""), ensure_ascii=False),
            now,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_share_memo_dict(row)), 201


@app.route("/share/<token>/image/<name>")
def share_image(token, name):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return "", 404
    name = os.path.basename(name)
    if not SAFE_IMG_NAME.match(name):
        return "", 404
    for row in _share_scope_memos(db, share):
        try:
            if name in json.loads(row["images"] or "[]"):
                return send_from_directory(UPLOAD_DIR, name, max_age=3600)
        except Exception:
            continue
    return "", 404


# -------------------------------------------------------- export/import


@app.route("/api/export", methods=["GET"])
def export_links():
    db = get_db()
    cats = {
        r["id"]: r["name"]
        for r in db.execute("SELECT id, name FROM categories").fetchall()
    }
    links = db.execute(
        f"SELECT {LINK_FIELDS} FROM links ORDER BY position, id"
    ).fetchall()
    memos = db.execute("SELECT * FROM memos ORDER BY position, id").fetchall()
    categories = db.execute(
        "SELECT name, position, color FROM categories ORDER BY position, id"
    ).fetchall()
    projects = db.execute(
        "SELECT id, name, position, color, tags FROM projects ORDER BY position, id"
    ).fetchall()
    proj_names = {r["id"]: r["name"] for r in projects}
    out_links = []
    for r in links:
        d = dict(r)
        d.pop("id", None)
        d["category"] = cats.get(d.pop("category_id", None), "")
        out_links.append(d)
    out_memos = []
    for r in memos:
        d = _memo_dict(r)
        d.pop("id", None)
        d["project"] = proj_names.get(d.pop("project_id", None), "")
        out_memos.append(d)
    out_projects = [
        {"name": r["name"], "position": r["position"], "color": r["color"], "tags": r["tags"]}
        for r in projects
    ]
    history = db.execute(
        "SELECT memo_uid, content, project, done_at FROM memo_history "
        "ORDER BY done_at, id"
    ).fetchall()
    priorities = db.execute(
        "SELECT id, name, color, position FROM priorities ORDER BY position, id"
    ).fetchall()
    return jsonify(
        {
            "version": 10,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "categories": [dict(r) for r in categories],
            "projects": out_projects,
            "priorities": [dict(r) for r in priorities],
            "links": out_links,
            "memos": out_memos,
            "history": [dict(r) for r in history],
        }
    )


@app.route("/api/import", methods=["POST"])
def import_links():
    data = request.get_json(silent=True) or {}
    links = data.get("links")
    memos = data.get("memos") or []
    categories = data.get("categories") or []
    if not isinstance(links, list) and not isinstance(memos, list):
        return jsonify({"error": "expected JSON with 'links' and/or 'memos' lists"}), 400
    links = links if isinstance(links, list) else []
    memos = memos if isinstance(memos, list) else []

    db = get_db()

    cat_ids = {}

    def ensure_category(name, color=""):
        name = (name or "").strip()
        if not name:
            return None
        if name in cat_ids:
            return cat_ids[name]
        row = db.execute(
            "SELECT id, color FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if row:
            cat_ids[name] = row["id"]
            if color and not (row["color"] or "").strip():
                db.execute(
                    "UPDATE categories SET color = ? WHERE id = ?", (color, row["id"])
                )
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM categories"
            ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO categories (name, position, color) VALUES (?, ?, ?)",
                (name, max_pos + 1, color or ""),
            )
            cat_ids[name] = cur.lastrowid
        return cat_ids[name]

    for cat in categories:
        if isinstance(cat, dict):
            ensure_category(cat.get("name"), (cat.get("color") or "").strip())
        else:
            ensure_category(cat)

    proj_ids = {}

    def ensure_project(name, color="", tags=""):
        name = (name or "").strip()
        if not name:
            return None
        if name in proj_ids:
            return proj_ids[name]
        row = db.execute(
            "SELECT id, color, tags FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if row:
            proj_ids[name] = row["id"]
            if color and not (row["color"] or "").strip():
                db.execute(
                    "UPDATE projects SET color = ? WHERE id = ?", (color, row["id"])
                )
            if tags and not (row["tags"] or "").strip():
                db.execute(
                    "UPDATE projects SET tags = ? WHERE id = ?",
                    (_normalize_tags(tags), row["id"]),
                )
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM projects"
            ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO projects (name, color, position, tags) VALUES (?, ?, ?, ?)",
                (name, color or "", max_pos + 1, _normalize_tags(tags)),
            )
            proj_ids[name] = cur.lastrowid
        return proj_ids[name]

    for proj in data.get("projects") or []:
        if isinstance(proj, dict):
            ensure_project(
                proj.get("name"),
                (proj.get("color") or "").strip(),
                proj.get("tags") or "",
            )
        else:
            ensure_project(proj)

    prio_map = {}
    for pr in data.get("priorities") or []:
        if not isinstance(pr, dict):
            continue
        pr_name = (pr.get("name") or "").strip()
        if not pr_name:
            continue
        row = db.execute(
            "SELECT id FROM priorities WHERE name = ?", (pr_name,)
        ).fetchone()
        if row:
            local_id = row["id"]
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM priorities"
            ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO priorities (name, color, position) VALUES (?, ?, ?)",
                (pr_name, (pr.get("color") or "").strip(), max_pos + 1),
            )
            local_id = cur.lastrowid
        try:
            prio_map[int(pr.get("id"))] = local_id
        except (TypeError, ValueError):
            pass

    def map_priority(value):
        try:
            p = int(value or 0)
        except (TypeError, ValueError):
            return 0
        if p <= 0:
            return 0
        return _valid_priority(db, prio_map.get(p, p))

    now = datetime.now(timezone.utc).isoformat()

    existing_links = {
        (
            (r["name"] or "").strip().lower(),
            r["url_public"] or "",
            r["url_local"] or "",
        ): r
        for r in db.execute("SELECT * FROM links").fetchall()
    }
    links_by_uid = {
        r["uid"]: r
        for r in db.execute("SELECT * FROM links WHERE uid != ''").fetchall()
    }
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM links").fetchone()[0]
    imported_links = updated_links = skipped_links = 0
    for link in links:
        name = (link.get("name") or "").strip()
        if not name:
            continue
        url_public = _normalize_url(link.get("url_public", ""))
        url_local = _normalize_url(link.get("url_local", ""))
        uid = (link.get("uid") or "").strip()

        if uid and uid in links_by_uid:
            existing = links_by_uid[uid]
            incoming_date = link.get("updated_at") or ""
            if incoming_date and incoming_date > (existing["updated_at"] or ""):
                db.execute(
                    "UPDATE links SET name=?, descr=?, url_public=?, url_local=?, memo=?, "
                    "category_id=?, tags=?, updated_at=? WHERE id=?",
                    (
                        name,
                        link.get("descr", existing["descr"]),
                        url_public,
                        url_local,
                        link.get("memo", existing["memo"]),
                        ensure_category(link.get("category", "")),
                        _normalize_tags(link.get("tags", existing["tags"])),
                        incoming_date,
                        existing["id"],
                    ),
                )
                _favicon_cache.pop(existing["id"], None)
                updated_links += 1
            else:
                skipped_links += 1
            continue

        key = (name.lower(), url_public, url_local)
        if key in existing_links:
            existing = existing_links[key]
            if existing is not None:
                updates = {}
                if not (existing["descr"] or "").strip() and (link.get("descr") or "").strip():
                    updates["descr"] = link["descr"]
                if not (existing["memo"] or "").strip() and (link.get("memo") or "").strip():
                    updates["memo"] = link["memo"]
                if existing["category_id"] is None and (link.get("category") or "").strip():
                    updates["category_id"] = ensure_category(link["category"])
                if not (existing["tags"] or "").strip() and (link.get("tags") or "").strip():
                    updates["tags"] = _normalize_tags(link["tags"])
                if updates:
                    updates["updated_at"] = now
                    set_clause = ", ".join(f"{k} = ?" for k in updates)
                    db.execute(
                        f"UPDATE links SET {set_clause} WHERE id = ?",
                        (*updates.values(), existing["id"]),
                    )
                    updated_links += 1
                    continue
            skipped_links += 1
            continue
        existing_links[key] = None
        max_pos += 1
        new_uid = uid or str(uuid.uuid4())
        db.execute(
            "INSERT INTO links (name, descr, url_public, url_local, memo, position, "
            "category_id, uid, created_at, updated_at, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                link.get("descr", ""),
                url_public,
                url_local,
                link.get("memo", ""),
                max_pos,
                ensure_category(link.get("category", "")),
                new_uid,
                link.get("created_at") or now,
                link.get("updated_at") or now,
                _normalize_tags(link.get("tags", "")),
            ),
        )
        links_by_uid[new_uid] = db.execute(
            "SELECT * FROM links WHERE uid = ?", (new_uid,)
        ).fetchone()
        imported_links += 1

    existing_memos = {
        (r["content"] or "").strip()
        for r in db.execute("SELECT content FROM memos").fetchall()
    }
    memos_by_uid = {
        r["uid"]: r
        for r in db.execute("SELECT * FROM memos WHERE uid != ''").fetchall()
    }
    max_mpos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    imported_memos = updated_memos = skipped_memos = 0
    for memo in memos:
        if isinstance(memo, dict):
            content = (memo.get("content") or "").strip()
            uid = (memo.get("uid") or "").strip()
            created = memo.get("created_at") or now
            updated = memo.get("updated_at") or ""
            done = 1 if memo.get("done") else 0
            due_date = (memo.get("due_date") or "").strip()
            priority = map_priority(memo.get("priority"))
            subtasks = _subtasks_json(memo.get("subtasks"))
            project_id = ensure_project(memo.get("project", ""))
            images = _images_json(memo.get("images"), check_files=True)
            recurrence = _valid_recurrence(memo.get("recurrence"))
        else:
            content = str(memo).strip()
            uid = ""
            created = now
            updated = ""
            done = 0
            due_date = ""
            priority = 0
            subtasks = "[]"
            project_id = None
            images = "[]"
            recurrence = ""
        if not content:
            continue

        if uid and uid in memos_by_uid:
            existing = memos_by_uid[uid]
            if updated and updated > (existing["updated_at"] or ""):
                merged_images = images if images != "[]" else (existing["images"] or "[]")
                db.execute(
                    "UPDATE memos SET content=?, done=?, due_date=?, priority=?, "
                    "subtasks=?, project_id=?, images=?, recurrence=?, updated_at=? WHERE id=?",
                    (content, done, due_date, priority, subtasks, project_id, merged_images, recurrence, updated, existing["id"]),
                )
                updated_memos += 1
            else:
                skipped_memos += 1
            continue

        if content in existing_memos:
            skipped_memos += 1
            continue
        existing_memos.add(content)
        max_mpos += 1
        new_uid = uid or str(uuid.uuid4())
        db.execute(
            "INSERT INTO memos (content, position, created_at, uid, updated_at, "
            "done, due_date, priority, subtasks, project_id, images, recurrence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (content, max_mpos, created, new_uid, updated or created, done, due_date, priority, subtasks, project_id, images, recurrence),
        )
        memos_by_uid[new_uid] = db.execute(
            "SELECT * FROM memos WHERE uid = ?", (new_uid,)
        ).fetchone()
        imported_memos += 1

    existing_hist = {
        (r["memo_uid"], r["done_at"])
        for r in db.execute("SELECT memo_uid, done_at FROM memo_history").fetchall()
    }
    imported_history = 0
    for h in data.get("history") or []:
        if not isinstance(h, dict):
            continue
        h_content = (h.get("content") or "").strip()
        h_done_at = (h.get("done_at") or "").strip()
        if not h_content or not h_done_at:
            continue
        key = ((h.get("memo_uid") or "").strip(), h_done_at)
        if key in existing_hist:
            continue
        db.execute(
            "INSERT INTO memo_history (memo_uid, content, project, done_at) "
            "VALUES (?, ?, ?, ?)",
            (key[0], h_content, (h.get("project") or "").strip(), h_done_at),
        )
        existing_hist.add(key)
        imported_history += 1

    db.commit()
    return jsonify(
        {
            "imported": imported_links,
            "updated": updated_links,
            "skipped": skipped_links,
            "imported_memos": imported_memos,
            "updated_memos": updated_memos,
            "skipped_memos": skipped_memos,
            "imported_history": imported_history,
        }
    )


init_db()
