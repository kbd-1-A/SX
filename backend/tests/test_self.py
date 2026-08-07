"""自我记忆测试：昵称提取（纯函数）+ 里程碑/昵称落库（临时 DB）。"""

import pytest

from app.memory.self import (
    add_mask_milestone,
    add_nickname,
    extract_nickname,
    format_self_memory,
    get_self_memory,
    remove_nickname,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import self as self_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(self_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_extract_nickname():
    assert extract_nickname("你可以叫我小叙") == "小叙"
    assert extract_nickname("以后叫我阿明吧") == "阿明"
    assert extract_nickname("叫我老张就好") == "老张"
    assert extract_nickname("没有昵称") is None
    assert extract_nickname("我随口说说") is None


def test_add_nickname_dedup(tmp_db):
    assert add_nickname("小叙") is True
    assert add_nickname("小叙") is False
    assert get_self_memory()["nicknames"] == ["小叙"]


def test_remove_nickname(tmp_db):
    add_nickname("小叙")
    assert remove_nickname("小叙") is True
    assert get_self_memory()["nicknames"] == []
    assert remove_nickname("小叙") is False


def test_add_mask_milestone_once(tmp_db):
    assert add_mask_milestone("love_guide") is True
    assert add_mask_milestone("love_guide") is False
    assert add_mask_milestone("work_advisor") is True
    milestones = get_self_memory()["milestones"]
    assert len(milestones) == 2


def test_format_self_memory(tmp_db):
    add_nickname("阿明")
    add_mask_milestone("work_advisor")
    text = format_self_memory()
    assert "关系阶段：初识" in text
    assert "阿明" in text
    assert "第一次聊工作问题" in text
