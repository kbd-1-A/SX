"""记忆确认、编辑、删除与到期的生命周期测试。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import anchors as anchors_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(anchors_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_inferred_memory_waits_for_confirmation(tmp_db):
    from app.memory.anchors import (
        add_anchors_from_text,
        confirm_anchor,
        format_recalled_anchors,
        list_anchors,
    )

    ids = add_anchors_from_text("以后你可以直接一点，别太客套", source_message_id=1)

    pending = list_anchors(status="pending")
    assert [anchor["id"] for anchor in pending] == ids
    assert "[memory:" not in format_recalled_anchors("你以后直接一点就好")

    confirmed = confirm_anchor(ids[0])
    assert confirmed and confirmed["status"] == "active"
    assert confirmed["confirmed_at"]
    assert "[memory:" in format_recalled_anchors("你以后直接一点就好")


def test_expired_memory_becomes_stale_and_is_not_recalled(tmp_db):
    from app.memory.anchors import (
        AnchorCandidate,
        add_anchor,
        list_anchors,
        recall_anchors,
    )

    anchor_id = add_anchor(
        AnchorCandidate(
            kind="open_loop",
            content="明天继续讨论接口设计",
            requires_confirmation=False,
            expires_in_days=-1,
        ),
        source_message_id=1,
    )

    assert anchor_id is not None
    stale = list_anchors(status="stale")
    assert stale[0]["id"] == anchor_id
    assert recall_anchors("接口设计") == []


def test_memory_can_be_edited_and_deleted(tmp_db):
    from app.memory.anchors import (
        AnchorCandidate,
        add_anchor,
        delete_anchor,
        get_anchor,
        update_anchor,
    )

    anchor_id = add_anchor(
        AnchorCandidate(
            kind="user_fact",
            content="我叫小宁",
            requires_confirmation=False,
        ),
        source_message_id=1,
    )
    assert anchor_id is not None

    updated = update_anchor(
        anchor_id,
        content="我希望被叫作阿宁",
        kind="preference",
        tags=["称呼", "称呼", "关系"],
        expires_at="2030-01-02T12:00:00+08:00",
    )

    assert updated == {
        **updated,
        "id": anchor_id,
        "kind": "preference",
        "content": "我希望被叫作阿宁",
        "tags": ["关系", "称呼"],
        "expires_at": "2030-01-02 04:00:00",
    }
    assert delete_anchor(anchor_id) is True
    assert get_anchor(anchor_id) is None
    assert delete_anchor(anchor_id) is False
