"""结构化关系锚点记忆。

V2 不急着上向量库，先记录高置信、可追溯的用户事实/偏好/未完事项。
所有长期记忆都必须能追到 source_message_id，避免时叙编造“我记得”。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import DB_PATH

ALLOWED_KINDS = {
    "user_fact",
    "preference",
    "episode",
    "open_loop",
    "relationship_note",
}
ALLOWED_STATUSES = {"pending", "active", "stale", "archived"}
DEFAULT_EXPIRY_DAYS: dict[str, int] = {
    "open_loop": 14,
    "episode": 30,
}


@dataclass(frozen=True)
class AnchorCandidate:
    kind: str
    content: str
    confidence: float = 0.9
    tags: tuple[str, ...] = ()
    requires_confirmation: bool = True
    expires_in_days: int | None = None


_EXPLICIT_MEMORY_PATTERNS = (
    re.compile(
        r"(?:你(?:要|得)?记住|记住|帮我记住|记一下|记着)"
        r"[:：,， ]*(?P<content>.{2,80})"
    ),
    re.compile(
        r"(?P<content>[^，,。！？!?]{2,80}?)"
        r"[，,。！？!? ]+(?:你(?:要|得)?记住|帮我记住|记住|记一下|记着)"
        r"(?:[。！？!?]|$)"
    ),
)
_NAME_PATTERNS = (
    re.compile(
        r"(?:我叫|我的名字是|请(?:你)?叫我|你可以叫我|叫我|喊我|称呼我)"
        r"[:： ]*(?P<name>[一-龥A-Za-z0-9_-]{1,24}?)(?=[，,。！？!? ]|$)"
    ),
)
_PREFERENCE_PATTERNS = (
    re.compile(r"(?:我不喜欢|别|不要)(.{2,40})"),
    re.compile(r"(?:我喜欢|我更喜欢|以后你可以|以后你就)(.{2,40})"),
)
_OPEN_LOOP_PATTERNS = (
    re.compile(r"(?:下次|回头|明天|之后|等会儿|等会)(?:再|继续)?(.{2,60})"),
)

_TAG_HINTS: dict[str, tuple[str, ...]] = {
    "工作": ("项目", "代码", "需求", "排期", "上线", "测试", "后端", "前端", "接口"),
    "表达偏好": ("小作文", "直接", "短一点", "别啰嗦", "口语", "自然"),
    "关系": ("时叙", "陪伴", "记住", "昵称", "叫我"),
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _clean(text: str) -> str:
    return text.strip(" ，。！？,.!?;；")


def _extract_name(text: str) -> str | None:
    """提取用户明确给出的姓名/称呼，避免把普通陈述误写成名字。"""
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = _clean(match.group("name"))
        for suffix in ("就好了", "就好", "就行", "好了", "吧", "哦", "了"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if name:
            return name
    return None


def _tags_for(text: str, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    tags = set(extra)
    for tag, hints in _TAG_HINTS.items():
        if any(h in text for h in hints):
            tags.add(tag)
    return tuple(sorted(tags))


def extract_anchor_candidates(text: str) -> list[AnchorCandidate]:
    """从用户原话中抽取高置信记忆候选。

    原则：宁可少记，不猜。明确要求记住、姓名/称呼、偏好、下次继续才写。
    """
    candidates: list[AnchorCandidate] = []
    name = _extract_name(text)
    if name:
        candidates.append(
            AnchorCandidate(
                kind="user_fact",
                content=f"用户希望被称呼为：{name}",
                confidence=0.98,
                tags=_tags_for(text, ("称呼", "明确身份")),
                requires_confirmation=False,
            )
        )
    for pat in _EXPLICIT_MEMORY_PATTERNS:
        match = pat.search(text)
        if match:
            content = _clean(match.group("content"))
            if content:
                # 「叫我 X，你要记住」已由姓名规则结构化，避免重复写两条。
                if _extract_name(content):
                    continue
                candidates.append(
                    AnchorCandidate(
                        kind="user_fact",
                        content=content,
                        confidence=0.95,
                        tags=_tags_for(content, ("明确要求记住",)),
                        requires_confirmation=False,
                    )
                )
    if candidates:
        return _dedupe_candidates(candidates)
    for pat in _PREFERENCE_PATTERNS:
        match = pat.search(text)
        if match:
            content = _clean(match.group(0))
            if content:
                candidates.append(
                    AnchorCandidate(
                        kind="preference",
                        content=content,
                        confidence=0.9,
                        tags=_tags_for(content, ("表达偏好",)),
                    )
                )
    for pat in _OPEN_LOOP_PATTERNS:
        match = pat.search(text)
        if match:
            content = _clean(match.group(0))
            if content:
                candidates.append(
                    AnchorCandidate(
                        kind="open_loop",
                        content=content,
                        confidence=0.85,
                        tags=_tags_for(content, ("未完事项",)),
                        expires_in_days=DEFAULT_EXPIRY_DAYS["open_loop"],
                    )
                )
    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[AnchorCandidate]) -> list[AnchorCandidate]:
    seen: set[tuple[str, str]] = set()
    out: list[AnchorCandidate] = []
    for candidate in candidates:
        key = (candidate.kind, candidate.content)
        if key in seen:
            continue
        contained_index: int | None = None
        for index, previous in enumerate(out):
            if candidate.kind != previous.kind:
                continue
            if candidate.content in previous.content:
                contained_index = -1
                break
            if previous.content in candidate.content:
                contained_index = index
                break
        if contained_index == -1:
            continue
        if contained_index is not None:
            replaced = out[contained_index]
            seen.discard((replaced.kind, replaced.content))
            out[contained_index] = candidate
            seen.add(key)
            continue
        seen.add(key)
        out.append(candidate)
    return out


def add_anchor(candidate: AnchorCandidate, source_message_id: int | None) -> int | None:
    """新增或刷新一条锚点；推断记忆默认进入待确认。"""
    content = _clean(candidate.content)
    if not content or candidate.kind not in ALLOWED_KINDS:
        return None
    status = "pending" if candidate.requires_confirmation else "active"
    expires_at = _expiry_from_days(candidate.expires_in_days)
    conn = _conn()
    existing = conn.execute(
        "SELECT id, status FROM memory_anchors WHERE kind = ? AND content = ?",
        (candidate.kind, content),
    ).fetchone()
    tags = json.dumps(list(candidate.tags), ensure_ascii=False)
    if existing:
        anchor_id = int(existing["id"])
        next_status = "active" if existing["status"] == "active" else status
        conn.execute(
            "UPDATE memory_anchors SET confidence = MAX(confidence, ?), tags = ?, "
            "source_message_id = ?, status = ?, expires_at = ?, "
            "confirmed_at = CASE WHEN ? = 'active' THEN COALESCE(confirmed_at, CURRENT_TIMESTAMP) "
            "ELSE NULL END, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                candidate.confidence,
                tags,
                source_message_id,
                next_status,
                expires_at,
                next_status,
                anchor_id,
            ),
        )
    else:
        cur = conn.execute(
            "INSERT INTO memory_anchors "
            "(kind, content, source_message_id, confidence, tags, status, expires_at, confirmed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'active' THEN CURRENT_TIMESTAMP ELSE NULL END)",
            (
                candidate.kind,
                content,
                source_message_id,
                candidate.confidence,
                tags,
                status,
                expires_at,
                status,
            ),
        )
        anchor_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return anchor_id


def add_anchors_from_text(text: str, source_message_id: int | None) -> list[int]:
    ids: list[int] = []
    for candidate in extract_anchor_candidates(text):
        anchor_id = add_anchor(candidate, source_message_id)
        if anchor_id is not None:
            ids.append(anchor_id)
    return ids


def list_anchors(limit: int = 20, status: str = "active") -> list[dict]:
    """读取记忆，读取前将到期的 active / pending 记忆转为 stale。"""
    if status != "all" and status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported memory status: {status}")
    expire_due_anchors()
    conn = _conn()
    query = (
        "SELECT id, kind, content, source_message_id, confidence, tags, status, "
        "expires_at, confirmed_at, created_at, updated_at, last_used_at "
        "FROM memory_anchors "
    )
    params: tuple[object, ...]
    if status == "all":
        query += "ORDER BY updated_at DESC, id DESC LIMIT ?"
        params = (limit,)
    else:
        query += "WHERE status = ? ORDER BY updated_at DESC, id DESC LIMIT ?"
        params = (status, limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_anchor(row) for row in rows]


def get_anchor(anchor_id: int) -> dict | None:
    expire_due_anchors()
    conn = _conn()
    row = conn.execute(
        "SELECT id, kind, content, source_message_id, confidence, tags, status, "
        "expires_at, confirmed_at, created_at, updated_at, last_used_at "
        "FROM memory_anchors WHERE id = ?",
        (anchor_id,),
    ).fetchone()
    conn.close()
    return _row_to_anchor(row) if row else None


def confirm_anchor(anchor_id: int) -> dict | None:
    """用户确认后，待确认记忆才会进入模型可召回集合。"""
    conn = _conn()
    row = conn.execute(
        "SELECT kind, status FROM memory_anchors WHERE id = ?",
        (anchor_id,),
    ).fetchone()
    if not row or row["status"] not in {"pending", "stale"}:
        conn.close()
        return None
    renewed_expiry = _expiry_from_days(DEFAULT_EXPIRY_DAYS.get(row["kind"]))
    cur = conn.execute(
        "UPDATE memory_anchors SET status = 'active', confirmed_at = CURRENT_TIMESTAMP, "
        "expires_at = CASE WHEN status = 'stale' THEN ? ELSE expires_at END, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (renewed_expiry, anchor_id),
    )
    conn.commit()
    conn.close()
    return get_anchor(anchor_id) if cur.rowcount else None


def update_anchor(
    anchor_id: int,
    *,
    content: str | None = None,
    kind: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    expires_at: str | None | object = ...,
) -> dict | None:
    """编辑记忆正文、分类、标签或过期时间。"""
    updates: list[str] = []
    values: list[object] = []
    if content is not None:
        cleaned = _clean(content)
        if not cleaned or len(cleaned) > 200:
            raise ValueError("memory content must be between 1 and 200 characters")
        updates.append("content = ?")
        values.append(cleaned)
    if kind is not None:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")
        updates.append("kind = ?")
        values.append(kind)
    if tags is not None:
        normalized_tags = sorted(
            {
                tag.strip()[:40]
                for tag in tags
                if isinstance(tag, str) and tag.strip()
            }
        )
        updates.append("tags = ?")
        values.append(json.dumps(normalized_tags, ensure_ascii=False))
    if expires_at is not ...:
        updates.append("expires_at = ?")
        values.append(_normalize_expiry(expires_at))
    if not updates:
        return get_anchor(anchor_id)

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(anchor_id)
    conn = _conn()
    cur = conn.execute(
        f"UPDATE memory_anchors SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    conn.close()
    return get_anchor(anchor_id) if cur.rowcount else None


def delete_anchor(anchor_id: int) -> bool:
    """永久删除用户指定记忆，避免继续被模型召回。"""
    conn = _conn()
    cur = conn.execute("DELETE FROM memory_anchors WHERE id = ?", (anchor_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def expire_due_anchors() -> int:
    """到期的记忆不删除，但不会再被召回，用户仍可在管理页查看。"""
    conn = _conn()
    cur = conn.execute(
        "UPDATE memory_anchors SET status = 'stale', updated_at = CURRENT_TIMESTAMP "
        "WHERE status IN ('active', 'pending') AND expires_at IS NOT NULL "
        "AND expires_at <= CURRENT_TIMESTAMP"
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def recall_anchors(query: str, limit: int = 6) -> list[dict]:
    """按简单字符/标签重合召回锚点。

    这不是语义检索，只是 V2 的轻量版本：宁可召回少，也不要把无关记忆塞给模型。
    """
    anchors = list_anchors(limit=80)
    scored: list[tuple[int, dict]] = []
    query_chars = {ch for ch in query if "\u4e00" <= ch <= "\u9fff"}
    for anchor in anchors:
        tags = anchor.get("tags") or []
        content = anchor["content"]
        score = 0
        if content and content in query:
            score += 8
        score += sum(3 for tag in tags if tag in query)
        score += len(query_chars & {ch for ch in content if "\u4e00" <= ch <= "\u9fff"})
        if score:
            scored.append((score, anchor))
    if not scored:
        return anchors[: min(limit, 3)]
    scored.sort(key=lambda item: (-item[0], -int(item[1]["id"])))
    recalled = [anchor for _, anchor in scored[:limit]]
    _touch([int(anchor["id"]) for anchor in recalled])
    return recalled


def format_recalled_anchors(query: str, limit: int = 6) -> str:
    anchors = recall_anchors(query, limit=limit)
    if not anchors:
        return "- 暂无可引用的长期记忆。"
    lines = []
    for anchor in anchors:
        lines.append(
            f"- [memory:{anchor['id']}] {anchor['kind']}：{anchor['content']}"
        )
    return "\n".join(lines)


def _touch(ids: list[int]) -> None:
    if not ids:
        return
    conn = _conn()
    conn.executemany(
        "UPDATE memory_anchors SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
        [(anchor_id,) for anchor_id in ids],
    )
    conn.commit()
    conn.close()


def _row_to_anchor(row: sqlite3.Row) -> dict:
    try:
        tags = json.loads(row["tags"] or "[]")
    except json.JSONDecodeError:
        tags = []
    return {
        "id": row["id"],
        "kind": row["kind"],
        "content": row["content"],
        "source_message_id": row["source_message_id"],
        "confidence": row["confidence"],
        "tags": tags,
        "status": row["status"],
        "expires_at": row["expires_at"],
        "confirmed_at": row["confirmed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_used_at": row["last_used_at"],
    }


def _expiry_from_days(days: int | None) -> str | None:
    if days is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _normalize_expiry(value: str | None | object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expires_at must be an ISO-8601 datetime string or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("expires_at must be an ISO-8601 datetime string") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
