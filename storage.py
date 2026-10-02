import hashlib
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


DEFAULT_DB_PATH = "posts.db"


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Connect to SQLite database with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize posts table if it does not already exist."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT UNIQUE NOT NULL,
                    file_name TEXT NOT NULL,
                    ig_media_id TEXT,
                    caption TEXT,
                    posted_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
    finally:
        conn.close()


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of an image file to prevent duplicates even if renamed."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_already_posted(file_path: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Check if the given file has already been posted based on its SHA-256 hash."""
    init_db(db_path)
    if not os.path.exists(file_path):
        return False

    file_hash = compute_file_hash(file_path)
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM posted_images WHERE file_hash = ? AND status = 'SUCCESS' LIMIT 1",
            (file_hash,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def record_post(
    file_path: str,
    ig_media_id: Optional[str],
    caption: str,
    status: str = "SUCCESS",
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Record an image post attempt in the database."""
    init_db(db_path)
    file_hash = compute_file_hash(file_path) if os.path.exists(file_path) else "unknown"
    file_name = os.path.basename(file_path)
    now = datetime.utcnow().isoformat() + "Z"

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO posted_images
                (file_hash, file_name, ig_media_id, caption, posted_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (file_hash, file_name, ig_media_id, caption, now, status),
            )
    finally:
        conn.close()


def get_posted_count(db_path: str = DEFAULT_DB_PATH) -> int:
    """Return total number of successfully posted images."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posted_images WHERE status = 'SUCCESS'")
        return cur.fetchone()[0]
    finally:
        conn.close()


def list_recent_posts(limit: int = 10, db_path: str = DEFAULT_DB_PATH) -> List[Dict]:
    """Return recent posted records."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM posted_images ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

