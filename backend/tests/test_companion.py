"""主动陪伴与时间引擎测试。"""

from datetime import datetime, timedelta, timezone

import pytest


TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import companion as companion_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(companion_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_extract_important_event_and_due_date():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "我明天有面试，估计会很紧张。",
        now=datetime(2026, 8, 7, 10, tzinfo=TZ),
    )

    assert candidates == [
        {
            "title": "我明天有面试，估计会很紧张",
            "category": "interview",
            "importance": 3,
            "due_at": "2026-08-08 09:00:00",
        }
    ]


def test_extract_explicit_chinese_reminder_time():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "今天下午5点15提醒我出去",
        now=datetime(2026, 8, 7, 17, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-07 17:15:00"


def test_extract_chinese_numeral_hour():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "今天下午五点15提醒我出去",
        now=datetime(2026, 8, 7, 17, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-07 17:15:00"


def test_extract_month_day_with_time():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "8月8日下午5点提醒我复盘",
        now=datetime(2026, 8, 7, 17, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-08 17:00:00"


def test_extract_relative_reminder_time():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "半小时后提醒我起来走走",
        now=datetime(2026, 8, 7, 17, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-07 17:30:00"


def test_extract_weekday_with_time():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "周五下午5点提醒我复盘",
        now=datetime(2026, 8, 3, 10, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-07 17:00:00"


def test_same_weekday_uses_today_when_time_is_still_ahead():
    from app.memory.companion import extract_follow_up_candidates

    candidates = extract_follow_up_candidates(
        "周五下午5点提醒我复盘",
        now=datetime(2026, 8, 7, 10, 0, tzinfo=TZ),
    )

    assert candidates[0]["due_at"] == "2026-08-07 17:00:00"


def test_due_now_event_is_created_after_due_time(tmp_db):
    from app.memory.companion import create_follow_up, evaluate_time_engine

    follow_up = create_follow_up(
        title="17:20提醒我出去",
        importance=2,
        due_at="2026-08-07 17:20:00",
    )
    assert follow_up

    created = evaluate_time_engine(now=datetime(2026, 8, 7, 17, 22, tzinfo=TZ))
    assert [event["kind"] for event in created] == ["due_now"]
    assert "提醒时间" in created[0]["content"]


def test_due_reminder_is_created_once(tmp_db):
    from app.memory.companion import (
        create_follow_up,
        evaluate_time_engine,
        list_recent_care_points,
    )

    follow_up = create_follow_up(
        title="明天的产品面试",
        category="interview",
        importance=3,
        due_at="2026-08-08 09:00:00",
    )
    assert follow_up

    now = datetime(2026, 8, 8, 8, 55, tzinfo=TZ)
    created = evaluate_time_engine(now=now)
    assert [event["kind"] for event in created] == ["due_5m", "greeting"]
    assert "还有5分钟" in created[0]["content"]
    assert evaluate_time_engine(now=now) == []
    assert len(list_recent_care_points()) == 2


def test_countdown_reminders_fire_at_five_three_one_and_zero_minutes(tmp_db):
    from app.memory.companion import create_follow_up, evaluate_time_engine

    follow_up = create_follow_up(
        title="出门提醒",
        importance=2,
        due_at="2026-08-08 09:00:00",
    )
    assert follow_up

    checkpoints = (
        (datetime(2026, 8, 8, 8, 55, tzinfo=TZ), "due_5m"),
        (datetime(2026, 8, 8, 8, 57, tzinfo=TZ), "due_3m"),
        (datetime(2026, 8, 8, 8, 59, tzinfo=TZ), "due_1m"),
        (datetime(2026, 8, 8, 9, 0, tzinfo=TZ), "due_now"),
    )
    for now, kind in checkpoints:
        created = evaluate_time_engine(now=now)
        assert [
            event["kind"]
            for event in created
            if event["follow_up_id"] == follow_up["id"]
        ] == [kind]


def test_quiet_mode_skips_daily_greeting(tmp_db):
    from app.memory.companion import evaluate_time_engine, set_companion_frequency

    set_companion_frequency("quiet")
    created = evaluate_time_engine(now=datetime(2026, 8, 7, 9, tzinfo=TZ))
    assert created == []


def test_disabled_companion_skips_even_important_reminders(tmp_db):
    from app.memory.companion import (
        create_follow_up,
        evaluate_time_engine,
        set_companion_settings,
    )

    create_follow_up(
        title="重要面试",
        category="interview",
        importance=3,
        due_at="2026-08-08 09:00:00",
    )
    settings = set_companion_settings(enabled=False)

    assert settings["enabled"] is False
    assert evaluate_time_engine(now=datetime(2026, 8, 8, 8, 55, tzinfo=TZ)) == []


def test_overview_does_not_create_events_without_an_explicit_check_in(tmp_db):
    from app.memory.companion import create_follow_up, get_companion_overview

    create_follow_up(
        title="重要面试",
        category="interview",
        importance=3,
        due_at="2026-08-08 09:00:00",
    )
    now = datetime(2026, 8, 8, 8, 55, tzinfo=TZ)

    passive = get_companion_overview(now=now)
    active = get_companion_overview(now=now, evaluate=True)

    assert passive["new_care_points"] == []
    assert [event["kind"] for event in active["new_care_points"]] == ["due_5m", "greeting"]


def test_explicit_style_of_follow_up_can_be_completed(tmp_db):
    from app.memory.companion import create_follow_up, get_follow_up, update_follow_up

    follow_up = create_follow_up(title="下次继续整理主动陪伴方案")
    assert follow_up
    done = update_follow_up(follow_up["id"], status="done")
    assert done and done["status"] == "done"
    assert get_follow_up(follow_up["id"])["status"] == "done"
