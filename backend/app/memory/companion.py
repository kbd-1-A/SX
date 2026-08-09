"""主动陪伴与时间引擎。

引擎不直接向外部设备推送通知，而是生成可持久化的「关心点」：
前端轮询或用户回到应用时即可看到，后续可替换为系统通知/数字人语音播报。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import DB_PATH

# Windows 的 Python 环境可能未安装 IANA tzdata；中国标准时间无夏令时，
# 用固定 UTC+8 可避免时间引擎因时区数据缺失而无法启动。
LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
FREQUENCIES = {"quiet", "normal", "active"}
FREQUENCY_LABELS = {
    "quiet": "安静",
    "normal": "正常",
    "active": "积极",
}
DEFAULT_COMPANION_SETTINGS = {
    "enabled": True,
    "frequency": "normal",
}
GENERAL_DAILY_LIMITS = {
    "quiet": 0,
    "normal": 2,
    "active": 3,
}
INACTIVITY_HOURS = {
    "quiet": 24,
    "normal": 3,
    "active": 1,
}

EVENT_HINTS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("interview", ("面试",), 3),
    ("exam", ("考试", "考证", "答辩"), 3),
    ("date", ("约会", "见面"), 2),
    ("deadline", ("截止", "ddl", "项目上线", "交付"), 3),
    ("work", ("项目", "需求", "排期", "汇报"), 2),
)
OPEN_LOOP_PATTERN = re.compile(r"(?:下次|回头|明天|后天|之后|等会儿|等会)")
MONTH_DAY_PATTERN = re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号]?")
TIME_PATTERN = re.compile(
    r"(?P<period>凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|深夜)?\s*"
    r"(?P<hour>\d{1,2}|[一二两三四五六七八九十]{1,3})(?:\s*(?:点|时|:|：))\s*"
    r"(?P<minute>\d{1,2})?\s*(?:分|分钟)?"
)
RELATIVE_TIME_PATTERN = re.compile(
    r"(?P<amount>半|\d+|[一二两三四五六七八九十]{1,3})"
    r"(?P<unit>分钟|分|小时|钟头)后"
)
WEEKDAY_PATTERN = re.compile(
    r"(?P<prefix>下周|下星期|本周|这周|这星期)?"
    r"(?:周|星期)(?P<weekday>[一二三四五六日天])"
)
CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
WEEKDAY_NUMBERS = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def _parse_hour(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + CHINESE_DIGITS.get(value[1:], 0)
    if len(value) == 3 and value[1] == "十":
        return CHINESE_DIGITS.get(value[0], 0) * 10 + CHINESE_DIGITS.get(value[2], 0)
    if value.endswith("十"):
        return CHINESE_DIGITS.get(value[:-1], 0) * 10
    return CHINESE_DIGITS.get(value)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _local_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(LOCAL_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=LOCAL_TZ)
    return now.astimezone(LOCAL_TZ)


def _timestamp(value: datetime) -> str:
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def _parse_db_timestamp(value: object) -> datetime | None:
    """SQLite CURRENT_TIMESTAMP 为 UTC；转换为本地时间后再参与时间策略。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def _load_settings() -> dict[str, Any]:
    conn = _conn()
    row = conn.execute(
        "SELECT companion_settings FROM user_profile WHERE id = 1"
    ).fetchone()
    conn.close()
    settings = dict(DEFAULT_COMPANION_SETTINGS)
    if row and row["companion_settings"]:
        try:
            saved = json.loads(row["companion_settings"])
        except (json.JSONDecodeError, TypeError):
            saved = {}
        if isinstance(saved, dict):
            if saved.get("frequency") in FREQUENCIES:
                settings["frequency"] = saved["frequency"]
            if isinstance(saved.get("enabled"), bool):
                settings["enabled"] = saved["enabled"]
    return settings


def get_companion_settings() -> dict[str, Any]:
    settings = _load_settings()
    return {
        **settings,
        "frequency_label": FREQUENCY_LABELS[settings["frequency"]],
    }


def set_companion_settings(
    *, frequency: str | None = None, enabled: bool | None = None
) -> dict[str, Any]:
    if frequency is not None and frequency not in FREQUENCIES:
        raise ValueError("unsupported companion frequency")
    if frequency is None and enabled is None:
        return get_companion_settings()
    settings = _load_settings()
    if frequency is not None:
        settings["frequency"] = frequency
    if enabled is not None:
        settings["enabled"] = enabled
    conn = _conn()
    conn.execute(
        "UPDATE user_profile SET companion_settings = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = 1",
        (json.dumps(settings, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return get_companion_settings()


def set_companion_frequency(frequency: str) -> dict[str, Any]:
    return set_companion_settings(frequency=frequency)


def _category_for(text: str) -> tuple[str, int]:
    lowered = text.lower()
    for category, hints, importance in EVENT_HINTS:
        if any(hint in text or hint in lowered for hint in hints):
            return category, importance
    return "other", 1


def _due_from_text(text: str, now: datetime) -> datetime | None:
    relative_match = RELATIVE_TIME_PATTERN.search(text)
    if relative_match:
        raw_amount = relative_match.group("amount")
        if raw_amount == "半":
            amount = 0.5
        else:
            amount = _parse_hour(raw_amount)
        if amount is not None:
            unit = relative_match.group("unit")
            delta = timedelta(
                minutes=amount * 60 if unit in {"小时", "钟头"} else amount
            )
            return now + delta

    time_match = TIME_PATTERN.search(text)
    period = time_match.group("period") if time_match else None
    if time_match:
        hour = _parse_hour(time_match.group("hour"))
        minute = int(time_match.group("minute") or 0)
        if hour is None or minute > 59:
            return None
        if period:
            if hour > 12:
                return None
            if period in {"下午", "傍晚", "晚上"} and 1 <= hour < 12:
                hour += 12
            elif period in {"凌晨", "深夜"} and hour == 12:
                hour = 0
        if hour > 23:
            return None

        month_match = MONTH_DAY_PATTERN.search(text)
        explicit_date = False
        weekday_match = WEEKDAY_PATTERN.search(text)
        if month_match:
            try:
                target = now.replace(
                    month=int(month_match.group("month")),
                    day=int(month_match.group("day")),
                )
            except ValueError:
                return None
            if target.date() < now.date():
                try:
                    target = target.replace(year=target.year + 1)
                except ValueError:
                    return None
            explicit_date = True
        elif weekday_match:
            target = _weekday_target(now, weekday_match)
            explicit_date = True
        elif "后天" in text:
            target = now + timedelta(days=2)
            explicit_date = True
        elif "明天" in text:
            target = now + timedelta(days=1)
            explicit_date = True
        else:
            target = now
        due = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if weekday_match and due <= now:
            due += timedelta(days=7)
        # 没有明确日期时，将已过去的时间理解为下一次提醒，避免刚输入就变成过期。
        if not explicit_date and "今天" not in text and due <= now:
            due += timedelta(days=1)
        return due

    base = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if "后天" in text:
        return base + timedelta(days=2)
    if "明天" in text:
        return base + timedelta(days=1)
    if "今天" in text:
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    weekday_match = WEEKDAY_PATTERN.search(text)
    if weekday_match:
        due = _weekday_target(now, weekday_match).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        return due + timedelta(days=7) if due <= now else due
    match = MONTH_DAY_PATTERN.search(text)
    if not match:
        return None
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        due = now.replace(month=month, day=day, hour=9, minute=0, second=0, microsecond=0)
    except ValueError:
        return None
    if due.date() < now.date():
        try:
            due = due.replace(year=due.year + 1)
        except ValueError:
            return None
    return due


def _weekday_target(now: datetime, match: re.Match[str]) -> datetime:
    target_weekday = WEEKDAY_NUMBERS[match.group("weekday")]
    prefix = match.group("prefix") or ""
    if prefix in {"下周", "下星期"}:
        days_until_next_monday = (7 - now.weekday()) % 7 or 7
        return now + timedelta(days=days_until_next_monday + target_weekday)
    days = (target_weekday - now.weekday()) % 7
    return now + timedelta(days=days)


def _clean_title(text: str) -> str:
    return text.strip(" ，。！？,.!?;；")[:120]


def extract_follow_up_candidates(
    text: str, now: datetime | None = None
) -> list[dict[str, Any]]:
    """从明确事件或未完事项中提取待跟进候选，宁可少建项。"""
    local_now = _local_now(now)
    category, importance = _category_for(text)
    due_at = _due_from_text(text, local_now)
    if not due_at and category == "other" and not OPEN_LOOP_PATTERN.search(text):
        return []
    title = _clean_title(text)
    if len(title) < 2:
        return []
    return [
        {
            "title": title,
            "category": category,
            "importance": importance,
            "due_at": _timestamp(due_at) if due_at else None,
        }
    ]


def create_follow_up(
    *,
    title: str,
    category: str = "other",
    importance: int = 1,
    due_at: str | None = None,
    source_message_id: int | None = None,
) -> dict[str, Any] | None:
    title = _clean_title(title)
    if not title:
        raise ValueError("follow-up title must not be empty")
    if not 1 <= importance <= 3:
        raise ValueError("importance must be between 1 and 3")
    if due_at is not None and _parse_timestamp(due_at) is None:
        raise ValueError("due_at must be YYYY-MM-DD HH:MM:SS")

    conn = _conn()
    existing = conn.execute(
        "SELECT * FROM follow_ups WHERE title = ? AND status = 'open'",
        (title,),
    ).fetchone()
    if existing:
        conn.close()
        return _follow_up_dict(existing)
    cur = conn.execute(
        "INSERT INTO follow_ups "
        "(title, category, due_at, importance, source_message_id) VALUES (?, ?, ?, ?, ?)",
        (title, category, due_at, importance, source_message_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _follow_up_dict(row) if row else None


def create_follow_ups_from_text(
    text: str, source_message_id: int | None, now: datetime | None = None
) -> list[dict[str, Any]]:
    return [
        follow_up
        for candidate in extract_follow_up_candidates(text, now=now)
        if (
            follow_up := create_follow_up(
                title=candidate["title"],
                category=candidate["category"],
                importance=candidate["importance"],
                due_at=candidate["due_at"],
                source_message_id=source_message_id,
            )
        )
        is not None
    ]


def list_follow_ups(limit: int = 20, status: str = "open") -> list[dict[str, Any]]:
    if status not in {"open", "done", "archived", "all"}:
        raise ValueError("unsupported follow-up status")
    conn = _conn()
    query = "SELECT * FROM follow_ups "
    params: tuple[object, ...]
    if status == "all":
        query += "ORDER BY CASE WHEN status = 'open' THEN 0 ELSE 1 END, importance DESC, due_at, id DESC LIMIT ?"
        params = (limit,)
    else:
        query += "WHERE status = ? ORDER BY importance DESC, due_at IS NULL, due_at, id DESC LIMIT ?"
        params = (status, limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_follow_up_dict(row) for row in rows]


def update_follow_up(
    follow_up_id: int,
    *,
    title: str | None = None,
    due_at: str | None | object = ...,
    importance: int | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    updates: list[str] = []
    values: list[object] = []
    if title is not None:
        title = _clean_title(title)
        if not title:
            raise ValueError("follow-up title must not be empty")
        updates.append("title = ?")
        values.append(title)
    if due_at is not ...:
        if due_at is not None and _parse_timestamp(due_at) is None:
            raise ValueError("due_at must be YYYY-MM-DD HH:MM:SS or null")
        updates.append("due_at = ?")
        values.append(due_at)
    if importance is not None:
        if not 1 <= importance <= 3:
            raise ValueError("importance must be between 1 and 3")
        updates.append("importance = ?")
        values.append(importance)
    if status is not None:
        if status not in {"open", "done", "archived"}:
            raise ValueError("unsupported follow-up status")
        updates.append("status = ?")
        values.append(status)
    if not updates:
        return get_follow_up(follow_up_id)
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(follow_up_id)
    conn = _conn()
    cur = conn.execute(
        f"UPDATE follow_ups SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (follow_up_id,)).fetchone()
    conn.close()
    return _follow_up_dict(row) if cur.rowcount and row else None


def get_follow_up(follow_up_id: int) -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (follow_up_id,)).fetchone()
    conn.close()
    return _follow_up_dict(row) if row else None


def _backfill_due_dates(now: datetime) -> None:
    """为旧版本已经保存、但尚未解析时间的事项补齐 due_at。"""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, title FROM follow_ups WHERE status = 'open' AND due_at IS NULL"
    ).fetchall()
    changed = False
    for row in rows:
        due_at = _due_from_text(row["title"], now)
        if not due_at:
            continue
        conn.execute(
            "UPDATE follow_ups SET due_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (_timestamp(due_at), row["id"]),
        )
        changed = True
    if changed:
        conn.commit()
    conn.close()


def _last_user_message_at() -> datetime | None:
    conn = _conn()
    row = conn.execute(
        "SELECT MAX(created_at) AS created_at FROM messages WHERE role = 'user'"
    ).fetchone()
    conn.close()
    return _parse_db_timestamp(row["created_at"]) if row else None


def _is_recently_active(now: datetime, frequency: str) -> bool:
    last_message_at = _last_user_message_at()
    if not last_message_at:
        return False
    return now - last_message_at < timedelta(hours=INACTIVITY_HOURS[frequency])


def _general_events_today(now: datetime) -> int:
    conn = _conn()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM companion_events "
        "WHERE kind IN ('greeting', 'evening_review', 'open_loop') "
        "AND DATE(created_at, '+8 hours') = ?",
        (now.date().isoformat(),),
    ).fetchone()
    conn.close()
    return int(row["count"]) if row else 0


def _create_event(
    *,
    kind: str,
    content: str,
    delivery_key: str,
    importance: int = 1,
    follow_up_id: int | None = None,
) -> dict[str, Any] | None:
    conn = _conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO companion_events "
        "(kind, content, follow_up_id, importance, delivery_key) VALUES (?, ?, ?, ?, ?)",
        (kind, content, follow_up_id, importance, delivery_key),
    )
    if not cur.rowcount:
        conn.close()
        return None
    row = conn.execute(
        "SELECT * FROM companion_events WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    if follow_up_id is not None:
        conn.execute(
            "UPDATE follow_ups SET last_cared_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (follow_up_id,),
        )
    conn.commit()
    conn.close()
    return _event_dict(row) if row else None


def _due_event_for(follow_up: dict[str, Any], now: datetime) -> tuple[str, str, str] | None:
    due_at = _parse_timestamp(follow_up["due_at"])
    if not due_at:
        return None
    delta = (due_at - now).total_seconds()
    # 轮询每 15 秒一次；每个阶段留出 30 秒容差，避免恰好错过边界。
    # 只在最后 5 分钟内开始提醒，避免用户提前数小时被打扰。
    countdown_stage: tuple[int, str] | None = None
    if 210 < delta <= 330:
        countdown_stage = (5, "还有5分钟")
    elif 90 < delta <= 210:
        countdown_stage = (3, "还有3分钟")
    elif 0 < delta <= 90:
        countdown_stage = (1, "还有1分钟")
    if countdown_stage:
        minutes, label = countdown_stage
        return (
            f"due_{minutes}m",
            f"{label}就是「{follow_up['title']}」的提醒时间。要不要现在先动起来？",
            f"due_{minutes}m:{follow_up['id']}:{due_at.strftime('%Y%m%d%H%M')}",
        )
    # 轮询可能在目标时间后几秒才到达，给“到点”事件留出 10 分钟窗口。
    if -10 * 60 <= delta <= 0:
        return (
            "due_now",
            f"现在是「{follow_up['title']}」的提醒时间。要不要我陪你一起开始？",
            f"due_now:{follow_up['id']}:{due_at.strftime('%Y%m%d%H%M')}",
        )
    if delta < 0 and now - due_at <= timedelta(days=7):
        return (
            "overdue",
            f"「{follow_up['title']}」的时间已经过去了。现在还好吗？要不要一起收个尾或复盘一下？",
            f"overdue:{follow_up['id']}:{now.date().isoformat()}",
        )
    return None


def evaluate_time_engine(now: datetime | None = None) -> list[dict[str, Any]]:
    """评估当前时间和待跟进事项，生成本次应露出的关心点。"""
    local_now = _local_now(now)
    _backfill_due_dates(local_now)
    settings = get_companion_settings()
    if not settings["enabled"]:
        return []
    frequency = settings["frequency"]
    recently_active = _is_recently_active(local_now, frequency)
    created: list[dict[str, Any]] = []

    # 重要截止提醒不受安静模式限制，避免错过真正紧急的事。
    for follow_up in list_follow_ups(limit=50, status="open"):
        due_event = _due_event_for(follow_up, local_now)
        if not due_event:
            continue
        kind, content, key = due_event
        if frequency == "quiet" and follow_up["importance"] < 3:
            continue
        event = _create_event(
            kind=kind,
            content=content,
            delivery_key=key,
            importance=follow_up["importance"],
            follow_up_id=follow_up["id"],
        )
        if event:
            created.append(event)

    general_remaining = GENERAL_DAILY_LIMITS[frequency] - _general_events_today(local_now)
    if frequency == "quiet" or recently_active or general_remaining <= 0:
        return created

    date_key = local_now.date().isoformat()
    if 8 <= local_now.hour < 12 and general_remaining > 0:
        event = _create_event(
            kind="greeting",
            content="早呀。今天有什么想先处理的？不用一口气说完，我陪你理一理。",
            delivery_key=f"greeting:{date_key}",
        )
        if event:
            created.append(event)
            general_remaining -= 1

    if 20 <= local_now.hour < 24 and general_remaining > 0:
        event = _create_event(
            kind="evening_review",
            content="今天差不多到收尾的时候了。有没有一件事，你想留给明天的自己继续做？",
            delivery_key=f"evening_review:{date_key}",
        )
        if event:
            created.append(event)
            general_remaining -= 1

    if general_remaining <= 0:
        return created

    for follow_up in list_follow_ups(limit=20, status="open"):
        if follow_up["due_at"] or follow_up["last_cared_at"]:
            continue
        created_at = _parse_db_timestamp(follow_up["created_at"])
        if created_at and local_now - created_at < timedelta(hours=12):
            continue
        event = _create_event(
            kind="open_loop",
            content=f"前两天你提过「{follow_up['title']}」。这件事现在还需要我陪你惦记着吗？",
            delivery_key=f"open_loop:{follow_up['id']}:{date_key}",
            importance=follow_up["importance"],
            follow_up_id=follow_up["id"],
        )
        if event:
            created.append(event)
            break
    return created


def list_recent_care_points(limit: int = 10) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM companion_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_event_dict(row) for row in rows]


def get_companion_overview(
    now: datetime | None = None,
    *,
    evaluate: bool = False,
) -> dict[str, Any]:
    """Return companion data without creating reminders unless explicitly triggered."""
    created = evaluate_time_engine(now=now) if evaluate else []
    return {
        "settings": get_companion_settings(),
        "follow_ups": list_follow_ups(limit=20, status="open"),
        "care_points": list_recent_care_points(limit=10),
        "new_care_points": created,
    }


def _follow_up_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "due_at": row["due_at"],
        "importance": row["importance"],
        "status": row["status"],
        "source_message_id": row["source_message_id"],
        "last_cared_at": row["last_cared_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "content": row["content"],
        "follow_up_id": row["follow_up_id"],
        "importance": row["importance"],
        "created_at": row["created_at"],
        "read_at": row["read_at"],
    }
