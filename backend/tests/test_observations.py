"""P1 观察层测试：观察记录 + 节奏画像聚合。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import observations as obs_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(obs_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_record_turn_and_rhythm_profile(tmp_db):
    from datetime import datetime, timedelta, timezone

    from app.memory.observations import get_rhythm_profile, record_turn

    tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
    record_turn(
        session_id=1,
        user_message_id=1,
        assistant_message_id=1,
        mask="daily_companion",
        reply_mode="catch_up",
        user_chars=10,
        reply_chars=20,
        reply_seconds=1.5,
        now=datetime(2026, 8, 15, 21, 30, tzinfo=tz),
    )
    record_turn(
        session_id=1,
        user_message_id=2,
        assistant_message_id=2,
        mask="work_advisor",
        reply_mode="work_think",
        user_chars=30,
        reply_chars=120,
        reply_seconds=2.1,
        now=datetime(2026, 8, 15, 22, 5, tzinfo=tz),
    )
    record_turn(
        session_id=1,
        user_message_id=3,
        assistant_message_id=3,
        mask="work_advisor",
        reply_mode="work_think",
        user_chars=15,
        reply_chars=80,
        reply_seconds=1.8,
        now=datetime(2026, 8, 15, 21, 50, tzinfo=tz),
    )

    profile = get_rhythm_profile(days=30)
    assert profile["total_turns"] == 3
    assert profile["active_hours"][0]["hour"] == 21
    assert profile["topic_heat"][0]["mask"] == "work_advisor"
    assert all(0 <= w["weekday"] <= 6 for w in profile["weekday_distribution"])


def test_format_rhythm_profile_insufficient(tmp_db):
    from app.memory.observations import format_rhythm_profile

    text = format_rhythm_profile()
    assert "还在了解你的节奏" in text
    assert "不构成事实记忆" in text


def test_format_rhythm_profile_sufficient(tmp_db):
    from datetime import datetime, timedelta, timezone

    from app.memory.observations import format_rhythm_profile, record_turn

    tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
    for i in range(1, 7):
        record_turn(
            session_id=1,
            user_message_id=i,
            assistant_message_id=i,
            mask="daily_companion",
            reply_mode="catch_up",
            user_chars=5,
            reply_chars=30,
            reply_seconds=1.0,
            now=datetime(2026, 8, 15, 21, 30 + i, tzinfo=tz),
        )

    text = format_rhythm_profile()
    assert "活跃" in text
    assert "聊「日常」的次数更多" in text
