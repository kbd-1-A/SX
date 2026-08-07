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
    anchor_cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_anchors)")}
    if "expires_at" not in anchor_cols:
        conn.execute("ALTER TABLE memory_anchors ADD COLUMN expires_at TIMESTAMP")
    if "confirmed_at" not in anchor_cols:
        conn.execute("ALTER TABLE memory_anchors ADD COLUMN confirmed_at TIMESTAMP")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT OR IGNORE INTO user_profile (id) VALUES (1)")
    _migrate(conn)
    conn.commit()
    conn.close()
