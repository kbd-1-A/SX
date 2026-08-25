"""消息级反馈：对时叙回复的赞/踩 sidecar（自主学习）。

- 与不可变会话日志分离：反馈是本地存储域 sidecar，不进入 messages 表。
- 乐观并发：客户端带 if_version，版本冲突时返回权威当前值。
- 目标校验：只接受非空的 assistant 消息。
- 反馈落地后反哺行为画像（保守、确定性）。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import DB_PATH
from app.memory.behavior import observe_feedback

FEEDBACK_RATINGS = {"positive", "negative"}
FEEDBACK_NOTE_MAX_CHARS = 500

logger = logging.getLogger(__name__)


class FeedbackValidationError(ValueError):
    """反馈目标或取值不合法。"""


class FeedbackVersionConflict(RuntimeError):
    """乐观并发冲突：携带服务端权威当前值。"""

    def __init__(self, current: dict):
        super().__init__("feedback_version_conflict")
        self.current = current


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _validate_message(conn: sqlite3.Connection, message_id: int) -> str:
    row = conn.execute(
        "SELECT role, content FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    if not row:
        raise FeedbackValidationError("feedback message not found")
    if row["role"] != "assistant":
        raise FeedbackValidationError("feedback only applies to assistant messages")
    content = (row["content"] or "").strip()
    if not content:
        raise FeedbackValidationError(
            "feedback only applies to non-empty assistant messages"
        )
    return content


def _row_to_feedback(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "message_id": row["message_id"],
        "rating": row["rating"],
        "note": row["note"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def set_feedback(
    message_id: int,
    rating: str,
    note: str | None = None,
    if_version: int | None = None,
) -> dict:
    """新增或更新反馈（乐观并发 + 目标校验），并触发保守的行为学习。

    学习失败不影响反馈落库；版本冲突抛 FeedbackVersionConflict。
    """
    if rating not in FEEDBACK_RATINGS:
        raise FeedbackValidationError("unsupported feedback rating")
    note = (note or "").strip()
    if len(note) > FEEDBACK_NOTE_MAX_CHARS:
        raise FeedbackValidationError("feedback note is too long")

    conn = _conn()
    try:
        content = _validate_message(conn, message_id)
        existing = conn.execute(
            "SELECT * FROM message_feedback WHERE message_id = ?", (message_id,)
        ).fetchone()
        if existing and if_version is not None and int(existing["version"]) != int(if_version):
            raise FeedbackVersionConflict(_row_to_feedback(existing))
        if existing:
            conn.execute(
                "UPDATE message_feedback SET rating = ?, note = ?, "
                "version = version + 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE message_id = ?",
                (rating, note, message_id),
            )
        else:
            conn.execute(
                "INSERT INTO message_feedback (message_id, rating, note, version) "
                "VALUES (?, ?, ?, 1)",
                (message_id, rating, note),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM message_feedback WHERE message_id = ?", (message_id,)
        ).fetchone()
    except (FeedbackVersionConflict, FeedbackValidationError):
        conn.close()
        raise
    feedback = _row_to_feedback(row)
    conn.close()

    try:
        observe_feedback(content, rating, message_id)
    except Exception:
        logger.exception("feedback_learning_failed message_id=%s", message_id)
    return feedback


def get_feedback(message_id: int) -> dict | None:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM message_feedback WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return _row_to_feedback(row) if row else None


def clear_feedback(message_id: int) -> bool:
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM message_feedback WHERE message_id = ?", (message_id,)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_feedback(limit: int = 200) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM message_feedback ORDER BY updated_at DESC, id DESC LIMIT ?",
        (max(1, min(limit, 1000)),),
    ).fetchall()
    conn.close()
    return [_row_to_feedback(row) for row in rows]


def feedback_stats(days: int = 30) -> dict:
    """近 N 天反馈聚合，供画像页或后续策略管线消费。"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = _conn()
    row = conn.execute(
        "SELECT "
        "COALESCE(SUM(CASE WHEN rating = 'positive' THEN 1 ELSE 0 END), 0) AS positive, "
        "COALESCE(SUM(CASE WHEN rating = 'negative' THEN 1 ELSE 0 END), 0) AS negative "
        "FROM message_feedback WHERE updated_at >= ?",
        (since,),
    ).fetchone()
    recent = conn.execute(
        "SELECT message_id, rating, note, updated_at FROM message_feedback "
        "WHERE note != '' AND updated_at >= ? ORDER BY updated_at DESC LIMIT 20",
        (since,),
    ).fetchall()
    conn.close()
    notes = [
        {
            "message_id": r["message_id"],
            "rating": r["rating"],
            "note": r["note"],
            "updated_at": r["updated_at"],
        }
        for r in recent
    ]
    return {
        "days": days,
        "positive": int(row["positive"]),
        "negative": int(row["negative"]),
        "total": int(row["positive"]) + int(row["negative"]),
        "recent_notes": notes,
    }
