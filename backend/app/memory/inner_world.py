"""时叙持续情绪状态（进记忆）。

当前情绪存于 user_profile.emotion_state（JSON 单行），事件历史 append 到 emotion_log。
每轮对话衰减一次；情绪变化时记录并更新状态。提供注入 persona 的格式化接口。

设计原则（仿 anchors.py）：
- 情绪有记忆、会衰减——"会记仇/记喜"
- 历史可追溯（emotion_log append-only）
- 当前状态单行（user_profile.emotion_state），不每轮重算
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.config import DB_PATH

PERSONA_DIR = Path(__file__).resolve().parents[2] / "persona"
EMOTION_MAP_PATH = PERSONA_DIR / "emotion_map.yaml"

_map_cache: dict | None = None


def load_emotion_map() -> dict:
    global _map_cache
    if _map_cache is None:
        with open(EMOTION_MAP_PATH, encoding="utf-8") as f:
            _map_cache = yaml.safe_load(f)
    return _map_cache


def _emotion_info(emotion: str) -> dict:
    m = load_emotion_map()
    emotions = m["emotions"]
    if emotion in emotions:
        return emotions[emotion]
    return emotions[m.get("default", "平静")]


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class InnerState:
    emotion: str = "平静"
    intensity: float = 0.0
    cause: str = ""
    since: str = ""  # 情绪起因的 ISO 时间
    updated_at: str = ""
    streak: int = 0  # 同一情绪连续轮数


def get_current() -> InnerState:
    conn = _conn()
    row = conn.execute(
        "SELECT emotion_state FROM user_profile WHERE id = 1"
    ).fetchone()
    conn.close()
    raw = row["emotion_state"] if row and row["emotion_state"] else "{}"
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        d = {}
    return InnerState(
        emotion=d.get("emotion", "平静"),
        intensity=float(d.get("intensity", 0.0)),
        cause=d.get("cause", ""),
        since=d.get("since", ""),
        updated_at=d.get("updated_at", ""),
        streak=int(d.get("streak", 0)),
    )


def _save(state: InnerState) -> None:
    state.updated_at = _now_iso()
    conn = _conn()
    conn.execute(
        "UPDATE user_profile SET emotion_state = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = 1",
        (json.dumps(asdict(state), ensure_ascii=False),),
    )
    conn.commit()
    conn.close()


def record_emotion(
    emotion: str,
    intensity: float,
    cause: str = "",
    source_message_id: int | None = None,
) -> InnerState:
    """记录一次情绪变化：更新当前状态 + 追加历史日志。streak 追踪同一情绪连续轮数。"""
    intensity = max(0.0, min(1.0, float(intensity)))
    prev = get_current()
    if emotion == prev.emotion and emotion != "平静":
        streak = prev.streak + 1
    else:
        streak = 1 if emotion != "平静" else 0
    state = InnerState(
        emotion=emotion, intensity=intensity, cause=cause,
        since=_now_iso(), streak=streak,
    )
    _save(state)
    conn = _conn()
    conn.execute(
        "INSERT INTO emotion_log (emotion, intensity, cause, source_message_id) "
        "VALUES (?, ?, ?, ?)",
        (emotion, intensity, cause, source_message_id),
    )
    conn.commit()
    conn.close()
    return state


def decay_current() -> InnerState:
    """每轮对话调用一次：强度按情绪衰减系数衰减；低于阈值归零到平静。"""
    state = get_current()
    if state.intensity <= 0 or state.emotion == "平静":
        return state
    info = _emotion_info(state.emotion)
    decay = float(info.get("decay", 0.7))
    state.intensity = round(state.intensity * decay, 3)
    if state.intensity < 0.05:
        state.emotion = "平静"
        state.intensity = 0.0
        state.cause = ""
    _save(state)
    return state


def _describe_ago(iso: str) -> str:
    if not iso:
        return ""
    try:
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    delta = datetime.now(timezone.utc) - t
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "刚刚"
    if mins < 60:
        return f"{mins}分钟前"
    hours = mins // 60
    if hours < 24:
        return f"{hours}小时前"
    return f"{hours // 24}天前"


def _transition_suggestion(emotion: str, streak: int) -> str:
    """连续多轮同一情绪时，建议自然转向。"""
    if streak < 3:
        return ""
    transitions = {
        "温柔": "你已经连续温柔了好几轮，可以稍微带一点点嗔怪或无奈，不要一直太软",
        "宠溺": "你已经宠了好几轮了，可以稍微收一收，变得无奈或俏皮",
        "心疼": "你已经心疼好几轮了，可以转为释然或温柔，不要一直太沉重",
        "欣喜": "你已经开心好几轮了，情绪该平复一些，转向平静或好奇",
        "得意": "你已经得意好几轮了，收敛一点，别太飘",
        "嗔怪": "你已经嗔怪好几轮了，可以转为释然或温柔，不要一直矫情",
        "委屈": "你已经委屈好几轮了，可以转为失落或释然",
        "无奈": "你已经无奈好几轮了，可以转为冷漠或释然",
        "生气": "你已经生气好几轮了，该慢慢软下来，转向释然或冷漠",
        "冷漠": "你已经冷漠好几轮了，可以慢慢回暖到平静",
    }
    return transitions.get(emotion, "")


def format_for_persona() -> str:
    """注入 system prompt 的当前情绪状态描述，含 few-shot 示例和情绪转移建议。"""
    state = get_current()
    if state.intensity <= 0 or state.emotion == "平静":
        return "- 当前情绪：平静。自然回复，不刻意带情绪。"

    info = _emotion_info(state.emotion)
    hint = info.get("system_hint", "")
    ago = _describe_ago(state.since)
    cause_part = f"，{ago}起因：{state.cause}" if state.cause else ""
    streak_part = f"，已连续{state.streak}轮" if state.streak >= 2 else ""

    lines = [
        f"- 当前情绪：{state.emotion}（强度{state.intensity:.1f}{cause_part}{streak_part}）。{hint}",
    ]

    transition = _transition_suggestion(state.emotion, state.streak)
    if transition:
        lines.append(f"- 情绪转移提示：{transition}")

    lines.append(f"- 用词示范：回复里自然带一两个情绪语气词（如「哼」「嗯～」「哎」「哇」），但不要每句都加")
    return "\n".join(lines)


def get_quick_react(emotion: str) -> list[str]:
    return list(_emotion_info(emotion).get("quick_react", ["嗯"]))


def get_subtitle_color(emotion: str) -> str:
    return _emotion_info(emotion).get("subtitle_color", "#ffffff")


def get_instruct(emotion: str) -> str:
    return _emotion_info(emotion).get("cosyvoice_instruct", "用自然语气说")


def list_emotion_history(limit: int = 20) -> list[dict]:
    """情绪事件时间线（供调试/管理页查看）。"""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, emotion, intensity, cause, source_message_id, created_at "
        "FROM emotion_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
