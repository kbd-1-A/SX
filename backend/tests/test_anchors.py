"""结构化记忆锚点测试。"""

import pytest

from app.memory.anchors import (
    add_anchors_from_text,
    extract_anchor_candidates,
    format_recalled_anchors,
    list_anchors,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import anchors as anchors_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(anchors_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_extract_explicit_memory():
    candidates = extract_anchor_candidates("你记住：我不喜欢小作文")
    assert candidates[0].kind == "user_fact"
    assert candidates[0].content == "我不喜欢小作文"


def test_extract_explicit_memory_when_remember_request_is_at_the_end():
    candidates = extract_anchor_candidates("我是卡布达，你要记住")
    assert candidates[0].kind == "user_fact"
    assert candidates[0].content == "我是卡布达"
    assert candidates[0].requires_confirmation is False


def test_extract_name_as_explicit_memory():
    candidates = extract_anchor_candidates("叫我卡布达就好")
    assert len(candidates) == 1
    assert candidates[0].kind == "user_fact"
    assert candidates[0].content == "用户希望被称呼为：卡布达"
    assert candidates[0].requires_confirmation is False


def test_extract_preference():
    candidates = extract_anchor_candidates("以后你可以直接点，别太客套")
    kinds = {c.kind for c in candidates}
    assert "preference" in kinds


def test_extract_open_loop():
    candidates = extract_anchor_candidates("下次继续做 V2 实现")
    assert candidates[0].kind == "open_loop"
    assert "下次继续做 V2 实现" in candidates[0].content


def test_add_anchors_dedup(tmp_db):
    ids1 = add_anchors_from_text("你记住：我不喜欢小作文", source_message_id=1)
    ids2 = add_anchors_from_text("你记住：我不喜欢小作文", source_message_id=2)
    anchors = list_anchors()
    assert ids1 == ids2
    assert len(anchors) == 1


def test_name_is_stored_as_active_memory(tmp_db):
    ids = add_anchors_from_text("叫我卡布达", source_message_id=1)
    anchors = list_anchors()
    assert len(ids) == 1
    assert len(anchors) == 1
    assert anchors[0]["id"] == ids[0]
    assert anchors[0]["content"] == "用户希望被称呼为：卡布达"
    assert anchors[0]["status"] == "active"


def test_format_recalled_anchors(tmp_db):
    add_anchors_from_text("你记住：我不喜欢小作文", source_message_id=1)
    text = format_recalled_anchors("你还记得小作文吗")
    assert "[memory:" in text
    assert "我不喜欢小作文" in text
