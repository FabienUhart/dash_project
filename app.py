import calendar
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import smtplib
import sqlite3
import ssl
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlparse

import re

# [VOTE-DECISION] Fuseau de l'app pour interpréter vote_deadline (ISO local sans TZ).
# tzdata (requirements) fournit la base IANA sur python:slim ; repli fixe si absente.
try:
    from zoneinfo import ZoneInfo
    _APP_TZ = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover - repli si tzdata manquante
    _APP_TZ = timezone(timedelta(hours=1))

# [HUB-EMAIL-INVITE] Charge .env en dev (os.environ déjà rempli par env_file en Docker).
# Secret SMTP lu UNIQUEMENT depuis l'environnement — jamais en base/export/front/logs.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import exifread
import requests
import urllib3
from flask import (
    Flask,
    Response,
    after_this_request,
    g,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

APP_VERSION = "23"  # X = version du format d'export (invariant 1) — v23 = [FOLDER-ATTACHMENTS] pièces jointes de dossier ; v22 = [ATTACHMENTS] ; v21 = [COMMENT-REACTIONS]


def _build_version():
    """Version complète de build « X.Y.Z » = premier tag [VX.Y.Z] de REALISATION.md
    (entrées newest-first, donc le premier rencontré = version courante). Source de
    vérité UNIQUE (pas de constante à maintenir en double). Repli sur APP_VERSION si
    le fichier manque (ex. image sans REALISATION.md — mais le Dockerfile le copie)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "REALISATION.md")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.search(r"\[V(\d+\.\d+\.\d+)\]", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return APP_VERSION


BUILD_VERSION = _build_version()
DB_PATH = os.environ.get("DB_PATH", "/app/data/dashboard.db")
UPLOAD_DIR = os.path.join(os.path.dirname(DB_PATH), "uploads")
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")
BACKUP_KEEP_DAYS = int(os.environ.get("BACKUP_KEEP_DAYS", "7"))
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
SAFE_IMG_NAME = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$")
DUE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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
# [ATTACHMENTS] pièces jointes jusqu'à 300 Mo/fichier → plafond de corps de requête à ~320 Mo
# (marge pour l'entête multipart + petits champs). Le worker gunicorn a besoin d'un --timeout
# allongé (Dockerfile) pour ne pas couper un upload lent de 300 Mo.
app.config["MAX_CONTENT_LENGTH"] = 320 * 1024 * 1024


# ─────────────────────────── [ATTACHMENTS] pièces jointes ───────────────────────────
# Généralise l'upload d'images : tout type de fichier accepté, stocké sur disque (nom seul en
# base). Types « aperçu sûr » (image/pdf/audio validés par SIGNATURE) → inline possible ; tout
# le reste → téléchargement forcé (Content-Disposition: attachment), jamais inline (anti-XSS :
# aucun HTML/SVG/script rendu). Table `attachments` additive, distincte de `memos.images`
# (qui reste dédiée aux photos EXIF/carte).
ATTACH_MAX = 300 * 1024 * 1024
SAFE_ATTACH_NAME = re.compile(r"^[0-9a-f]{32}(?:\.[A-Za-z0-9]{1,12})?$")


def _clean_orig_name(name):
    """Nom d'origine assaini (pour le download), extension conservée. Jamais de chemin/HTML."""
    base = os.path.basename(str(name or "")).strip()
    base = re.sub(r"[^\w.\- ]", "_", base)[:200]
    return base or "fichier"


def _attach_preview(head, ext):
    """(mime, preview) — preview True SEULEMENT pour image/pdf/audio validés par signature.
    Tout le reste → (mime deviné, False) = servi en téléchargement forcé (anti-XSS)."""
    if ext in ALLOWED_IMG_EXT and _looks_like_image(head, ext):
        return ("image/" + ("jpeg" if ext in ("jpg", "jpeg") else ext), True)
    if ext == "pdf" and head[:5] == b"%PDF-":
        return ("application/pdf", True)
    if ext == "mp3" and (head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
        return ("audio/mpeg", True)
    if ext == "wav" and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ("audio/wav", True)
    if ext == "ogg" and head[:4] == b"OggS":
        return ("audio/ogg", True)
    if ext in ("m4a", "aac") and head[4:8] == b"ftyp":
        return ("audio/mp4", True)
    if ext == "flac" and head[:4] == b"fLaC":
        return ("audio/flac", True)
    return (mimetypes.guess_type("x." + ext)[0] or "application/octet-stream", False)


def _save_attachment(f):
    """Sauvegarde STREAMÉE sur disque (jamais 300 Mo en RAM ; f.save = copyfileobj). Garde de
    taille APRÈS écriture (le plafond MAX_CONTENT_LENGTH borne déjà le corps). Retourne
    ({filename, orig, mime, size, preview}, None) ou (None, err)."""
    orig = _clean_orig_name(f.filename)
    raw_ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else ""
    ext = re.sub(r"[^a-z0-9]", "", raw_ext)[:12]
    head = f.stream.read(16)
    f.stream.seek(0)
    mime, preview = _attach_preview(head, ext)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = uuid.uuid4().hex + (("." + ext) if ext else "")
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)  # streamé sur disque
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size > ATTACH_MAX:
        try:
            os.remove(path)
        except OSError:
            pass
        return None, "fichier trop volumineux (max 300 Mo)"
    return {"filename": name, "orig": orig, "mime": mime, "size": size, "preview": preview}, None


def _attach_row_dict(r, url):
    return {
        "id": r["id"], "name": r["filename"],
        "orig_name": r["orig_name"] or r["filename"],
        "mime": r["mime"] or "", "size": r["size"] or 0,
        "preview": bool(r["preview"]), "created_at": r["created_at"], "url": url,
    }


def _attachments_map(db, memo_ids, url_fn):
    """{memo_id: [attach_dict]} pour un lot de mémos ; `url_fn(row)` construit l'URL (owner/invité)."""
    ids = [i for i in memo_ids if i is not None]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out = {}
    for r in db.execute(
        f"SELECT * FROM attachments WHERE memo_id IN ({ph}) ORDER BY id", ids
    ).fetchall():
        out.setdefault(r["memo_id"], []).append(_attach_row_dict(r, url_fn(r)))
    return out


def _serve_attachment_row(r, force_download):
    """Sert un fichier joint : inline si type « aperçu sûr » ET pas de download forcé, sinon
    téléchargement forcé (attachment) avec le nom d'origine. Jamais inline pour un non-média."""
    name = os.path.basename(r["filename"])
    if not SAFE_ATTACH_NAME.match(name):
        return "", 404
    inline = bool(r["preview"]) and not force_download
    return send_from_directory(
        UPLOAD_DIR, name, max_age=3600,
        as_attachment=(not inline),
        download_name=(r["orig_name"] or name),
        mimetype=(r["mime"] or None),
    )


def _delete_attachment_file(filename):
    name = os.path.basename(str(filename or ""))
    if SAFE_ATTACH_NAME.match(name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


def _import_memo_attachments(db, memo_id, memo_uid, att_list, now):
    """[ATTACHMENTS] v22 : import ADDITIF non destructif. N'ajoute que les fichiers dont le binaire
    EXISTE sur le volume (comme les images) et pas déjà rattachés (dédup par (memo_id, filename))."""
    if not isinstance(att_list, list):
        return
    have = {r["filename"] for r in db.execute(
        "SELECT filename FROM attachments WHERE memo_id = ?", (memo_id,)
    ).fetchall()}
    for a in att_list:
        if not isinstance(a, dict):
            continue
        fn = os.path.basename(str(a.get("filename") or ""))
        if not SAFE_ATTACH_NAME.match(fn) or fn in have:
            continue
        if not os.path.isfile(os.path.join(UPLOAD_DIR, fn)):
            continue  # binaire absent → ignoré (tolérant, comme les références d'image orphelines)
        try:
            size = int(a.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (memo_id, memo_uid, fn, _clean_orig_name(a.get("orig_name") or fn), str(a.get("mime") or "")[:100],
             size, 1 if a.get("preview") else 0, (a.get("created_at") or "").strip() or now, str(a.get("created_by") or "").strip()[:200]),
        )
        have.add(fn)


def _project_attachments_list(db, project_id, url_fn):
    """[FOLDER-ATTACHMENTS] Pièces jointes rattachées à UN dossier (project_id rempli, memo_id=0)."""
    return [
        _attach_row_dict(r, url_fn(r))
        for r in db.execute(
            "SELECT * FROM attachments WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
    ]


def _import_project_attachments(db, project_id, att_list, now):
    """[FOLDER-ATTACHMENTS] v23 : import ADDITIF non destructif des fichiers d'un DOSSIER. Même
    règle que les mémos : binaire présent + pas déjà rattaché (dédup par (project_id, filename))."""
    if not isinstance(att_list, list):
        return
    have = {r["filename"] for r in db.execute(
        "SELECT filename FROM attachments WHERE project_id = ?", (project_id,)
    ).fetchall()}
    for a in att_list:
        if not isinstance(a, dict):
            continue
        fn = os.path.basename(str(a.get("filename") or ""))
        if not SAFE_ATTACH_NAME.match(fn) or fn in have:
            continue
        if not os.path.isfile(os.path.join(UPLOAD_DIR, fn)):
            continue
        try:
            size = int(a.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, project_id, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (0, '', ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (project_id, fn, _clean_orig_name(a.get("orig_name") or fn), str(a.get("mime") or "")[:100],
             size, 1 if a.get("preview") else 0, (a.get("created_at") or "").strip() or now, str(a.get("created_by") or "").strip()[:200]),
        )
        have.add(fn)


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
    # [ONE-LINK-MULTI] Un hub par e-mail invité : agrège ses shares (un seul lien + un seul
    # code, stables). Additif, jamais exporté. Réutilise shares/share_guests tels quels.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS guest_hubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT DEFAULT '',
            hub_token TEXT NOT NULL UNIQUE,
            pin TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
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
    if "emoji" not in ccols:
        conn.execute("ALTER TABLE categories ADD COLUMN emoji TEXT DEFAULT ''")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "tags" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN tags TEXT DEFAULT ''")
    if "emoji" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN emoji TEXT DEFAULT ''")
    if "parent_id" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN parent_id INTEGER")
    if "emoji" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN emoji TEXT DEFAULT ''")
    if "location" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN location TEXT DEFAULT ''")
    if "location" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN location TEXT DEFAULT ''")
    # [MAP-TIMELINE] flag « voyage » héritable : NULL = hérite, 1 = voyage, 0 = non.
    if "is_trip" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN is_trip INTEGER DEFAULT NULL")
    if "title" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN title TEXT DEFAULT ''")
    if "assignees" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN assignees TEXT DEFAULT '[]'")
    if "deleted_at" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN deleted_at TEXT DEFAULT ''")
    if "description" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN description TEXT DEFAULT ''")
    if "marker_color" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN marker_color TEXT DEFAULT ''")
    if "marker_color" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN marker_color TEXT DEFAULT ''")
    if "map_groups" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN map_groups TEXT DEFAULT '[]'")
    if "due_time" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN due_time TEXT DEFAULT ''")
    if "created_by" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN created_by TEXT DEFAULT ''")
    # [VOTE-EXCLUDE] Mémo « hors vote » : visible/éditable mais PAS une option du vote.
    # Additif, non exporté (comme les voix — donnée d'atelier, pas de bump : export v20).
    if "vote_excluded" not in mcols:
        conn.execute("ALTER TABLE memos ADD COLUMN vote_excluded INTEGER DEFAULT 0")
    # [VOTE-DECISION] Dossier en mode vote (V1 « choisir un »). Colonnes additives sur
    # projects, jamais destructif (invariant 1). Absent = vote_enabled=0 → dossier normal.
    # vote_winner_ids (TEXT JSON) = gel de l'ex æquo §9.a ET marqueur « déjà figé »
    # ('' = jamais figé, '[]'/'[id,...]' = figé) — sert le snapshot paresseux idempotent.
    for col, ddl in (
        ("vote_enabled", "INTEGER DEFAULT 0"),
        ("vote_mode", "TEXT DEFAULT ''"),
        ("vote_deadline", "TEXT DEFAULT ''"),
        ("vote_closed", "INTEGER DEFAULT 0"),
        ("vote_winner_id", "INTEGER"),
        ("vote_winner_ids", "TEXT DEFAULT ''"),
    ):
        if col not in pcols:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {ddl}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memo_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_id INTEGER NOT NULL,
            memo_uid TEXT DEFAULT '',
            author TEXT NOT NULL DEFAULT 'moi',
            share_id INTEGER,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(memo_comments)").fetchall()}
    if "parent_id" not in ccols:
        conn.execute("ALTER TABLE memo_comments ADD COLUMN parent_id INTEGER")
    if "priority" not in ccols:
        conn.execute("ALTER TABLE memo_comments ADD COLUMN priority INTEGER DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comment_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL,
            viewer TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            UNIQUE(comment_id, viewer)
        )
        """
    )
    # [COMMENT-REACTIONS] v21 : réactions emoji (palette fixe) sur les commentaires. Additif,
    # jamais destructif. Une réaction max par (commentaire, emoji, votant). voter = '' owner /
    # « Nom <email> » invité (pattern created_by). Exportées (v21) ; purgées en cascade.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comment_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            voter TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(comment_id, emoji, voter)
        )
        """
    )
    # [FAVORITES] Projets/vues épinglés en tête de la sidebar. OWNER-ONLY, additif, JAMAIS
    # exporté/importé (pas de bump de format — reste v21) : donnée de confort locale, comme
    # les accusés de lecture. Ordre = date d'ajout (position). Purge en cascade à la
    # suppression du projet (delete_project). UNIQUE(kind, ref) → POST idempotent.
    # [FAVORITES V1.1] modèle TYPÉ {kind, ref} (kind='project'|'view'). Migration douce depuis
    # le schéma V1 (favorites(project_id PK)) : rebuild en portant chaque favori projet en
    # {kind:'project', ref:project_id}, sans perte. V1 jamais déployé → sur un serveur neuf on
    # crée directement le schéma typé. Donnée de confort NON exportée → ré-écriture in-place sûre.
    fav_cols = [r[1] for r in conn.execute("PRAGMA table_info(favorites)").fetchall()]
    if fav_cols and "kind" not in fav_cols:  # ancien schéma V1 présent → migrer vers typé
        conn.execute("ALTER TABLE favorites RENAME TO favorites_v1")
        conn.execute(
            """CREATE TABLE favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(kind, ref)
            )"""
        )
        conn.execute(
            "INSERT INTO favorites (kind, ref, position, created_at) "
            "SELECT 'project', CAST(project_id AS TEXT), position, created_at FROM favorites_v1"
        )
        conn.execute("DROP TABLE favorites_v1")
    else:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(kind, ref)
            )"""
        )
    # [ATTACHMENTS] Pièces jointes génériques (tout type) rattachées à un mémo. Additive,
    # distincte de memos.images (photos EXIF/carte). Noms de fichiers seuls en base, binaire
    # sur le volume data/uploads/. `preview` = type « aperçu sûr » (image/pdf/audio validé par
    # signature) ; sinon téléchargement forcé. `share_id` = provenance invité (comme les révisions).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_id INTEGER NOT NULL,
            memo_uid TEXT DEFAULT '',
            filename TEXT NOT NULL,
            orig_name TEXT DEFAULT '',
            mime TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            preview INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            created_by TEXT DEFAULT '',
            share_id INTEGER
        )
        """
    )
    # [FOLDER-ATTACHMENTS] v23 : une pièce jointe peut viser un DOSSIER au lieu d'un mémo.
    # Colonne additive `project_id` (nullable) : rempli = attache de dossier (memo_id = 0,
    # aucun mémo n'a l'id 0 → invisible des requêtes mémo `WHERE memo_id = ?`) ; NULL = attache
    # de mémo (comportement v22 inchangé). Additif, jamais destructif (invariant 1).
    acols = {r[1] for r in conn.execute("PRAGMA table_info(attachments)").fetchall()}
    if "project_id" not in acols:
        conn.execute("ALTER TABLE attachments ADD COLUMN project_id INTEGER")
    # [PHOTO-MAP] Métadonnées EXIF des images, donnée DÉRIVÉE des fichiers (jamais
    # exportée, pas de bump de version) : remplie à l'upload + backfill, pour que la
    # carte du projet lise les lieux/dates sans re-parser/re-géocoder à chaque ouverture.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS image_meta (
            filename TEXT PRIMARY KEY,
            memo_id INTEGER,
            memo_uid TEXT DEFAULT '',
            lat REAL,
            lng REAL,
            label TEXT DEFAULT '',
            taken_at TEXT DEFAULT '',
            has_gps INTEGER NOT NULL DEFAULT 0,
            created_at TEXT
        )
        """
    )
    # [VOTE-DECISION] Voix (personne, mémo) portées par un dossier. Additif, jamais
    # exporté en V1 (donnée d'atelier éphémère, précédent comment_seen). L'index unique
    # (project_id, voter) garantit « single = une voix par (personne, dossier) » en BASE ;
    # extension V2 multi = échange du seul index (colonnes inchangées, §3.1).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memo_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            memo_id INTEGER NOT NULL,
            voter TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    # [VOTE-GROUPS] V20.9 : votes NOMMÉS multiples par dossier. vote_id sur memo_votes :
    # NULL = voix du vote du DOSSIER (V1/V2, zéro migration) ; non NULL = voix d'un vote nommé.
    vcols = {r[1] for r in conn.execute("PRAGMA table_info(memo_votes)").fetchall()}
    if "vote_id" not in vcols:
        conn.execute("ALTER TABLE memo_votes ADD COLUMN vote_id INTEGER")
    # [VOTE-MULTI] V2 : index unique ÉLARGI (project_id, voter, memo_id) → autorise N mémos
    # par personne (mode multi). En single, l'unicité une-voix-par-personne devient
    # applicative (`_cast_vote` UPDATE la ligne). [VOTE-GROUPS] rendu PARTIEL `WHERE vote_id
    # IS NULL` : ne gouverne QUE le vote-dossier ; les votes nommés (project_id = porteur
    # partagé) sont protégés à part par `ux_memo_votes_named` (D1 : un mémo dans 2 votes).
    votes_idx = {r[1] for r in conn.execute("PRAGMA index_list(memo_votes)").fetchall()}
    if "ux_memo_votes_single" in votes_idx:
        conn.execute("DROP INDEX ux_memo_votes_single")
    _multi = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='ux_memo_votes_multi'"
    ).fetchone()
    if _multi and _multi[0] and "vote_id" not in (_multi[0] or ""):
        conn.execute("DROP INDEX ux_memo_votes_multi")  # ancien non partiel → recréer partiel
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_memo_votes_multi "
        "ON memo_votes(project_id, voter, memo_id) WHERE vote_id IS NULL"
    )
    # SQLite : les NULL sont distincts dans un UNIQUE → l'index partiel WHERE vote_id IS NOT NULL
    # protège les votes nommés (une voix par (vote, personne, mémo)) sans toucher le vote-dossier.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_memo_votes_named "
        "ON memo_votes(vote_id, voter, memo_id) WHERE vote_id IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            vote_mode TEXT DEFAULT '',
            vote_deadline TEXT DEFAULT '',
            vote_closed INTEGER DEFAULT 0,
            vote_winner_ids TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT,
            event_date TEXT DEFAULT ''
        )
        """
    )
    # [VOTE-V1.1] date de l'événement (créneau) d'un vote nommé — planifie le gagnant unique
    # à la clôture (due_date/due_time). Distinct de vote_deadline. Additif, non exporté.
    vtcols = {r[1] for r in conn.execute("PRAGMA table_info(votes)").fetchall()}
    if "event_date" not in vtcols:
        conn.execute("ALTER TABLE votes ADD COLUMN event_date TEXT DEFAULT ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_options (
            vote_id INTEGER NOT NULL,
            memo_id INTEGER NOT NULL,
            UNIQUE(vote_id, memo_id)
        )
        """
    )
    # [VOTE-GROUPS] permission de création héritable (modèle is_trip) : '' hérité / 'owner' / 'guests'.
    if "vote_create" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN vote_create TEXT DEFAULT ''")
    scols = {r[1] for r in conn.execute("PRAGMA table_info(shares)").fetchall()}
    if "pin" not in scols:
        conn.execute("ALTER TABLE shares ADD COLUMN pin TEXT DEFAULT ''")
    # [HUB-SESSION] jeton de session par hub (transporté en cookie HttpOnly) ; '' = aucune session.
    hcols = {r[1] for r in conn.execute("PRAGMA table_info(guest_hubs)").fetchall()}
    if "session_token" not in hcols:
        conn.execute("ALTER TABLE guest_hubs ADD COLUMN session_token TEXT DEFAULT ''")
    # [GUEST-EDIT] dernière connexion PAR INVITÉ (une date par personne, pas par dossier).
    if "last_seen_at" not in hcols:
        conn.execute("ALTER TABLE guest_hubs ADD COLUMN last_seen_at TEXT DEFAULT ''")
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
    # Footer owner : version COMPLÈTE de build (X.Y.Z) pour distinguer local/Zimaboard.
    return render_template("index.html", version=BUILD_VERSION)


@app.route("/api/version", methods=["GET"])
def api_version():
    # Version courante exposée (même exposition que /api/links, pas d'auth propre).
    return jsonify({"version": BUILD_VERSION, "export": int(APP_VERSION)})


# ---------------------------------------------------------------- links

LINK_FIELDS = (
    "id, name, descr, url_public, url_local, memo, position, category_id, "
    "uid, created_at, updated_at, tags"
)


def _clean_emoji(value):
    return (str(value or "")).strip()[:8]


def _clean_location(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return ""
    if not isinstance(value, dict):
        return ""
    try:
        lat = float(value.get("lat"))
        lng = float(value.get("lng"))
    except (TypeError, ValueError):
        return ""
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return ""
    label = str(value.get("label") or "").strip()[:80]
    return json.dumps({"lat": round(lat, 6), "lng": round(lng, 6), "label": label}, ensure_ascii=False)


def _parse_location(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _reverse_geocode(lat, lng):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lng,
                "zoom": 16,
                "accept-language": "fr",
            },
            headers={"User-Agent": f"dash-perso/{APP_VERSION}"},
            timeout=4,
        )
        if not r.ok:
            return ""
        data = r.json() or {}
        a = data.get("address") or {}
        place = (
            a.get("amenity")
            or a.get("suburb")
            or a.get("neighbourhood")
            or a.get("road")
            or ""
        )
        city = (
            a.get("city")
            or a.get("town")
            or a.get("village")
            or a.get("municipality")
            or ""
        )
        label = ", ".join(p for p in (place, city) if p) or (data.get("name") or "")
        return str(label)[:80]
    except Exception:
        return ""


# [IMAGE-EXIF] Lecture EXIF à la volée (jamais stockée, jamais exportée).
# Cache mémoire (lat,lng arrondis) -> label pour ne pas marteler Nominatim
# (mémorise aussi "" : un échec ne sera pas re-tenté). Non persistant — vidé au
# redémarrage, ce qui est conforme au contrat (rien en base).
_exif_geo_cache = {}


def _exif_dms_to_deg(value, ref):
    # value = liste de 3 Ratio exifread [deg, min, sec] ; ref = 'N'/'S'/'E'/'W'.
    try:
        d, m, s = [float(x.num) / float(x.den) for x in value.values]
        deg = d + m / 60.0 + s / 3600.0
        if str(ref).strip().upper() in ("S", "W"):
            deg = -deg
        return deg
    except Exception:
        return None


def _image_exif(name):
    # Renvoie {lat,lng,label,datetime} pour un fichier image déjà validé, ou None
    # si illisible / sans GPS ni date de prise de vue (no-op silencieux).
    path = os.path.join(UPLOAD_DIR, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        return None
    if not tags:
        return None

    lat = lng = None
    try:
        glat = tags.get("GPS GPSLatitude")
        glng = tags.get("GPS GPSLongitude")
        if glat is not None and glng is not None:
            lat = _exif_dms_to_deg(glat, tags.get("GPS GPSLatitudeRef", "N"))
            lng = _exif_dms_to_deg(glng, tags.get("GPS GPSLongitudeRef", "E"))
            if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                lat = lng = None
    except Exception:
        lat = lng = None

    dt = ""
    try:
        raw = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if raw:
            # Format EXIF "YYYY:MM:DD HH:MM:SS" -> ISO "YYYY-MM-DDTHH:MM:SS".
            d_part, _, t_part = str(raw).strip().partition(" ")
            d_iso = d_part.replace(":", "-")
            dt = (d_iso + "T" + t_part).strip("T")
    except Exception:
        dt = ""

    if lat is None and not dt:
        return None

    label = ""
    if lat is not None:
        key = (round(lat, 4), round(lng, 4))
        if key in _exif_geo_cache:
            label = _exif_geo_cache[key]
        else:
            label = _reverse_geocode(lat, lng)
            _exif_geo_cache[key] = label

    return {
        "lat": round(lat, 6) if lat is not None else None,
        "lng": round(lng, 6) if lng is not None else None,
        "label": label,
        "datetime": dt,
    }


def _record_image_meta(db, name, memo_id, memo_uid):
    # [PHOTO-MAP] Persiste l'EXIF d'une image à l'ajout (lieu + date de prise de vue),
    # donnée DÉRIVÉE. Réutilise _image_exif (un seul géocodage par coords, caché).
    # Idempotent (PK filename via INSERT OR REPLACE). Silencieux : ne bloque jamais
    # l'upload — un échec d'extraction laisse simplement l'image hors du calque carte.
    try:
        meta = _image_exif(name) or {}
        lat = meta.get("lat")
        lng = meta.get("lng")
        db.execute(
            "INSERT OR REPLACE INTO image_meta "
            "(filename, memo_id, memo_uid, lat, lng, label, taken_at, has_gps, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                name,
                memo_id,
                memo_uid or "",
                lat,
                lng,
                meta.get("label", "") or "",
                meta.get("datetime", "") or "",
                1 if lat is not None else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    except Exception:
        pass


def _forget_image_meta(db, names):
    # [PHOTO-MAP] Retire les lignes image_meta des fichiers supprimés définitivement
    # (la donnée dérivée suit le cycle de vie du fichier — pas de marqueur fantôme).
    # `db` peut être une connexion request (get_db) OU la connexion de _purge_trash.
    # `names` accepte : un nom seul, une liste de noms, ou une chaîne JSON-liste
    # (comme memos.images, pour réutiliser _delete_image_files au même endroit).
    if isinstance(names, str):
        s = names.strip()
        if s[:1] in ("[", "{"):
            try:
                names = json.loads(s)
            except Exception:
                names = []
        else:
            names = [names]
    names = [os.path.basename(str(n)) for n in (names or [])]
    if not names:
        return
    try:
        placeholders = ",".join("?" * len(names))
        db.execute(
            f"DELETE FROM image_meta WHERE filename IN ({placeholders})", names
        )
    except Exception:
        pass


def _geocode_search(q):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "jsonv2",
                "limit": 5,
                "accept-language": "fr",
                "addressdetails": 1,
            },
            headers={"User-Agent": f"dash-perso/{APP_VERSION}"},
            timeout=5,
        )
        if not r.ok:
            return []
        out = []
        for item in r.json() or []:
            try:
                a = item.get("address") or {}
                name = (
                    item.get("name")
                    or a.get("amenity")
                    or a.get("shop")
                    or a.get("tourism")
                    or a.get("road")
                    or ""
                )
                city = (
                    a.get("city")
                    or a.get("town")
                    or a.get("village")
                    or a.get("municipality")
                    or ""
                )
                short = ", ".join(p for p in (name, city) if p) or str(
                    item.get("display_name") or ""
                )[:60]
                out.append(
                    {
                        "label": short[:60],
                        "full": str(item.get("display_name") or "")[:160],
                        "lat": float(item["lat"]),
                        "lng": float(item["lon"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def _enrich_location(loc_json):
    loc = _parse_location(loc_json)
    if not loc or (loc.get("label") or "").strip():
        return loc_json
    label = _reverse_geocode(loc["lat"], loc["lng"])
    if label:
        loc["label"] = label
        return json.dumps(loc, ensure_ascii=False)
    return loc_json


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
            "SELECT c.id, c.name, c.position, c.color, c.emoji, COUNT(l.id) AS link_count "
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
    emoji = _clean_emoji(data.get("emoji"))
    cur = db.execute(
        "INSERT INTO categories (name, position, color, emoji) VALUES (?, ?, ?, ?)",
        (name, max_pos + 1, color, emoji),
    )
    db.commit()
    return (
        jsonify(
            {"id": cur.lastrowid, "name": name, "position": max_pos + 1, "color": color, "emoji": emoji}
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
    emoji = _clean_emoji(data.get("emoji", existing["emoji"]))
    db.execute(
        "UPDATE categories SET name = ?, color = ?, emoji = ? WHERE id = ?",
        (name, color, emoji, cat_id),
    )
    db.commit()
    return jsonify({"id": cat_id, "name": name, "color": color, "emoji": emoji})


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


def _clean_is_trip(value):
    """[MAP-TIMELINE] Tri-état : 1 = voyage, 0 = non, None = hérite. Jamais autre chose."""
    if value is True or value == 1:
        return 1
    if value is False or value == 0:
        return 0
    return None


def _resolve_trip(db, project_id):
    """[MAP-TIMELINE] Résolution « au plus proche » : remonte le projet puis ses
    ancêtres, le premier is_trip non NULL tranche. Aucun tranché → pas voyage
    (défaut). Garde anti-cycle (les cycles sont déjà interdits par _resolve_parent)."""
    seen = set()
    pid = project_id
    while pid is not None and pid not in seen:
        seen.add(pid)
        row = db.execute(
            "SELECT parent_id, is_trip FROM projects WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            return False
        v = _row_get(row, "is_trip", None)
        if v == 1:
            return True
        if v == 0:
            return False
        pid = row["parent_id"]
    return False


@app.route("/api/projects", methods=["GET"])
def list_projects():
    db = get_db()
    sql = (
        "SELECT p.id, p.name, p.color, p.position, p.tags, p.emoji, p.parent_id, p.location, p.description, p.marker_color, p.is_trip, "
        "p.vote_enabled, p.vote_mode, p.vote_deadline, p.vote_closed, p.vote_winner_id, p.vote_winner_ids, p.vote_create, "
        "COUNT(CASE WHEN m.done = 0 AND COALESCE(m.deleted_at, '') = '' THEN m.id END) AS memo_count "
        "FROM projects p LEFT JOIN memos m ON m.project_id = p.id "
        "GROUP BY p.id ORDER BY p.position, p.id"
    )
    rows = db.execute(sql).fetchall()
    # [VOTE-DECISION] gel paresseux du gagnant à la 1re lecture après deadline (§2.7).
    if [1 for r in rows if r["vote_enabled"] and _ensure_vote_snapshot(db, r)]:
        db.commit()
    owner_name = _owner_name(db)
    # [FOLDER-ATTACHMENTS] map project_id -> [attach_dict] en un seul SELECT.
    proj_att = {}
    for a in db.execute("SELECT * FROM attachments WHERE project_id IS NOT NULL ORDER BY id").fetchall():
        proj_att.setdefault(a["project_id"], []).append(_attach_row_dict(a, _owner_attach_url(a)))
    out = []
    for r in rows:
        d = dict(r)
        for k in ("vote_enabled", "vote_mode", "vote_deadline", "vote_closed", "vote_winner_id", "vote_winner_ids"):
            d.pop(k, None)
        d.update(_vote_project_payload(db, r, owner=True))
        # [VOTE-GROUPS] votes nommés + permission (brut pour les chips owner + résolu affiché).
        d["votes"] = _project_named_votes(db, r["id"], "", owner_name, is_owner=True)
        d["vote_create"] = _row_get(r, "vote_create", "") or ""
        d["vote_create_resolved"] = _resolve_vote_create(db, r["id"])
        d["can_create_vote"] = True  # owner crée toujours
        d["attachments"] = proj_att.get(r["id"], [])  # [FOLDER-ATTACHMENTS]
        out.append(d)
    return jsonify(out)


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
    emoji = _clean_emoji(data.get("emoji"))
    description = _clean_description(data.get("description"))
    marker_color = _clean_hex_color(data.get("marker_color"), "")
    is_trip = _clean_is_trip(data.get("is_trip"))  # [MAP-TIMELINE]
    cur = db.execute(
        "INSERT INTO projects (name, color, position, tags, emoji, description, marker_color, is_trip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, color, max_pos + 1, tags, emoji, description, marker_color, is_trip),
    )
    db.commit()
    return (
        jsonify(
            {"id": cur.lastrowid, "name": name, "color": color, "position": max_pos + 1, "tags": tags, "emoji": emoji, "description": description, "marker_color": marker_color, "is_trip": is_trip}
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
    emoji = _clean_emoji(data.get("emoji", existing["emoji"]))
    location = (
        _enrich_location(_clean_location(data.get("location")))
        if "location" in data
        else (existing["location"] or "")
    )
    description = (
        _clean_description(data.get("description"))
        if "description" in data
        else _row_get(existing, "description")
    )
    if "parent_id" in data:
        parent_id, err = _resolve_parent(db, project_id, data.get("parent_id"))
        if err:
            return jsonify({"error": err}), 400
    else:
        parent_id = existing["parent_id"]
    marker_color = (
        _clean_hex_color(data.get("marker_color"), "")
        if "marker_color" in data
        else _row_get(existing, "marker_color")
    )
    # [MAP-TIMELINE] flag voyage tri-état (owner-only — cette route est derrière Authelia).
    is_trip = (
        _clean_is_trip(data.get("is_trip"))
        if "is_trip" in data
        else _row_get(existing, "is_trip", None)
    )
    # [VOTE-DECISION] config du vote (owner-only, derrière Authelia). Additif : activer
    # ne touche pas les voix ; désactiver les CONSERVE (masquées, restaurées si réactivé).
    vote_enabled = (
        (1 if data.get("vote_enabled") else 0)
        if "vote_enabled" in data
        else _row_get(existing, "vote_enabled", 0)
    )
    vote_mode = (
        _clean_vote_mode(data.get("vote_mode"))
        if "vote_mode" in data
        else (_row_get(existing, "vote_mode", "") or "")
    )
    vote_deadline = (
        _clean_vote_deadline(data.get("vote_deadline"))
        if "vote_deadline" in data
        else (_row_get(existing, "vote_deadline", "") or "")
    )
    # [VOTE-GROUPS] permission de création de votes nommés ('' hérité / 'owner' / 'guests').
    vote_create = (
        _clean_vote_create(data.get("vote_create"))
        if "vote_create" in data
        else (_row_get(existing, "vote_create", "") or "")
    )
    db.execute(
        "UPDATE projects SET name = ?, color = ?, tags = ?, emoji = ?, parent_id = ?, location = ?, description = ?, marker_color = ?, is_trip = ?, "
        "vote_enabled = ?, vote_mode = ?, vote_deadline = ?, vote_create = ? WHERE id = ?",
        (name, color, tags, emoji, parent_id, location, description, marker_color, is_trip,
         vote_enabled, vote_mode, vote_deadline, vote_create, project_id),
    )
    # [VOTE-MULTI] bascule multi→single : purge des voix surnuméraires (garde la + récente
    # par votant). Le front prévient (confirm danger) ; le serveur applique la règle.
    if _clean_vote_mode(_row_get(existing, "vote_mode", "")) == "multi" and _clean_vote_mode(vote_mode) == "single":
        _collapse_votes_to_single(db, project_id)
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    out = {"id": project_id, "name": name, "color": color, "tags": tags, "emoji": emoji, "parent_id": parent_id, "location": _parse_location(location), "description": description, "marker_color": marker_color, "is_trip": is_trip}
    out.update(_vote_project_payload(db, row, owner=True))
    out["vote_create"] = vote_create
    out["vote_create_resolved"] = _resolve_vote_create(db, project_id)
    out["votes"] = _project_named_votes(db, project_id, "", _owner_name(db), is_owner=True)
    return jsonify(out)


@app.route("/api/projects/<int:project_id>/vote/close", methods=["POST"])
def close_vote(project_id):
    # [VOTE-DECISION] Clôture manuelle owner-only : fige le gagnant immédiatement.
    # {winner_id} optionnel = arbitrage d'un ex æquo (§9.a). Idempotent.
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not row["vote_enabled"]:
        return jsonify({"error": "pas un vote"}), 400
    winner_id = None
    data = request.get_json(silent=True) or {}
    if data.get("winner_id") not in (None, "", 0):
        try:
            winner_id = int(data["winner_id"])
        except (TypeError, ValueError):
            winner_id = None
    _freeze_vote(db, project_id, manual_winner_id=winner_id)
    db.execute("UPDATE projects SET vote_closed = 1 WHERE id = ?", (project_id,))
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return jsonify(_vote_project_payload(db, row, owner=True))


@app.route("/api/projects/<int:project_id>/vote/reopen", methods=["POST"])
def reopen_vote(project_id):
    # [VOTE-DECISION] Réouverture owner-only : EXIGE une deadline redéfinie ou effacée
    # (§2.7) ; refuse une deadline déjà dépassée (400). Efface le gel, conserve les voix.
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not row["vote_enabled"]:
        return jsonify({"error": "pas un vote"}), 400
    data = request.get_json(silent=True) or {}
    new_deadline = _clean_vote_deadline(data.get("vote_deadline"))
    if new_deadline and _deadline_passed(new_deadline):
        return jsonify({"error": "la nouvelle deadline est déjà dépassée"}), 400
    db.execute(
        "UPDATE projects SET vote_closed = 0, vote_winner_id = NULL, vote_winner_ids = '', vote_deadline = ? WHERE id = ?",
        (new_deadline, project_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return jsonify(_vote_project_payload(db, row, owner=True))


@app.route("/api/projects/<int:project_id>/vote/reset", methods=["POST"])
def reset_vote(project_id):
    # [VOTE-RESET] Remise à zéro owner-only : supprime TOUTES les voix + efface le gel +
    # rouvre. Même garde que reopen : deadline redéfinie/effacée (400 si dépassée). La
    # config (enabled/mode) et les mémos ne sont PAS touchés.
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if not row["vote_enabled"]:
        return jsonify({"error": "pas un vote"}), 400
    data = request.get_json(silent=True) or {}
    new_deadline = _clean_vote_deadline(data.get("vote_deadline"))
    if new_deadline and _deadline_passed(new_deadline):
        return jsonify({"error": "la nouvelle deadline est déjà dépassée"}), 400
    db.execute("DELETE FROM memo_votes WHERE project_id = ?", (project_id,))
    db.execute(
        "UPDATE projects SET vote_closed = 0, vote_winner_id = NULL, vote_winner_ids = '', vote_deadline = ? WHERE id = ?",
        (new_deadline, project_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return jsonify(_vote_project_payload(db, row, owner=True))


def _do_named_vote(db, vid, memo, voter, is_owner):
    """[VOTE-GROUPS] Voter dans un vote NOMMÉ. `memo` = ligne {id, project_id}. Renvoie une
    réponse Flask (payload du vote) ou une erreur 400/409. Scope + option revalidés serveur."""
    try:
        vid = int(vid)
    except (TypeError, ValueError):
        return jsonify({"error": "pas une option de vote"}), 400
    vote = _vote_row(db, vid)
    if not vote:
        return jsonify({"error": "pas une option de vote"}), 400
    if memo["id"] not in set(_vote_option_ids(db, vid, live_only=False)):
        return jsonify({"error": "pas une option de vote"}), 400
    if memo["id"] not in _vote_scope_memo_ids(db, vote["project_id"]):
        return jsonify({"error": "pas une option de vote"}), 400
    if _ensure_named_snapshot(db, vote):
        db.commit()
        vote = _vote_row(db, vid)
    if _named_vote_is_closed(vote):
        return jsonify({"error": "vote clos"}), 409
    _cast_named_vote(db, vote, memo["id"], voter)
    db.commit()
    return jsonify({"vote_id": vid, "project_id": vote["project_id"],
                    "vote": _named_vote_payload(db, vote, voter, _owner_name(db), is_owner)})


@app.route("/api/memos/<int:memo_id>/vote", methods=["POST"])
def vote_memo(memo_id):
    # [VOTE-DECISION/VOTE-GROUPS] Voter (owner, voter = ''). {vote_id} → vote nommé ;
    # absent/null = vote du DOSSIER (compat V1/V2). 400 pas-option, 409 clos.
    db = get_db()
    data = request.get_json(silent=True) or {}
    memo = db.execute(
        "SELECT id, project_id, vote_excluded FROM memos WHERE id = ? AND COALESCE(deleted_at, '') = ''",
        (memo_id,),
    ).fetchone()
    if not memo or not memo["project_id"]:
        return jsonify({"error": "pas une option de vote"}), 400
    vid = data.get("vote_id")
    if vid not in (None, "", 0):  # [VOTE-GROUPS] vote nommé (vote_excluded ne s'y applique pas)
        return _do_named_vote(db, vid, memo, "", is_owner=True)
    if _row_get(memo, "vote_excluded", 0):
        return jsonify({"error": "pas une option de vote"}), 400  # [VOTE-EXCLUDE]
    proj = db.execute("SELECT * FROM projects WHERE id = ?", (memo["project_id"],)).fetchone()
    if not proj or not proj["vote_enabled"]:
        return jsonify({"error": "pas une option de vote"}), 400
    if _ensure_vote_snapshot(db, proj):
        db.commit()
        proj = db.execute("SELECT * FROM projects WHERE id = ?", (memo["project_id"],)).fetchone()
    if _vote_is_closed(proj):
        return jsonify({"error": "vote clos"}), 409
    _cast_vote(db, proj["id"], memo_id, "", _clean_vote_mode(proj["vote_mode"]))  # [VOTE-MULTI]
    db.commit()
    pv = _vote_project_payload(db, proj, owner=True)
    return jsonify({"project_id": proj["id"], "vote": pv,
                    "options": _vote_options_payload(db, proj["id"], "", _owner_name(db), pv)})


# ─────────────────── [VOTE-GROUPS] routes votes nommés (owner, derrière Authelia) ───────────────────

def _create_named_vote(db, project_id, data, created_by):
    """Crée un vote nommé + ses options. Renvoie (payload, status). created_by = '' (owner) ou
    « Nom <email> » (invité). Revalide nom (unique/dossier), ≥1 option dans le périmètre."""
    name = _clean_vote_name(data.get("name"))
    if not name:
        return {"error": "nom requis"}, 400
    if _vote_name_exists(db, project_id, name):
        return {"error": "un vote porte déjà ce nom dans ce dossier"}, 409
    scope = _vote_scope_memo_ids(db, project_id)
    valid, seen = [], set()
    for m in (data.get("memo_ids") or []):
        try:
            mid = int(m)
        except (TypeError, ValueError):
            continue
        if mid in scope and mid not in seen:
            seen.add(mid)
            valid.append(mid)
    if not valid:
        return {"error": "au moins une option requise"}, 400
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO votes (project_id, name, vote_mode, vote_deadline, vote_closed, vote_winner_ids, created_by, created_at, event_date) "
        "VALUES (?, ?, ?, ?, 0, '', ?, ?, ?)",
        (project_id, name, _clean_vote_mode(data.get("vote_mode")), _clean_vote_deadline(data.get("vote_deadline")), created_by, now,
         _clean_vote_deadline(data.get("event_date"))),  # [VOTE-V1.1]
    )
    vid = cur.lastrowid
    _set_vote_options(db, vid, project_id, valid)
    db.commit()
    return None, vid


def _update_named_vote(db, vote, data):
    """Applique un PUT à un vote nommé (nom/mode/deadline/options). Renvoie (err, status) ou (None, None)."""
    vid = vote["id"]
    if "name" in data:
        name = _clean_vote_name(data.get("name"))
        if not name:
            return {"error": "nom requis"}, 400
        if _vote_name_exists(db, vote["project_id"], name, exclude_vid=vid):
            return {"error": "un vote porte déjà ce nom dans ce dossier"}, 409
        db.execute("UPDATE votes SET name = ? WHERE id = ?", (name, vid))
    if "vote_mode" in data:
        old_mode = _clean_vote_mode(vote["vote_mode"])
        new_mode = _clean_vote_mode(data.get("vote_mode"))
        db.execute("UPDATE votes SET vote_mode = ? WHERE id = ?", (new_mode, vid))
        if old_mode == "multi" and new_mode == "single":
            _collapse_named_to_single(db, vid)  # purge « plus récente gagne »
    if "vote_deadline" in data:
        db.execute("UPDATE votes SET vote_deadline = ? WHERE id = ?", (_clean_vote_deadline(data.get("vote_deadline")), vid))
    if "event_date" in data:  # [VOTE-V1.1]
        db.execute("UPDATE votes SET event_date = ? WHERE id = ?", (_clean_vote_deadline(data.get("event_date")), vid))
    if "memo_ids" in data:
        valid = _set_vote_options(db, vid, vote["project_id"], data.get("memo_ids"))
        if not valid:
            return {"error": "au moins une option requise"}, 400
    db.commit()
    return None, None


@app.route("/api/projects/<int:project_id>/votes", methods=["POST"])
def create_project_vote(project_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
        return jsonify({"error": "not found"}), 404
    err, res = _create_named_vote(db, project_id, request.get_json(silent=True) or {}, "")
    if err:
        return jsonify(err), res
    return jsonify(_named_vote_payload(db, _vote_row(db, res), "", _owner_name(db), True)), 201


@app.route("/api/votes/<int:vid>", methods=["PUT"])
def put_named_vote(vid):
    db = get_db()
    vote = _vote_row(db, vid)
    if not vote:
        return jsonify({"error": "not found"}), 404
    err, status = _update_named_vote(db, vote, request.get_json(silent=True) or {})
    if err:
        return jsonify(err), status
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), "", _owner_name(db), True))


@app.route("/api/votes/<int:vid>/close", methods=["POST"])
def close_named_vote(vid):
    db = get_db()
    vote = _vote_row(db, vid)
    if not vote:
        return jsonify({"error": "not found"}), 404
    _freeze_named_vote(db, vid)
    db.execute("UPDATE votes SET vote_closed = 1 WHERE id = ?", (vid,))
    db.commit()
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), "", _owner_name(db), True))


@app.route("/api/votes/<int:vid>/reopen", methods=["POST"])
def reopen_named_vote(vid):
    db = get_db()
    vote = _vote_row(db, vid)
    if not vote:
        return jsonify({"error": "not found"}), 404
    new_deadline = _clean_vote_deadline((request.get_json(silent=True) or {}).get("vote_deadline"))
    if new_deadline and _deadline_passed(new_deadline):
        return jsonify({"error": "la nouvelle deadline est déjà dépassée"}), 400
    db.execute("UPDATE votes SET vote_closed = 0, vote_winner_ids = '', vote_deadline = ? WHERE id = ?", (new_deadline, vid))
    db.commit()
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), "", _owner_name(db), True))


@app.route("/api/votes/<int:vid>/reset", methods=["POST"])
def reset_named_vote(vid):
    db = get_db()
    vote = _vote_row(db, vid)
    if not vote:
        return jsonify({"error": "not found"}), 404
    new_deadline = _clean_vote_deadline((request.get_json(silent=True) or {}).get("vote_deadline"))
    if new_deadline and _deadline_passed(new_deadline):
        return jsonify({"error": "la nouvelle deadline est déjà dépassée"}), 400
    db.execute("DELETE FROM memo_votes WHERE vote_id = ?", (vid,))
    db.execute("UPDATE votes SET vote_closed = 0, vote_winner_ids = '', vote_deadline = ? WHERE id = ?", (new_deadline, vid))
    db.commit()
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), "", _owner_name(db), True))


@app.route("/api/votes/<int:vid>", methods=["DELETE"])
def delete_named_vote_route(vid):
    db = get_db()
    if not _vote_row(db, vid):
        return jsonify({"error": "not found"}), 404
    _delete_named_vote(db, vid)  # supprime vote + options + voix ; AUCUN mémo supprimé
    db.commit()
    return "", 204


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    db = get_db()
    db.execute("UPDATE memos SET project_id = NULL WHERE project_id = ?", (project_id,))
    db.execute("UPDATE projects SET parent_id = NULL WHERE parent_id = ?", (project_id,))
    db.execute("DELETE FROM memo_votes WHERE project_id = ?", (project_id,))  # [VOTE-DECISION] dossier + nommés (porteur)
    # [VOTE-GROUPS] votes nommés du dossier + leurs options (leurs voix parties ci-dessus)
    db.execute("DELETE FROM vote_options WHERE vote_id IN (SELECT id FROM votes WHERE project_id = ?)", (project_id,))
    db.execute("DELETE FROM votes WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM favorites WHERE kind = 'project' AND ref = ?", (str(project_id),))  # [FAVORITES] purge en cascade
    # [FOLDER-ATTACHMENTS] purge en cascade des fichiers du dossier (binaires + lignes).
    for a in db.execute("SELECT filename FROM attachments WHERE project_id = ?", (project_id,)).fetchall():
        _delete_attachment_file(a["filename"])
    db.execute("DELETE FROM attachments WHERE project_id = ?", (project_id,))
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


# ─────────────────────────── [VOTE-DECISION] vote helpers ───────────────────────────
# Dossier en mode vote (V1 « choisir un »). État clos DÉRIVÉ à chaque lecture ; gagnant
# figé PARESSEUSEMENT (snapshot) à la 1re lecture constatant open→closed. Aucun cron.

VOTE_DEADLINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _clean_vote_deadline(value):
    """ISO local 'YYYY-MM-DDTHH:mm' (interprété Europe/Paris) ou '' — jamais de HTML."""
    v = str(value or "").strip()
    if not v:
        return ""
    # tolère les secondes que renvoient certains <input type=datetime-local>
    if len(v) == 19 and v[16] == ":":
        v = v[:16]
    return v if VOTE_DEADLINE_RE.match(v) else ""


def _clean_vote_mode(value):
    return "multi" if str(value or "").strip() == "multi" else "single"


def _deadline_passed(deadline):
    """La deadline (ISO local sans TZ = Europe/Paris, fuseau de l'app) est-elle dépassée ?"""
    d = str(deadline or "").strip()
    if not d:
        return False
    try:
        dt = datetime.fromisoformat(d)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_APP_TZ)
    return datetime.now(timezone.utc) > dt


def _vote_is_closed(row):
    return bool(row["vote_closed"]) or _deadline_passed(row["vote_deadline"])


def _voter_email(voter):
    """Partie e-mail d'un voter « Nom <email> » (identifiant STABLE, survit au renommage).
    '' pour le propriétaire (voter vide). Sert le match des cascades (§3.1)."""
    m = re.search(r"<([^<>]+)>\s*$", str(voter or ""))
    return (m.group(1).strip().lower() if m else "")


def _voter_key(voter):
    """Clé d'identité d'un voter : '' = owner, sinon e-mail (repli chaîne minuscule)."""
    v = str(voter or "").strip()
    if not v:
        return ""
    return _voter_email(v) or v.lower()


def _vote_display_name(voter, owner_name):
    """Nom AFFICHABLE d'un voter — jamais l'e-mail brut (owner-only, invariant 5)."""
    v = str(voter or "").strip()
    if not v:
        return owner_name
    m = re.match(r"^(.*?)\s*<[^<>]+>\s*$", v)
    name = (m.group(1).strip() if m else v)
    return name or owner_name


def _compute_winners(db, project_id):
    """(winner_id | None, [winner_ids]) selon les voix courantes. Options = mémos enfants
    DIRECTS non corbeille. Ex æquo → winner_id None, winner_ids = tous les mémos de tête.
    Zéro voix → (None, [])."""
    rows = db.execute(
        "SELECT v.memo_id AS mid, COUNT(*) AS n FROM memo_votes v "
        "JOIN memos m ON m.id = v.memo_id "
        "WHERE v.project_id = ? AND v.vote_id IS NULL AND m.project_id = ? AND COALESCE(m.deleted_at, '') = '' "  # [VOTE-GROUPS] vote-dossier seul
        "AND COALESCE(m.vote_excluded, 0) = 0 "  # [VOTE-EXCLUDE] un mémo exclu n'est jamais gagnant
        "GROUP BY v.memo_id",
        (project_id, project_id),
    ).fetchall()
    if not rows:
        return None, []
    top = max(r["n"] for r in rows)
    winners = sorted(r["mid"] for r in rows if r["n"] == top)
    if not winners:
        return None, []
    if len(winners) == 1:
        return winners[0], winners
    return None, winners


def _freeze_vote(db, project_id, manual_winner_id=None):
    """Écrit le snapshot du gagnant. manual_winner_id = arbitrage owner d'un ex æquo
    (§9.a) : n'est retenu que s'il fait partie des mémos de tête. Idempotent au niveau
    appelant (n'appeler que si pas déjà figé, sauf clôture manuelle)."""
    winner_id, winner_ids = _compute_winners(db, project_id)
    if manual_winner_id is not None and manual_winner_id in winner_ids:
        winner_id, winner_ids = manual_winner_id, [manual_winner_id]
    db.execute(
        "UPDATE projects SET vote_winner_id = ?, vote_winner_ids = ? WHERE id = ?",
        (winner_id, json.dumps(winner_ids), project_id),
    )
    return winner_id, winner_ids


def _ensure_vote_snapshot(db, row):
    """Gel PARESSEUX : si le vote est passé open→closed PAR DEADLINE et jamais figé
    (vote_winner_ids == ''), fige maintenant. Renvoie True si une écriture a eu lieu
    (l'appelant doit committer). Idempotent : ne refige jamais un gel existant."""
    if not row["vote_enabled"]:
        return False
    if row["vote_closed"]:
        return False  # clôture manuelle : déjà figée à la clôture
    if (row["vote_winner_ids"] or "") != "":
        return False  # déjà figé
    if not _deadline_passed(row["vote_deadline"]):
        return False
    _freeze_vote(db, row["id"])
    return True


def _vote_project_payload(db, row, owner=False):
    """Payload vote d'un dossier (résolu à la lecture). Suppose le snapshot déjà assuré."""
    if not row["vote_enabled"]:
        return {"vote_enabled": False}
    closed = _vote_is_closed(row)
    state = "closed" if closed else "open"
    winner_id, winner_ids = None, []
    if closed:
        wr = db.execute(
            "SELECT vote_winner_id, vote_winner_ids FROM projects WHERE id = ?",
            (row["id"],),
        ).fetchone()
        winner_id = wr["vote_winner_id"]
        try:
            winner_ids = json.loads(wr["vote_winner_ids"]) if (wr["vote_winner_ids"] or "") else []
        except Exception:
            winner_ids = []
    out = {
        "vote_enabled": True,
        "vote_mode": row["vote_mode"] or "single",
        "vote_deadline": row["vote_deadline"] or "",
        "vote_state": state,
        "vote_winner_id": winner_id,
        "vote_winner_ids": winner_ids,
    }
    if owner:
        out["vote_closed"] = bool(row["vote_closed"])
    return out


def _vote_voters_map(db, project_id):
    out = {}
    for r in db.execute(
        "SELECT memo_id, voter FROM memo_votes WHERE project_id = ? AND vote_id IS NULL",  # [VOTE-GROUPS] dossier
        (project_id,),
    ).fetchall():
        out.setdefault(r["memo_id"], []).append(r["voter"])
    return out


def _memo_vote_fields(voters, me, owner_name, pv, memo_id):
    """Champs vote d'un mémo-option pour l'appelant `me` (voter, '' = owner)."""
    mine_key = _voter_key(me) if me is not None else "\x00none"
    return {
        "vote_count": len(voters),
        "vote_voters": [_vote_display_name(v, owner_name) for v in voters],
        "vote_mine": any(_voter_key(v) == mine_key for v in voters),
        "is_winner": pv["vote_state"] == "closed"
        and (memo_id == pv["vote_winner_id"] or memo_id in pv["vote_winner_ids"]),
    }


def _find_vote(db, project_id, voter):
    """Voix existante de `voter` dans le dossier (match par e-mail → robuste au renommage)."""
    key = _voter_key(voter)
    for r in db.execute(
        "SELECT id, memo_id, voter FROM memo_votes WHERE project_id = ? AND vote_id IS NULL",  # [VOTE-GROUPS] dossier
        (project_id,),
    ).fetchall():
        if _voter_key(r["voter"]) == key:
            return r
    return None


def _find_vote_for_memo(db, project_id, memo_id, voter):
    """Voix de `voter` sur CE mémo précis (match par e-mail). [VOTE-MULTI]"""
    key = _voter_key(voter)
    for r in db.execute(
        "SELECT id, voter FROM memo_votes WHERE project_id = ? AND memo_id = ? AND vote_id IS NULL",  # [VOTE-GROUPS] dossier
        (project_id, memo_id),
    ).fetchall():
        if _voter_key(r["voter"]) == key:
            return r
    return None


def _cast_vote(db, project_id, memo_id, voter, mode="single"):
    """single : toggle (re-cliquer sa voix = retirer) / retarget (voter un autre = déplacer
    la voix unique). multi : toggle par (voter, mémo) — voter un 2ᵉ mémo n'écrase pas le 1ᵉʳ,
    re-cliquer retire cette voix-là seulement. [VOTE-MULTI]"""
    now = datetime.now(timezone.utc).isoformat()
    if mode == "multi":
        existing = _find_vote_for_memo(db, project_id, memo_id, voter)
        if existing:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (existing["id"],))
        else:
            db.execute(
                "INSERT INTO memo_votes (project_id, memo_id, voter, created_at) VALUES (?, ?, ?, ?)",
                (project_id, memo_id, voter, now),
            )
        return
    existing = _find_vote(db, project_id, voter)
    if existing:
        if existing["memo_id"] == memo_id:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (existing["id"],))
        else:
            db.execute(
                "UPDATE memo_votes SET memo_id = ?, voter = ?, created_at = ? WHERE id = ?",
                (memo_id, voter, now, existing["id"]),
            )
    else:
        db.execute(
            "INSERT INTO memo_votes (project_id, memo_id, voter, created_at) VALUES (?, ?, ?, ?)",
            (project_id, memo_id, voter, now),
        )


def _collapse_votes_to_single(db, project_id):
    """[VOTE-MULTI] Bascule multi→single : chaque votant ne garde que sa voix LA PLUS
    RÉCENTE (created_at), les autres sont supprimées (réutilise « plus récente gagne » §7)."""
    seen = set()
    for r in db.execute(
        "SELECT id, voter FROM memo_votes WHERE project_id = ? AND vote_id IS NULL "  # [VOTE-GROUPS] dossier
        "ORDER BY created_at DESC, id DESC",
        (project_id,),
    ).fetchall():
        k = _voter_key(r["voter"])
        if k in seen:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (r["id"],))
        else:
            seen.add(k)


def _vote_options_payload(db, project_id, me, owner_name, pv):
    """Liste [{memo_id, vote_count, vote_voters, vote_mine, is_winner}] des options d'un
    dossier au vote — renvoyée au client après un vote pour patcher l'UI sans recharger."""
    vmap = _vote_voters_map(db, project_id)
    opts = []
    for r in db.execute(
        "SELECT id FROM memos WHERE project_id = ? AND COALESCE(deleted_at, '') = '' "
        "AND COALESCE(vote_excluded, 0) = 0 ORDER BY position, id",  # [VOTE-EXCLUDE]
        (project_id,),
    ).fetchall():
        voters = vmap.get(r["id"], [])
        opts.append({"memo_id": r["id"], **_memo_vote_fields(voters, me, owner_name, pv, r["id"])})
    return opts


def _share_scope_project_ids(db, share):
    """Dossiers couverts par un partage (pour scoper les cascades de voix)."""
    if share["kind"] == "project":
        return _project_descendants(db, share["target_id"])
    row = db.execute(
        "SELECT project_id FROM memos WHERE id = ?", (share["target_id"],)
    ).fetchone()
    return [row["project_id"]] if row and row["project_id"] else []


def _delete_votes_for_email(db, email, project_ids):
    """Supprime les voix d'un e-mail (match STABLE §3.1), restreintes à `project_ids`
    (None = tous). Utilisé quand un invité perd un accès (retrait/refus/suppression)."""
    email = (email or "").strip().lower()
    if not email:
        return
    if project_ids is None:
        rows = db.execute("SELECT id, voter FROM memo_votes").fetchall()
    else:
        if not project_ids:
            return
        ph = ",".join("?" * len(project_ids))
        rows = db.execute(
            f"SELECT id, voter FROM memo_votes WHERE project_id IN ({ph})",
            list(project_ids),
        ).fetchall()
    for r in rows:
        if _voter_email(r["voter"]) == email:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (r["id"],))


# ───────────────────── [VOTE-GROUPS] V20.9 : votes NOMMÉS multiples par dossier ─────────────────────
# Un dossier porte N votes nommés (table `votes`), chacun sur un sous-ensemble EXPLICITE de
# ses mémos (dossier + descendants) via `vote_options`. Voix = memo_votes.vote_id NON NULL.
# Le vote-dossier V1/V2 (vote_id NULL) reste INCHANGÉ. Non exporté (D4).

VOTE_CREATE_VALUES = ("owner", "guests")


def _resolve_vote_create(db, project_id):
    """Permission de création héritable (modèle `_resolve_trip`) : le projet puis ses ancêtres,
    la 1re valeur non vide tranche. Défaut racine = 'guests' (les invités peuvent, D3)."""
    seen = set()
    pid = project_id
    while pid is not None and pid not in seen:
        seen.add(pid)
        row = db.execute("SELECT parent_id, vote_create FROM projects WHERE id = ?", (pid,)).fetchone()
        if not row:
            return "guests"
        v = (_row_get(row, "vote_create", "") or "").strip()
        if v in VOTE_CREATE_VALUES:
            return v
        pid = row["parent_id"]
    return "guests"


def _clean_vote_create(value):
    v = (str(value or "")).strip()
    return v if v in VOTE_CREATE_VALUES else ""


def _clean_vote_name(value):
    return re.sub(r"[<>]", "", str(value or "")).strip()[:80]


def _vote_scope_memo_ids(db, project_id):
    """Mémos éligibles comme options d'un vote de ce dossier : porteur + descendants, non corbeille."""
    ids = _project_descendants(db, project_id)
    ph = ",".join("?" * len(ids))
    return {
        r["id"] for r in db.execute(
            f"SELECT id FROM memos WHERE project_id IN ({ph}) AND COALESCE(deleted_at,'')=''", ids
        ).fetchall()
    }


def _vote_row(db, vid):
    return db.execute("SELECT * FROM votes WHERE id = ?", (vid,)).fetchone()


def _vote_option_ids(db, vid, live_only=True):
    if live_only:
        rows = db.execute(
            "SELECT o.memo_id AS memo_id FROM vote_options o JOIN memos m ON m.id = o.memo_id "
            "WHERE o.vote_id = ? AND COALESCE(m.deleted_at,'')='' ORDER BY m.position, m.id", (vid,)
        ).fetchall()
    else:
        rows = db.execute("SELECT memo_id FROM vote_options WHERE vote_id = ?", (vid,)).fetchall()
    return [r["memo_id"] for r in rows]


def _named_vote_is_closed(row):
    return bool(row["vote_closed"]) or _deadline_passed(row["vote_deadline"])


def _compute_named_winners(db, vid):
    """Mémos de tête d'un vote nommé (options vivantes du vote). Ex æquo inclus, zéro voix → []."""
    rows = db.execute(
        "SELECT v.memo_id AS mid, COUNT(*) AS n FROM memo_votes v "
        "JOIN vote_options o ON o.vote_id = v.vote_id AND o.memo_id = v.memo_id "
        "JOIN memos m ON m.id = v.memo_id "
        "WHERE v.vote_id = ? AND COALESCE(m.deleted_at,'')='' GROUP BY v.memo_id",
        (vid,),
    ).fetchall()
    if not rows:
        return []
    top = max(r["n"] for r in rows)
    return sorted(r["mid"] for r in rows if r["n"] == top)


def _freeze_named_vote(db, vid):
    winners = _compute_named_winners(db, vid)
    db.execute("UPDATE votes SET vote_winner_ids = ? WHERE id = ?", (json.dumps(winners), vid))
    # [VOTE-V1.1] planifie le gagnant à la clôture SI date d'événement posée ET gagnant UNIQUE.
    # Ex æquo → aucun write (pas deux mémos sur le même créneau ; l'owner départage puis re-clôt).
    # Le write ÉCRASE due_date/due_time du gagnant (objet même du vote-créneau). Même site que
    # le snapshot → vaut pour la clôture manuelle ET par deadline (_ensure_named_snapshot).
    if len(winners) == 1:
        row = db.execute("SELECT event_date FROM votes WHERE id = ?", (vid,)).fetchone()
        ev = _clean_vote_deadline(_row_get(row, "event_date", "")) if row else ""
        if ev:
            db.execute(
                "UPDATE memos SET due_date = ?, due_time = ?, updated_at = ? WHERE id = ?",
                (ev[:10], ev[11:16], datetime.now(timezone.utc).isoformat(), winners[0]),
            )
    return winners


def _ensure_named_snapshot(db, row):
    """Gel paresseux d'un vote nommé (mécanique `_ensure_vote_snapshot` généralisée)."""
    if row["vote_closed"]:
        return False
    if (row["vote_winner_ids"] or "") != "":
        return False
    if not _deadline_passed(row["vote_deadline"]):
        return False
    _freeze_named_vote(db, row["id"])
    return True


def _named_voters_map(db, vid):
    out = {}
    for r in db.execute("SELECT memo_id, voter FROM memo_votes WHERE vote_id = ?", (vid,)).fetchall():
        out.setdefault(r["memo_id"], []).append(r["voter"])
    return out


def _find_named_vote(db, vid, voter):
    key = _voter_key(voter)
    for r in db.execute("SELECT id, memo_id, voter FROM memo_votes WHERE vote_id = ?", (vid,)).fetchall():
        if _voter_key(r["voter"]) == key:
            return r
    return None


def _find_named_vote_for_memo(db, vid, memo_id, voter):
    key = _voter_key(voter)
    for r in db.execute("SELECT id, voter FROM memo_votes WHERE vote_id = ? AND memo_id = ?", (vid, memo_id)).fetchall():
        if _voter_key(r["voter"]) == key:
            return r
    return None


def _cast_named_vote(db, vote, memo_id, voter):
    """Toggle/retarget d'une voix dans un vote NOMMÉ (`vote` = ligne `votes`)."""
    now = datetime.now(timezone.utc).isoformat()
    vid, pid = vote["id"], vote["project_id"]
    if _clean_vote_mode(vote["vote_mode"]) == "multi":
        existing = _find_named_vote_for_memo(db, vid, memo_id, voter)
        if existing:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (existing["id"],))
        else:
            db.execute("INSERT INTO memo_votes (project_id, memo_id, voter, created_at, vote_id) VALUES (?,?,?,?,?)",
                       (pid, memo_id, voter, now, vid))
        return
    existing = _find_named_vote(db, vid, voter)
    if existing:
        if existing["memo_id"] == memo_id:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (existing["id"],))
        else:
            db.execute("UPDATE memo_votes SET memo_id = ?, voter = ?, created_at = ? WHERE id = ?",
                       (memo_id, voter, now, existing["id"]))
    else:
        db.execute("INSERT INTO memo_votes (project_id, memo_id, voter, created_at, vote_id) VALUES (?,?,?,?,?)",
                   (pid, memo_id, voter, now, vid))


def _collapse_named_to_single(db, vid):
    seen = set()
    for r in db.execute("SELECT id, voter FROM memo_votes WHERE vote_id = ? ORDER BY created_at DESC, id DESC", (vid,)).fetchall():
        k = _voter_key(r["voter"])
        if k in seen:
            db.execute("DELETE FROM memo_votes WHERE id = ?", (r["id"],))
        else:
            seen.add(k)


def _vote_manages(vote_row, viewer_key, is_owner):
    """Peut gérer ce vote ? owner = tout ; invité = seulement SES créations (match e-mail)."""
    if is_owner:
        return True
    return viewer_key != "" and _voter_key(vote_row["created_by"]) == viewer_key


def _named_vote_payload(db, row, viewer, owner_name, is_owner):
    """Payload d'un vote nommé. viewer = voter appelant ('' owner, None anonyme)."""
    closed = _named_vote_is_closed(row)
    winner_ids = []
    if closed:
        try:
            winner_ids = json.loads(row["vote_winner_ids"]) if (row["vote_winner_ids"] or "") else []
        except Exception:
            winner_ids = []
    viewer_key = _voter_key(viewer) if viewer is not None else "\x00none"
    vmap = _named_voters_map(db, row["id"])
    opts = []
    for mid in _vote_option_ids(db, row["id"]):
        voters = vmap.get(mid, [])
        opts.append({
            "memo_id": mid,
            "vote_count": len(voters),
            "vote_voters": [_vote_display_name(v, owner_name) for v in voters],
            "vote_mine": any(_voter_key(v) == viewer_key for v in voters),
            "is_winner": closed and mid in winner_ids,
        })
    created = (row["created_by"] or "").strip()
    mine = (is_owner and not created) or (viewer_key != "\x00none" and viewer_key != "" and _voter_key(created) == viewer_key)
    return {
        "id": row["id"],
        "name": row["name"],
        "vote_mode": _clean_vote_mode(row["vote_mode"]),
        "vote_deadline": row["vote_deadline"] or "",
        "event_date": _row_get(row, "event_date", "") or "",  # [VOTE-V1.1]
        "vote_state": "closed" if closed else "open",
        "vote_winner_ids": winner_ids,
        "options": opts,
        "mine": bool(mine),
        "created_by_display": _vote_display_name(created, owner_name) if created else owner_name,
    }


def _project_named_votes(db, project_id, viewer, owner_name, is_owner):
    """Votes nommés d'un dossier (gel paresseux inclus). [] si aucun."""
    rows = db.execute("SELECT * FROM votes WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()
    if [1 for r in rows if _ensure_named_snapshot(db, r)]:
        db.commit()
        rows = db.execute("SELECT * FROM votes WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()
    return [_named_vote_payload(db, r, viewer, owner_name, is_owner) for r in rows]


def _delete_named_vote(db, vid):
    db.execute("DELETE FROM memo_votes WHERE vote_id = ?", (vid,))
    db.execute("DELETE FROM vote_options WHERE vote_id = ?", (vid,))
    db.execute("DELETE FROM votes WHERE id = ?", (vid,))


def _set_vote_options(db, vid, project_id, memo_ids):
    """Fixe la liste d'options (adhésion EXPLICITE) : memo_ids revalidés dans le périmètre du
    dossier. Retirer une option → supprime ses voix DANS CE VOTE. Renvoie la liste validée."""
    scope = _vote_scope_memo_ids(db, project_id)
    wanted, seen = [], set()
    for m in (memo_ids or []):
        try:
            mid = int(m)
        except (TypeError, ValueError):
            continue
        if mid in scope and mid not in seen:
            seen.add(mid)
            wanted.append(mid)
    current = set(_vote_option_ids(db, vid, live_only=False))
    for mid in current - seen:  # retraits → purge des voix de cette option DANS CE VOTE
        db.execute("DELETE FROM vote_options WHERE vote_id = ? AND memo_id = ?", (vid, mid))
        db.execute("DELETE FROM memo_votes WHERE vote_id = ? AND memo_id = ?", (vid, mid))
    for mid in seen - current:
        db.execute("INSERT OR IGNORE INTO vote_options (vote_id, memo_id) VALUES (?, ?)", (vid, mid))
    return wanted


def _prune_memo_from_out_of_scope_votes(db, memo_id):
    """[VOTE-GROUPS §7] Mémo déplacé hors du périmètre d'un vote → retiré de ses options + voix
    de cette option purgées (revalidation serveur du périmètre porteur + descendants)."""
    for r in db.execute(
        "SELECT o.vote_id AS vid, v.project_id AS pid FROM vote_options o "
        "JOIN votes v ON v.id = o.vote_id WHERE o.memo_id = ?", (memo_id,)
    ).fetchall():
        if memo_id not in _vote_scope_memo_ids(db, r["pid"]):
            db.execute("DELETE FROM vote_options WHERE vote_id = ? AND memo_id = ?", (r["vid"], memo_id))
            db.execute("DELETE FROM memo_votes WHERE vote_id = ? AND memo_id = ?", (r["vid"], memo_id))


def _vote_name_exists(db, project_id, name, exclude_vid=None):
    q = "SELECT id FROM votes WHERE project_id = ? AND lower(name) = lower(?)"
    args = [project_id, name]
    if exclude_vid is not None:
        q += " AND id != ?"
        args.append(exclude_vid)
    return db.execute(q, args).fetchone() is not None


def _project_descendants(db, root_id):
    ids = [root_id]
    seen = {root_id}
    queue = [root_id]
    while queue:
        pid = queue.pop()
        for r in db.execute(
            "SELECT id FROM projects WHERE parent_id = ?", (pid,)
        ).fetchall():
            if r["id"] not in seen:
                seen.add(r["id"])
                ids.append(r["id"])
                queue.append(r["id"])
    return ids


def _project_photos(db, memo_ids):
    # [PHOTO-MAP] Lit le calque photo depuis image_meta (donnée dérivée, déjà géocodée
    # à l'upload) pour un ensemble de mémos NON corbeille. Aucune écriture, aucun appel
    # réseau. Renvoie aussi project_id + groups du mémo porteur → le front réutilise le
    # même focus sous-projet/groupe que les points-mémo. Photos sans GPS incluses (pas
    # de marqueur côté front, mais listables dans la frise si elles ont une date).
    if not memo_ids:
        return []
    placeholders = ",".join("?" * len(memo_ids))
    rows = db.execute(
        f"SELECT im.filename, im.memo_id, im.lat, im.lng, im.label, im.taken_at, "
        f"im.has_gps, m.project_id, m.map_groups, m.title, m.emoji "
        f"FROM image_meta im JOIN memos m ON m.id = im.memo_id "
        f"WHERE im.memo_id IN ({placeholders}) AND COALESCE(m.deleted_at, '') = '' "
        f"ORDER BY im.taken_at, im.filename",
        list(memo_ids),
    ).fetchall()
    out = []
    for r in rows:
        try:
            groups = json.loads(r["map_groups"] or "[]")
        except Exception:
            groups = []
        out.append({
            "filename": r["filename"],
            "memo_id": r["memo_id"],
            "project_id": r["project_id"],
            "lat": r["lat"],
            "lng": r["lng"],
            "label": r["label"] or "",
            "taken_at": r["taken_at"] or "",
            "has_gps": bool(r["has_gps"]),
            "groups": groups if isinstance(groups, list) else [],
            "title": (r["emoji"] + " " if r["emoji"] else "") + (r["title"] or ""),
        })
    return out


@app.route("/api/projects/<int:project_id>/photos", methods=["GET"])
def project_photos(project_id):
    # [PHOTO-MAP] Calque photo d'un projet, récursif sur ses sous-projets. Lecture seule.
    db = get_db()
    if not _valid_project_id(db, project_id):
        return jsonify({"error": "not found"}), 404
    proj_ids = _project_descendants(db, project_id)
    placeholders = ",".join("?" * len(proj_ids))
    memo_ids = [
        r["id"]
        for r in db.execute(
            f"SELECT id FROM memos WHERE project_id IN ({placeholders}) "
            "AND COALESCE(deleted_at, '') = ''",
            proj_ids,
        ).fetchall()
    ]
    return jsonify(_project_photos(db, memo_ids))


def _resolve_parent(db, project_id, parent_value):
    if parent_value in (None, "", 0):
        return None, None
    try:
        pid = int(parent_value)
    except (TypeError, ValueError):
        return None, "parent invalide"
    if pid == project_id:
        return None, "un projet ne peut pas être son propre parent"
    if not db.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone():
        return None, "projet parent introuvable"
    if project_id is not None and pid in _project_descendants(db, project_id):
        return None, "impossible : le parent choisi est un sous-projet de ce projet"
    return pid, None


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
            "SELECT p.id, p.name, p.color, p.position, "
            "COUNT(CASE WHEN COALESCE(m.deleted_at, '') = '' THEN m.id END) AS memo_count "
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


def _memo_dict(row, owner_name=None):
    d = dict(row)
    cb = (d.get("created_by") or "").strip()
    # '' = propriétaire (résolu à l'affichage, survit au renommage owner) ;
    # chaîne non vide = identité invité « Nom <email> ».
    d["created_by_display"] = cb if cb else (owner_name or "")
    try:
        d["subtasks"] = json.loads(d.get("subtasks") or "[]")
    except Exception:
        d["subtasks"] = []
    try:
        d["images"] = json.loads(d.get("images") or "[]")
    except Exception:
        d["images"] = []
    try:
        d["assignees"] = json.loads(d.get("assignees") or "[]")
    except Exception:
        d["assignees"] = []
    try:
        d["map_groups"] = json.loads(d.get("map_groups") or "[]")
    except Exception:
        d["map_groups"] = []
    d["location"] = _parse_location(d.get("location"))
    d["done"] = bool(d.get("done"))
    d["vote_excluded"] = bool(d.get("vote_excluded"))  # [VOTE-EXCLUDE]
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


def _assignees_json(value):
    """Liste de personnes (noms ou e-mails, saisie libre), nettoyée et dédupliquée."""
    if not isinstance(value, list):
        return "[]"
    clean, seen = [], set()
    for a in value:
        name = re.sub(r"[<>&\"']", "", str(a or "")).strip()[:60]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(name)
        if len(clean) >= 20:
            break
    return json.dumps(clean, ensure_ascii=False)


def _map_groups_json(value):
    """Groupes de carte d'un mémo (étiquettes nommées, saisie libre), nettoyés/dédupliqués."""
    if not isinstance(value, list):
        return "[]"
    clean, seen = [], set()
    for g in value:
        name = re.sub(r"[<>&\"']", "", str(g or "")).strip()[:60]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(name)
        if len(clean) >= 30:
            break
    return json.dumps(clean, ensure_ascii=False)


def _clean_title(value):
    return re.sub(r"[<>]", "", str(value or "")).strip()[:200]


def _clean_description(value):
    return re.sub(r"[<>]", "", str(value or "")).strip()[:1000]


def _clean_due_time(value):
    v = str(value or "").strip()
    return v if DUE_TIME_RE.match(v) else ""


@app.route("/api/memos", methods=["GET"])
def list_memos():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memos WHERE COALESCE(deleted_at, '') = '' ORDER BY position, id"
    ).fetchall()
    guest_last = {}
    for r in db.execute(
        "SELECT memo_id, editor, before IS NULL AS created, edited_at "
        "FROM memo_revisions WHERE share_id IS NOT NULL "
        "ORDER BY edited_at DESC, id DESC"
    ).fetchall():
        if r["memo_id"] not in guest_last:
            guest_last[r["memo_id"]] = r
    ccounts = {
        r["memo_id"]: r["n"]
        for r in db.execute(
            "SELECT memo_id, COUNT(*) AS n FROM memo_comments GROUP BY memo_id"
        ).fetchall()
    }
    owner_name = _owner_name(db)
    # [VOTE-DECISION] contexte vote : dossiers activés (+ gel paresseux), voix par mémo.
    enabled = db.execute("SELECT * FROM projects WHERE vote_enabled = 1").fetchall()
    if [1 for pr in enabled if _ensure_vote_snapshot(db, pr)]:
        db.commit()
        enabled = db.execute("SELECT * FROM projects WHERE vote_enabled = 1").fetchall()
    vpay = {pr["id"]: _vote_project_payload(db, pr, owner=True) for pr in enabled}
    vmap = {pr["id"]: _vote_voters_map(db, pr["id"]) for pr in enabled}
    amap = _attachments_map(db, [r["id"] for r in rows], lambda r: "/api/attachments/" + str(r["id"]))  # [ATTACHMENTS]
    out = []
    for row in rows:
        d = _memo_dict(row, owner_name)
        d["attachments"] = amap.get(d["id"], [])  # [ATTACHMENTS]
        g = guest_last.get(d["id"])
        if g:
            d["guest_editor"] = g["editor"]
            d["guest_action"] = "created" if g["created"] else "edited"
            d["guest_at"] = g["edited_at"]
        d["comment_count"] = ccounts.get(d["id"], 0)
        pv = vpay.get(d.get("project_id"))
        if pv and not d.get("vote_excluded"):  # [VOTE-EXCLUDE] mémo exclu = pas une option
            voters = vmap[d["project_id"]].get(d["id"], [])
            d.update(_memo_vote_fields(voters, "", owner_name, pv, d["id"]))
        out.append(d)
    return jsonify(out)


@app.route("/api/memos", methods=["POST"])
def create_memo():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    title = _clean_title(data.get("title"))
    if not content and not title:
        return jsonify({"error": "content required"}), 400
    db = get_db()
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    uid = str(uuid.uuid4())
    cur = db.execute(
        "INSERT INTO memos (content, position, created_at, uid, updated_at, "
        "done, due_date, due_time, priority, subtasks, project_id, recurrence, emoji, location, "
        "title, assignees, marker_color, map_groups) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            content,
            max_pos + 1,
            now,
            uid,
            now,
            1 if data.get("done") else 0,
            (data.get("due_date") or "").strip(),
            _clean_due_time(data.get("due_time")) if (data.get("due_date") or "").strip() else "",
            _valid_priority(db, data.get("priority")),
            _subtasks_json(data.get("subtasks")),
            _valid_project_id(db, data.get("project_id")),
            _valid_recurrence(data.get("recurrence")),
            _clean_emoji(data.get("emoji")),
            _enrich_location(_clean_location(data.get("location"))),
            title,
            _assignees_json(data.get("assignees")),
            _clean_hex_color(data.get("marker_color"), ""),
            _map_groups_json(data.get("map_groups")),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_memo_dict(row, _owner_name(db))), 201


def _memo_snapshot(content, done, due_date, priority, subtasks_json, recurrence,
                   title="", assignees_json="[]", due_time=""):
    try:
        subs = json.loads(subtasks_json or "[]")
    except Exception:
        subs = []
    try:
        assignees = json.loads(assignees_json or "[]")
    except Exception:
        assignees = []
    return {
        "content": content,
        "done": bool(done),
        "due_date": due_date or "",
        "due_time": due_time or "",
        "priority": priority or 0,
        "subtasks": subs,
        "recurrence": recurrence or "",
        "title": title or "",
        "assignees": assignees,
    }


def _row_get(row, key, default=""):
    try:
        return row[key] if row[key] is not None else default
    except (KeyError, IndexError):
        return default


def _log_revision(db, memo_row, after, editor, share_id=None):
    before = _memo_snapshot(
        memo_row["content"], memo_row["done"], memo_row["due_date"],
        memo_row["priority"], memo_row["subtasks"], memo_row["recurrence"],
        _row_get(memo_row, "title"), _row_get(memo_row, "assignees", "[]"),
        _row_get(memo_row, "due_time"),
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
    title = (
        _clean_title(data.get("title"))
        if "title" in data
        else _row_get(existing, "title")
    )
    if not content and not title:
        return {"error": "content required"}, 400
    assignees = (
        _assignees_json(data.get("assignees"))
        if "assignees" in data
        else (_row_get(existing, "assignees", "[]") or "[]")
    )
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
    due_time = (
        _clean_due_time(data.get("due_time"))
        if "due_time" in data
        else _row_get(existing, "due_time")
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

    if not due_date:
        due_time = ""
    after = _memo_snapshot(content, done, due_date, priority, subtasks, recurrence,
                           title, assignees, due_time)
    _log_revision(db, existing, after, editor, share_id)

    emoji = _clean_emoji(data.get("emoji", existing["emoji"]))
    location = (
        _enrich_location(_clean_location(data.get("location")))
        if "location" in data
        else (existing["location"] or "")
    )
    marker_color = (
        _clean_hex_color(data.get("marker_color"), "")
        if "marker_color" in data
        else _row_get(existing, "marker_color")
    )
    map_groups = (
        _map_groups_json(data.get("map_groups"))
        if "map_groups" in data
        else (_row_get(existing, "map_groups", "[]") or "[]")
    )
    db.execute(
        "UPDATE memos SET content=?, done=?, due_date=?, due_time=?, priority=?, subtasks=?, "
        "project_id=?, recurrence=?, emoji=?, location=?, title=?, assignees=?, "
        "marker_color=?, map_groups=?, updated_at=? WHERE id=?",
        (
            content,
            done,
            due_date,
            due_time,
            priority,
            subtasks,
            project_id,
            recurrence,
            emoji,
            location,
            title,
            assignees,
            marker_color,
            map_groups,
            now,
            memo_id,
        ),
    )
    db.commit()
    # [VOTE-GROUPS §7] Mémo déplacé → retiré des votes nommés dont il sort du périmètre.
    if project_id != existing["project_id"]:
        _prune_memo_from_out_of_scope_votes(db, memo_id)
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
    # [VOTE-EXCLUDE] owner-only (jamais dans _perform_memo_update → share ne peut pas le poser).
    # Sortir un mémo du vote supprime ses voix (cohérent : plus une option).
    if status == 200 and "vote_excluded" in data:
        excl = 1 if data.get("vote_excluded") else 0
        db.execute("UPDATE memos SET vote_excluded = ? WHERE id = ?", (excl, memo_id))
        if excl:
            db.execute("DELETE FROM memo_votes WHERE memo_id = ?", (memo_id,))
        db.commit()
        row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
        payload = _memo_dict(row, _owner_name(db))
    return jsonify(payload), status


@app.route("/api/memos/<int:memo_id>", methods=["DELETE"])
def delete_memo(memo_id):
    # Suppression douce : le mémo part dans la corbeille (restaurable), purge auto après BACKUP_KEEP_DAYS jours.
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE memos SET deleted_at = ? WHERE id = ?", (now, memo_id))
    db.commit()
    return "", 204


def _purge_memo_row(db, memo_id):
    row = db.execute("SELECT images FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if row:
        _delete_image_files(row["images"])
        _forget_image_meta(db, row["images"])  # [PHOTO-MAP]
    # [ATTACHMENTS] purge des fichiers joints + lignes (le binaire suit le mémo purgé).
    for a in db.execute("SELECT filename FROM attachments WHERE memo_id = ?", (memo_id,)).fetchall():
        _delete_attachment_file(a["filename"])
    db.execute("DELETE FROM attachments WHERE memo_id = ?", (memo_id,))
    db.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
    db.execute("DELETE FROM shares WHERE kind = 'memo' AND target_id = ?", (memo_id,))
    # [COMMENT-REACTIONS] purge des réactions AVANT les commentaires (comment_id → orphelin sinon).
    db.execute("DELETE FROM comment_reactions WHERE comment_id IN (SELECT id FROM memo_comments WHERE memo_id = ?)", (memo_id,))
    db.execute("DELETE FROM memo_comments WHERE memo_id = ?", (memo_id,))
    db.execute("DELETE FROM memo_votes WHERE memo_id = ?", (memo_id,))  # [VOTE-DECISION] voix dossier + nommées
    db.execute("DELETE FROM vote_options WHERE memo_id = ?", (memo_id,))  # [VOTE-GROUPS] retire des options nommées


@app.route("/api/trash", methods=["GET"])
def list_trash():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memos WHERE COALESCE(deleted_at, '') != '' "
        "ORDER BY deleted_at DESC, id DESC"
    ).fetchall()
    return jsonify([_memo_dict(r) for r in rows])


@app.route("/api/trash/<int:memo_id>/restore", methods=["POST"])
def restore_memo(memo_id):
    db = get_db()
    db.execute("UPDATE memos SET deleted_at = '' WHERE id = ?", (memo_id,))
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not row:
        return "", 404
    return jsonify(_memo_dict(row))


@app.route("/api/trash/<int:memo_id>", methods=["DELETE"])
def purge_memo(memo_id):
    db = get_db()
    _purge_memo_row(db, memo_id)
    db.commit()
    return "", 204


@app.route("/api/trash", methods=["DELETE"])
def empty_trash():
    db = get_db()
    ids = [
        r["id"]
        for r in db.execute(
            "SELECT id FROM memos WHERE COALESCE(deleted_at, '') != ''"
        ).fetchall()
    ]
    for mid in ids:
        _purge_memo_row(db, mid)
    db.commit()
    return jsonify({"purged": len(ids)})


@app.route("/api/memos/<int:memo_id>/duplicate", methods=["POST"])
def duplicate_memo(memo_id):
    db = get_db()
    src = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not src:
        return "", 404
    now = datetime.now(timezone.utc).isoformat()
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    title = _row_get(src, "title", "") or ""
    new_title = (title + " (copie)") if title else ""
    cur = db.execute(
        "INSERT INTO memos (content, position, created_at, uid, updated_at, "
        "done, due_date, due_time, priority, subtasks, project_id, recurrence, emoji, location, "
        "title, assignees) "
        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            src["content"], max_pos + 1, now, str(uuid.uuid4()), now,
            _row_get(src, "due_date", ""), _row_get(src, "due_time", ""),
            _row_get(src, "priority", 0),
            _row_get(src, "subtasks", "[]"), _row_get(src, "project_id"),
            _row_get(src, "recurrence", ""), _row_get(src, "emoji", ""),
            _row_get(src, "location", ""), new_title, _row_get(src, "assignees", "[]"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_memo_dict(row)), 201


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    name = os.path.basename(filename)
    if not SAFE_IMG_NAME.match(name):
        return "", 404
    return send_from_directory(UPLOAD_DIR, name, max_age=86400)


@app.route("/api/image-exif/<name>")
def image_exif(name):
    # [IMAGE-EXIF] Métadonnées photo lues à la volée (propriétaire). Lecture seule,
    # rien stocké. Symétrique de /uploads/<name> : tout fichier valide est lisible.
    name = os.path.basename(name)
    if not SAFE_IMG_NAME.match(name):
        return "", 404
    return jsonify(_image_exif(name) or {})


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
    # [PHOTO-MAP] Persiste l'EXIF du fichier (lieu/date) pour le calque carte. Donnée
    # dérivée : aucune écriture sur le mémo. Géocodage caché, fait ici une seule fois.
    _record_image_meta(db, name, memo_id, existing["uid"])
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
    _forget_image_meta(db, name)  # [PHOTO-MAP] la méta suit le fichier
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row))


# ─────────────────────────── [ATTACHMENTS] routes owner ───────────────────────────
def _owner_attach_url(r):
    return "/api/attachments/" + str(r["id"])


@app.route("/api/memos/<int:memo_id>/attachments", methods=["GET"])
def list_attachments(memo_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM memos WHERE id = ?", (memo_id,)).fetchone():
        return jsonify({"error": "not found"}), 404
    return jsonify(_attachments_map(db, [memo_id], _owner_attach_url).get(memo_id, []))


@app.route("/api/memos/<int:memo_id>/attachments", methods=["POST"])
def add_attachment(memo_id):
    db = get_db()
    memo = db.execute("SELECT id, uid FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not memo:
        return jsonify({"error": "not found"}), 404
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "file required"}), 400
    now = datetime.now(timezone.utc).isoformat()
    added_names = []
    for f in files:
        info, err = _save_attachment(f)
        if err:
            return jsonify({"error": err}), 400
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', NULL)",
            (memo_id, memo["uid"], info["filename"], info["orig"], info["mime"], info["size"], 1 if info["preview"] else 0, now),
        )
        added_names.append(info["orig"])
    _attach_log_comment(db, memo, True, added_names, "moi", None)  # [ATTACHMENTS-COMMENT]
    db.execute("UPDATE memos SET updated_at = ? WHERE id = ?", (now, memo_id))
    db.commit()
    return jsonify(_attachments_map(db, [memo_id], _owner_attach_url).get(memo_id, [])), 201


@app.route("/api/attachments/<int:att_id>", methods=["GET"])
def download_attachment(att_id):
    db = get_db()
    r = db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if not r:
        return "", 404
    return _serve_attachment_row(r, request.args.get("download") in ("1", "true", "yes"))


@app.route("/api/attachments/<int:att_id>", methods=["DELETE"])
def delete_attachment(att_id):
    db = get_db()
    r = db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if not r:
        return jsonify({"error": "not found"}), 404
    _delete_attachment_file(r["filename"])
    db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
    memo = db.execute("SELECT id, uid FROM memos WHERE id = ?", (r["memo_id"],)).fetchone()
    if memo:
        _attach_log_comment(db, memo, False, [r["orig_name"] or r["filename"]], "moi", None)  # [ATTACHMENTS-COMMENT]
    db.execute("UPDATE memos SET updated_at = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), r["memo_id"]))
    db.commit()
    return "", 204


# ─────────────────── [FOLDER-ATTACHMENTS] pièces jointes de dossier (owner) ───────────────────
@app.route("/api/projects/<int:project_id>/attachments", methods=["GET"])
def list_project_attachments(project_id):
    db = get_db()
    if not _valid_project_id(db, project_id):
        return jsonify({"error": "not found"}), 404
    return jsonify(_project_attachments_list(db, project_id, _owner_attach_url))


@app.route("/api/projects/<int:project_id>/attachments", methods=["POST"])
def add_project_attachment(project_id):
    db = get_db()
    if not _valid_project_id(db, project_id):
        return jsonify({"error": "not found"}), 404
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "file required"}), 400
    now = datetime.now(timezone.utc).isoformat()
    for f in files:
        info, err = _save_attachment(f)
        if err:
            return jsonify({"error": err}), 400
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, project_id, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (0, '', ?, ?, ?, ?, ?, ?, ?, '', NULL)",
            (project_id, info["filename"], info["orig"], info["mime"], info["size"], 1 if info["preview"] else 0, now),
        )
    db.commit()
    return jsonify(_project_attachments_list(db, project_id, _owner_attach_url)), 201


# ─────────────────── [FILES-VIEW] vues « retrouver les fichiers » (owner) ───────────────────
def _owner_img_url(name):
    return "/uploads/" + name


@app.route("/api/projects/<int:project_id>/files", methods=["GET"])
def project_files(project_id):
    db = get_db()
    if not _valid_project_id(db, project_id):
        return jsonify({"error": "not found"}), 404
    subtree = request.args.get("subtree", "1") not in ("0", "false", "no")
    pids = _project_descendants(db, project_id) if subtree else [project_id]
    ph = ",".join("?" * len(pids))
    memos = db.execute(
        f"SELECT id, project_id, title, content, images FROM memos "
        f"WHERE project_id IN ({ph}) AND COALESCE(deleted_at, '') = '' ORDER BY position, id", pids
    ).fetchall()
    return jsonify(_collect_files(db, memos, pids, lambda i: "/api/attachments/" + str(i), _owner_img_url))


@app.route("/api/files", methods=["GET"])
def all_files():
    db = get_db()
    pids = [r["id"] for r in db.execute("SELECT id FROM projects").fetchall()]
    memos = db.execute(
        "SELECT id, project_id, title, content, images FROM memos "
        "WHERE COALESCE(deleted_at, '') = '' ORDER BY position, id"
    ).fetchall()
    return jsonify(_collect_files(db, memos, pids, lambda i: "/api/attachments/" + str(i), _owner_img_url))


# ─────────────────── [PHOTO-BATCH-DOWNLOAD] téléchargement en .zip d'un lot ───────────────────
# Récupère d'un coup, en .zip, les fichiers d'un mémo OU d'un dossier (récursif optionnel). DEUX
# stocks de fichiers coexistent et sont affichés dans l'app : la table `attachments` (tout type,
# V22) et la colonne legacy `memos.images` (photos EXIF/carte). Le filtre « photos » = UNION
# (attachments mime image/* + toutes les images legacy). Le zip est construit sur un fichier
# TEMPORAIRE (jamais 300 Mo en RAM), streamé par send_file puis supprimé (after_this_request).
# ZIP_STORED : les médias sont déjà compressés → pas de re-compression coûteuse sur le Zimaboard.
def _zip_seg(s, fallback="fichier"):
    """Segment de chemin de zip assaini : jamais de séparateur, ni HTML, ni chemin absolu."""
    base = os.path.basename(str(s or "")).strip().replace("/", "_").replace("\\", "_")
    base = re.sub(r"[^\w.\- ]", "_", base).strip(". ")[:120]
    return base or fallback


def _memo_zip_files(db, memo_row, scope):
    """[{disk, name}] des fichiers d'un mémo pour `scope` ('all'|'photos'). Union attachments +
    images legacy ; ne renvoie QUE les binaires réellement présents sur le volume (tolérant)."""
    photos_only = scope != "all"
    out, seen = [], set()
    for r in db.execute(
        "SELECT * FROM attachments WHERE memo_id = ? ORDER BY id", (memo_row["id"],)
    ).fetchall():
        mime = r["mime"] or ""
        if photos_only and not mime.startswith("image/"):
            continue
        disk = os.path.basename(r["filename"] or "")
        if not SAFE_ATTACH_NAME.match(disk) or disk in seen:
            continue
        path = os.path.join(UPLOAD_DIR, disk)
        if not os.path.isfile(path):
            continue
        seen.add(disk)
        out.append({"disk": path, "name": r["orig_name"] or disk})
    try:
        imgs = json.loads(memo_row["images"] or "[]")  # legacy : toujours des photos
    except Exception:
        imgs = []
    for name in imgs:
        disk = os.path.basename(str(name or ""))
        if not SAFE_IMG_NAME.match(disk) or disk in seen:
            continue
        path = os.path.join(UPLOAD_DIR, disk)
        if not os.path.isfile(path):
            continue
        seen.add(disk)
        out.append({"disk": path, "name": disk})
    return out


# ─────────────────── [FILES-VIEW] agrégation « retrouver les fichiers » ───────────────────
def _project_crumb(db, project_id, cache):
    """Fil d'Ariane racine→dossier : [{id, name, emoji}]. Mémoïsé par appel (anti-boucle)."""
    if project_id in cache:
        return cache[project_id]
    chain, cur, guard = [], project_id, 0
    while cur is not None and guard < 60:
        r = db.execute("SELECT id, name, emoji, parent_id FROM projects WHERE id = ?", (cur,)).fetchone()
        if not r:
            break
        chain.append({"id": r["id"], "name": r["name"], "emoji": r["emoji"] or ""})
        cur = r["parent_id"]
        guard += 1
    chain.reverse()
    cache[project_id] = chain
    return chain


def _collect_files(db, memo_rows, project_ids, att_url, img_url):
    """[FILES-VIEW] Agrège en une liste plate : pièces jointes de DOSSIER (project_ids), pièces
    jointes de MÉMO + images legacy (memo_rows). Chaque entrée porte sa SOURCE (type + id cible +
    fil d'Ariane cliquable) pour « retrouver facilement ». URLs construites par les callbacks
    (owner / invité). Les images legacy sont toujours des photos (mime image/*)."""
    cache = {}
    out = []
    pset = list(project_ids or [])
    if pset:
        ph = ",".join("?" * len(pset))
        for a in db.execute(f"SELECT * FROM attachments WHERE project_id IN ({ph}) ORDER BY id", pset).fetchall():
            crumb = _project_crumb(db, a["project_id"], cache)
            out.append({
                "kind": "attachment", "id": a["id"], "filename": a["filename"],
                "orig_name": a["orig_name"] or a["filename"], "mime": a["mime"] or "",
                "size": a["size"] or 0, "preview": bool(a["preview"]), "created_at": a["created_at"] or "",
                "url": att_url(a["id"]),
                "source": {"type": "project", "id": a["project_id"],
                           "title": crumb[-1]["name"] if crumb else "", "crumb": crumb},
            })
    mids = [m["id"] for m in memo_rows]
    att_by_mid = {}
    if mids:
        phm = ",".join("?" * len(mids))
        for a in db.execute(f"SELECT * FROM attachments WHERE memo_id IN ({phm}) ORDER BY id", mids).fetchall():
            att_by_mid.setdefault(a["memo_id"], []).append(a)
    for m in memo_rows:
        crumb = _project_crumb(db, m["project_id"], cache) if m["project_id"] else []
        title = m["title"] or _text_excerpt(m["content"]) or ("Mémo #" + str(m["id"]))
        src = {"type": "memo", "id": m["id"], "title": title, "crumb": crumb}
        for a in att_by_mid.get(m["id"], []):
            out.append({
                "kind": "attachment", "id": a["id"], "filename": a["filename"],
                "orig_name": a["orig_name"] or a["filename"], "mime": a["mime"] or "",
                "size": a["size"] or 0, "preview": bool(a["preview"]), "created_at": a["created_at"] or "",
                "url": att_url(a["id"]), "source": src,
            })
        try:
            imgs = json.loads(m["images"] or "[]")
        except Exception:
            imgs = []
        for name in imgs:
            nm = os.path.basename(str(name or ""))
            if not SAFE_IMG_NAME.match(nm):
                continue
            out.append({
                "kind": "image", "id": None, "filename": nm, "orig_name": nm,
                "mime": "image/*", "size": 0, "preview": True, "created_at": "",
                "url": img_url(nm), "source": src,
            })
    return out


def _project_path_names(db, root_id, project_id):
    """Noms de dossiers assainis de l'enfant de `root_id` jusqu'à `project_id` inclus (vide si
    project_id == root_id). Anti-boucle par garde de profondeur."""
    chain, cur, guard = [], project_id, 0
    while cur is not None and cur != root_id and guard < 60:
        r = db.execute("SELECT name, parent_id FROM projects WHERE id = ?", (cur,)).fetchone()
        if not r:
            break
        chain.append(_zip_seg(r["name"], "dossier"))
        cur = r["parent_id"]
        guard += 1
    chain.reverse()
    return chain


def _project_zip_entries(db, root_id, scope, include_subs):
    """[{disk, arc}] pour un dossier : arborescence lisible SousDossier/TitreMémo/fichier.
    include_subs=False → uniquement les mémos DIRECTEMENT dans le dossier."""
    pids = _project_descendants(db, root_id) if include_subs else [root_id]
    ph = ",".join("?" * len(pids))
    rows = db.execute(
        f"SELECT * FROM memos WHERE project_id IN ({ph}) AND COALESCE(deleted_at, '') = '' "
        "ORDER BY position, id",
        pids,
    ).fetchall()
    entries = []
    for m in rows:
        files = _memo_zip_files(db, m, scope)
        if not files:
            continue
        title = _zip_seg(m["title"] or _text_excerpt(m["content"]) or ("memo-" + str(m["id"])), "memo-" + str(m["id"]))
        folder = "/".join(_project_path_names(db, root_id, m["project_id"]) + [title])
        for f in files:
            entries.append({"disk": f["disk"], "arc": folder + "/" + _zip_seg(f["name"])})
    # [FOLDER-ATTACHMENTS] fichiers rattachés aux dossiers eux-mêmes → à la racine du dossier.
    photos_only = scope != "all"
    for pid in pids:
        prefix = _project_path_names(db, root_id, pid)
        for r in db.execute("SELECT * FROM attachments WHERE project_id = ? ORDER BY id", (pid,)).fetchall():
            if photos_only and not (r["mime"] or "").startswith("image/"):
                continue
            disk = os.path.basename(r["filename"] or "")
            if not SAFE_ATTACH_NAME.match(disk):
                continue
            path = os.path.join(UPLOAD_DIR, disk)
            if not os.path.isfile(path):
                continue
            entries.append({"disk": path, "arc": "/".join(prefix + [_zip_seg(r["orig_name"] or disk)])})
    return entries


def _memo_zip_entries(db, memo_row, scope):
    """[{disk, arc}] à plat pour un mémo (arc = nom d'origine assaini)."""
    return [{"disk": f["disk"], "arc": _zip_seg(f["name"])} for f in _memo_zip_files(db, memo_row, scope)]


def _send_zip(entries, base_name):
    """Construit un zip temporaire (dédup des collisions d'arc), le streame en pièce jointe puis
    le supprime. base_name → nom du fichier ; send_file/Werkzeug encode RFC 5987 (accents OK)."""
    if not entries:
        return "", 404
    tmp = tempfile.NamedTemporaryFile(prefix="dashzip_", suffix=".zip", delete=False)
    tmp.close()
    try:
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            used = set()
            for e in entries:
                arc = e["arc"]
                if arc in used:
                    root, ext = os.path.splitext(arc)
                    i = 2
                    while f"{root} ({i}){ext}" in used:
                        i += 1
                    arc = f"{root} ({i}){ext}"
                used.add(arc)
                zf.write(e["disk"], arc)
    except Exception:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        return "", 500

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        return resp

    return send_file(
        tmp.name, mimetype="application/zip", as_attachment=True,
        download_name=_zip_seg(base_name, "fichiers") + ".zip", max_age=0,
    )


def _zip_scope(args):
    return "all" if args.get("scope") == "all" else "photos"


def _zip_subs(args):
    return args.get("subprojects", "1") not in ("0", "false", "no")


def _zip_base(label, scope, fallback):
    return (label or fallback) + ("-fichiers" if scope == "all" else "-photos")


@app.route("/api/memos/<int:memo_id>/download.zip")
def download_memo_zip(memo_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM memos WHERE id = ? AND COALESCE(deleted_at, '') = ''", (memo_id,)
    ).fetchone()
    if not row:
        return "", 404
    scope = _zip_scope(request.args)
    base = _zip_base(row["title"] or _text_excerpt(row["content"]), scope, "memo-" + str(memo_id))
    return _send_zip(_memo_zip_entries(db, row, scope), base)


@app.route("/api/projects/<int:project_id>/download.zip")
def download_project_zip(project_id):
    db = get_db()
    proj = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        return "", 404
    scope = _zip_scope(request.args)
    entries = _project_zip_entries(db, project_id, scope, _zip_subs(request.args))
    return _send_zip(entries, _zip_base(proj["name"], scope, "dossier-" + str(project_id)))


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


# ───────────────────────── [ONE-LINK-MULTI] hubs invité ─────────────────────────
# Le lien appartient à la personne (e-mail), pas au dossier. Un hub agrège les
# share_guests d'un e-mail sous un seul hub_token + un seul pin (invariant 5 :
# n'expose jamais plus que l'union de ses shares ; chaque /share garde son scope).

def _hub_by_token(db, hub_token):
    if not hub_token or len(hub_token) < 16:
        return None
    return db.execute(
        "SELECT * FROM guest_hubs WHERE hub_token = ?", (hub_token,)
    ).fetchone()


def _ensure_hub(db, email, name=""):
    """Garantit le hub d'un e-mail (idempotent). Crée hub_token + pin à la 1re fois ;
    ne change jamais un hub_token/pin existant. Met à jour le nom si fourni (cosmétique)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or len(email) > 120:
        return None
    name = (name or "").strip()[:60]
    row = db.execute("SELECT * FROM guest_hubs WHERE email = ?", (email,)).fetchone()
    if row:
        if name and name != (row["name"] or ""):
            db.execute("UPDATE guest_hubs SET name = ? WHERE id = ?", (name, row["id"]))
            db.commit()
            row = db.execute("SELECT * FROM guest_hubs WHERE id = ?", (row["id"],)).fetchone()
        return row
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO guest_hubs (email, name, hub_token, pin, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (email, name, secrets.token_urlsafe(24), f"{secrets.randbelow(10000):04d}", now),
    )
    db.commit()
    return db.execute("SELECT * FROM guest_hubs WHERE email = ?", (email,)).fetchone()


def _hub_folders(db, email):
    """Liste des accès (share_guests) d'un e-mail, joints à leur share. Cibles supprimées
    exclues. Renvoie de quoi ouvrir chaque /share sans re-code (guest_token inclus)."""
    email = (email or "").strip().lower()
    rows = db.execute(
        "SELECT g.guest_token, g.status, s.token, s.kind, s.target_id, s.can_edit "
        "FROM share_guests g JOIN shares s ON s.id = g.share_id "
        "WHERE lower(g.email) = ? ORDER BY g.id",
        (email,),
    ).fetchall()
    out = []
    for r in rows:
        if r["kind"] == "memo":
            t = db.execute(
                "SELECT content, title, emoji FROM memos WHERE id = ? "
                "AND COALESCE(deleted_at,'') = ''", (r["target_id"],)
            ).fetchone()
            if not t:
                continue
            label = _row_get(t, "title") or _text_excerpt(t["content"], 60)
            emoji, color = _row_get(t, "emoji"), ""
        else:
            t = db.execute(
                "SELECT name, emoji, color FROM projects WHERE id = ?", (r["target_id"],)
            ).fetchone()
            if not t:
                continue
            label, emoji, color = t["name"], _row_get(t, "emoji"), _row_get(t, "color")
        out.append({
            "token": r["token"],
            "guest_token": r["guest_token"],
            "label": label,
            "emoji": emoji or "",
            "color": color or "",
            "kind": r["kind"],
            "can_edit": bool(r["can_edit"]),
            "url": f"/share/{r['token']}",
        })
    return out


def _touch_guest_seen(db, email):
    """[GUEST-EDIT] Dernière connexion PAR INVITÉ (une date par personne, pas par
    dossier), posée quand l'invité PROUVE son identité : bon PIN (hub_approve),
    /data du hub prouvé (cookie ou header), ou X-Guest-Token APPROUVÉ sur un
    /share/<token>/data direct. Sans hub pour cet e-mail → no-op silencieux.
    Throttle 5 min : le refresh auto des pages invité tourne toutes les 15 s —
    sans garde, une écriture SQLite par invité actif toutes les 15 s (inutile
    sur le Zimaboard). Jamais exposé côté invité (owner-only via /api/hubs)."""
    email = (email or "").strip().lower()
    if not email:
        return
    hub = db.execute(
        "SELECT id, last_seen_at FROM guest_hubs WHERE email = ?", (email,)
    ).fetchone()
    if not hub:
        return
    now = datetime.now(timezone.utc)
    last = _row_get(hub, "last_seen_at") or ""
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < 300:
                return
        except ValueError:
            pass
    db.execute(
        "UPDATE guest_hubs SET last_seen_at = ? WHERE id = ?",
        (now.isoformat(), hub["id"]),
    )
    db.commit()


# Throttle des tentatives de PIN par hub_token (le PIN du hub déverrouille TOUS les
# dossiers de la personne → cible sensible). Fenêtre glissante en mémoire (best-effort
# par worker ; le plafond share_guests reste la garde dure côté écriture).
_HUB_PIN_ATTEMPTS = {}
_HUB_PIN_MAX = 10
_HUB_PIN_WINDOW = 600  # secondes


def _hub_pin_throttled(hub_token):
    now = time.time()
    hits = [t for t in _HUB_PIN_ATTEMPTS.get(hub_token, []) if now - t < _HUB_PIN_WINDOW]
    _HUB_PIN_ATTEMPTS[hub_token] = hits
    return len(hits) >= _HUB_PIN_MAX


def _hub_pin_fail(hub_token):
    _HUB_PIN_ATTEMPTS.setdefault(hub_token, []).append(time.time())


# ───────────────────────── [HUB-EMAIL-INVITE] envoi du lien-hub par e-mail ─────────────────────────
# Secret SMTP lu UNIQUEMENT depuis l'environnement. Jamais stocké en base, jamais exporté,
# jamais renvoyé au front, jamais loggué (ni SMTP_PASS ni le code en clair).

def _smtp_config():
    """Config SMTP depuis l'env. Renvoie None si SMTP_PASS vide (feature désactivée)."""
    pwd = (os.environ.get("SMTP_PASS") or "").strip()
    if not pwd:
        return None
    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host:
        return None
    try:
        port = int((os.environ.get("SMTP_PORT") or "587").strip())
    except ValueError:
        port = 587
    user = (os.environ.get("SMTP_USER") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or user or "").strip()
    if not sender:
        return None
    return {"host": host, "port": port, "user": user, "pwd": pwd, "from": sender}


# Rate-limit des envois (anti-abus). Fenêtre glissante en mémoire, par worker.
_INVITE_SENT = []
_INVITE_MAX = 5
_INVITE_WINDOW = 60  # secondes


def _invite_throttled():
    now = time.time()
    _INVITE_SENT[:] = [t for t in _INVITE_SENT if now - t < _INVITE_WINDOW]
    return len(_INVITE_SENT) >= _INVITE_MAX


def _send_hub_invite(cfg, to_email, name, hub_url, pin):
    """Envoie le lien-hub + code à l'e-mail DU HUB (jamais un destinataire libre du client).
    starttls sur 587. Lève en cas d'échec SMTP (le secret n'apparaît jamais dans le message)."""
    greeting = name.strip() if (name or "").strip() else "Bonjour"
    body = (
        f"{greeting},\n\n"
        f"Vous avez accès à des dossiers partagés sur le Dashboard.\n\n"
        f"Votre lien personnel (tous vos dossiers, à garder) :\n  {hub_url}\n\n"
        f"Votre code d'accès à 4 chiffres : {pin}\n\n"
        f"Ouvrez le lien, saisissez le code une fois, et vous accédez à tout.\n"
        f"Ce lien et ce code sont personnels — ne les partagez pas.\n"
    )
    msg = EmailMessage()
    msg["Subject"] = "Vos dossiers partagés — Dashboard"
    msg["From"] = cfg["from"]
    msg["To"] = to_email
    msg.set_content(body)  # set_content gère l'échappement/encodage (pas d'injection d'en-têtes)
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
        s.ehlo()
        s.starttls(context=ssl.create_default_context())
        s.ehlo()
        if cfg["user"]:
            s.login(cfg["user"], cfg["pwd"])
        s.send_message(msg)


def _share_memo_dict(row):
    d = _memo_dict(row)
    return {
        "id": d["id"],
        "content": d["content"],
        "done": d["done"],
        "due_date": d["due_date"],
        "due_time": d.get("due_time", "") or "",
        "priority": d["priority"],
        "subtasks": d["subtasks"],
        "images": d["images"],
        "recurrence": d["recurrence"],
        "emoji": d.get("emoji", ""),
        "project_id": d.get("project_id"),
        "location": d.get("location"),
        "title": d.get("title", "") or "",
        "assignees": d.get("assignees", []),
        "point_color": d.get("marker_color", "") or "",
        "map_groups": d.get("map_groups", []),
        "created_at": d.get("created_at", "") or "",
        "vote_excluded": bool(d.get("vote_excluded")),  # [VOTE-EXCLUDE] lecture invité (badge)
    }


def _share_scope_memos(db, share, deleted=False):
    cond = "COALESCE(deleted_at, '') {} ''".format("!=" if deleted else "=")
    if share["kind"] == "memo":
        row = db.execute(
            f"SELECT * FROM memos WHERE id = ? AND {cond}", (share["target_id"],)
        ).fetchone()
        return [row] if row else []
    ids = _project_descendants(db, share["target_id"])
    placeholders = ",".join("?" * len(ids))
    return db.execute(
        f"SELECT * FROM memos WHERE project_id IN ({placeholders}) AND {cond} "
        "ORDER BY position, id",
        ids,
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
                "SELECT content, title FROM memos WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = (
                (_row_get(t, "title") or _text_excerpt(t["content"])) if t else None
            )
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


@app.route("/api/guests/grant", methods=["POST"])
def grant_guest_project():
    # Ouvre l'accès d'un invité (par e-mail) à un projet : réutilise un partage projet
    # aux mêmes droits si possible, sinon en crée un, et pré-approuve l'invité.
    db = get_db()
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()[:60]
    can_edit = 1 if data.get("can_edit") else 0
    try:
        project_id = int(data.get("project_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "project_id requis"}), 400
    if not email or "@" not in email or len(email) > 120:
        return jsonify({"error": "e-mail invalide"}), 400
    proj = db.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        return jsonify({"error": "projet introuvable"}), 404
    now = datetime.now(timezone.utc).isoformat()
    share = db.execute(
        "SELECT * FROM shares WHERE kind = 'project' AND target_id = ? AND can_edit = ? "
        "ORDER BY id LIMIT 1",
        (project_id, can_edit),
    ).fetchone()
    if share:
        share_id, token, pin, reused = share["id"], share["token"], share["pin"], True
    else:
        token = secrets.token_urlsafe(24)
        pin = f"{secrets.randbelow(10000):04d}"
        cur = db.execute(
            "INSERT INTO shares (token, kind, target_id, can_edit, created_at, pin) "
            "VALUES (?, 'project', ?, ?, ?, ?)",
            (token, project_id, can_edit, now, pin),
        )
        share_id, reused = cur.lastrowid, False
    existing = db.execute(
        "SELECT * FROM share_guests WHERE share_id = ? AND email = ?", (share_id, email)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE share_guests SET status = 'approved', approved_at = ?, "
            "name = COALESCE(NULLIF(?, ''), name) WHERE id = ?",
            (now, name, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO share_guests (share_id, email, name, guest_token, status, created_at, approved_at) "
            "VALUES (?, ?, ?, ?, 'approved', ?, ?)",
            (share_id, email, name, secrets.token_urlsafe(24), now, now),
        )
    db.commit()
    hub = _ensure_hub(db, email, name)  # [ONE-LINK-MULTI] garantit le hub de l'e-mail
    return jsonify({
        "share_id": share_id, "token": token, "pin": pin, "can_edit": bool(can_edit),
        "project": proj["name"], "reused": reused, "url": f"/share/{token}",
        "hub_token": hub["hub_token"] if hub else "", "hub_pin": hub["pin"] if hub else "",
    })


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
    share = db.execute("SELECT * FROM shares WHERE id = ?", (share_id,)).fetchone()
    if share:  # [VOTE-DECISION] les invités perdent l'accès → leurs voix du périmètre partent
        scope = _share_scope_project_ids(db, share)
        for g in db.execute(
            "SELECT email FROM share_guests WHERE share_id = ?", (share_id,)
        ).fetchall():
            _delete_votes_for_email(db, g["email"], scope)
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


def _owner_name(db):
    """Nom du propriétaire (mentions @, assignations, accusés de lecture).
    Configurable dans Paramètres ; défaut « Fabien »."""
    return (_get_state(db, "owner_name", "Fabien") or "Fabien").strip() or "Fabien"


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_MARKER_COLOR = "#e53935"


def _clean_hex_color(value, default):
    """Renvoie une couleur #rrggbb valide, sinon le défaut. Jamais de HTML."""
    v = (str(value or "")).strip()
    return v if _HEX_COLOR_RE.match(v) else default


def _map_marker_color(db):
    """Couleur de repli des points de la carte (mémo sans priorité ni projet).
    Configurable dans Paramètres ; défaut rouge visible."""
    return _clean_hex_color(
        _get_state(db, "map_marker_color", DEFAULT_MARKER_COLOR), DEFAULT_MARKER_COLOR
    )


@app.route("/api/settings", methods=["GET"])
def get_settings():
    db = get_db()
    return jsonify(
        {
            "owner_name": _owner_name(db),
            "map_marker_color": _map_marker_color(db),
            "reaction_emojis": _reaction_palette(db),  # [REACTION-PALETTE] palette configurable
            # [HUB-EMAIL-INVITE] booléen seulement — JAMAIS le secret SMTP.
            "smtp_enabled": _smtp_config() is not None,
        }
    )


@app.route("/api/settings", methods=["PUT"])
def put_settings():
    db = get_db()
    data = request.get_json(silent=True) or {}
    if "owner_name" in data:
        name = (str(data.get("owner_name") or "")).strip()[:40]
        if not name:
            return jsonify({"error": "nom vide"}), 400
        _set_state(db, "owner_name", name)
        db.commit()
    if "map_marker_color" in data:
        color = _clean_hex_color(data.get("map_marker_color"), DEFAULT_MARKER_COLOR)
        _set_state(db, "map_marker_color", color)
        db.commit()
    if "reaction_emojis" in data:
        # [REACTION-PALETTE] Config owner-only de la palette. Validation STRICTE de chaque emoji
        # (un seul grapheme, aucune injection). Liste vide autorisée (owner retire tout).
        raw = data.get("reaction_emojis")
        if not isinstance(raw, list):
            return jsonify({"error": "reaction_emojis doit être une liste"}), 400
        if len(raw) > 40:
            return jsonify({"error": "trop de réactions"}), 400
        cleaned = []
        for e in raw:
            c = _clean_reaction_emoji(e)
            if not c:
                return jsonify({"error": "emoji invalide"}), 400
            if c not in cleaned:
                cleaned.append(c)
        _set_state(db, "reaction_emojis", json.dumps(cleaned, ensure_ascii=False))
        db.commit()
    return jsonify(
        {
            "owner_name": _owner_name(db),
            "map_marker_color": _map_marker_color(db),
            "reaction_emojis": _reaction_palette(db),
        }
    )


# [FAVORITES] Projets/vues épinglés (owner-only, derrière Authelia — RIEN côté /share). Modèle
# TYPÉ {kind, ref} : kind='project' (ref=id projet) | 'view' (ref ∈ FAV_VIEWS). Liste ordonnée par
# position (date d'ajout) ; les favoris projet dont le projet a disparu sont filtrés (défense en
# profondeur avec la purge en cascade de delete_project). Jamais exporté. Toggle par (kind, ref).
FAV_VIEWS = ("plan", "agenda", "memos")


def _clean_favorite(data):
    """Valide un favori {kind, ref} → (kind, ref_text) ou (None, None). ref stocké en TEXT."""
    kind = str((data or {}).get("kind") or "").strip()
    ref = (data or {}).get("ref")
    if kind == "view":
        r = str(ref if ref is not None else "").strip()
        return ("view", r) if r in FAV_VIEWS else (None, None)
    if kind == "project":
        try:
            return ("project", str(int(ref)))
        except (TypeError, ValueError):
            return (None, None)
    return (None, None)


def _favorites_payload(db):
    """Liste TYPÉE ordonnée des favoris, projets disparus filtrés (défense en profondeur)."""
    proj_ids = {r["id"] for r in db.execute("SELECT id FROM projects").fetchall()}
    out = []
    for r in db.execute(
        "SELECT kind, ref FROM favorites ORDER BY position, created_at, id"
    ).fetchall():
        if r["kind"] == "project":
            try:
                pid = int(r["ref"])
            except (TypeError, ValueError):
                continue
            if pid in proj_ids:  # projet supprimé → jamais renvoyé
                out.append({"kind": "project", "ref": pid})
        elif r["kind"] == "view" and r["ref"] in FAV_VIEWS:
            out.append({"kind": "view", "ref": r["ref"]})
    return out


@app.route("/api/favorites", methods=["GET"])
def list_favorites():
    db = get_db()
    return jsonify({"favorites": _favorites_payload(db)})


@app.route("/api/favorites/reorder", methods=["PUT"])
def reorder_favorites():
    # [FAVORITES V1.2] Réordonne la liste TYPÉE (owner-only). Reçoit l'ordre complet [{kind,ref}] ;
    # revalide chaque item, met à jour `position` pour ceux qui existent, ignore les disparus
    # (aucun 500). Ordre MIXTE projet/vue assumé. Renvoie la liste à jour comme GET.
    db = get_db()
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list):
        return jsonify({"error": "order doit être une liste"}), 400
    pos = 0
    for it in order:
        kind, ref = _clean_favorite(it if isinstance(it, dict) else {})
        if not kind:
            continue
        cur = db.execute(
            "UPDATE favorites SET position = ? WHERE kind = ? AND ref = ?", (pos, kind, ref)
        )
        if cur.rowcount:  # item réellement présent → position consommée
            pos += 1
    db.commit()
    return jsonify({"favorites": _favorites_payload(db)})


@app.route("/api/favorites", methods=["POST"])
def add_favorite():
    db = get_db()
    kind, ref = _clean_favorite(request.get_json(silent=True) or {})
    if not kind:
        return jsonify({"error": "favori invalide"}), 400
    if kind == "project" and not db.execute(
        "SELECT 1 FROM projects WHERE id = ?", (int(ref),)
    ).fetchone():
        return jsonify({"error": "not found"}), 404
    # Idempotent : ne recrée ni ne réordonne un favori déjà présent (INSERT OR IGNORE).
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM favorites").fetchone()[0]
    db.execute(
        "INSERT OR IGNORE INTO favorites (kind, ref, position, created_at) VALUES (?, ?, ?, ?)",
        (kind, ref, max_pos + 1, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return jsonify({"favorite": True, "kind": kind, "ref": ref})


@app.route("/api/favorites", methods=["DELETE"])
def remove_favorite():
    db = get_db()
    kind, ref = _clean_favorite(request.get_json(silent=True) or {})
    if not kind:
        return jsonify({"error": "favori invalide"}), 400
    db.execute("DELETE FROM favorites WHERE kind = ? AND ref = ?", (kind, ref))
    db.commit()
    return jsonify({"favorite": False, "kind": kind, "ref": ref})


@app.route("/api/guests", methods=["GET"])
def list_guests():
    db = get_db()
    rows = db.execute(
        "SELECT g.*, s.kind, s.target_id, s.can_edit, s.token FROM share_guests g "
        "JOIN shares s ON s.id = g.share_id ORDER BY g.id DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("guest_token", None)
        if r["kind"] == "memo":
            t = db.execute(
                "SELECT content, title FROM memos WHERE id = ?", (r["target_id"],)
            ).fetchone()
            d["target"] = (
                (_row_get(t, "title") or _text_excerpt(t["content"], 60))
                if t else "(supprimé)"
            )
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


@app.route("/api/guests/rename", methods=["POST"])
def rename_guest():
    """Renomme un invité (tous ses accès, par e-mail). Cosmétique : les attributions
    déjà enregistrées (assignés, commentaires) gardent l'ancien nom."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (str(data.get("name") or "")).strip()[:60]
    if not email:
        return jsonify({"error": "email requis"}), 400
    if not name:
        return jsonify({"error": "nom vide"}), 400
    db = get_db()
    cur = db.execute(
        "UPDATE share_guests SET name = ? WHERE lower(email) = ?", (name, email)
    )
    db.commit()
    return jsonify({"email": email, "name": name, "updated": cur.rowcount})


@app.route("/api/guests/update", methods=["POST"])
def update_guest_identity():
    """[GUEST-EDIT] Modifie l'identité d'un invité (owner-only) : nom et/ou e-mail.
    Re-keyage atomique share_guests + guest_hubs (pending inclus, un seul commit) ;
    collision avec un e-mail déjà invité → 409 sans rien modifier (jamais de fusion
    silencieuse — invariant 5). Lien (hub_token), code (pin), session (session_token)
    et guest_token INTACTS : transparent pour l'invité. L'historique (commentaires
    signés, memos.created_by, memo_revisions.editor) n'est PAS réécrit (comme le
    renommage existant)."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (str(data.get("name") or "")).strip()[:60]
    new_email = (str(data.get("new_email") or "")).strip().lower()
    if not email:
        return jsonify({"error": "email requis"}), 400
    db = get_db()
    has_access = (
        db.execute(
            "SELECT 1 FROM share_guests WHERE lower(email) = ? LIMIT 1", (email,)
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM guest_hubs WHERE email = ? LIMIT 1", (email,)
        ).fetchone()
    )
    if not has_access:
        return jsonify({"error": "invité introuvable"}), 404
    if new_email == email:
        new_email = ""
    if new_email:
        if "@" not in new_email or len(new_email) > 120:
            return jsonify({"error": "e-mail invalide"}), 400
        clash = (
            db.execute(
                "SELECT 1 FROM share_guests WHERE lower(email) = ? LIMIT 1", (new_email,)
            ).fetchone()
            or db.execute(
                "SELECT 1 FROM guest_hubs WHERE email = ? LIMIT 1", (new_email,)
            ).fetchone()
        )
        if clash:
            return jsonify({"error": "cet e-mail a déjà des accès"}), 409
    updated = 0
    if name:
        updated += db.execute(
            "UPDATE share_guests SET name = ? WHERE lower(email) = ?", (name, email)
        ).rowcount
        db.execute("UPDATE guest_hubs SET name = ? WHERE email = ?", (name, email))
    if new_email:
        updated += db.execute(
            "UPDATE share_guests SET email = ? WHERE lower(email) = ?", (new_email, email)
        ).rowcount
        db.execute(
            "UPDATE guest_hubs SET email = ? WHERE email = ?", (new_email, email)
        )
    db.commit()
    return jsonify({"email": new_email or email, "name": name, "updated": updated})


@app.route("/api/guests/<int:guest_id>", methods=["DELETE"])
def delete_guest(guest_id):
    # Suppression (a) : retire UN accès dossier d'un invité. Le hub & le code restent,
    # le dossier disparaît simplement de sa page hub (et son /share cesse pour lui).
    db = get_db()
    g = db.execute(
        "SELECT sg.email AS email, s.kind AS kind, s.target_id AS target_id "
        "FROM share_guests sg JOIN shares s ON s.id = sg.share_id WHERE sg.id = ?",
        (guest_id,),
    ).fetchone()
    if g:  # [VOTE-DECISION] cascade des voix de cet accès (scope du partage concerné)
        _delete_votes_for_email(db, g["email"], _share_scope_project_ids(db, g))
    db.execute("DELETE FROM share_guests WHERE id = ?", (guest_id,))
    db.commit()
    return "", 204


# ───────────────── [ONE-LINK-MULTI] gestion des hubs (owner-only, derrière Authelia) ─────────────────

@app.route("/api/hubs", methods=["GET"])
def list_hubs():
    """Un hub par e-mail (créé à la volée pour les invités historiques — idempotent).
    Sert l'en-tête « par personne » de 🔗 Partages : lien-hub + code + accès."""
    db = get_db()
    emails = [
        r["email"] for r in db.execute(
            "SELECT DISTINCT lower(email) AS email FROM share_guests WHERE email != ''"
        ).fetchall()
    ]
    out = {}
    for email in emails:
        name = ""
        nrow = db.execute(
            "SELECT name FROM share_guests WHERE lower(email) = ? AND COALESCE(name,'') != '' "
            "ORDER BY id LIMIT 1", (email,)
        ).fetchone()
        if nrow:
            name = nrow["name"]
        hub = _ensure_hub(db, email, name)
        if not hub:
            continue
        out[email] = {
            "email": email,
            "name": hub["name"] or "",
            "hub_token": hub["hub_token"],
            "pin": hub["pin"] or "",
            "url": f"/share/hub/{hub['hub_token']}",
            "folders_count": len(_hub_folders(db, email)),
            # [GUEST-EDIT] dernière connexion (ISO, '' = jamais) — owner-only,
            # jamais dans share_data/hub_data.
            "last_seen_at": _row_get(hub, "last_seen_at") or "",
        }
    return jsonify(list(out.values()))


@app.route("/api/hubs/<hub_token>", methods=["DELETE"])
def delete_hub(hub_token):
    # Suppression (b) : RETIRER L'INVITÉ — coupe tout. Supprime tous ses share_guests
    # ET le hub → lien mort. Les shares (dossiers) subsistent pour d'autres invités.
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    if not hub:
        return jsonify({"error": "hub introuvable"}), 404
    _delete_votes_for_email(db, hub["email"], None)  # [VOTE-DECISION] coupe tout → toutes ses voix
    db.execute("DELETE FROM share_guests WHERE lower(email) = ?", (hub["email"],))
    db.execute("DELETE FROM guest_hubs WHERE id = ?", (hub["id"],))
    db.commit()
    return "", 204


@app.route("/api/hubs/<hub_token>/rotate", methods=["POST"])
def rotate_hub(hub_token):
    # (c) Régénérer le LIEN : nouveau hub_token, accès & code conservés. Nouvelle URL à renvoyer.
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    if not hub:
        return jsonify({"error": "hub introuvable"}), 404
    new_token = secrets.token_urlsafe(24)
    # [HUB-SESSION] Nouveau lien ⇒ nouvelle session : l'ancien cookie (path périmé) n'est plus
    # jamais envoyé, ET le token serveur change (ceinture + bretelles) → tous re-PIN.
    db.execute(
        "UPDATE guest_hubs SET hub_token = ?, session_token = ? WHERE id = ?",
        (new_token, secrets.token_urlsafe(24), hub["id"]),
    )
    db.commit()
    return jsonify({"hub_token": new_token, "url": f"/share/hub/{new_token}", "pin": hub["pin"] or ""})


@app.route("/api/hubs/<hub_token>/rotate-pin", methods=["POST"])
def rotate_hub_pin(hub_token):
    # (d) Régénérer le CODE : nouveau pin, lien & accès conservés. Découplé de (c).
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    if not hub:
        return jsonify({"error": "hub introuvable"}), 404
    new_pin = f"{secrets.randbelow(10000):04d}"
    # [HUB-SESSION] Nouveau code ⇒ nouvelle session : toutes les sessions cookie retombent
    # sur l'écran code (révocation globale, tous les appareils).
    db.execute(
        "UPDATE guest_hubs SET pin = ?, session_token = ? WHERE id = ?",
        (new_pin, secrets.token_urlsafe(24), hub["id"]),
    )
    db.commit()
    return jsonify({"hub_token": hub_token, "pin": new_pin})


@app.route("/api/hubs/<hub_token>/send-invite", methods=["POST"])
def send_hub_invite(hub_token):
    # [HUB-EMAIL-INVITE] Envoie le lien-hub + code à l'e-mail DE CE HUB (jamais un destinataire
    # libre du client → pas de relais ouvert). Owner-only (derrière Authelia). Secret hors base.
    cfg = _smtp_config()
    if not cfg:
        return jsonify({"error": "SMTP non configuré (renseigner SMTP_* dans .env)"}), 400
    if _invite_throttled():
        return jsonify({"error": "trop d'envois, réessaie dans une minute"}), 429
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    if not hub:
        return jsonify({"error": "hub introuvable"}), 404
    to_email = parseaddr(hub["email"] or "")[1].strip().lower()  # destinataire = e-mail du hub, point.
    if "@" not in to_email:
        return jsonify({"error": "e-mail du hub invalide"}), 400
    hub_url = request.host_url.rstrip("/") + "/share/hub/" + hub["hub_token"]
    try:
        _send_hub_invite(cfg, to_email, hub["name"] or "", hub_url, hub["pin"] or "")
    except Exception:
        # Ne jamais exposer/loguer le secret ni le détail SMTP brut.
        app.logger.warning("send-invite: échec SMTP pour le hub %s", hub["id"])
        return jsonify({"error": "échec de l'envoi (voir la configuration SMTP)"}), 502
    _INVITE_SENT.append(time.time())
    return jsonify({"ok": True, "email": to_email})


def _data_version(db):
    """[AUTO-REFRESH] Empreinte cheap de l'état des données visibles du dashboard.

    Change dès qu'une donnée change, quelle que soit l'origine (owner, invité,
    autre onglet/appareil, API) → le poll du front recharge sur toute variation.
    Colonnes légères uniquement : le contenu des mémos/liens n'est jamais lu
    (toute édition bump `updated_at`) ; positions incluses (les reorders ne
    touchent pas `updated_at`). `app_state` exclut `activity_seen_at` (volatile,
    propre au badge — sinon « marquer vu » déclencherait un reload inutile).
    Lecture seule, aucun changement d'export.
    """
    h = hashlib.md5()
    queries = (
        "SELECT id, position, category_id, updated_at FROM links ORDER BY id",
        "SELECT id, name, color, emoji, position FROM categories ORDER BY id",
        "SELECT id, position, project_id, priority, done, due_date, due_time, "
        "deleted_at, updated_at FROM memos ORDER BY id",
        "SELECT * FROM projects ORDER BY id",
        "SELECT * FROM priorities ORDER BY id",
        "SELECT * FROM shares ORDER BY id",
        "SELECT id, share_id, email, name, status, approved_at FROM share_guests ORDER BY id",
        "SELECT id, email, name, pin FROM guest_hubs ORDER BY id",
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(created_at), '') FROM memo_comments",
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM comment_reactions",  # [COMMENT-REACTIONS]
        # [VOTE-DECISION] voix ; les flags/état de vote des projets sont déjà couverts par
        # le « SELECT * FROM projects » ci-dessus (vote_enabled/deadline/closed/winner…).
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(MAX(created_at), '') FROM memo_votes",
        # [VOTE-GROUPS] votes nommés + options + rattachement des voix (memo_votes.vote_id).
        "SELECT id, name, vote_mode, vote_deadline, vote_closed, vote_winner_ids, created_by, event_date FROM votes ORDER BY id",
        "SELECT vote_id, memo_id FROM vote_options ORDER BY vote_id, memo_id",
        "SELECT COALESCE(vote_id, -1) AS vid, COUNT(*) FROM memo_votes GROUP BY vid ORDER BY vid",
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM memo_history",
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM attachments",  # [ATTACHMENTS]
        "SELECT kind, ref, position FROM favorites ORDER BY position, kind, ref",  # [FAVORITES]
        "SELECT key, value FROM app_state WHERE key != 'activity_seen_at' ORDER BY key",
    )
    for q in queries:
        for row in db.execute(q):
            h.update(repr(tuple(row)).encode())
        h.update(b"|")
    return h.hexdigest()


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
    unseen += db.execute(
        "SELECT COUNT(*) FROM memo_comments WHERE share_id IS NOT NULL AND created_at > ?",
        (seen_at,),
    ).fetchone()[0]
    return jsonify(
        {
            "pending_guests": pending,
            "unseen": unseen,
            "revisions": out_rev,
            "data_version": _data_version(db),
        }
    )


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
        _clean_title(snap.get("title", _row_get(existing, "title"))),
        json.dumps(snap.get("assignees") if snap.get("assignees") is not None
                   else json.loads(_row_get(existing, "assignees", "[]") or "[]"),
                   ensure_ascii=False),
        _clean_due_time(snap.get("due_time")) if snap.get("due_date") else "",
    )
    _log_revision(db, existing, after, "moi (restauration)")
    db.execute(
        "UPDATE memos SET content=?, done=?, due_date=?, due_time=?, priority=?, subtasks=?, "
        "recurrence=?, title=?, assignees=?, updated_at=? WHERE id=?",
        (
            after["content"],
            1 if after["done"] else 0,
            after["due_date"],
            after["due_time"],
            after["priority"],
            json.dumps(after["subtasks"], ensure_ascii=False),
            after["recurrence"],
            after["title"],
            json.dumps(after["assignees"], ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            memo_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_memo_dict(row))


# [COMMENT-REACTIONS] / [REACTION-PALETTE] V21.0.57 : palette CONFIGURABLE (owner).
# REACTION_EMOJIS = SEED par défaut (6 base) tant qu'aucune config n'est enregistrée dans
# `app_state`. L'owner ajoute/retire dans les Paramètres (modèle priorités/catégories) ;
# la validation des réactions se fait contre la palette configurée, plus contre cette constante.
REACTION_EMOJIS = ("👍", "👎", "❤️", "😂", "😮", "🎉")

# Codepoints "accessoires" d'un grapheme emoji — autorisés, mais ne comptent JAMAIS comme base.
_EMOJI_ZWJ = 0x200D
_EMOJI_VS = (0xFE0E, 0xFE0F)               # sélecteurs de variation (texte/emoji)
_EMOJI_SKIN = range(0x1F3FB, 0x1F400)      # modificateurs de teinte de peau
_EMOJI_ENCLOSE = (0x20E3, 0x20E0)          # keycap / cercle englobant
_EMOJI_REGIONAL = range(0x1F1E6, 0x1F200)  # indicateurs régionaux (drapeaux)


def _is_emoji_core(cp):
    """cp appartient-il à une plage pictographique emoji (base autonome) ?"""
    return (
        0x1F000 <= cp <= 0x1FAFF          # pictographes, symboles & suppléments
        or 0x2600 <= cp <= 0x27BF         # symboles divers + dingbats
        or 0x2B00 <= cp <= 0x2BFF         # ⭐ ⬆ …
        or 0x2300 <= cp <= 0x23FF         # ⌚ ⏰ ⏳ …
        or 0x2190 <= cp <= 0x21FF         # flèches (↔️ …)
        or cp in (0x203C, 0x2049)         # ‼ ⁉
        or cp in (0x00A9, 0x00AE, 0x2122, 0x2139)  # © ® ™ ℹ
    )


def _clean_reaction_emoji(raw):
    """[REACTION-PALETTE] Valide un AJOUT de réaction : UN SEUL grapheme emoji, rien d'autre.
    Python pur (plages Unicode + garde de longueur), jamais de librairie/CDN (invariant 6).
    Rejette texte, HTML, espaces, multi-caractères et deux emojis collés → renvoie '' (→ 400)."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    cps = [ord(c) for c in s]
    if len(cps) > 10:                      # garde de longueur (séquence ZWJ ≈ 7-8 cp max)
        return ""
    bases = 0                              # bases pictographiques NON jointes par ZWJ
    regional = 0
    has_core = False
    for i, cp in enumerate(cps):
        if cp == _EMOJI_ZWJ or cp in _EMOJI_VS or cp in _EMOJI_SKIN or cp in _EMOJI_ENCLOSE:
            continue                       # accessoires (teinte, VS, ZWJ, keycap) : jamais une base
        if cp in _EMOJI_REGIONAL:
            regional += 1
            has_core = True
            continue
        if _is_emoji_core(cp):
            has_core = True
            if i == 0 or cps[i - 1] != _EMOJI_ZWJ:
                bases += 1                 # nouvelle base (sauf maillon d'une séquence ZWJ)
            continue
        return ""                          # tout le reste (ASCII, lettres, <, >, &, espace…) → rejet
    if not has_core:
        return ""                          # que des accessoires (VS/ZWJ seuls) → rejet
    if regional:                           # drapeau = exactement 2 indicateurs = 1 grapheme
        return s if (regional == 2 and not bases) else ""
    return s if bases == 1 else ""         # 0 base ou ≥2 (deux emojis) → rejet


def _reaction_palette(db):
    """[REACTION-PALETTE] Palette configurée. Défaut = REACTION_EMOJIS (6 base) tant qu'aucune
    config `reaction_emojis` n'est enregistrée. Liste ordonnée, dédupliquée, re-validée.
    Peut être vide si l'owner a tout retiré (aucune réaction possible)."""
    row = db.execute("SELECT value FROM app_state WHERE key = 'reaction_emojis'").fetchone()
    if row is None:
        return list(REACTION_EMOJIS)
    try:
        lst = json.loads(row["value"])
    except (ValueError, TypeError):
        return list(REACTION_EMOJIS)
    if not isinstance(lst, list):
        return list(REACTION_EMOJIS)
    out = []
    for e in lst:
        c = _clean_reaction_emoji(e)
        if c and c not in out:
            out.append(c)
    return out


def _valid_reaction_emoji(value, palette):
    """Réaction acceptée = présente dans la palette CONFIGURÉE (base + ajouts). '' sinon → 400."""
    v = str(value or "").strip()
    return v if v in palette else ""


def _comment_reactions_map(db, comment_ids):
    """{comment_id: [{emoji, voter}]} pour un lot de commentaires (brut, non agrégé)."""
    ids = [c for c in comment_ids if c is not None]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out = {}
    for rr in db.execute(
        f"SELECT comment_id, emoji, voter FROM comment_reactions WHERE comment_id IN ({ph}) "
        "ORDER BY created_at, id", ids
    ).fetchall():
        out.setdefault(rr["comment_id"], []).append({"emoji": rr["emoji"], "voter": rr["voter"]})
    return out


def _aggregate_reactions(reacts, me, owner_name, palette=None):
    """Agrège [{emoji, voter}] → [{emoji, count, mine, voters(noms affichables)}] dans l'ordre
    de la palette CONFIGURÉE (`palette`, défaut = 6 base). `me` = identité appelant ('' owner,
    None anonyme) ; e-mail jamais exposé. Les emojis présents mais HORS palette (ex. retirés
    après coup) sont affichés APRÈS, jamais masqués (non destructif à l'affichage)."""
    by_emoji = {}
    for rr in (reacts or []):
        by_emoji.setdefault(rr["emoji"], []).append(rr["voter"])
    order = list(palette) if palette else list(REACTION_EMOJIS)
    for e in by_emoji:
        if e not in order:
            order.append(e)
    mine_key = _voter_key(me) if me is not None else "\x00none"
    out = []
    for emoji in order:
        voters = by_emoji.get(emoji)
        if not voters:
            continue
        out.append({
            "emoji": emoji,
            "count": len(voters),
            "mine": any(_voter_key(v) == mine_key for v in voters),
            "voters": [_vote_display_name(v, owner_name) for v in voters],
        })
    return out


def _find_reaction(db, comment_id, emoji, voter):
    """Réaction de `voter` sur (commentaire, emoji) — match par e-mail (robuste au renommage)."""
    key = _voter_key(voter)
    for r in db.execute(
        "SELECT id, voter FROM comment_reactions WHERE comment_id = ? AND emoji = ?",
        (comment_id, emoji),
    ).fetchall():
        if _voter_key(r["voter"]) == key:
            return r
    return None


def _toggle_reaction(db, comment_id, emoji, voter):
    """Toggle : re-cliquer sa réaction la retire. Une réaction max par (commentaire, emoji, votant)."""
    existing = _find_reaction(db, comment_id, emoji, voter)
    if existing:
        db.execute("DELETE FROM comment_reactions WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            "INSERT INTO comment_reactions (comment_id, emoji, voter, created_at) VALUES (?, ?, ?, ?)",
            (comment_id, emoji, voter, datetime.now(timezone.utc).isoformat()),
        )


def _comment_dict(r, seen_map=None, reactions_map=None, me=None, owner_name="", palette=None):
    return {
        "id": r["id"],
        "memo_id": r["memo_id"],
        "author": r["author"],
        "body": r["body"],
        "created_at": r["created_at"],
        "guest": r["share_id"] is not None,
        "parent_id": _row_get(r, "parent_id"),
        "priority": _row_get(r, "priority", 0) or 0,
        "seen": (seen_map or {}).get(r["id"], []),
        # [COMMENT-REACTIONS] agrégées pour l'appelant (me) ; voters = noms affichables seuls.
        "reactions": _aggregate_reactions((reactions_map or {}).get(r["id"]), me, owner_name, palette),
    }


def _comment_seen_map(db, comment_ids):
    ids = [c for c in comment_ids if c is not None]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out = {}
    for s in db.execute(
        f"SELECT comment_id, viewer FROM comment_seen WHERE comment_id IN ({ph}) "
        "ORDER BY seen_at, id",
        ids,
    ).fetchall():
        out.setdefault(s["comment_id"], []).append(s["viewer"])
    return out


def _mark_comments_seen(db, memo_id, viewer):
    viewer = (viewer or "").strip()[:140]
    if not viewer:
        return
    now = datetime.now(timezone.utc).isoformat()
    for c in db.execute(
        "SELECT id FROM memo_comments WHERE memo_id = ?", (memo_id,)
    ).fetchall():
        db.execute(
            "INSERT OR IGNORE INTO comment_seen (comment_id, viewer, seen_at) VALUES (?, ?, ?)",
            (c["id"], viewer, now),
        )


def _valid_comment_priority(value):
    try:
        p = int(value)
    except (TypeError, ValueError):
        return 0
    return p if p in (1, 2, 3) else 0


def _valid_parent_comment(db, memo_id, parent_id):
    # Un seul niveau : si on répond à une réponse, on rattache au commentaire racine.
    try:
        pid = int(parent_id)
    except (TypeError, ValueError):
        return None
    row = db.execute(
        "SELECT id, parent_id FROM memo_comments WHERE id = ? AND memo_id = ?",
        (pid, memo_id),
    ).fetchone()
    if not row:
        return None
    return row["parent_id"] or row["id"]


def _clean_comment_body(value):
    return re.sub(r"[<>]", "", str(value or "")).strip()[:2000]


def _insert_comment(db, memo_row, body, author, share_id=None, parent_id=None, priority=0):
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO memo_comments (memo_id, memo_uid, author, share_id, body, created_at, parent_id, priority) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (memo_row["id"], memo_row["uid"] or "", author, share_id, body, now, parent_id, priority),
    )
    return db.execute(
        "SELECT * FROM memo_comments WHERE id = ?", (cur.lastrowid,)
    ).fetchone()


def _attach_log_comment(db, memo_row, added, names, author, share_id):
    """[ATTACHMENTS-COMMENT] Commentaire automatique d'ajout/suppression de fichier. Commentaire
    NORMAL (compte dans 💬, déclenche 🔔 si invité via share_id) attribué à l'auteur de l'action.
    Le « par qui » vient de l'attribution du commentaire (author) — pas répété dans le corps."""
    names = [n for n in (names or []) if n]
    if not names:
        return
    if added:
        body = ("📎 a ajouté le fichier « %s »" % names[0]) if len(names) == 1 else (
            "📎 a ajouté %d fichiers : %s" % (len(names), ", ".join(names)))
    else:
        body = "🗑 a supprimé le fichier « %s »" % names[0]
    _insert_comment(db, memo_row, body, author, share_id)


@app.route("/api/memos/<int:memo_id>/comments", methods=["GET"])
def list_comments(memo_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memo_comments WHERE memo_id = ? ORDER BY created_at, id",
        (memo_id,),
    ).fetchall()
    ids = [r["id"] for r in rows]
    seen = _comment_seen_map(db, ids)
    reacts = _comment_reactions_map(db, ids)  # [COMMENT-REACTIONS]
    owner_name = _owner_name(db)
    palette = _reaction_palette(db)  # [REACTION-PALETTE]
    return jsonify([_comment_dict(r, seen, reacts, me="", owner_name=owner_name, palette=palette) for r in rows])


@app.route("/api/memos/<int:memo_id>/comments", methods=["POST"])
def add_comment(memo_id):
    db = get_db()
    memo = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not memo:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    body = _clean_comment_body(data.get("body"))
    if not body:
        return jsonify({"error": "body required"}), 400
    parent_id = _valid_parent_comment(db, memo_id, data.get("parent_id")) if data.get("parent_id") else None
    priority = _valid_comment_priority(data.get("priority"))
    row = _insert_comment(db, memo, body, "moi", parent_id=parent_id, priority=priority)
    db.commit()
    return jsonify(_comment_dict(row)), 201


@app.route("/api/memos/<int:memo_id>/comments/seen", methods=["POST"])
def mark_comments_seen_owner(memo_id):
    db = get_db()
    _mark_comments_seen(db, memo_id, _owner_name(db))
    db.commit()
    return "", 204


@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    db = get_db()
    db.execute("DELETE FROM comment_reactions WHERE comment_id = ?", (comment_id,))  # [COMMENT-REACTIONS]
    db.execute("DELETE FROM memo_comments WHERE id = ?", (comment_id,))
    db.commit()
    return "", 204


def _react_result(db, comment_id, me):
    """Réactions agrégées d'un commentaire pour l'appelant (renvoyé après un toggle)."""
    reacts = _comment_reactions_map(db, [comment_id]).get(comment_id)
    return {"reactions": _aggregate_reactions(reacts, me, _owner_name(db), _reaction_palette(db))}


@app.route("/api/comments/<int:comment_id>/react", methods=["POST"])
def react_comment(comment_id):
    # [COMMENT-REACTIONS] Réagir (owner, voter = ''). Toggle. 400 hors palette, 404 inconnu.
    db = get_db()
    if not db.execute("SELECT 1 FROM memo_comments WHERE id = ?", (comment_id,)).fetchone():
        return jsonify({"error": "not found"}), 404
    emoji = _valid_reaction_emoji((request.get_json(silent=True) or {}).get("emoji"), _reaction_palette(db))
    if not emoji:
        return jsonify({"error": "emoji hors palette"}), 400
    _toggle_reaction(db, comment_id, emoji, "")
    db.commit()
    return jsonify(_react_result(db, comment_id, ""))


SHARE_ASSETS = {"quill.min.js", "quill.snow.css", "leaflet.js", "leaflet.css", "gsap.min.js", "favicon.svg", "Inter.woff2",
                "leaflet.markercluster.js", "MarkerCluster.css", "MarkerCluster.Default.css",  # [PHOTO-CLUSTER]
                "quill-table-better.js", "quill-table-better.css"}  # [MEMO-TABLES]


@app.route("/api/geocode")
def geocode():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify({"results": []})
    return jsonify({"results": _geocode_search(q)})


@app.route("/api/qr")
def qr_code():
    data = (request.args.get("data") or "").strip()
    if not data or len(data) > 1024:
        return "", 400
    import io
    import qrcode
    import qrcode.image.svg
    qr = qrcode.QRCode(box_size=10, border=2, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml")


@app.route("/share/assets/<name>")
def share_assets(name):
    if name not in SHARE_ASSETS:
        return "", 404
    return send_from_directory(app.static_folder, name, max_age=86400)


@app.route("/share/<token>")
def share_page(token):
    if not _share_by_token(get_db(), token):
        return "Lien de partage invalide ou révoqué.", 404
    return render_template("share.html", version=APP_VERSION)


# ───────────── [ONE-LINK-MULTI] routes publiques du hub (bypass Authelia) ─────────────
# [HUB-ROUTE-PREFIX] Préfixe /share/hub/<token> : couvert par le bypass Authelia /share/*
# (aucun changement Caddy). hub_token = 24 octets aléatoires (jamais "hub"/"data"/"assets"),
# et le segment statique "hub" distingue de /share/<token> et /share/<token>/data (Werkzeug).

@app.route("/share/hub/<hub_token>")
def hub_page(hub_token):
    # Shell statique : aucune donnée invité dans le HTML (la liste vient de /approve après PIN).
    if not _hub_by_token(get_db(), hub_token):
        return "Lien invalide ou révoqué.", 404
    return render_template("hub.html", version=APP_VERSION)


# [HUB-SESSION] Cookie de session du hub : HttpOnly (illisible en JS), Path scopé à CE hub
# (deux invités sur le même navigateur coexistent ; jamais envoyé à /share/<token> ni au reste
# de l'app ; rotation du lien → l'ancien path n'est plus jamais envoyé), 180 j glissants
# (re-posé à chaque /data prouvé). Secure conditionnel : X-Forwarded-Proto posé par Caddy en
# prod, absent en HTTP local (localhost:8099) pour rester testable.
def _set_hub_session_cookie(resp, hub_token, session_token):
    secure = request.is_secure or (request.headers.get("X-Forwarded-Proto") or "").lower() == "https"
    resp.set_cookie(
        "dashhubsession", session_token,
        max_age=15552000, path=f"/share/hub/{hub_token}",
        httponly=True, samesite="Lax", secure=secure,
    )


@app.route("/share/hub/<hub_token>/approve", methods=["POST"])
def hub_approve(hub_token):
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    # Réponse 403 générique et indiscernable (hub inexistant ≡ pin faux) → pas d'énumération.
    if not hub:
        return jsonify({"error": "code invalide"}), 403
    if _hub_pin_throttled(hub_token):
        return jsonify({"error": "trop de tentatives, réessaie plus tard"}), 429
    data = request.get_json(silent=True) or {}
    pin = (str(data.get("pin") or "")).strip()
    # Comparaison à temps constant (anti-timing).
    if not pin or not hmac.compare_digest(pin, hub["pin"] or ""):
        _hub_pin_fail(hub_token)
        return jsonify({"error": "code invalide"}), 403
    # Cascade d'approbation : UNIQUEMENT les share_guests de CET e-mail (jamais d'un autre).
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE share_guests SET status = 'approved', "
        "approved_at = CASE WHEN COALESCE(approved_at,'')='' THEN ? ELSE approved_at END "
        "WHERE lower(email) = ? AND status != 'approved'",
        (now, (hub["email"] or "").strip().lower()),
    )
    # [HUB-SESSION] Bon PIN → session serveur (un token par hub, partagé par les appareils),
    # transportée en cookie HttpOnly. Générée au premier besoin, invalidée par rotate/rotate-pin.
    session_token = _row_get(hub, "session_token") or ""
    if not session_token:
        session_token = secrets.token_urlsafe(24)
        db.execute(
            "UPDATE guest_hubs SET session_token = ? WHERE id = ?", (session_token, hub["id"])
        )
    db.commit()
    _touch_guest_seen(db, hub["email"])  # [GUEST-EDIT] bon PIN = identité prouvée
    resp = jsonify({"name": hub["name"] or "", "folders": _hub_folders(db, hub["email"])})
    _set_hub_session_cookie(resp, hub_token, session_token)
    return resp


def _hub_approved_shares(db, email):
    """Shares APPROUVÉS de cet e-mail, enrichis du scope (anti-chevauchement). UNIQUEMENT
    cet e-mail (invariant 5). Chaque share : token, can_edit, kind, target, desc_set, spec."""
    email = (email or "").strip().lower()
    rows = db.execute(
        "SELECT s.id, s.token, s.kind, s.target_id, s.can_edit "
        "FROM shares s JOIN share_guests g ON g.share_id = s.id "
        "WHERE lower(g.email) = ? AND g.status = 'approved' ORDER BY s.id",
        (email,),
    ).fetchall()
    out = []
    seen = set()
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        if r["kind"] == "project":
            desc = set(_project_descendants(db, r["target_id"]))
            spec = len(desc)
        else:
            desc = set()
            spec = 0  # un share mémo est le plus spécifique possible
        out.append({
            "id": r["id"], "token": r["token"], "can_edit": bool(r["can_edit"]),
            "kind": r["kind"], "target_id": r["target_id"], "desc": desc, "spec": spec,
        })
    return out


def _hub_winner(covering):
    """Share gagnant pour un item couvert par plusieurs shares : can_edit > spécificité > id."""
    return sorted(
        covering, key=lambda s: (0 if s["can_edit"] else 1, s["spec"], s["id"])
    )[0]


def _hub_proof(db, hub):
    """[HUB-SESSION] Preuve d'accès au hub : cookie de session OU header (repli).
    - cookie `dashhubsession` : comparé (temps constant) au session_token de CE hub —
      le hub est déjà résolu par hub_token, donc un cookie volé/forgé présenté sur un
      autre hub échoue ;
    - header `X-Guest-Token` (existant, inchangé) : un guest_token APPROUVÉ dont
      l'e-mail == celui du hub. JAMAIS de confiance au hub_token seul (il est dans l'URL)."""
    cookie = (request.cookies.get("dashhubsession") or "").strip()
    session_token = _row_get(hub, "session_token") or ""
    if cookie and session_token and hmac.compare_digest(cookie, session_token):
        return True
    gtok = (request.headers.get("X-Guest-Token") or "").strip()
    if not gtok:
        return None
    return db.execute(
        "SELECT * FROM share_guests WHERE guest_token = ? AND status = 'approved' "
        "AND lower(email) = ?",
        (gtok, (hub["email"] or "").strip().lower()),
    ).fetchone()


@app.route("/share/hub/<hub_token>/data")
def hub_data(hub_token):
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    if not hub:
        return jsonify({"error": "invalid"}), 404
    # Pas de master token : preuve = cookie de session OU guest_token approuvé de CET e-mail
    # (sinon 403, écran code). [HUB-SESSION] Le cookie n'authentifie QUE cette lecture — la
    # cascade d'approbation reste réservée au PIN (approve), il ne promeut jamais un pending.
    if not _hub_proof(db, hub):
        return jsonify({"error": "code requis"}), 403
    _touch_guest_seen(db, hub["email"])  # [GUEST-EDIT] preuve valide (cookie ou header)
    shares = _hub_approved_shares(db, hub["email"])
    proj_shares = [s for s in shares if s["kind"] == "project"]
    memo_shares = [s for s in shares if s["kind"] == "memo"]

    all_p = {
        r["id"]: r for r in db.execute(
            "SELECT id, name, emoji, color, parent_id, location, description, marker_color FROM projects"
        ).fetchall()
    }
    proj_names = {
        pid: ((p["emoji"] + " ") if p["emoji"] else "") + p["name"]
        for pid, p in all_p.items()
    }

    # ── Union des projets (dédup par id), tagués du share gagnant ──
    union_pids = set()
    for s in proj_shares:
        union_pids |= s["desc"]
    projects = []
    for pid in union_pids:
        p = all_p.get(pid)
        if not p:
            continue
        covering = [s for s in proj_shares if pid in s["desc"]]
        win = _hub_winner(covering)
        parent = p["parent_id"] if p["parent_id"] in union_pids else None  # jamais de parent hors union
        projects.append({
            "id": p["id"], "name": p["name"], "emoji": p["emoji"], "color": p["color"],
            "parent_id": parent, "location": _parse_location(p["location"]),
            "description": _row_get(p, "description"), "point_color": _row_get(p, "marker_color"),
            "share_token": win["token"], "can_edit": win["can_edit"],
            # [MAP-TIMELINE] booléen résolu serveur (lecture seule côté invité).
            "trip": _resolve_trip(db, p["id"]),
        })

    # ── Union des mémos (dédup par id), tagués du share gagnant ──
    def _cover_memo(memo_pid, memo_id):
        cov = [s for s in proj_shares if memo_pid in s["desc"]]
        cov += [s for s in memo_shares if s["target_id"] == memo_id]
        return cov

    def _collect_memos(deleted):
        rows_by_id = {}
        for s in shares:
            share = {"kind": s["kind"], "target_id": s["target_id"]}
            for r in _share_scope_memos(db, share, deleted=deleted):
                rows_by_id[r["id"]] = r
        return rows_by_id

    rows_by_id = _collect_memos(False)
    memo_ids = list(rows_by_id.keys())
    comments_by_memo = {}
    if memo_ids:
        ph = ",".join("?" * len(memo_ids))
        crows = db.execute(
            f"SELECT * FROM memo_comments WHERE memo_id IN ({ph}) ORDER BY created_at, id",
            memo_ids,
        ).fetchall()
        cseen = _comment_seen_map(db, [c["id"] for c in crows])
        creacts = _comment_reactions_map(db, [c["id"] for c in crows])  # [COMMENT-REACTIONS]
        _cname = _owner_name(db)
        _cpalette = _reaction_palette(db)  # [REACTION-PALETTE]
        _cme = f"{hub['name'] or hub['email']} <{hub['email']}>"
        for c in crows:
            comments_by_memo.setdefault(c["memo_id"], []).append(_comment_dict(c, cseen, creacts, me=_cme, owner_name=_cname, palette=_cpalette))
    # [VOTE-DECISION] contexte vote de l'union hub (gel paresseux inclus). Identité du
    # votant = e-mail du hub (le match des voix est par e-mail → robuste au renommage).
    vote_owner_name = _owner_name(db)
    me = f"{hub['name'] or hub['email']} <{hub['email']}>"
    vote_pids = set(union_pids) | {r["project_id"] for r in rows_by_id.values() if r["project_id"]}
    vpay, vmap = {}, {}
    if vote_pids:
        ph = ",".join("?" * len(vote_pids))
        venabled = db.execute(
            f"SELECT * FROM projects WHERE vote_enabled = 1 AND id IN ({ph})", list(vote_pids)
        ).fetchall()
        if [1 for pr in venabled if _ensure_vote_snapshot(db, pr)]:
            db.commit()
            venabled = db.execute(
                f"SELECT * FROM projects WHERE vote_enabled = 1 AND id IN ({ph})", list(vote_pids)
            ).fetchall()
        for pr in venabled:
            vpay[pr["id"]] = _vote_project_payload(db, pr, owner=False)
            vmap[pr["id"]] = _vote_voters_map(db, pr["id"])
    for pr in projects:
        pr.update(vpay.get(pr["id"], {"vote_enabled": False}))
        # [VOTE-GROUPS] votes nommés + permission résolue (can_edit du dossier ET 'guests').
        pr["votes"] = _project_named_votes(db, pr["id"], me, vote_owner_name, is_owner=False)
        pr["can_create_vote"] = bool(pr.get("can_edit")) and _resolve_vote_create(db, pr["id"]) == "guests"
    # [FOLDER-ATTACHMENTS] pièces jointes de dossier, URL scopée au share couvrant CE dossier.
    if union_pids:
        ph = ",".join("?" * len(union_pids))
        pamap = {}
        for a in db.execute(f"SELECT * FROM attachments WHERE project_id IN ({ph}) ORDER BY id", list(union_pids)).fetchall():
            pamap.setdefault(a["project_id"], []).append(a)
        for pr in projects:
            tok = pr["share_token"]
            pr["attachments"] = [_attach_row_dict(a, "/share/" + tok + "/attachment/" + str(a["id"])) for a in pamap.get(pr["id"], [])]
    memos = []
    for mid, r in rows_by_id.items():
        covering = _cover_memo(r["project_id"], mid)
        if not covering:
            continue  # sécurité : jamais un mémo hors des shares de l'e-mail
        win = _hub_winner(covering)
        d = _share_memo_dict(r)
        d["project"] = proj_names.get(r["project_id"], "")
        d["comments"] = comments_by_memo.get(mid, [])
        d["share_token"] = win["token"]
        d["can_edit"] = win["can_edit"]
        # [ATTACHMENTS] URL scopée au share couvrant ce mémo (token propre à chaque dossier du hub).
        d["attachments"] = _attachments_map(db, [mid], lambda r, t=win["token"]: "/share/" + t + "/attachment/" + str(r["id"])).get(mid, [])
        pv = vpay.get(r["project_id"])
        if pv and not _row_get(r, "vote_excluded", 0):  # [VOTE-EXCLUDE]
            voters = vmap[r["project_id"]].get(mid, [])
            d.update(_memo_vote_fields(voters, me, vote_owner_name, pv, mid))
        memos.append(d)

    # ── Racines (sidebar) : une par share ──
    roots = []
    for s in shares:
        if s["kind"] == "project":
            p = all_p.get(s["target_id"])
            if not p:
                continue
            roots.append({
                "share_token": s["token"], "can_edit": s["can_edit"], "kind": "project",
                "root_id": s["target_id"],
                "label": p["name"], "emoji": p["emoji"], "color": p["color"],
            })
        else:
            m = db.execute(
                "SELECT content, title, emoji FROM memos WHERE id = ? AND COALESCE(deleted_at,'')=''",
                (s["target_id"],),
            ).fetchone()
            if not m:
                continue
            roots.append({
                "share_token": s["token"], "can_edit": s["can_edit"], "kind": "memo",
                "memo_id": s["target_id"],
                "label": _row_get(m, "title") or _text_excerpt(m["content"], 60),
                "emoji": _row_get(m, "emoji"), "color": "",
            })

    # ── Corbeille (union des shares can_edit), taguée du share gagnant ──
    trash = []
    del_rows = _collect_memos(True)
    for mid, r in del_rows.items():
        covering = [s for s in _cover_memo(r["project_id"], mid) if s["can_edit"]]
        if not covering:
            continue
        win = _hub_winner(covering)
        td = _share_memo_dict(r)
        td["deleted_at"] = _row_get(r, "deleted_at", "")
        td["share_token"] = win["token"]
        td["can_edit"] = True
        trash.append(td)

    # ── Membres : union (propriétaire + invités approuvés de tous ses shares) ──
    members = [_owner_name(db)]
    share_ids = [s["id"] for s in shares]
    if share_ids:
        ph = ",".join("?" * len(share_ids))
        for g in db.execute(
            f"SELECT DISTINCT name, email FROM share_guests "
            f"WHERE share_id IN ({ph}) AND status = 'approved'",
            share_ids,
        ).fetchall():
            label = g["name"] or g["email"]
            if label and label not in members:
                members.append(label)

    resp = jsonify({
        "kind": "hub",
        "name": hub["name"] or "",
        "roots": roots,
        "projects": projects,
        "memos": memos,
        "trash": trash,
        "members": members,
        "priorities": [
            dict(r) for r in db.execute(
                "SELECT id, name, color FROM priorities ORDER BY position, id"
            ).fetchall()
        ],
        "marker_color": _map_marker_color(db),
        "reaction_emojis": _reaction_palette(db),  # [REACTION-PALETTE] palette consommée par les invités
        # [HUB-TOKEN-REFRESH] jetons par dossier rafraîchis à CHAQUE chargement (pas qu'à approve)
        # → un dossier ajouté après coup devient éditable sans re-saisir le code. L'invité est
        # déjà prouvé (hubProof) ; on ne fait que reposer des guest_token qu'il a droit d'avoir.
        "folders": _hub_folders(db, hub["email"]),
        # [GUEST-RESEND-LINK] booléen anodin (jamais le secret) : le front masque le bouton
        # « Recevoir mon lien » si l'envoi d'e-mail n'est pas configuré.
        "smtp_enabled": _smtp_config() is not None,
    })
    # [HUB-SESSION] Expiration glissante : re-pose le cookie à chaque /data prouvé (Max-Age
    # repart pour 180 j). Le token n'est généré qu'à approve — rien à poser s'il est vide.
    session_token = _row_get(hub, "session_token") or ""
    if session_token:
        _set_hub_session_cookie(resp, hub_token, session_token)
    return resp


# [GUEST-RESEND-LINK] rate-limit PAR HUB : ~2 envois/heure (fenêtre glissante en mémoire,
# best-effort par worker — le destinataire forcé reste la garde dure anti-abus).
_RESEND_SENT = {}
_RESEND_MAX = 2
_RESEND_WINDOW = 3600  # secondes


def _resend_throttled(hub_id):
    now = time.time()
    lst = [t for t in _RESEND_SENT.get(hub_id, []) if now - t < _RESEND_WINDOW]
    _RESEND_SENT[hub_id] = lst
    return len(lst) >= _RESEND_MAX


@app.route("/share/hub/<hub_token>/send-link", methods=["POST"])
def hub_send_link(hub_token):
    """[GUEST-RESEND-LINK] L'invité connecté se renvoie SON lien + code à l'adresse
    DÉJÀ enregistrée du hub (pas de modification d'adresse par l'invité — identité
    e-mail owner-only, cf. [GUEST-EDIT]). Route publique sous /share/* (bypass
    Authelia existant — invariant 5, jamais de nouveau préfixe de premier niveau).
    Preuve requise (_hub_proof : cookie de session OU X-Guest-Token approuvé) sinon
    403 générique ; destinataire FORCÉ = e-mail du hub (le corps de la requête est
    IGNORÉ — jamais une adresse du client) ; rate-limit ~2/h par hub → 429 ;
    corps mail réutilisé de [HUB-EMAIL-INVITE] ; secret SMTP jamais exposé/logué."""
    db = get_db()
    hub = _hub_by_token(db, hub_token)
    # 403 générique indiscernable (hub inexistant ≡ preuve absente) → pas d'énumération.
    if not hub or not _hub_proof(db, hub):
        return jsonify({"error": "accès refusé"}), 403
    cfg = _smtp_config()
    if not cfg:
        return jsonify({"error": "envoi par e-mail non disponible"}), 400
    if _resend_throttled(hub["id"]):
        return jsonify({"error": "trop d'envois — réessaie plus tard"}), 429
    to_email = parseaddr(hub["email"] or "")[1].strip().lower()  # destinataire = e-mail du hub, point.
    if "@" not in to_email:
        return jsonify({"error": "envoi impossible"}), 400
    hub_url = request.host_url.rstrip("/") + "/share/hub/" + hub["hub_token"]
    try:
        _send_hub_invite(cfg, to_email, hub["name"] or "", hub_url, hub["pin"] or "")
    except Exception:
        # Ne jamais exposer/loguer le secret ni le détail SMTP brut.
        app.logger.warning("send-link: échec SMTP pour le hub %s", hub["id"])
        return jsonify({"error": "échec de l'envoi"}), 502
    _RESEND_SENT.setdefault(hub["id"], []).append(time.time())
    return jsonify({"ok": True})


@app.route("/share/<token>/data")
def share_data(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    # [GUEST-EDIT] dernière connexion : un invité peut n'utiliser que son lien direct
    # (sans passer par le hub). Header APPROUVÉ uniquement ; sans hub → no-op.
    gtok = (request.headers.get("X-Guest-Token") or "").strip()
    me = None  # [VOTE-DECISION] identité du votant appelant (None = anonyme)
    if gtok:
        g = db.execute(
            "SELECT name, email FROM share_guests WHERE guest_token = ? AND share_id = ? "
            "AND status = 'approved'",
            (gtok, share["id"]),
        ).fetchone()
        if g:
            _touch_guest_seen(db, g["email"])
            me = f"{g['name'] or g['email']} <{g['email']}>"
    rows = _share_scope_memos(db, share)
    memos = []
    proj_names = {}
    scope_projects = []
    if share["kind"] == "project":
        all_p = {
            r["id"]: r
            for r in db.execute(
                "SELECT id, name, emoji, color, parent_id, location, description, marker_color FROM projects"
            ).fetchall()
        }
        proj_names = {
            pid: ((p["emoji"] + " ") if p["emoji"] else "") + p["name"]
            for pid, p in all_p.items()
        }
        for pid in _project_descendants(db, share["target_id"]):
            p = all_p.get(pid)
            if p:
                scope_projects.append(
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "emoji": p["emoji"],
                        "color": p["color"],
                        "parent_id": p["parent_id"],
                        "location": _parse_location(p["location"]),
                        "description": _row_get(p, "description"),
                        "point_color": _row_get(p, "marker_color"),
                        # [MAP-TIMELINE] booléen RÉSOLU par le serveur (l'arbre du partage
                        # peut être tronqué au scope) — lecture seule côté invité.
                        "trip": _resolve_trip(db, p["id"]),
                    }
                )
    memo_ids = [r["id"] for r in rows]
    comments_by_memo = {}
    if memo_ids:
        ph = ",".join("?" * len(memo_ids))
        crows = db.execute(
            f"SELECT * FROM memo_comments WHERE memo_id IN ({ph}) ORDER BY created_at, id",
            memo_ids,
        ).fetchall()
        cseen = _comment_seen_map(db, [c["id"] for c in crows])
        creacts = _comment_reactions_map(db, [c["id"] for c in crows])  # [COMMENT-REACTIONS]
        _cname = _owner_name(db)
        _cpalette = _reaction_palette(db)  # [REACTION-PALETTE]
        for c in crows:
            comments_by_memo.setdefault(c["memo_id"], []).append(_comment_dict(c, cseen, creacts, me=me, owner_name=_cname, palette=_cpalette))
    # [VOTE-DECISION] contexte vote des dossiers du périmètre (gel paresseux inclus).
    vote_owner_name = _owner_name(db)
    vote_pids = {r["project_id"] for r in rows if r["project_id"]}
    vote_pids |= {p["id"] for p in scope_projects}
    vpay, vmap = {}, {}
    if vote_pids:
        ph = ",".join("?" * len(vote_pids))
        venabled = db.execute(
            f"SELECT * FROM projects WHERE vote_enabled = 1 AND id IN ({ph})", list(vote_pids)
        ).fetchall()
        if [1 for pr in venabled if _ensure_vote_snapshot(db, pr)]:
            db.commit()
            venabled = db.execute(
                f"SELECT * FROM projects WHERE vote_enabled = 1 AND id IN ({ph})", list(vote_pids)
            ).fetchall()
        for pr in venabled:
            vpay[pr["id"]] = _vote_project_payload(db, pr, owner=False)
            vmap[pr["id"]] = _vote_voters_map(db, pr["id"])
    # [FOLDER-ATTACHMENTS] pièces jointes de dossier du périmètre (un seul SELECT).
    if scope_projects:
        spids = [p["id"] for p in scope_projects]
        ph = ",".join("?" * len(spids))
        pamap = {}
        for a in db.execute(f"SELECT * FROM attachments WHERE project_id IN ({ph}) ORDER BY id", spids).fetchall():
            pamap.setdefault(a["project_id"], []).append(
                _attach_row_dict(a, "/share/" + token + "/attachment/" + str(a["id"])))
        for p in scope_projects:
            p["attachments"] = pamap.get(p["id"], [])
    for p in scope_projects:
        p.update(vpay.get(p["id"], {"vote_enabled": False}))
        # [VOTE-GROUPS] votes nommés + permission résolue (booléen lecture seule, façon `trip`).
        p["votes"] = _project_named_votes(db, p["id"], me, vote_owner_name, is_owner=False)
        p["can_create_vote"] = bool(share["can_edit"]) and me is not None and _resolve_vote_create(db, p["id"]) == "guests"
    att_map = _attachments_map(db, [r["id"] for r in rows], lambda a: "/share/" + token + "/attachment/" + str(a["id"]))  # [ATTACHMENTS]
    for r in rows:
        d = _share_memo_dict(r)
        if share["kind"] == "project" and r["project_id"] != share["target_id"]:
            d["project"] = proj_names.get(r["project_id"], "")
        d["comments"] = comments_by_memo.get(r["id"], [])
        d["attachments"] = att_map.get(r["id"], [])  # [ATTACHMENTS]
        pv = vpay.get(r["project_id"])
        if pv and not _row_get(r, "vote_excluded", 0):  # [VOTE-EXCLUDE]
            voters = vmap[r["project_id"]].get(r["id"], [])
            d.update(_memo_vote_fields(voters, me, vote_owner_name, pv, r["id"]))
        memos.append(d)
    payload = {
        "projects": scope_projects,
        "root_id": share["target_id"] if share["kind"] == "project" else None,
        "kind": share["kind"],
        "can_edit": bool(share["can_edit"]),
        "memos": memos,
        "priorities": [
            dict(r)
            for r in db.execute(
                "SELECT id, name, color FROM priorities ORDER BY position, id"
            ).fetchall()
        ],
        "marker_color": _map_marker_color(db),
        "reaction_emojis": _reaction_palette(db),  # [REACTION-PALETTE] palette consommée par les invités
    }
    if share["kind"] == "project":
        proj = db.execute(
            "SELECT name, color, emoji, description FROM projects WHERE id = ?", (share["target_id"],)
        ).fetchone()
        if not proj:
            return jsonify({"error": "invalid"}), 404
        payload["title"] = (proj["emoji"] + " " if proj["emoji"] else "") + proj["name"]
        payload["color"] = proj["color"]
        payload["description"] = _row_get(proj, "description")
        payload["vote"] = vpay.get(share["target_id"], {"vote_enabled": False})  # [VOTE-DECISION]
    else:
        payload["title"] = "Mémo partagé"
        payload["color"] = ""
        payload["description"] = ""
    # Personnes du partage (suggestions d'assignés + récap) : propriétaire + invités approuvés
    members = [_owner_name(db)]
    for g in db.execute(
        "SELECT name, email FROM share_guests WHERE share_id = ? AND status = 'approved' ORDER BY id",
        (share["id"],),
    ).fetchall():
        label = g["name"] or g["email"]
        if label and label not in members:
            members.append(label)
    payload["members"] = members
    # Corbeille du périmètre (mémos supprimés, restaurables) — visible si modifiable.
    trash = []
    if share["can_edit"]:
        for r in _share_scope_memos(db, share, deleted=True):
            td = _share_memo_dict(r)
            td["deleted_at"] = _row_get(r, "deleted_at", "")
            trash.append(td)
    payload["trash"] = trash
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
        _ensure_hub(db, email, name)  # [ONE-LINK-MULTI]
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
    _ensure_hub(db, email, name)  # [ONE-LINK-MULTI]
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
        for k in ("content", "done", "subtasks", "due_date", "due_time", "priority", "recurrence", "location", "title", "assignees", "marker_color", "map_groups")
        if k in raw
    }
    if "project_id" in raw and share["kind"] == "project":
        try:
            wanted = int(raw["project_id"])
        except (TypeError, ValueError):
            wanted = None
        if wanted in _project_descendants(db, share["target_id"]):
            data["project_id"] = wanted
    editor = guest["name"] or guest["email"]
    payload, status = _perform_memo_update(
        db, existing, data, editor=f"{editor} <{guest['email']}>", share_id=share["id"]
    )
    if status == 200:
        payload = _share_memo_dict_from_payload(payload)
    return jsonify(payload), status


def _share_guest_or_403(db, share):
    if not share["can_edit"]:
        return None, (jsonify({"error": "lecture seule"}), 403)
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return None, (
            jsonify({"error": "guest_required",
                     "status": guest["status"] if guest else "anonymous"}),
            403,
        )
    return guest, None


@app.route("/share/<token>/memo/<int:memo_id>", methods=["DELETE"])
def share_delete_memo(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_guest_or_403(db, share)
    if err:
        return err
    if memo_id not in {r["id"] for r in _share_scope_memos(db, share)}:
        return jsonify({"error": "not found"}), 404
    now = datetime.now(timezone.utc).isoformat()
    db.execute("UPDATE memos SET deleted_at = ? WHERE id = ?", (now, memo_id))
    db.commit()
    return "", 204


@app.route("/share/<token>/memo/<int:memo_id>/restore", methods=["POST"])
def share_restore_memo(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_guest_or_403(db, share)
    if err:
        return err
    if memo_id not in {r["id"] for r in _share_scope_memos(db, share, deleted=True)}:
        return jsonify({"error": "not found"}), 404
    db.execute("UPDATE memos SET deleted_at = '' WHERE id = ?", (memo_id,))
    db.commit()
    return "", 204


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
    # [PHOTO-MAP] Idem côté invité : persiste l'EXIF (scope déjà vérifié plus haut).
    _record_image_meta(db, name, memo_id, existing["uid"])
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
    _forget_image_meta(db, name)  # [PHOTO-MAP] la méta suit le fichier
    db.execute(
        "UPDATE memos SET images = ?, updated_at = ? WHERE id = ?",
        (json.dumps(images), datetime.now(timezone.utc).isoformat(), memo_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    return jsonify(_share_memo_dict(row))


# ─────────────────────────── [ATTACHMENTS] routes invité (sous /share/*) ───────────────────────────
# Invariant 5 : upload = invité APPROUVÉ + can_edit + mémo DANS le scope ; download = tout invité
# ayant accès (le fichier doit appartenir à un mémo du scope). Non-média TOUJOURS en attachment.
@app.route("/share/<token>/memo/<int:memo_id>/attachments", methods=["POST"])
def share_add_attachment(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"]:
        return jsonify({"error": "lecture seule"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    if memo_id not in {r["id"] for r in _share_scope_memos(db, share)}:
        return jsonify({"error": "not found"}), 404
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "file required"}), 400
    memo = db.execute("SELECT id, uid FROM memos WHERE id = ?", (memo_id,)).fetchone()
    by = f"{guest['name'] or guest['email']} <{guest['email']}>"
    now = datetime.now(timezone.utc).isoformat()
    added_names = []
    for f in files:
        info, err = _save_attachment(f)
        if err:
            return jsonify({"error": err}), 400
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (memo_id, memo["uid"], info["filename"], info["orig"], info["mime"], info["size"], 1 if info["preview"] else 0, now, by, share["id"]),
        )
        added_names.append(info["orig"])
    _attach_log_comment(db, memo, True, added_names, by, share["id"])  # [ATTACHMENTS-COMMENT] déclenche 🔔
    db.execute("UPDATE memos SET updated_at = ? WHERE id = ?", (now, memo_id))
    db.commit()
    url_fn = lambda r: "/share/" + token + "/attachment/" + str(r["id"])
    return jsonify(_attachments_map(db, [memo_id], url_fn).get(memo_id, [])), 201


# [FOLDER-ATTACHMENTS] Upload invité d'un fichier sur un DOSSIER : partage de projet only, dossier
# dans le sous-arbre autorisé, invité approuvé + can_edit (invariant 5, mêmes gardes que les mémos).
@app.route("/share/<token>/project/<int:project_id>/attachments", methods=["POST"])
def share_add_project_attachment(token, project_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"]:
        return jsonify({"error": "lecture seule"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    if share["kind"] != "project" or project_id not in set(_project_descendants(db, share["target_id"])):
        return jsonify({"error": "not found"}), 404
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "file required"}), 400
    by = f"{guest['name'] or guest['email']} <{guest['email']}>"
    now = datetime.now(timezone.utc).isoformat()
    for f in files:
        info, err = _save_attachment(f)
        if err:
            return jsonify({"error": err}), 400
        db.execute(
            "INSERT INTO attachments (memo_id, memo_uid, project_id, filename, orig_name, mime, size, preview, created_at, created_by, share_id) "
            "VALUES (0, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, info["filename"], info["orig"], info["mime"], info["size"], 1 if info["preview"] else 0, now, by, share["id"]),
        )
    db.commit()
    url_fn = lambda r: "/share/" + token + "/attachment/" + str(r["id"])
    return jsonify(_project_attachments_list(db, project_id, url_fn)), 201


# [FILES-VIEW] Vue « retrouver les fichiers » d'un dossier partagé, bornée au sous-arbre du token
# (invariant 5). Lecture seule (comme share_data), pas de vue globale côté invité.
@app.route("/share/<token>/project/<int:project_id>/files")
def share_project_files(token, project_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or share["kind"] != "project":
        return jsonify({"error": "not found"}), 404
    if project_id not in set(_project_descendants(db, share["target_id"])):
        return jsonify({"error": "not found"}), 404
    pids = _project_descendants(db, project_id)  # ⊆ sous-arbre autorisé (descendants d'un projet du scope)
    ph = ",".join("?" * len(pids))
    memos = db.execute(
        f"SELECT id, project_id, title, content, images FROM memos "
        f"WHERE project_id IN ({ph}) AND COALESCE(deleted_at, '') = '' ORDER BY position, id", pids
    ).fetchall()
    files = _collect_files(
        db, memos, pids,
        lambda i: "/share/" + token + "/attachment/" + str(i),
        lambda n: "/share/" + token + "/image/" + n,
    )
    return jsonify(files)


def _attach_in_share_scope(db, share, r):
    """[FOLDER-ATTACHMENTS] Pièce jointe (mémo OU dossier) dans le périmètre du partage (invariant 5).
    Fichier de dossier : uniquement un partage de projet dont le dossier est un descendant."""
    if r["project_id"]:
        return share["kind"] == "project" and r["project_id"] in set(_project_descendants(db, share["target_id"]))
    return r["memo_id"] in {m["id"] for m in _share_scope_memos(db, share)}


@app.route("/share/<token>/attachment/<int:att_id>")
def share_download_attachment(token, att_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return "", 404
    r = db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if not r or not _attach_in_share_scope(db, share, r):
        return "", 404
    return _serve_attachment_row(r, request.args.get("download") in ("1", "true", "yes"))


@app.route("/share/<token>/attachment/<int:att_id>", methods=["DELETE"])
def share_delete_attachment(token, att_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or not share["can_edit"]:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    r = db.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if not r or not _attach_in_share_scope(db, share, r):
        return jsonify({"error": "not found"}), 404
    _delete_attachment_file(r["filename"])
    db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
    memo = db.execute("SELECT id, uid FROM memos WHERE id = ?", (r["memo_id"],)).fetchone()
    if memo:  # [ATTACHMENTS-COMMENT] déclenche 🔔 (invité approuvé, dans le scope — invariant 5)
        by = f"{guest['name'] or guest['email']} <{guest['email']}>"
        _attach_log_comment(db, memo, False, [r["orig_name"] or r["filename"]], by, share["id"])
    db.execute("UPDATE memos SET updated_at = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), r["memo_id"]))
    db.commit()
    return "", 204


# [PHOTO-BATCH-DOWNLOAD] Zip côté invité : lecture seule scopée au token (comme share_image /
# share_download_attachment — pas d'approbation requise pour LIRE). L'invité ne peut zipper que ce
# que son token couvre ; subprojects borné au sous-arbre autorisé (invariant 5).
@app.route("/share/<token>/memo/<int:memo_id>/download.zip")
def share_download_memo_zip(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return "", 404
    if memo_id not in {m["id"] for m in _share_scope_memos(db, share)}:
        return "", 404
    row = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    scope = _zip_scope(request.args)
    base = _zip_base(row["title"] or _text_excerpt(row["content"]), scope, "memo-" + str(memo_id))
    return _send_zip(_memo_zip_entries(db, row, scope), base)


@app.route("/share/<token>/project/<int:project_id>/download.zip")
def share_download_project_zip(token, project_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or share["kind"] != "project":
        return "", 404
    # le dossier demandé doit être la cible du partage OU un de ses descendants → tout son
    # sous-arbre est alors, lui aussi, dans le périmètre autorisé.
    if project_id not in set(_project_descendants(db, share["target_id"])):
        return "", 404
    proj = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    scope = _zip_scope(request.args)
    entries = _project_zip_entries(db, project_id, scope, _zip_subs(request.args))
    return _send_zip(entries, _zip_base(proj["name"] if proj else "", scope, "dossier-" + str(project_id)))


def _share_memo_dict_from_payload(d):
    return {
        "id": d["id"],
        "content": d["content"],
        "done": d["done"],
        "due_date": d["due_date"],
        "due_time": d.get("due_time", "") or "",
        "priority": d["priority"],
        "subtasks": d["subtasks"],
        "images": d["images"],
        "recurrence": d["recurrence"],
        "emoji": d.get("emoji", ""),
        "project_id": d.get("project_id"),
        "location": d.get("location"),
        "title": d.get("title", "") or "",
        "assignees": d.get("assignees", []),
        "point_color": d.get("marker_color", "") or "",
        "map_groups": d.get("map_groups", []),
        "created_at": d.get("created_at", "") or "",
        "vote_excluded": bool(d.get("vote_excluded")),  # [VOTE-EXCLUDE]
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
    title = _clean_title(data.get("title"))
    if not content and not title:
        return jsonify({"error": "content required"}), 400
    assignees = _assignees_json(data.get("assignees"))
    target_project = share["target_id"]
    if data.get("project_id"):
        try:
            wanted = int(data["project_id"])
        except (TypeError, ValueError):
            wanted = None
        if wanted in _project_descendants(db, share["target_id"]):
            target_project = wanted
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM memos").fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    new_uid = str(uuid.uuid4())
    editor = guest["name"] or guest["email"]
    created_by = f"{editor} <{guest['email']}>"
    cur = db.execute(
        "INSERT INTO memos (content, position, created_at, uid, updated_at, "
        "done, due_date, priority, subtasks, project_id, recurrence, title, assignees, created_by) "
        "VALUES (?, ?, ?, ?, ?, 0, '', 0, '[]', ?, '', ?, ?, ?)",
        (content, max_pos + 1, now, new_uid, now, target_project, title, assignees, created_by),
    )
    db.execute(
        "INSERT INTO memo_revisions (memo_id, memo_uid, editor, share_id, before, after, edited_at) "
        "VALUES (?, ?, ?, ?, NULL, ?, ?)",
        (
            cur.lastrowid,
            new_uid,
            f"{editor} <{guest['email']}>",
            share["id"],
            json.dumps(_memo_snapshot(content, 0, "", 0, "[]", "", title, assignees), ensure_ascii=False),
            now,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_share_memo_dict(row)), 201


@app.route("/share/<token>/projects", methods=["POST"])
def share_add_project(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"] or share["kind"] != "project":
        return jsonify({"error": "non autorisé"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if db.execute("SELECT 1 FROM projects WHERE name = ?", (name,)).fetchone():
        return jsonify({"error": "un projet porte déjà ce nom"}), 409
    parent_id = share["target_id"]
    if data.get("parent_id"):
        try:
            wanted = int(data["parent_id"])
        except (TypeError, ValueError):
            wanted = None
        if wanted in _project_descendants(db, share["target_id"]):
            parent_id = wanted
    max_pos = db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM projects"
    ).fetchone()[0]
    cur = db.execute(
        "INSERT INTO projects (name, color, position, tags, emoji, parent_id) "
        "VALUES (?, '', ?, '', ?, ?)",
        (name, max_pos + 1, _clean_emoji(data.get("emoji")), parent_id),
    )
    editor = guest["name"] or guest["email"]
    parent_name = db.execute(
        "SELECT name FROM projects WHERE id = ?", (parent_id,)
    ).fetchone()["name"]
    db.execute(
        "INSERT INTO memo_revisions (memo_id, memo_uid, editor, share_id, before, after, edited_at) "
        "VALUES (0, '', ?, ?, NULL, ?, ?)",
        (
            f"{editor} <{guest['email']}>",
            share["id"],
            json.dumps(
                {"content": f"📁 Projet « {name} » créé dans « {parent_name} »",
                 "done": False, "due_date": "", "priority": 0, "subtasks": [], "recurrence": ""},
                ensure_ascii=False,
            ),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": name, "parent_id": parent_id}), 201


@app.route("/share/<token>/project/<int:proj_id>", methods=["PUT"])
def share_update_project(token, proj_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    if not share["can_edit"] or share["kind"] != "project":
        return jsonify({"error": "non autorisé"}), 403
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    scope = set(_project_descendants(db, share["target_id"]))
    if proj_id not in scope:
        return jsonify({"error": "projet hors du partage"}), 404
    existing = db.execute(
        "SELECT * FROM projects WHERE id = ?", (proj_id,)
    ).fetchone()
    if not existing:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    updates = {}

    if "parent_id" in data:
        if proj_id == share["target_id"]:
            return jsonify({"error": "la racine du partage ne peut pas être déplacée"}), 400
        try:
            parent_id = int(data.get("parent_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "parent invalide"}), 400
        if parent_id not in scope:
            return jsonify({"error": "parent hors du partage"}), 400
        resolved, err = _resolve_parent(db, proj_id, parent_id)
        if err:
            return jsonify({"error": err}), 400
        updates["parent_id"] = resolved

    renamed_from = None
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        if name != existing["name"]:
            if db.execute(
                "SELECT 1 FROM projects WHERE name = ? AND id != ?", (name, proj_id)
            ).fetchone():
                return jsonify({"error": "un projet porte déjà ce nom"}), 409
            renamed_from = existing["name"]
            updates["name"] = name
    if "emoji" in data:
        updates["emoji"] = _clean_emoji(data.get("emoji"))
    if "color" in data:
        updates["color"] = (data.get("color") or "").strip()
    if "marker_color" in data:
        updates["marker_color"] = _clean_hex_color(data.get("marker_color"), "")
    if "location" in data:
        updates["location"] = _enrich_location(_clean_location(data.get("location")))
    if "description" in data:
        updates["description"] = _clean_description(data.get("description"))

    if not updates:
        return jsonify({"error": "rien à modifier"}), 400
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(
        f"UPDATE projects SET {set_clause} WHERE id = ?",
        (*updates.values(), proj_id),
    )
    if renamed_from:
        editor = guest["name"] or guest["email"]
        db.execute(
            "INSERT INTO memo_revisions (memo_id, memo_uid, editor, share_id, before, after, edited_at) "
            "VALUES (0, '', ?, ?, NULL, ?, ?)",
            (
                f"{editor} <{guest['email']}>",
                share["id"],
                json.dumps(
                    {"content": f"📁 Projet « {renamed_from} » renommé en « {updates['name']} »",
                     "done": False, "due_date": "", "priority": 0, "subtasks": [], "recurrence": ""},
                    ensure_ascii=False,
                ),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (proj_id,)).fetchone()
    return jsonify({"id": proj_id, "name": row["name"], "emoji": row["emoji"], "color": row["color"], "parent_id": row["parent_id"], "description": _row_get(row, "description"), "point_color": _row_get(row, "marker_color")})


@app.route("/share/<token>/memo/<int:memo_id>/comments", methods=["POST"])
def share_add_comment(token, memo_id):
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
    memo = db.execute("SELECT * FROM memos WHERE id = ?", (memo_id,)).fetchone()
    data = request.get_json(silent=True) or {}
    body = _clean_comment_body(data.get("body"))
    if not body:
        return jsonify({"error": "body required"}), 400
    parent_id = _valid_parent_comment(db, memo_id, data.get("parent_id")) if data.get("parent_id") else None
    priority = _valid_comment_priority(data.get("priority"))
    author = guest["name"] or guest["email"]
    row = _insert_comment(db, memo, body, f"{author} <{guest['email']}>", share["id"], parent_id=parent_id, priority=priority)
    db.commit()
    return jsonify(_comment_dict(row)), 201


@app.route("/share/<token>/comment/<int:comment_id>/react", methods=["POST"])
def share_react_comment(token, comment_id):
    # [COMMENT-REACTIONS] Réagir côté invité. Route publique sous /share/* (bypass Authelia,
    # invariant 5). can_edit NON requis (décision 2 : réagir n'est pas éditer) mais invité
    # APPROUVÉ requis + mémo du commentaire dans le scope. 400 hors palette.
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required", "status": guest["status"] if guest else "anonymous"}), 403
    crow = db.execute("SELECT id, memo_id FROM memo_comments WHERE id = ?", (comment_id,)).fetchone()
    if not crow or crow["memo_id"] not in {r["id"] for r in _share_scope_memos(db, share)}:
        return jsonify({"error": "not found"}), 404
    emoji = _valid_reaction_emoji((request.get_json(silent=True) or {}).get("emoji"), _reaction_palette(db))
    if not emoji:
        return jsonify({"error": "emoji hors palette"}), 400
    voter = f"{guest['name'] or guest['email']} <{guest['email']}>"
    _toggle_reaction(db, comment_id, emoji, voter)
    db.commit()
    return jsonify(_react_result(db, comment_id, voter))


@app.route("/share/<token>/memo/<int:memo_id>/vote", methods=["POST"])
def share_vote_memo(token, memo_id):
    # [VOTE-DECISION] Voter côté invité. Route publique sous /share/* (bypass Authelia,
    # invariant 5). can_edit NON requis (§2.3 : voter n'est pas éditer) mais invité
    # APPROUVÉ requis + scope revalidé serveur. 409 si le dossier est clos (§9.c).
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required", "status": guest["status"] if guest else "anonymous"}), 403
    if memo_id not in {r["id"] for r in _share_scope_memos(db, share)}:
        return jsonify({"error": "not found"}), 404
    memo = db.execute("SELECT id, project_id, vote_excluded FROM memos WHERE id = ?", (memo_id,)).fetchone()
    if not memo or not memo["project_id"]:
        return jsonify({"error": "pas une option de vote"}), 400
    voter = f"{guest['name'] or guest['email']} <{guest['email']}>"
    vid = (request.get_json(silent=True) or {}).get("vote_id")
    if vid not in (None, "", 0):  # [VOTE-GROUPS] vote nommé — porteur DOIT être dans le scope partagé
        try:
            vote = _vote_row(db, int(vid))
        except (TypeError, ValueError):
            vote = None
        if not vote or vote["project_id"] not in set(_share_scope_project_ids(db, share)):
            return jsonify({"error": "pas une option de vote"}), 400
        return _do_named_vote(db, vid, memo, voter, is_owner=False)
    if _row_get(memo, "vote_excluded", 0):
        return jsonify({"error": "pas une option de vote"}), 400  # [VOTE-EXCLUDE]
    proj = db.execute("SELECT * FROM projects WHERE id = ?", (memo["project_id"],)).fetchone()
    if not proj or not proj["vote_enabled"]:
        return jsonify({"error": "pas une option de vote"}), 400
    if _ensure_vote_snapshot(db, proj):
        db.commit()
        proj = db.execute("SELECT * FROM projects WHERE id = ?", (memo["project_id"],)).fetchone()
    if _vote_is_closed(proj):
        return jsonify({"error": "vote clos"}), 409
    _cast_vote(db, proj["id"], memo_id, voter, _clean_vote_mode(proj["vote_mode"]))  # [VOTE-MULTI]
    db.commit()
    pv = _vote_project_payload(db, proj, owner=False)
    return jsonify({"project_id": proj["id"], "vote": pv,
                    "options": _vote_options_payload(db, proj["id"], voter, _owner_name(db), pv)})


# ─────────────────── [VOTE-GROUPS] routes votes nommés côté invité (sous /share/*) ───────────────────
# Gate §4 : invité approuvé sur lien can_edit + permission résolue 'guests' (création) ;
# gestion = créateur seulement (match e-mail). 403 « non autorisé » GÉNÉRIQUE (indiscernable).

def _share_vote_guest_or_403(db, share):
    if not share["can_edit"]:
        return None, (jsonify({"error": "non autorisé"}), 403)
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return None, (jsonify({"error": "non autorisé"}), 403)
    return guest, None


def _share_managed_vote(db, share, guest, vid):
    """Vote existant, porteur dans le scope, ET géré par cet invité (créateur). Sinon 403 générique."""
    vote = _vote_row(db, vid)
    if not vote or vote["project_id"] not in set(_share_scope_project_ids(db, share)):
        return None, (jsonify({"error": "non autorisé"}), 403)
    gkey = _voter_key(f"{guest['name'] or guest['email']} <{guest['email']}>")
    if not _vote_manages(vote, gkey, False):
        return None, (jsonify({"error": "non autorisé"}), 403)
    return vote, None


def _share_restrict_memo_ids(db, share, memo_ids):
    """Limite les options proposées par un invité aux mémos de SON scope de partage."""
    allowed = {r["id"] for r in _share_scope_memos(db, share)}
    out = []
    for m in (memo_ids or []):
        try:
            mid = int(m)
        except (TypeError, ValueError):
            continue
        if mid in allowed:
            out.append(mid)
    return out


@app.route("/share/<token>/votes", methods=["POST"])
def share_create_vote(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_vote_guest_or_403(db, share)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    scope_pids = set(_share_scope_project_ids(db, share))
    pid = share["target_id"] if share["kind"] == "project" else None
    if data.get("project_id"):
        try:
            wanted = int(data["project_id"])
        except (TypeError, ValueError):
            wanted = None
        if wanted in scope_pids:
            pid = wanted
    if pid is None or pid not in scope_pids or _resolve_vote_create(db, pid) != "guests":
        return jsonify({"error": "non autorisé"}), 403
    data["memo_ids"] = _share_restrict_memo_ids(db, share, data.get("memo_ids"))
    created_by = f"{guest['name'] or guest['email']} <{guest['email']}>"
    err2, res = _create_named_vote(db, pid, data, created_by)
    if err2:
        return jsonify(err2), res
    return jsonify(_named_vote_payload(db, _vote_row(db, res), created_by, _owner_name(db), False)), 201


@app.route("/share/<token>/votes/<int:vid>", methods=["PUT"])
def share_put_vote(token, vid):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_vote_guest_or_403(db, share)
    if err:
        return err
    vote, err2 = _share_managed_vote(db, share, guest, vid)
    if err2:
        return err2
    data = request.get_json(silent=True) or {}
    if "memo_ids" in data:
        data["memo_ids"] = _share_restrict_memo_ids(db, share, data.get("memo_ids"))
    err3, status = _update_named_vote(db, vote, data)
    if err3:
        return jsonify(err3), status
    voter = f"{guest['name'] or guest['email']} <{guest['email']}>"
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), voter, _owner_name(db), False))


def _share_vote_action(token, vid, action):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_vote_guest_or_403(db, share)
    if err:
        return err
    vote, err2 = _share_managed_vote(db, share, guest, vid)
    if err2:
        return err2
    voter = f"{guest['name'] or guest['email']} <{guest['email']}>"
    if action == "close":
        _freeze_named_vote(db, vid)
        db.execute("UPDATE votes SET vote_closed = 1 WHERE id = ?", (vid,))
        db.commit()
    else:  # reopen / reset
        new_deadline = _clean_vote_deadline((request.get_json(silent=True) or {}).get("vote_deadline"))
        if new_deadline and _deadline_passed(new_deadline):
            return jsonify({"error": "la nouvelle deadline est déjà dépassée"}), 400
        if action == "reset":
            db.execute("DELETE FROM memo_votes WHERE vote_id = ?", (vid,))
        db.execute("UPDATE votes SET vote_closed = 0, vote_winner_ids = '', vote_deadline = ? WHERE id = ?", (new_deadline, vid))
        db.commit()
    return jsonify(_named_vote_payload(db, _vote_row(db, vid), voter, _owner_name(db), False))


@app.route("/share/<token>/votes/<int:vid>/close", methods=["POST"])
def share_close_vote(token, vid):
    return _share_vote_action(token, vid, "close")


@app.route("/share/<token>/votes/<int:vid>/reopen", methods=["POST"])
def share_reopen_vote(token, vid):
    return _share_vote_action(token, vid, "reopen")


@app.route("/share/<token>/votes/<int:vid>/reset", methods=["POST"])
def share_reset_vote(token, vid):
    return _share_vote_action(token, vid, "reset")


@app.route("/share/<token>/votes/<int:vid>", methods=["DELETE"])
def share_delete_vote(token, vid):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest, err = _share_vote_guest_or_403(db, share)
    if err:
        return err
    vote, err2 = _share_managed_vote(db, share, guest, vid)
    if err2:
        return err2
    _delete_named_vote(db, vid)
    db.commit()
    return "", 204


@app.route("/share/<token>/memo/<int:memo_id>/seen", methods=["POST"])
def share_mark_seen(token, memo_id):
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    if memo_id not in {r["id"] for r in _share_scope_memos(db, share)}:
        return jsonify({"error": "not found"}), 404
    _mark_comments_seen(db, memo_id, guest["name"] or guest["email"])
    db.commit()
    return "", 204


@app.route("/share/<token>/geocode")
def share_geocode(token):
    db = get_db()
    share = _share_by_token(db, token)
    if not share or not share["can_edit"]:
        return jsonify({"error": "invalid"}), 404
    guest = _guest_from_request(db, share)
    if not guest or guest["status"] != "approved":
        return jsonify({"error": "guest_required"}), 403
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify({"results": []})
    return jsonify({"results": _geocode_search(q)})


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


@app.route("/share/<token>/image-exif/<name>")
def share_image_exif(token, name):
    # [IMAGE-EXIF] Métadonnées photo à la volée pour un invité — MÊME contrôle de
    # scope que share_image (invariant 5) : le fichier doit appartenir à un mémo du
    # partage, sinon 404. Aucune fuite d'EXIF hors périmètre, aucune nouvelle capacité.
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
                return jsonify(_image_exif(name) or {})
        except Exception:
            continue
    return "", 404


@app.route("/share/<token>/photos", methods=["GET"])
def share_photos(token):
    # [PHOTO-MAP] Calque photo d'un partage, STRICTEMENT scopé (invariant 5) : même
    # périmètre que share_image / share_data (jeton + _share_scope_memos), jamais une
    # image hors partage. Lecture seule, aucune nouvelle capacité publique. Le front
    # filtre ensuite par sous-projet/groupe comme pour les points-mémo.
    db = get_db()
    share = _share_by_token(db, token)
    if not share:
        return jsonify({"error": "invalid"}), 404
    ids = [r["id"] for r in _share_scope_memos(db, share)]
    return jsonify(_project_photos(db, ids))


# -------------------------------------------------------- export/import


@app.route("/api/export", methods=["GET"])
def export_links():
    return jsonify(_build_export(get_db()))


def _export_slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return (s or "dossier")[:60]


@app.route("/api/projects/<int:project_id>/export", methods=["GET"])
def export_project_subtree(project_id):
    # [EXPORT-SUBTREE] Export d'un dossier SEUL (owner-only, derrière Authelia — pas de
    # variante /share). JSON v20 standard filtré au sous-arbre → avalé par l'import existant.
    db = get_db()
    row = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    resp = jsonify(_build_export(db, root_id=project_id))
    resp.headers["Content-Disposition"] = (
        'attachment; filename="dossier-' + _export_slug(row["name"]) + '-v20.json"'
    )
    return resp


def _build_export(db, root_id=None):
    # [EXPORT-SUBTREE] root_id non nul → export FILTRÉ au sous-arbre (dossier + descendants +
    # leurs mémos/commentaires/historique). MÊME format v20, MÊMES exclusions que l'export
    # global (pas de binaires d'image — juste les noms de fichiers, comme le global ; pas de
    # votes/voix/config vote). L'import existant l'avale tel quel (upsert par uid/nom, invariant 2).
    subtree = None if root_id is None else set(_project_descendants(db, root_id))
    cats = {
        r["id"]: r["name"]
        for r in db.execute("SELECT id, name FROM categories").fetchall()
    }
    # Un sous-arbre n'embarque ni liens (rattachés aux catégories, pas aux projets) ni
    # catégories (aucun mémo/projet ne les référence). Les PRIORITÉS restent (référentiel :
    # `memos.priority` est remappé par NOM à l'import — invariant 1 v10).
    links = [] if subtree is not None else db.execute(
        f"SELECT {LINK_FIELDS} FROM links ORDER BY position, id"
    ).fetchall()
    if subtree is not None:
        ph = ",".join("?" * len(subtree))
        memos = db.execute(
            f"SELECT * FROM memos WHERE COALESCE(deleted_at, '') = '' AND project_id IN ({ph}) "
            "ORDER BY position, id", list(subtree)
        ).fetchall()
    else:
        memos = db.execute(
            "SELECT * FROM memos WHERE COALESCE(deleted_at, '') = '' ORDER BY position, id"
        ).fetchall()
    categories = [] if subtree is not None else db.execute(
        "SELECT name, position, color, emoji FROM categories ORDER BY position, id"
    ).fetchall()
    all_projects = db.execute(
        "SELECT id, name, position, color, tags, emoji, parent_id, location, description, marker_color, is_trip FROM projects ORDER BY position, id"
    ).fetchall()
    # proj_names = TOUS les projets (pour résoudre le nom du parent, y compris le parent du
    # dossier racine qui est HORS du sous-arbre → à l'import il raccroche si ce nom existe,
    # sinon le dossier atterrit à la racine). Export = seulement les projets du sous-arbre.
    proj_names = {r["id"]: r["name"] for r in all_projects}
    projects = all_projects if subtree is None else [r for r in all_projects if r["id"] in subtree]
    # uids des mémos du périmètre → filtre commentaires + historique (par memo_uid).
    memo_uids = {m["uid"] for m in memos if m["uid"]} if subtree is not None else None
    out_links = []
    for r in links:
        d = dict(r)
        d.pop("id", None)
        d["category"] = cats.get(d.pop("category_id", None), "")
        out_links.append(d)
    # [ATTACHMENTS] v22 : pièces jointes nichées par mémo (noms de fichiers seuls, jamais le binaire).
    att_by_id = {}
    if memos:
        ph_m = ",".join("?" * len(memos))
        for a in db.execute(
            "SELECT memo_id, filename, orig_name, mime, size, preview, created_at, created_by "
            f"FROM attachments WHERE memo_id IN ({ph_m}) ORDER BY id", [m["id"] for m in memos]
        ).fetchall():
            att_by_id.setdefault(a["memo_id"], []).append({
                "filename": a["filename"], "orig_name": a["orig_name"] or a["filename"],
                "mime": a["mime"] or "", "size": a["size"] or 0,
                "preview": 1 if a["preview"] else 0, "created_at": a["created_at"], "created_by": a["created_by"] or "",
            })
    out_memos = []
    for r in memos:
        d = _memo_dict(r)
        mid = d.pop("id", None)
        d.pop("created_by_display", None)  # runtime-only, jamais exporté ; created_by (brut) reste
        d["project"] = proj_names.get(d.pop("project_id", None), "")
        d["attachments"] = att_by_id.get(mid, [])  # [ATTACHMENTS] v22
        out_memos.append(d)
    # [FOLDER-ATTACHMENTS] v23 : pièces jointes de dossier nichées par projet (noms de fichiers
    # seuls, jamais le binaire — comme les mémos). Rattachées par NOM à l'import (comme le reste
    # d'un projet). Absent chez un importeur v1→v22 = aucune pièce jointe de dossier (compat).
    proj_att_by_id = {}
    if projects:
        ph_p = ",".join("?" * len(projects))
        for a in db.execute(
            "SELECT project_id, filename, orig_name, mime, size, preview, created_at, created_by "
            f"FROM attachments WHERE project_id IN ({ph_p}) ORDER BY id", [p["id"] for p in projects]
        ).fetchall():
            proj_att_by_id.setdefault(a["project_id"], []).append({
                "filename": a["filename"], "orig_name": a["orig_name"] or a["filename"],
                "mime": a["mime"] or "", "size": a["size"] or 0,
                "preview": 1 if a["preview"] else 0, "created_at": a["created_at"], "created_by": a["created_by"] or "",
            })
    out_projects = [
        {
            "name": r["name"],
            "position": r["position"],
            "color": r["color"],
            "tags": r["tags"],
            "emoji": r["emoji"],
            "parent": proj_names.get(r["parent_id"], ""),
            "location": _parse_location(r["location"]),
            "description": _row_get(r, "description"),
            "marker_color": _row_get(r, "marker_color"),
            # [MAP-TIMELINE] v20 : valeur BRUTE non résolue (null = hérite).
            "is_trip": _row_get(r, "is_trip", None),
            "attachments": proj_att_by_id.get(r["id"], []),  # [FOLDER-ATTACHMENTS] v23
        }
        for r in projects
    ]
    history = db.execute(
        "SELECT memo_uid, content, project, done_at FROM memo_history "
        "ORDER BY done_at, id"
    ).fetchall()
    if subtree is not None:
        history = [r for r in history if r["memo_uid"] in memo_uids]
    priorities = db.execute(
        "SELECT id, name, color, position FROM priorities ORDER BY position, id"
    ).fetchall()
    comments = db.execute(
        "SELECT c.id, c.memo_uid, c.author, c.body, c.created_at, "
        "COALESCE(c.priority, 0) AS priority, p.created_at AS parent_created_at "
        "FROM memo_comments c LEFT JOIN memo_comments p ON p.id = c.parent_id "
        "WHERE c.memo_uid != '' ORDER BY c.created_at, c.id"
    ).fetchall()
    if subtree is not None:
        comments = [r for r in comments if r["memo_uid"] in memo_uids]
    # [COMMENT-REACTIONS] v21 : réactions brutes (voter comme created_by v19) nichées par commentaire.
    reacts_by_cid = {}
    for rr in db.execute("SELECT comment_id, emoji, voter, created_at FROM comment_reactions ORDER BY created_at, id").fetchall():
        reacts_by_cid.setdefault(rr["comment_id"], []).append(
            {"emoji": rr["emoji"], "voter": rr["voter"], "created_at": rr["created_at"]})
    out_comments = []
    for r in comments:
        d = dict(r)
        cid = d.pop("id", None)
        d["reactions"] = reacts_by_cid.get(cid, [])
        out_comments.append(d)
    result = {
        "version": 23,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": [dict(r) for r in categories],
        "projects": out_projects,
        "priorities": [dict(r) for r in priorities],
        "links": out_links,
        "memos": out_memos,
        "history": [dict(r) for r in history],
        "comments": out_comments,
    }
    # [REACTION-PALETTE] v21 : palette custom exportée avec les réglages (comme les priorités).
    # Émise SEULEMENT si l'owner a configuré une palette (clé présente) → un export par défaut
    # reste sans le champ, donc l'import v20/v21 sans palette = base par défaut, aucun crash.
    if db.execute("SELECT 1 FROM app_state WHERE key = 'reaction_emojis'").fetchone():
        result["reaction_emojis"] = _reaction_palette(db)
    return result


def _rotate_backups():
    cutoff = time.time() - BACKUP_KEEP_DAYS * 86400
    for name in os.listdir(BACKUP_DIR):
        p = os.path.join(BACKUP_DIR, name)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def _create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        data = _build_export(conn)
        day = date.today().isoformat()
        json_path = os.path.join(BACKUP_DIR, f"export-{day}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        db_copy = os.path.join(BACKUP_DIR, f"dashboard-{day}.db")
        dest = sqlite3.connect(db_copy)
        with dest:
            conn.backup(dest)
        dest.close()
        _rotate_backups()
        return [os.path.basename(json_path), os.path.basename(db_copy)]
    finally:
        conn.close()


def _maybe_backup():
    day = date.today().isoformat()
    if not os.path.exists(os.path.join(BACKUP_DIR, f"export-{day}.json")):
        _create_backup()


def _purge_trash():
    # Purge définitive des mémos en corbeille depuis plus de BACKUP_KEEP_DAYS jours.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=BACKUP_KEEP_DAYS)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM memos WHERE COALESCE(deleted_at, '') != '' "
                "AND deleted_at < ?",
                (cutoff,),
            ).fetchall()
        ]
        for mid in ids:
            r = conn.execute("SELECT images FROM memos WHERE id = ?", (mid,)).fetchone()
            if r:
                _delete_image_files(r["images"])
                _forget_image_meta(conn, r["images"])  # [PHOTO-MAP]
            conn.execute("DELETE FROM memos WHERE id = ?", (mid,))
            conn.execute(
                "DELETE FROM shares WHERE kind = 'memo' AND target_id = ?", (mid,)
            )
            conn.execute("DELETE FROM memo_comments WHERE memo_id = ?", (mid,))
        conn.commit()
    finally:
        conn.close()


def _backfill_image_meta():
    # [PHOTO-MAP] Remplit image_meta pour les images ajoutées AVANT la feature.
    # Idempotent : ne traite que les filenames absents de image_meta (skip le reste,
    # donc une 2e passe ne fait rien). Throttlé : ne dort 1.1 s qu'APRÈS une image
    # qui a réellement déclenché un appel réseau Nominatim (GPS non encore en cache),
    # pour ne pas marteler le géocodeur (~1 req/s). Daemon, connexion propre, n'ouvre
    # jamais le boot : un échec par image est silencieux.
    time.sleep(20)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    except Exception:
        return
    try:
        known = {r["filename"] for r in conn.execute(
            "SELECT filename FROM image_meta"
        ).fetchall()}
        rows = conn.execute(
            "SELECT id, uid, images FROM memos WHERE COALESCE(deleted_at, '') = ''"
        ).fetchall()
        for r in rows:
            try:
                names = json.loads(r["images"] or "[]")
            except Exception:
                names = []
            for name in names:
                name = os.path.basename(str(name))
                if not name or name in known:
                    continue
                cache_size = len(_exif_geo_cache)
                _record_image_meta(conn, name, r["id"], r["uid"])
                conn.commit()
                known.add(name)
                # Géocode réseau réel = le cache a grandi → respecter le débit Nominatim.
                if len(_exif_geo_cache) > cache_size:
                    time.sleep(1.1)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _backup_loop():
    time.sleep(15)
    while True:
        try:
            _maybe_backup()
        except Exception:
            pass
        try:
            _purge_trash()
        except Exception:
            pass
        time.sleep(3600)


@app.route("/api/backups", methods=["GET"])
def list_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    out = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        p = os.path.join(BACKUP_DIR, name)
        if os.path.isfile(p):
            out.append(
                {
                    "name": name,
                    "size": os.path.getsize(p),
                    "mtime": datetime.fromtimestamp(
                        os.path.getmtime(p), tz=timezone.utc
                    ).isoformat(),
                }
            )
    return jsonify({"backups": out, "keep_days": BACKUP_KEEP_DAYS})


@app.route("/api/backups", methods=["POST"])
def create_backup_now():
    return jsonify({"created": _create_backup()}), 201


def _memo_import_sig(content, title, done, due_date, due_time):
    """[IMPORT-PREVIEW] Signature de comparaison d'un mémo (indépendante de l'instance et de
    updated_at) : contenu visible. Deux mémos de même signature = « identiques » → skip."""
    return "\x01".join([
        (content or "").strip(),
        (title or "").strip(),
        "1" if done else "0",
        (due_date or "").strip(),
        (due_time or "").strip(),
    ])


def _import_dry_run(db, data):
    """[IMPORT-PREVIEW] Analyse LECTURE PURE d'un fichier d'import (aucune écriture, aucun
    bump _data_version) → rapport {projects (arbre), memos, bilan}. Statuts D2 :
    project new/merge (par nom) ; mémo new/skip/conflict(active|trashed) (par uid + signature)."""
    existing_proj = {(r["name"] or "").strip().lower() for r in db.execute("SELECT name FROM projects").fetchall()}
    by_name = {}
    for p in (data.get("projects") or []):
        if not isinstance(p, dict):
            continue
        nm = (p.get("name") or "").strip()
        if not nm:
            continue
        by_name[nm] = {"name": nm, "parent": (p.get("parent") or "").strip(),
                       "status": "merge" if nm.lower() in existing_proj else "new", "children": []}
    roots = []
    for node in by_name.values():
        par = node["parent"]
        (by_name[par]["children"] if (par and par in by_name) else roots).append(node)
    def _clean(n):
        return {"name": n["name"], "status": n["status"], "children": [_clean(c) for c in n["children"]]}
    proj_tree = [_clean(r) for r in roots]
    proj_new = sum(1 for n in by_name.values() if n["status"] == "new")
    proj_merge = len(by_name) - proj_new

    memos_by_uid = {r["uid"]: r for r in db.execute("SELECT * FROM memos WHERE uid != ''").fetchall()}
    out_memos = []
    c_new = c_skip = c_active = c_trashed = 0
    for m in (data.get("memos") or []):
        if not isinstance(m, dict):
            continue
        content = (m.get("content") or "").strip()
        title = _clean_title(m.get("title"))
        if not content and not title:
            continue
        uid = (m.get("uid") or "").strip()
        row = memos_by_uid.get(uid) if uid else None
        entry = {"uid": uid, "title": title or _text_excerpt(content, 60),
                 "project_name": (m.get("project") or "").strip()}
        if not row:
            entry["status"] = "new"; c_new += 1
        elif (_row_get(row, "deleted_at") or "").strip():
            entry.update(status="conflict", conflict_kind="trashed",
                         updated_local=(row["updated_at"] or ""), updated_fichier=(m.get("updated_at") or ""))
            c_trashed += 1
        else:
            sig_f = _memo_import_sig(content, title, m.get("done"), (m.get("due_date") or "").strip(), m.get("due_time"))
            sig_d = _memo_import_sig(row["content"], _row_get(row, "title"), row["done"], row["due_date"], _row_get(row, "due_time"))
            if sig_f == sig_d:
                entry["status"] = "skip"; c_skip += 1
            else:
                entry.update(status="conflict", conflict_kind="active",
                             updated_local=(row["updated_at"] or ""), updated_fichier=(m.get("updated_at") or ""))
                c_active += 1
        out_memos.append(entry)
    return {
        "projects": proj_tree,
        "memos": out_memos,
        "bilan": {"projects_new": proj_new, "projects_merge": proj_merge, "memos_new": c_new,
                  "memos_skip": c_skip, "conflicts_active": c_active, "conflicts_trashed": c_trashed},
    }


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

    # [EXPORT-SUBTREE] Import CIBLÉ « Importer ici » : query param optionnel target_parent_id.
    # Ne s'applique qu'aux projets RACINE du fichier qui sont NOUVEAUX (nom inconnu) — invariant 2 :
    # l'import ajoute, il ne réorganise pas. Absent = comportement actuel exact.
    # Cible validée STRICTEMENT : projet existant ET pas lui-même un élément du fichier (anti-cycle).
    target_parent_id = None
    tp_raw = request.args.get("target_parent_id")
    if tp_raw not in (None, "", "0"):
        try:
            tp = int(tp_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "target_parent_id invalide"}), 400
        trow = db.execute("SELECT name FROM projects WHERE id = ?", (tp,)).fetchone()
        if not trow:
            return jsonify({"error": "dossier cible introuvable"}), 400
        file_names_lc = {
            (p.get("name") or "").strip().lower()
            for p in (data.get("projects") or []) if isinstance(p, dict)
        }
        if (trow["name"] or "").strip().lower() in file_names_lc:
            return jsonify({"error": "le dossier cible fait partie du fichier importé (cycle)"}), 400
        target_parent_id = tp

    # [IMPORT-PREVIEW] Dry-run : analyse LECTURE PURE (aucune écriture, pas de commit ni de bump
    # _data_version) → rapport. Retour AVANT toute écriture (ensure_category/project écrivent).
    if request.args.get("dry_run") in ("1", "true", "yes"):
        return jsonify(_import_dry_run(db, data))

    # [IMPORT-PREVIEW] Résolutions par uid : 'overwrite' | 'duplicate' | 'skip'. Absent = skip
    # (= comportement V20.12 : newer-wins par uid). Seul le flux « Importer ici » les envoie.
    res_map = data.get("resolutions") if isinstance(data.get("resolutions"), dict) else {}

    cat_ids = {}

    def ensure_category(name, color="", emoji=""):
        name = (name or "").strip()
        if not name:
            return None
        if name in cat_ids:
            return cat_ids[name]
        row = db.execute(
            "SELECT id, color, emoji FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if row:
            cat_ids[name] = row["id"]
            if color and not (row["color"] or "").strip():
                db.execute(
                    "UPDATE categories SET color = ? WHERE id = ?", (color, row["id"])
                )
            if emoji and not (row["emoji"] or "").strip():
                db.execute(
                    "UPDATE categories SET emoji = ? WHERE id = ?",
                    (_clean_emoji(emoji), row["id"]),
                )
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM categories"
            ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO categories (name, position, color, emoji) VALUES (?, ?, ?, ?)",
                (name, max_pos + 1, color or "", _clean_emoji(emoji)),
            )
            cat_ids[name] = cur.lastrowid
        return cat_ids[name]

    for cat in categories:
        if isinstance(cat, dict):
            ensure_category(
                cat.get("name"),
                (cat.get("color") or "").strip(),
                cat.get("emoji") or "",
            )
        else:
            ensure_category(cat)

    proj_ids = {}
    new_projects = set()  # [EXPORT-SUBTREE] noms des projets CRÉÉS par cet import (racines ciblables)

    def ensure_project(name, color="", tags="", emoji="", location=None, description="", marker_color="", is_trip=None):
        name = (name or "").strip()
        if not name:
            return None
        if name in proj_ids:
            return proj_ids[name]
        row = db.execute(
            "SELECT id, color, tags, emoji, location, description, marker_color, is_trip FROM projects WHERE name = ?", (name,)
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
            if emoji and not (row["emoji"] or "").strip():
                db.execute(
                    "UPDATE projects SET emoji = ? WHERE id = ?",
                    (_clean_emoji(emoji), row["id"]),
                )
            if location and not (row["location"] or "").strip():
                db.execute(
                    "UPDATE projects SET location = ? WHERE id = ?",
                    (_clean_location(location), row["id"]),
                )
            if description and not (_row_get(row, "description") or "").strip():
                db.execute(
                    "UPDATE projects SET description = ? WHERE id = ?",
                    (_clean_description(description), row["id"]),
                )
            if marker_color and not (_row_get(row, "marker_color") or "").strip():
                db.execute(
                    "UPDATE projects SET marker_color = ? WHERE id = ?",
                    (_clean_hex_color(marker_color, ""), row["id"]),
                )
            # [MAP-TIMELINE] v20 : upsert non destructif — n'enrichit que si l'existant
            # n'a PAS tranché (NULL). Un 0/1 local n'est JAMAIS écrasé (ni par NULL,
            # ni par une autre valeur — le tri-état local fait foi).
            it = _clean_is_trip(is_trip)
            if it is not None and _row_get(row, "is_trip", None) is None:
                db.execute(
                    "UPDATE projects SET is_trip = ? WHERE id = ?", (it, row["id"])
                )
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) FROM projects"
            ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO projects (name, color, position, tags, emoji, location, description, marker_color, is_trip) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, color or "", max_pos + 1, _normalize_tags(tags), _clean_emoji(emoji), _clean_location(location), _clean_description(description), _clean_hex_color(marker_color, ""), _clean_is_trip(is_trip)),
            )
            proj_ids[name] = cur.lastrowid
            new_projects.add(name)  # [EXPORT-SUBTREE]
        return proj_ids[name]

    for proj in data.get("projects") or []:
        if isinstance(proj, dict):
            ensure_project(
                proj.get("name"),
                (proj.get("color") or "").strip(),
                proj.get("tags") or "",
                proj.get("emoji") or "",
                proj.get("location"),
                proj.get("description") or "",
                proj.get("marker_color") or "",
                proj.get("is_trip"),  # [MAP-TIMELINE] v20 — absent (v1→v19) = None = hérite
            )
        else:
            ensure_project(proj)

    for proj in data.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        parent_name = (proj.get("parent") or "").strip()
        child_id = proj_ids.get((proj.get("name") or "").strip())
        if not parent_name or not child_id:
            continue
        parent_id = proj_ids.get(parent_name) or (
            lambda r: r["id"] if r else None
        )(db.execute("SELECT id FROM projects WHERE name = ?", (parent_name,)).fetchone())
        if not parent_id:
            continue
        row = db.execute(
            "SELECT parent_id FROM projects WHERE id = ?", (child_id,)
        ).fetchone()
        if row and row["parent_id"] is None:
            resolved, err = _resolve_parent(db, child_id, parent_id)
            if not err:
                db.execute(
                    "UPDATE projects SET parent_id = ? WHERE id = ?",
                    (resolved, child_id),
                )

    # [EXPORT-SUBTREE] Ciblage « Importer ici » : rattache les RACINES NOUVELLES du fichier
    # (parent hors fichier) au dossier cible. N'affecte QUE les projets créés par cet import
    # (jamais un existant → invariant 2). Prime sur la résolution par nom pour ces racines.
    if target_parent_id is not None:
        file_names = {
            (p.get("name") or "").strip()
            for p in (data.get("projects") or []) if isinstance(p, dict) and (p.get("name") or "").strip()
        }
        for proj in data.get("projects") or []:
            if not isinstance(proj, dict):
                continue
            name = (proj.get("name") or "").strip()
            if name not in new_projects:
                continue  # projet existant → jamais déplacé
            par = (proj.get("parent") or "").strip()
            if par and par in file_names:
                continue  # a un parent DANS le fichier → sous-dossier, pas une racine
            child_id = proj_ids.get(name)
            if not child_id:
                continue
            resolved, err = _resolve_parent(db, child_id, target_parent_id)
            if not err:
                db.execute("UPDATE projects SET parent_id = ? WHERE id = ?", (resolved, child_id))

    # [FOLDER-ATTACHMENTS] v23 : pièces jointes de dossier, rattachées par NOM (comme le projet).
    _now_pa = datetime.now(timezone.utc).isoformat()
    for proj in data.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        pid = proj_ids.get((proj.get("name") or "").strip())
        if pid:
            _import_project_attachments(db, pid, proj.get("attachments"), _now_pa)

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

    # [REACTION-PALETTE] Restaure la palette custom SI le fichier en fournit une ET qu'aucune
    # config locale n'existe (non destructif : ne clobbe jamais la palette courante de l'owner).
    # Fichier v20/v21 sans le champ = base par défaut, aucun crash. Chaque emoji re-validé.
    rp = data.get("reaction_emojis")
    if isinstance(rp, list) and db.execute(
        "SELECT 1 FROM app_state WHERE key = 'reaction_emojis'"
    ).fetchone() is None:
        cleaned = []
        for e in rp:
            c = _clean_reaction_emoji(e)
            if c and c not in cleaned:
                cleaned.append(c)
        if cleaned:
            _set_state(db, "reaction_emojis", json.dumps(cleaned, ensure_ascii=False))

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

    existing_memos = set()
    for r in db.execute("SELECT content, title FROM memos").fetchall():
        c = (r["content"] or "").strip()
        existing_memos.add(c if c else "\x00title:" + (_row_get(r, "title") or "").strip())
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
            memo_emoji = _clean_emoji(memo.get("emoji"))
            memo_location = _clean_location(memo.get("location"))
            title = _clean_title(memo.get("title"))
            assignees = _assignees_json(memo.get("assignees"))
            memo_marker = _clean_hex_color(memo.get("marker_color"), "")
            memo_groups = _map_groups_json(memo.get("map_groups"))
            memo_time = _clean_due_time(memo.get("due_time")) if due_date else ""
            memo_created_by = str(memo.get("created_by") or "").strip()[:200]
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
            memo_emoji = ""
            memo_location = ""
            title = ""
            assignees = "[]"
            memo_marker = ""
            memo_groups = "[]"
            memo_time = ""
            memo_created_by = ""
        if not content and not title:
            continue

        res = str(res_map.get(uid) or "").strip().lower() if uid else ""
        # [IMPORT-PREVIEW] 'duplicate' → ne touche pas l'existant, tombe vers l'INSERT (uid neuf).
        if uid and uid in memos_by_uid and res != "duplicate":
            existing = memos_by_uid[uid]
            merged_images = images if images != "[]" else (existing["images"] or "[]")
            merged_marker = memo_marker or _row_get(existing, "marker_color")
            merged_time = memo_time or _row_get(existing, "due_time")
            if not due_date:
                merged_time = ""
            merged_created_by = memo_created_by or _row_get(existing, "created_by")
            if res == "overwrite":
                # [IMPORT-PREVIEW] Écraser/Restaurer : force la mise à jour, restaure si en corbeille
                # (deleted_at=''), rattache au projet visé par l'import (project_id résolu du fichier).
                db.execute(
                    "UPDATE memos SET content=?, done=?, due_date=?, due_time=?, priority=?, "
                    "subtasks=?, project_id=?, images=?, recurrence=?, emoji=?, location=?, "
                    "title=?, assignees=?, marker_color=?, map_groups=?, created_by=?, deleted_at='', updated_at=? WHERE id=?",
                    (content, done, due_date, merged_time, priority, subtasks, project_id, merged_images, recurrence, memo_emoji, memo_location, title, assignees, merged_marker, memo_groups, merged_created_by, (updated or now), existing["id"]),
                )
                updated_memos += 1
            elif updated and updated > (existing["updated_at"] or ""):
                db.execute(
                    "UPDATE memos SET content=?, done=?, due_date=?, due_time=?, priority=?, "
                    "subtasks=?, project_id=?, images=?, recurrence=?, emoji=?, location=?, "
                    "title=?, assignees=?, marker_color=?, map_groups=?, created_by=?, updated_at=? WHERE id=?",
                    (content, done, due_date, merged_time, priority, subtasks, project_id, merged_images, recurrence, memo_emoji, memo_location, title, assignees, merged_marker, memo_groups, merged_created_by, updated, existing["id"]),
                )
                updated_memos += 1
            else:
                skipped_memos += 1
            _import_memo_attachments(db, existing["id"], uid, memo.get("attachments"), now)  # [ATTACHMENTS] v22
            continue

        # INSERT (mémo nouveau OU 'duplicate' explicite). Le dédup par contenu est court-circuité
        # pour une duplication demandée (on VEUT une copie), et l'uid est régénéré.
        if res != "duplicate":
            dedup_key = content if content else "\x00title:" + title
            if dedup_key in existing_memos:
                skipped_memos += 1
                continue
            existing_memos.add(dedup_key)
        max_mpos += 1
        new_uid = str(uuid.uuid4()) if res == "duplicate" else (uid or str(uuid.uuid4()))
        db.execute(
            "INSERT INTO memos (content, position, created_at, uid, updated_at, "
            "done, due_date, due_time, priority, subtasks, project_id, images, recurrence, emoji, location, "
            "title, assignees, marker_color, map_groups, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (content, max_mpos, created, new_uid, updated or created, done, due_date, memo_time, priority, subtasks, project_id, images, recurrence, memo_emoji, memo_location, title, assignees, memo_marker, memo_groups, memo_created_by),
        )
        memos_by_uid[new_uid] = db.execute(
            "SELECT * FROM memos WHERE uid = ?", (new_uid,)
        ).fetchone()
        _import_memo_attachments(db, memos_by_uid[new_uid]["id"], new_uid, memo.get("attachments"), now)  # [ATTACHMENTS] v22
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

    existing_comments = set()
    comment_id_by_key = {}
    for r in db.execute(
        "SELECT id, memo_uid, created_at, author FROM memo_comments"
    ).fetchall():
        existing_comments.add((r["memo_uid"], r["created_at"], r["author"]))
        comment_id_by_key[(r["memo_uid"], r["created_at"])] = r["id"]
    imported_comments = 0
    for c in data.get("comments") or []:
        if not isinstance(c, dict):
            continue
        c_uid = (c.get("memo_uid") or "").strip()
        c_body = _clean_comment_body(c.get("body"))
        c_at = (c.get("created_at") or "").strip()
        c_author = str(c.get("author") or "moi").strip()[:140] or "moi"
        if not c_uid or not c_body or not c_at:
            continue
        memo_row = memos_by_uid.get(c_uid)
        if not memo_row:
            continue
        key = (c_uid, c_at, c_author)
        if key in existing_comments:
            cid = comment_id_by_key.get((c_uid, c_at))
        else:
            c_prio = _valid_comment_priority(c.get("priority"))
            parent_at = (c.get("parent_created_at") or "").strip()
            parent_id = comment_id_by_key.get((c_uid, parent_at)) if parent_at else None
            cur = db.execute(
                "INSERT INTO memo_comments (memo_id, memo_uid, author, share_id, body, created_at, parent_id, priority) "
                "VALUES (?, ?, ?, NULL, ?, ?, ?, ?)",
                (memo_row["id"], c_uid, c_author, c_body, c_at, parent_id, c_prio),
            )
            existing_comments.add(key)
            cid = cur.lastrowid
            comment_id_by_key[(c_uid, c_at)] = cid
            imported_comments += 1
        # [COMMENT-REACTIONS] v21 : additif non destructif — AJOUTE les réactions manquantes
        # (dédup par UNIQUE(comment_id, emoji, voter)), emoji hors palette ignoré. Compat v1→v20 :
        # champ absent = aucune réaction. Voter brut (comme created_by v19).
        if cid is not None:
            for rr in (c.get("reactions") or []):
                if not isinstance(rr, dict):
                    continue
                # Validation de FORMAT (pas de palette) : un import est non destructif et
                # additif — on préserve les réactions historiques, même sur un emoji retiré
                # de la palette courante (invariant 2). Seule la garbage (texte/HTML) est rejetée.
                r_emoji = _clean_reaction_emoji(rr.get("emoji"))
                if not r_emoji:
                    continue
                r_voter = str(rr.get("voter") or "").strip()[:200]
                r_at = (rr.get("created_at") or "").strip() or now
                db.execute(
                    "INSERT OR IGNORE INTO comment_reactions (comment_id, emoji, voter, created_at) VALUES (?, ?, ?, ?)",
                    (cid, r_emoji, r_voter, r_at),
                )

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
            "imported_comments": imported_comments,
        }
    )


init_db()
threading.Thread(target=_backup_loop, daemon=True).start()
threading.Thread(target=_backfill_image_meta, daemon=True).start()  # [PHOTO-MAP]
