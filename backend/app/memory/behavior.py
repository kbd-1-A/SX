"""用户长期行为画像。

只记录可追溯的重复行为或明确表达的沟通要求：
- 单次闲聊不会被升级成「性格标签」；
- 推断信号至少累计 3 次才生效；
- 用户明确改变表达偏好时，旧偏好立即降级；
- 超过一段时间未出现的画像会过期，不再注入提示词。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import DB_PATH

PROFILE_EXPIRY_DAYS = 90
INFERRED_ACTIVATION_COUNT = 3
MAX_EVIDENCE_ITEMS = 5

TRAIT_DEFINITIONS = {
    "stable": {
        "label": "稳定",
        "patterns": (
            re.compile(r"慢慢来|不急|稳住|一步一步|先做好眼前"),
        ),
    },
    "cautious": {
        "label": "谨慎",
        "patterns": (
            re.compile(r"风险|确认一下|稳妥|保守一点|谨慎|保险起见|先验证"),
        ),
    },
    "direct": {
        "label": "直接",
        "patterns": (
            re.compile(r"直接说|别绕弯|说重点|先说结论|直说"),
        ),
    },
    "humorous": {
        "label": "幽默",
        "patterns": (
            re.compile(r"哈哈|h{2,}|笑死|😂|🤣|玩梗|整活"),
        ),
    },
    "anxious": {
        "label": "焦虑倾向",
        "patterns": (
            re.compile(r"焦虑|紧张|害怕|担心|压力好大|崩溃|睡不着|不安"),
        ),
    },
}

STYLE_DEFINITIONS = {
    "short_reply": {
        "label": "偏好简短回复",
        "patterns": (
            re.compile(r"短一点|简短一点|别写太长|别小作文|少说点"),
        ),
    },
    "less_cliche": {
        "label": "偏好少套话",
        "patterns": (
            re.compile(r"少套话|别套话|别客套|不要客套"),
        ),
    },
    "direct_reply": {
        "label": "偏好直接表达",
        "patterns": (
            re.compile(r"直接一点|直说|别绕弯|说重点|先说结论"),
        ),
    },
    "rhetorical_question": {
        "label": "常用反问表达",
        "patterns": (
            re.compile(r"是不是|对不对|对吧|难道|怎么会"),
        ),
    },
    "colloquial": {
        "label": "偏好口语化",
        "patterns": (
            re.compile(r"口语一点|自然一点|像朋友一样说|别太正式|咋样|咱们"),
        ),
    },
    "detailed_reply": {
        "label": "偏好详细回复",
        "patterns": (
            re.compile(r"详细一点|展开说|多说一点|写详细些"),
        ),
    },
    "gentle_reply": {
        "label": "偏好委婉表达",
        "patterns": (
            re.compile(r"委婉一点|温柔一点|别那么直接"),
        ),
    },
    "formal_reply": {
        "label": "偏好正式表达",
        "patterns": (
            re.compile(r"正式一点|专业一点|严谨一点"),
        ),
    },
}

STYLE_CONFLICTS = {
    "short_reply": ("detailed_reply",),
    "detailed_reply": ("short_reply",),
    "direct_reply": ("gentle_reply",),
    "gentle_reply": ("direct_reply",),
    "colloquial": ("formal_reply",),
    "formal_reply": ("colloquial",),
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_text() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _empty_profile() -> dict[str, Any]:
    return {"version": 1, "traits": {}, "styles": {}}


def _load() -> dict[str, Any]:
    conn = _conn()
    row = conn.execute(
        "SELECT behavior_profile FROM user_profile WHERE id = 1"
    ).fetchone()
    conn.close()
    data = _empty_profile()
    if row and row["behavior_profile"]:
        try:
            saved = json.loads(row["behavior_profile"])
        except (json.JSONDecodeError, TypeError):
            saved = {}
        if isinstance(saved, dict):
            data.update(
                {
                    "version": saved.get("version", 1),
                    "traits": saved.get("traits")
                    if isinstance(saved.get("traits"), dict)
                    else {},
                    "styles": saved.get("styles")
                    if isinstance(saved.get("styles"), dict)
                    else {},
                }
            )
    return data


def _save(data: dict[str, Any]) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE user_profile SET behavior_profile = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = 1",
        (json.dumps(data, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()


def _definition(kind: str, key: str) -> dict[str, Any]:
    definitions = TRAIT_DEFINITIONS if kind == "traits" else STYLE_DEFINITIONS
    return definitions[key]


def _new_entry(kind: str, key: str) -> dict[str, Any]:
    definition = _definition(kind, key)
    return {
        "label": definition["label"],
        "observations": 0,
        "oppositions": 0,
        "explicit": False,
        "superseded": False,
        "confidence": 0.0,
        "status": "candidate",
        "last_seen_at": None,
        "expires_at": None,
        "evidence": [],
    }


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _is_explicit_style_signal(text: str, key: str) -> bool:
    """是否为用户对时叙输出方式的直接要求，而非普通口头表达。"""
    if key not in STYLE_DEFINITIONS:
        return False
    return any(pattern.search(text) for pattern in STYLE_DEFINITIONS[key]["patterns"])


def _signals_for(text: str) -> list[tuple[str, str, bool]]:
    """每个特征每条消息至多贡献一次，防止一段重复文本刷高置信度。"""
    signals: list[tuple[str, str, bool]] = []
    for kind, definitions in (
        ("traits", TRAIT_DEFINITIONS),
        ("styles", STYLE_DEFINITIONS),
    ):
        for key, definition in definitions.items():
            if any(pattern.search(text) for pattern in definition["patterns"]):
                signals.append((kind, key, _is_explicit_style_signal(text, key)))
    return signals


def _excerpt(text: str) -> str:
    return text.strip().replace("\n", " ")[:80]


def _refresh_entry(entry: dict[str, Any], now: datetime) -> bool:
    """根据证据、冲突和时间重新计算状态；返回是否发生变化。"""
    before = (
        entry.get("status"),
        entry.get("confidence"),
        entry.get("expires_at"),
    )
    observations = int(entry.get("observations", 0))
    oppositions = int(entry.get("oppositions", 0))
    net_score = observations - oppositions
    explicit = bool(entry.get("explicit"))
    superseded = bool(entry.get("superseded"))
    last_seen = _parse_time(entry.get("last_seen_at"))
    expired = (
        last_seen is not None
        and now - last_seen > timedelta(days=PROFILE_EXPIRY_DAYS)
    )
    if superseded:
        entry["status"] = "stale"
        entry["confidence"] = 0.0
        entry["expires_at"] = None
    elif expired:
        entry["status"] = "stale"
        entry["confidence"] = 0.0
        entry["expires_at"] = (
            last_seen + timedelta(days=PROFILE_EXPIRY_DAYS)
        ).strftime("%Y-%m-%d %H:%M:%S")
    else:
        entry["expires_at"] = (
            last_seen + timedelta(days=PROFILE_EXPIRY_DAYS)
        ).strftime("%Y-%m-%d %H:%M:%S") if last_seen else None
        if explicit and net_score > 0:
            entry["status"] = "active"
            entry["confidence"] = 0.95
        elif (
            observations >= INFERRED_ACTIVATION_COUNT
            and net_score >= INFERRED_ACTIVATION_COUNT
        ):
            entry["status"] = "active"
            entry["confidence"] = round(
                min(0.9, 0.55 + observations * 0.1 + net_score * 0.03), 2
            )
        elif oppositions > 0 and entry.get("status") == "active":
            entry["status"] = "stale"
            entry["confidence"] = 0.0
        else:
            entry["status"] = "candidate"
            entry["confidence"] = round(
                max(0.0, min(0.69, 0.25 + observations * 0.1 - oppositions * 0.12)),
                2,
            )
    after = (
        entry.get("status"),
        entry.get("confidence"),
        entry.get("expires_at"),
    )
    return before != after


def _record_signal(
    data: dict[str, Any],
    *,
    kind: str,
    key: str,
    text: str,
    source_message_id: int | None,
    explicit: bool,
    now: datetime,
) -> None:
    bucket = data[kind]
    entry = bucket.setdefault(key, _new_entry(kind, key))
    entry["label"] = _definition(kind, key)["label"]
    entry["observations"] = int(entry.get("observations", 0)) + 1
    entry["explicit"] = bool(entry.get("explicit")) or explicit
    entry["superseded"] = False
    entry["last_seen_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    evidence = entry.setdefault("evidence", [])
    if not any(item.get("message_id") == source_message_id for item in evidence):
        evidence.append(
            {
                "message_id": source_message_id,
                "excerpt": _excerpt(text),
                "observed_at": entry["last_seen_at"],
            }
        )
    entry["evidence"] = evidence[-MAX_EVIDENCE_ITEMS:]
    _refresh_entry(entry, now)


def _record_conflict(
    data: dict[str, Any],
    *,
    key: str,
    now: datetime,
) -> None:
    entry = data["styles"].get(key)
    if not entry:
        return
    # 明确表达新偏好时，旧偏好应立即退出提示词，而不是等三次反例。
    entry["oppositions"] = max(
        int(entry.get("oppositions", 0)) + INFERRED_ACTIVATION_COUNT,
        int(entry.get("observations", 0)),
    )
    entry["explicit"] = False
    entry["superseded"] = True
    entry["last_seen_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    entry["status"] = "stale"
    entry["confidence"] = 0.0
    _refresh_entry(entry, now)


def _expire(data: dict[str, Any], now: datetime) -> bool:
    changed = False
    for kind in ("traits", "styles"):
        for entry in data[kind].values():
            changed = _refresh_entry(entry, now) or changed
    return changed


def observe_behavior(text: str, source_message_id: int | None) -> dict[str, Any]:
    """记录一条用户消息中的画像信号，并返回最新画像。

    推断信号需重复出现才会变 active；明确的回复要求立即可用。
    """
    data = _load()
    now = _now()
    changed = _expire(data, now)
    for kind, key, explicit in _signals_for(text):
        _record_signal(
            data,
            kind=kind,
            key=key,
            text=text,
            source_message_id=source_message_id,
            explicit=explicit,
            now=now,
        )
        changed = True
        if kind == "styles" and explicit:
            for conflicting_key in STYLE_CONFLICTS.get(key, ()):
                _record_conflict(data, key=conflicting_key, now=now)
    if changed:
        _save(data)
    return data


def get_behavior_profile() -> dict[str, Any]:
    """读取画像并在读取时让过期项失效。"""
    data = _load()
    if _expire(data, _now()):
        _save(data)
    return data


def format_behavior_profile() -> str:
    """返回只含高置信、未过期结论的提示词片段。"""
    data = get_behavior_profile()
    traits = [
        entry["label"]
        for entry in data["traits"].values()
        if entry.get("status") == "active"
    ]
    styles = [
        entry["label"]
        for entry in data["styles"].values()
        if entry.get("status") == "active"
    ]
    lines = [
        "# 用户长期画像（高置信）",
        "- 仅用于调整回应；不要直接给用户贴性格标签。",
        "- 当前请求优先于历史画像；语境变化时不要机械套用。",
    ]
    if traits:
        lines.append("- 性格/状态倾向：" + "、".join(traits))
    if styles:
        lines.append("- 交流偏好：" + "、".join(styles))
    if not traits and not styles:
        lines.append("- 暂无足够重复行为形成稳定画像。")
    return "\n".join(lines)
