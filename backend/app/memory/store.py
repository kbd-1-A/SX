"""SQLite 读写：会话任务、消息。"""

import sqlite3

from app.config import DB_PATH


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_session() -> int:
    """新开一条独立会话任务。"""
    conn = _conn()
    cur = conn.execute("INSERT INTO sessions DEFAULT VALUES")
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def session_exists(session_id: int) -> bool:
    conn = _conn()
    row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row is not None


def get_or_create_session(session_id: int | None = None) -> int:
    """返回指定会话；未指定时返回最近一次会话，没有则新建。"""
    if session_id is not None and session_exists(session_id):
        return session_id
    conn = _conn()
    row = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        sid = row["id"]
        conn.close()
        return sid
    conn.close()
    return create_session()


def get_session_summary(session_id: int) -> dict | None:
    conn = _conn()
    row = conn.execute(
        """
        SELECT
            s.id,
            s.created_at,
            COUNT(m.id) AS message_count,
            MAX(m.created_at) AS last_message_at,
            (
                SELECT content FROM messages
                WHERE session_id = s.id AND role = 'user'
                ORDER BY id DESC LIMIT 1
            ) AS last_user_message,
            (
                SELECT content FROM messages
                WHERE session_id = s.id
                ORDER BY id DESC LIMIT 1
            ) AS last_message
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        WHERE s.id = ?
        GROUP BY s.id
        """,
        (session_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _session_row_to_dict(row)


def list_sessions(limit: int = 30) -> list[dict]:
    """按最近活跃顺序返回会话任务。"""
    conn = _conn()
    rows = conn.execute(
        """
        SELECT
            s.id,
            s.created_at,
            COUNT(m.id) AS message_count,
            MAX(m.created_at) AS last_message_at,
            (
                SELECT content FROM messages
                WHERE session_id = s.id AND role = 'user'
                ORDER BY id DESC LIMIT 1
            ) AS last_user_message,
            (
                SELECT content FROM messages
                WHERE session_id = s.id
                ORDER BY id DESC LIMIT 1
            ) AS last_message
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.id
        ORDER BY COALESCE(MAX(m.created_at), s.created_at) DESC, s.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [_session_row_to_dict(row) for row in rows]


def _session_row_to_dict(row: sqlite3.Row) -> dict:
    last_user = row["last_user_message"] or ""
    last_message = row["last_message"] or ""
    preview = last_user or last_message or "新的记忆时间线"
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "last_message_at": row["last_message_at"] or row["created_at"],
        "message_count": row["message_count"],
        "preview": preview,
    }


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
