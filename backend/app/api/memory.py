"""REST：历史消息、画像。"""

from fastapi import APIRouter

from app.memory.profile import bump_intimacy, get_profile
from app.memory.store import get_messages, get_or_create_session

router = APIRouter(prefix="/api")


@router.get("/messages")
def api_messages(limit: int = 50):
    session_id = get_or_create_session()
    return get_messages(session_id, limit=limit)


@router.get("/profile")
def api_profile():
    return get_profile()


@router.post("/profile/intimacy")
def api_bump_intimacy():
    return bump_intimacy()
