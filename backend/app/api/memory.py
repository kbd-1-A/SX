"""REST：历史消息、画像。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory.anchors import (
    confirm_anchor,
    delete_anchor,
    list_anchors,
    update_anchor,
)
from app.memory.companion import (
    create_follow_up,
    extract_follow_up_candidates,
    get_companion_overview,
    set_companion_settings,
    update_follow_up,
)
from app.memory.profile import bump_intimacy, get_profile
from app.memory.self import get_self_memory, remove_nickname
from app.memory.store import (
    create_session,
    get_messages,
    get_or_create_session,
    get_session_summary,
    list_sessions,
)

router = APIRouter(prefix="/api")


class AnchorUpdatePayload(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = None
    tags: list[str] | None = None
    expires_at: str | None = None
    clear_expiry: bool = False


class CompanionSettingsPayload(BaseModel):
    frequency: str | None = None
    enabled: bool | None = None


class FollowUpCreatePayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: str = Field(default="other", max_length=30)
    due_at: str | None = None
    importance: int = Field(default=1, ge=1, le=3)


class FollowUpUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    due_at: str | None = None
    clear_due_at: bool = False
    importance: int | None = Field(default=None, ge=1, le=3)
    status: str | None = None


@router.get("/messages")
def api_messages(limit: int = 50, session_id: int | None = None):
    sid = get_or_create_session(session_id)
    return get_messages(sid, limit=limit)


@router.get("/sessions")
def api_sessions(limit: int = 30):
    sessions = list_sessions(limit=limit)
    if sessions:
        return sessions
    sid = create_session()
    summary = get_session_summary(sid)
    return [summary] if summary else []


@router.post("/sessions")
def api_create_session():
    sid = create_session()
    return get_session_summary(sid)


@router.get("/profile")
def api_profile():
    return get_profile()


@router.get("/companion/overview")
def api_companion_overview():
    return get_companion_overview()


@router.post("/companion/check-in")
def api_companion_check_in():
    """Evaluate reminders only after an explicit user interaction."""
    return get_companion_overview(evaluate=True)


@router.patch("/companion/settings")
def api_companion_settings(payload: CompanionSettingsPayload):
    try:
        return set_companion_settings(
            frequency=payload.frequency,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/companion/follow-ups")
def api_create_follow_up(payload: FollowUpCreatePayload):
    fields = payload.model_fields_set
    inferred = extract_follow_up_candidates(payload.title)
    candidate = inferred[0] if inferred else None
    category = payload.category
    due_at = payload.due_at
    importance = payload.importance
    if candidate:
        if "category" not in fields:
            category = candidate["category"]
        if "due_at" not in fields:
            due_at = candidate["due_at"]
        if "importance" not in fields:
            importance = candidate["importance"]
    try:
        follow_up = create_follow_up(
            title=payload.title,
            category=category,
            due_at=due_at,
            importance=importance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not follow_up:
        raise HTTPException(status_code=500, detail="follow-up could not be created")
    return follow_up


@router.patch("/companion/follow-ups/{follow_up_id}")
def api_update_follow_up(follow_up_id: int, payload: FollowUpUpdatePayload):
    fields = payload.model_fields_set
    try:
        follow_up = update_follow_up(
            follow_up_id,
            title=payload.title if "title" in fields else None,
            due_at=None if payload.clear_due_at else payload.due_at if "due_at" in fields else ...,
            importance=payload.importance if "importance" in fields else None,
            status=payload.status if "status" in fields else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not follow_up:
        raise HTTPException(status_code=404, detail="follow-up not found")
    return follow_up


@router.get("/memory/anchors")
def api_memory_anchors(limit: int = 20, status: str = "active"):
    try:
        return list_anchors(limit=max(1, min(limit, 100)), status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/memory/self")
def api_self_memory():
    """读取历史的称呼/关系记忆，供记忆管理页统一展示。"""
    return get_self_memory()


@router.delete("/memory/self/nicknames/{nickname}")
def api_delete_nickname_memory(nickname: str):
    if not remove_nickname(nickname):
        raise HTTPException(status_code=404, detail="nickname memory not found")
    return {"nickname": nickname, "deleted": True}


@router.post("/memory/anchors/{anchor_id}/confirm")
def api_confirm_memory_anchor(anchor_id: int):
    anchor = confirm_anchor(anchor_id)
    if not anchor:
        raise HTTPException(status_code=404, detail="memory anchor not found or cannot confirm")
    return anchor


@router.patch("/memory/anchors/{anchor_id}")
def api_update_memory_anchor(anchor_id: int, payload: AnchorUpdatePayload):
    fields = payload.model_fields_set
    try:
        anchor = update_anchor(
            anchor_id,
            content=payload.content if "content" in fields else None,
            kind=payload.kind if "kind" in fields else None,
            tags=payload.tags if "tags" in fields else None,
            expires_at=(
                None
                if payload.clear_expiry
                else payload.expires_at
                if "expires_at" in fields
                else ...
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not anchor:
        raise HTTPException(status_code=404, detail="memory anchor not found")
    return anchor


@router.delete("/memory/anchors/{anchor_id}")
def api_delete_memory_anchor(anchor_id: int):
    if not delete_anchor(anchor_id):
        raise HTTPException(status_code=404, detail="memory anchor not found")
    return {"id": anchor_id, "deleted": True}


@router.post("/profile/intimacy")
def api_bump_intimacy():
    return bump_intimacy()
