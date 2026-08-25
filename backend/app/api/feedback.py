"""反馈 REST：对时叙回复的赞/踩 sidecar（自主学习）。"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.memory.feedback import (
    FeedbackValidationError,
    FeedbackVersionConflict,
    clear_feedback,
    feedback_stats,
    get_feedback,
    list_feedback,
    set_feedback,
)

router = APIRouter(prefix="/api")


class FeedbackPayload(BaseModel):
    rating: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    if_version: int | None = None


@router.put("/messages/{message_id}/feedback")
def api_set_feedback(message_id: int, payload: FeedbackPayload):
    try:
        return set_feedback(
            message_id,
            payload.rating,
            note=payload.note,
            if_version=payload.if_version,
        )
    except FeedbackVersionConflict as exc:
        # 乐观并发冲突：返回权威当前值，客户端据此重试或回显。
        return JSONResponse(status_code=409, content=exc.current)
    except FeedbackValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/messages/{message_id}/feedback")
def api_get_feedback(message_id: int):
    feedback = get_feedback(message_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="feedback not found")
    return feedback


@router.delete("/messages/{message_id}/feedback")
def api_delete_feedback(message_id: int):
    if not clear_feedback(message_id):
        raise HTTPException(status_code=404, detail="feedback not found")
    return {"message_id": message_id, "deleted": True}


@router.get("/feedback")
def api_list_feedback(limit: int = 200):
    return list_feedback(limit=limit)


@router.get("/feedback/stats")
def api_feedback_stats(days: int = 30):
    return feedback_stats(days=max(1, min(days, 365)))
