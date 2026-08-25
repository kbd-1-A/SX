"""P1 观察层 + P2 隐式反馈：让时叙不靠对话也能学习用户的节奏。

- 观察层（P1，纯确定性、零 LLM）：每轮对话落一条元数据（时间/面具/动作/情绪/长度），
  聚合出活跃时段、话题热度、风格-续聊相关性，形成「生活节奏画像」注入提示词。
- 隐式反馈（P2）：从行为痕迹推断信号——用户紧接着继续聊（正向）、中断长回复（负向），
  写入 append-only 表，按保守阈值反哺已有的行为画像。
- 全程可审计；任何学习副作用失败都不影响主对话。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import DB_PATH

logger = logging.getLogger(__name__)

# Windows 的 Python 环境可能未安装 IANA tzdata；中国标准时间无夏令时，用固定 UTC+8。
LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

CONTINUATION_WINDOW_MINUTES = 15
INTERRUPT_MIN_CHARS = 60
MIN_RHYTHM_TURNS = 5
RHYTHM_DAYS = 30

MASK_LABELS = {
    "daily_companion": "日常",
    "old_bestie": "吐槽",
    "love_guide": "感情",
    "work_advisor": "工作",
}
MODE_LABELS = {
    "catch_up": "日常接话",
    "vent_with_user": "一起吐槽",
    "comfort": "低落陪伴",
    "advise": "给建议",
    "work_think": "工作参谋",
    "play": "玩梗",
    "clarify": "澄清",
    "close_loop": "收束",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _local_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(LOCAL_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=LOCAL_TZ)
    return now.astimezone(LOCAL_TZ)


def _utc_since(days: int, now: datetime | None = None) -> str:
    """把「N 天前」换算成 UTC 字符串，与 SQLite CURRENT_TIMESTAMP 比较。"""
    local = _local_now(now) - timedelta(days=days)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _minutes_ago_utc(minutes: int, now: datetime | None = None) -> str:
    local = _local_now(now) - timedelta(minutes=minutes)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# P1 观察层
# ---------------------------------------------------------------------------


def record_turn(
    *,
    session_id: int,
    user_message_id: int | None,
    assistant_message_id: int | None,
    mask: str = "",
    reply_mode: str = "",
    emotion: str | None = None,
    user_chars: int = 0,
    reply_chars: int = 0,
    reply_seconds: float = 0.0,
    now: datetime | None = None,
) -> int | None:
    """每轮对话落一条观察记录；hour_of_day/weekday 用本地时间预计算。"""
    local_now = _local_now(now)
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO turn_observations "
        "(session_id, user_message_id, assistant_message_id, mask, reply_mode, emotion, "
        "user_chars, reply_chars, reply_seconds, hour_of_day, weekday) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            user_message_id,
            assistant_message_id,
            mask or "",
            reply_mode or "",
            emotion or "",
            user_chars,
            reply_chars,
            reply_seconds,
            local_now.hour,
            local_now.weekday(),
        ),
    )
    conn.commit()
    conn.close()
    return int(cur.lastrowid)


def get_rhythm_profile(days: int = RHYTHM_DAYS, now: datetime | None = None) -> dict[str, Any]:
    """聚合近 N 天观察：活跃时段、话题热度、风格-续聊相关性。"""
    since = _utc_since(days, now)
    conn = _conn()

    row = conn.execute(
        "SELECT COUNT(*) AS total FROM turn_observations WHERE created_at >= ?",
        (since,),
    ).fetchone()
    total_turns = int(row["total"]) if row else 0

    hours = conn.execute(
        "SELECT hour_of_day, COUNT(*) AS count FROM turn_observations "
        "WHERE created_at >= ? GROUP BY hour_of_day ORDER BY count DESC, hour_of_day LIMIT 3",
        (since,),
    ).fetchall()
    active_hours = [{"hour": r["hour_of_day"], "count": r["count"]} for r in hours]

    weekdays = conn.execute(
        "SELECT weekday, COUNT(*) AS count FROM turn_observations "
        "WHERE created_at >= ? GROUP BY weekday ORDER BY count DESC, weekday LIMIT 7",
        (since,),
    ).fetchall()
    weekday_distribution = [
        {"weekday": r["weekday"], "count": r["count"]} for r in weekdays
    ]

    topics = conn.execute(
        "SELECT mask, COUNT(*) AS count FROM turn_observations "
        "WHERE created_at >= ? AND mask != '' GROUP BY mask ORDER BY count DESC, mask LIMIT 3",
        (since,),
    ).fetchall()
    topic_heat = [{"mask": r["mask"], "count": r["count"]} for r in topics]

    modes = conn.execute(
        "SELECT o.reply_mode, COUNT(DISTINCT o.id) AS total, "
        "COUNT(DISTINCT i.id) AS continued "
        "FROM turn_observations o "
        "LEFT JOIN implicit_feedback i "
        "  ON i.assistant_message_id = o.assistant_message_id AND i.signal = 'continued_after' "
        "WHERE o.created_at >= ? AND o.reply_mode != '' "
        "GROUP BY o.reply_mode ORDER BY total DESC",
        (since,),
    ).fetchall()
    conn.close()

    continuation_by_mode = [
        {
            "reply_mode": r["reply_mode"],
            "total": int(r["total"]),
            "continued": int(r["continued"]),
            "rate": round(int(r["continued"]) / int(r["total"]), 2)
            if int(r["total"])
            else 0.0,
        }
        for r in modes
    ]
    return {
        "days": days,
        "total_turns": total_turns,
        "active_hours": active_hours,
        "weekday_distribution": weekday_distribution,
        "topic_heat": topic_heat,
        "continuation_by_mode": continuation_by_mode,
    }


def format_rhythm_profile(days: int = RHYTHM_DAYS) -> str:
    """注入 system prompt 的节奏观察；任何失败静默返回空，绝不影响主回复。"""
    try:
        profile = get_rhythm_profile(days=days)
    except Exception:
        logger.exception("rhythm_profile_load_failed")
        return ""
    lines = [
        "# 关于我们的节奏（观察统计）",
        "- 仅用于调整语气与节奏，不构成事实记忆。",
    ]
    if profile["total_turns"] < MIN_RHYTHM_TURNS:
        return "\n".join(lines + ["- 还在了解你的节奏。"])
    if profile["active_hours"]:
        labels = [f"{h['hour']:02d} 点" for h in profile["active_hours"][:2]]
        lines.append(f"- 你最近常在 {'、'.join(labels)} 活跃")
    if profile["topic_heat"]:
        top_topic = profile["topic_heat"][0]
        label = MASK_LABELS.get(top_topic["mask"], top_topic["mask"])
        lines.append(f"- 聊「{label}」的次数更多")
    candidates = [
        mode
        for mode in profile["continuation_by_mode"]
        if mode["total"] >= 2 and mode["rate"] >= 0.6
    ]
    if candidates:
        best = max(candidates, key=lambda mode: mode["rate"])
        label = MODE_LABELS.get(best["reply_mode"], best["reply_mode"])
        lines.append(f"- 我按「{label}」接你时，你更愿意继续聊")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# P2 隐式反馈
# ---------------------------------------------------------------------------


def record_continuation_signal(
    session_id: int, now: datetime | None = None
) -> int | None:
    """用户在上一条 assistant 回复后短时间内继续发消息 → 正向续聊信号。"""
    since = _minutes_ago_utc(CONTINUATION_WINDOW_MINUTES, now)
    conn = _conn()
    row = conn.execute(
        "SELECT id FROM messages WHERE session_id = ? AND role = 'assistant' "
        "AND content != '' AND created_at >= ? ORDER BY id DESC LIMIT 1",
        (session_id, since),
    ).fetchone()
    if not row:
        conn.close()
        return None
    cur = conn.execute(
        "INSERT INTO implicit_feedback (session_id, assistant_message_id, signal, polarity) "
        "VALUES (?, ?, 'continued_after', 'positive')",
        (session_id, row["id"]),
    )
    conn.commit()
    conn.close()
    return int(cur.lastrowid)


def record_interrupt_signal(
    session_id: int, partial: str, now: datetime | None = None
) -> int | None:
    """用户中断了正在生成的长回复 → 负向信号（仅当部分回复足够长）。"""
    partial = (partial or "").strip()
    if len(partial) < INTERRUPT_MIN_CHARS:
        return None
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO implicit_feedback (session_id, signal, polarity, content) "
        "VALUES (?, 'interrupted_long', 'negative', ?)",
        (session_id, partial[-500:]),
    )
    conn.commit()
    conn.close()
    return int(cur.lastrowid)


def _mark_applied(signal_id: int) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE implicit_feedback SET applied = 1 WHERE id = ?", (signal_id,)
    )
    conn.commit()
    conn.close()


def apply_implicit_learning(limit: int = 50) -> int:
    """把未消费的中断长回复信号反哺行为画像。

    保守：复用 behavior 的「3 次才激活」阈值，单次中断不会改人格；
    失败只记日志并保留信号（下次再消费），绝不阻塞主流程。
    """
    from app.memory.behavior import observe_feedback

    conn = _conn()
    rows = conn.execute(
        "SELECT id, content FROM implicit_feedback "
        "WHERE applied = 0 AND signal = 'interrupted_long' AND content != '' "
        "ORDER BY id ASC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    conn.close()
    if not rows:
        return 0

    applied = 0
    for row in rows:
        try:
            observe_feedback(row["content"], "negative", None)
            _mark_applied(int(row["id"]))
            applied += 1
        except Exception:
            logger.exception("implicit_learning_failed signal_id=%s", row["id"])
            continue
    return applied
