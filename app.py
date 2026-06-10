import json
import os
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "color" not in ccols:
        conn.execute("ALTER TABLE categories ADD COLUMN color TEXT DEFAULT ''")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "tags" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN tags TEXT DEFAULT ''")
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


# ---------------------------------------------------------------- memos


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
    rows = get_db().execute("SELECT * FROM memos ORDER BY position, id").fetchall()
    return jsonify([_memo_dict(r) for r in rows])


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
        "done, due_date, priority, subtasks, project_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            content,
            max_pos + 1,
            now,
            uid,
            now,
            1 if data.get("done") else 0,
            (data.get("due_date") or "").strip(),
            int(data.get("priority") or 0),
            _subtasks_json(data.get("subtasks")),
            _valid_project_id(db, data.get("project_id")),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_memo_dict(row)), 201


@app.route("/api/memos/<int:memo_id>", methods=["PUT"])
def update_memo(memo_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    existing = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    content = (data.get("content", existing["content"]) or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    done = 1 if data.get("done", existing["done"]) else 0
    due_date = (data.get("due_date", existing["due_date"]) or "").strip()
    priority = int(data.get("priority", existing["priority"]) or 0)
    if "subtasks" in data:
        subtasks = _subtasks_json(data.get("subtasks"))
    else:
        subtasks = existing["subtasks"] or "[]"
    project_id = (
        _valid_project_id(db, data.get("project_id"))
        if "project_id" in data
        else existing["project_id"]
    )
    db.execute(
        "UPDATE memos SET content=?, done=?, due_date=?, priority=?, subtasks=?, "
        "project_id=?, updated_at=? WHERE id=?",
        (
            content,
            done,
            due_date,
            priority,
            subtasks,
            project_id,
            datetime.now(timezone.utc).isoformat(),
            memo_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row))


@app.route("/api/memos/<int:memo_id>", methods=["DELETE"])
def delete_memo(memo_id):
    db = get_db()
    row = db.execute("SELECT images FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if row:
        _delete_image_files(row["images"])
    db.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
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
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_IMG_EXT:
        return jsonify({"error": "format non supporté (png, jpg, gif, webp)"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(UPLOAD_DIR, name))
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
    return jsonify(
        {
            "version": 8,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "categories": [dict(r) for r in categories],
            "projects": out_projects,
            "links": out_links,
            "memos": out_memos,
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
            priority = int(memo.get("priority") or 0)
            subtasks = _subtasks_json(memo.get("subtasks"))
            project_id = ensure_project(memo.get("project", ""))
            images = _images_json(memo.get("images"), check_files=True)
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
        if not content:
            continue

        if uid and uid in memos_by_uid:
            existing = memos_by_uid[uid]
            if updated and updated > (existing["updated_at"] or ""):
                merged_images = images if images != "[]" else (existing["images"] or "[]")
                db.execute(
                    "UPDATE memos SET content=?, done=?, due_date=?, priority=?, "
                    "subtasks=?, project_id=?, images=?, updated_at=? WHERE id=?",
                    (content, done, due_date, priority, subtasks, project_id, merged_images, updated, existing["id"]),
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
            "done, due_date, priority, subtasks, project_id, images) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (content, max_mpos, created, new_uid, updated or created, done, due_date, priority, subtasks, project_id, images),
        )
        memos_by_uid[new_uid] = db.execute(
            "SELECT * FROM memos WHERE uid = ?", (new_uid,)
        ).fetchone()
        imported_memos += 1

    db.commit()
    return jsonify(
        {
            "imported": imported_links,
            "updated": updated_links,
            "skipped": skipped_links,
            "imported_memos": imported_memos,
            "updated_memos": updated_memos,
            "skipped_memos": skipped_memos,
        }
    )


init_db()
