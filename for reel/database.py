import sqlite3
import os
from config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "reels_history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_reels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reel_id TEXT UNIQUE,
            original_url TEXT,
            views INTEGER,
            likes INTEGER,
            caption TEXT,
            local_filepath TEXT,
            published_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_reel_processed(reel_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM processed_reels WHERE reel_id = ?", (reel_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def record_reel(reel_id: str, original_url: str, views: int, likes: int, caption: str, local_filepath: str, status: str = "downloaded"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO processed_reels 
        (reel_id, original_url, views, likes, caption, local_filepath, published_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (reel_id, original_url, views, likes, caption, local_filepath, status))
    conn.commit()
    conn.close()

def mark_published(reel_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE processed_reels SET published_status = 'published' WHERE reel_id = ?", (reel_id,))
    conn.commit()
    conn.close()
