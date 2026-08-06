"""SQLite 读写：会话、消息。"""

import sqlite3

from app.config import DB_PATH


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_session() -> int:
    """V1 简化为单会话：返回最近一次会话，没有则新建。"""
    conn = _conn()
    row = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        sid = row["id"]
        conn.close()
        return sid
    cur = conn.execute("INSERT INTO sessions DEFAULT VALUES")
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def add_message(session_id: int, role: str, content: str) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def get_messages(session_id: int, limit: int = 50) -> list[dict]:
    """按时间升序返回最近 limit 条。"""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]
