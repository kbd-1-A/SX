"""观察层 REST：时叙对用户节奏的自主学习数据（P1）。"""

from fastapi import APIRouter

from app.memory.observations import get_rhythm_profile

router = APIRouter(prefix="/api")


@router.get("/observations/rhythm")
def api_observations_rhythm(days: int = 30):
    return get_rhythm_profile(days=max(1, min(days, 90)))
