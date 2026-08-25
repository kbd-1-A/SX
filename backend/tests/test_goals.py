"""目标生命周期（自主学习）测试。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import companion as companion_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(companion_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_create_emits_created_event(tmp_db):
    from app.memory.companion import create_follow_up, list_goal_events

    goal = create_follow_up(title="周五前完成项目汇报")
    assert goal["phase"] == "active"
    assert goal["stall_rounds"] == 0

    events = list_goal_events(goal["id"])
    assert [e["event_type"] for e in events] == ["created"]


def test_pause_resume_lifecycle(tmp_db):
    from app.memory.companion import (
        create_follow_up,
        list_goal_events,
        pause_follow_up,
        resume_follow_up,
    )

    goal = create_follow_up(title="整理主动陪伴方案")
    paused = pause_follow_up(goal["id"])
    assert paused["phase"] == "paused"

    resumed = resume_follow_up(goal["id"])
    assert resumed["phase"] == "active"

    events = [e["event_type"] for e in list_goal_events(goal["id"])]
    assert events == ["resumed", "paused", "created"]


def test_complete_and_reopen_lifecycle(tmp_db):
    from app.memory.companion import (
        create_follow_up,
        list_goal_events,
        update_follow_up,
    )

    goal = create_follow_up(title="下次继续做 V2 实现")
    done = update_follow_up(goal["id"], status="done")
    assert done["status"] == "done"
    assert done["completed_at"] is not None

    reopened = update_follow_up(goal["id"], status="open")
    assert reopened["status"] == "open"
    assert reopened["completed_at"] is None

    types = [e["event_type"] for e in list_goal_events(goal["id"])]
    assert types == ["reopened", "completed", "created"]


def test_stall_blocks_after_three_rounds(tmp_db):
    from app.memory.companion import create_follow_up, mark_goal_stalled

    goal = create_follow_up(title="一个长期没推进的目标")
    assert mark_goal_stalled(goal["id"])["stall_rounds"] == 1
    assert mark_goal_stalled(goal["id"])["stall_rounds"] == 2
    blocked = mark_goal_stalled(goal["id"])
    assert blocked["phase"] == "blocked"
    assert blocked["blocked_reason"]["code"] == "stalled"

    # 已阻塞后不再重复累计
    assert mark_goal_stalled(goal["id"]) is None


def test_unblock_resets_stall_and_reason(tmp_db):
    from app.memory.companion import (
        block_follow_up,
        create_follow_up,
        unblock_follow_up,
    )

    goal = create_follow_up(title="显式阻塞测试")
    blocked = block_follow_up(
        goal["id"], reason_code="manual", reason_message="先放一放"
    )
    assert blocked["phase"] == "blocked"
    assert blocked["blocked_reason"]["code"] == "manual"

    unblocked = unblock_follow_up(goal["id"])
    assert unblocked["phase"] == "active"
    assert unblocked["blocked_reason"] is None
    assert unblocked["stall_rounds"] == 0


def test_completed_goal_cannot_pause_or_block(tmp_db):
    from app.memory.companion import (
        block_follow_up,
        create_follow_up,
        pause_follow_up,
        update_follow_up,
    )

    goal = create_follow_up(title="已完成的目标")
    update_follow_up(goal["id"], status="done")

    assert pause_follow_up(goal["id"]) is None
    assert block_follow_up(goal["id"]) is None
