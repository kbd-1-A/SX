"""自我记忆：时叙对「我们之间」的动态认知。

V1 只记高置信项：关系里程碑 + 昵称。用户事实不自动抽取（防幻觉）。
里程碑由面具选择器的场景判定驱动——某场景第一次出现即记，规则驱动、零额外 LLM。
"""

import json
import re
import sqlite3
from datetime import date

from app.config import DB_PATH

_NICK_PATTERNS = [
    re.compile(r"(?:以后|你|你可以|不如)?(?:叫我|喊我)([一-龥A-Za-z0-9]{1,8})"),
]
_NICK_SUFFIXES = ("就好", "就行", "就好了", "吧", "哦", "了", "好了")

_MASK_LABELS = {
    "love_guide": "感情",
    "old_bestie": "吐槽",
    "work_advisor": "工作",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _empty() -> dict:
    return {
        "milestones": [],
        "nicknames": [],
        "relationship_phase": "初识",
        "last_conversation_ending": "",
    }


def _load() -> dict:
    conn = _conn()
    row = conn.execute("SELECT self_memory FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    data = _empty()
    if row and row["self_memory"]:
        try:
            data.update(json.loads(row["self_memory"]))
        except (json.JSONDecodeError, TypeError):
            pass
    return data


def _save(data: dict) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE user_profile SET self_memory = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (json.dumps(data, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()


def get_self_memory() -> dict:
    return _load()


def extract_nickname(text: str) -> str | None:
    """从用户消息里提取高置信昵称（「叫我X」「喊我X」…），无则 None。"""
    for pat in _NICK_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        name = m.group(1)
        for suf in _NICK_SUFFIXES:
            if name.endswith(suf):
                name = name[: -len(suf)]
                break
        name = name.strip("，。！？,.!? ")
        if name:
            return name
    return None


def add_nickname(name: str) -> bool:
    """记录昵称（去重），返回是否新增。"""
    data = _load()
    if name in data["nicknames"]:
        return False
    data["nicknames"].append(name)
    _save(data)
    return True


def add_mask_milestone(mask: str) -> bool:
    """面具场景首次出现时记里程碑；已记过返回 False。"""
    label = _MASK_LABELS.get(mask)
    if not label:
        return False
    data = _load()
    if any(ms.get("mask") == mask for ms in data["milestones"]):
        return False
    data["milestones"].append(
        {
            "date": date.today().isoformat(),
            "event": f"第一次聊{label}问题",
            "mask": mask,
        }
    )
    _save(data)
    return True


def format_self_memory() -> str:
    """把自我记忆格式化成可注入 system prompt 的文本。"""
    data = _load()
    lines = [f"- 关系阶段：{data['relationship_phase']}"]
    for ms in data["milestones"]:
        lines.append(f"- {ms['date']}：{ms['event']}")
    if data["nicknames"]:
        lines.append("- 用户让我叫 ta：" + "、".join(data["nicknames"]))
    if not data["milestones"] and not data["nicknames"]:
        lines.append("- 还在认识阶段：我们之间还没有值得记住的节点。")
    return "\n".join(lines)
