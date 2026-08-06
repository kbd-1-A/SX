"""用户画像：V1 只读展示 + 手动加分。自动演化后置。"""

import json

from app.memory.store import _conn


def get_profile() -> dict:
    conn = _conn()
    row = conn.execute(
        "SELECT intimacy, interests, updated_at FROM user_profile WHERE id = 1"
    ).fetchone()
    conn.close()
    if not row:
        return {"intimacy": 0, "interests": {}, "updated_at": None}
    try:
        interests = json.loads(row["interests"] or "{}")
    except json.JSONDecodeError:
        interests = {}
    return {
        "intimacy": row["intimacy"],
        "interests": interests,
        "updated_at": row["updated_at"],
    }


def bump_intimacy() -> dict:
    conn = _conn()
    conn.execute(
        "UPDATE user_profile SET intimacy = intimacy + 1, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = 1"
    )
    conn.commit()
    conn.close()
    return get_profile()
