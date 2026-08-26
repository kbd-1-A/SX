"""数据库初始化：建表 + 画像首行。"""

import sqlite3
from pathlib import Path

from app.config import DB_PATH

_SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def _migrate(conn: sqlite3.Connection) -> None:
    """轻量列级迁移：CREATE TABLE IF NOT EXISTS 不改已存在的表，缺列就 ALTER。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_profile)")}
    if "self_memory" not in cols:
        conn.execute(
            "ALTER TABLE user_profile ADD COLUMN self_memory TEXT DEFAULT '{}'"
        )
    if "behavior_profile" not in cols:
        conn.execute(
            "ALTER TABLE user_profile ADD COLUMN behavior_profile TEXT DEFAULT '{}'"
        )
    if "companion_settings" not in cols:
        conn.execute(
            "ALTER TABLE user_profile ADD COLUMN companion_settings TEXT DEFAULT '{}'"
        )
    if "emotion_state" not in cols:
        conn.execute(
            "ALTER TABLE user_profile ADD COLUMN emotion_state TEXT DEFAULT '{}'"
        )
    anchor_cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_anchors)")}
    if "expires_at" not in anchor_cols:
        conn.execute("ALTER TABLE memory_anchors ADD COLUMN expires_at TIMESTAMP")
    if "confirmed_at" not in anchor_cols:
        conn.execute("ALTER TABLE memory_anchors ADD COLUMN confirmed_at TIMESTAMP")

    # follow_ups 升级为目标系统：phase 生命周期 + 阻塞 + 完成时间
    follow_up_cols = {r[1] for r in conn.execute("PRAGMA table_info(follow_ups)")}
    if "phase" not in follow_up_cols:
        conn.execute(
            "ALTER TABLE follow_ups ADD COLUMN phase TEXT NOT NULL DEFAULT 'active'"
        )
    if "blocked_reason" not in follow_up_cols:
        conn.execute("ALTER TABLE follow_ups ADD COLUMN blocked_reason TEXT")
    if "stall_rounds" not in follow_up_cols:
        conn.execute(
            "ALTER TABLE follow_ups ADD COLUMN stall_rounds INTEGER NOT NULL DEFAULT 0"
        )
    if "completed_at" not in follow_up_cols:
        conn.execute("ALTER TABLE follow_ups ADD COLUMN completed_at TIMESTAMP")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # WAL：读不阻塞写，后台学习与对话并发写库不互相等待（持久化到库文件）
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
    _migrate(conn)
    conn.commit()
    conn.close()
