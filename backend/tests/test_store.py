"""会话任务与消息存储测试。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import store as store_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(store_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_create_and_list_sessions(tmp_db):
    from app.memory.store import add_message, create_session, list_sessions

    sid1 = create_session()
    sid2 = create_session()
    add_message(sid1, "user", "第一条时间线")
    add_message(sid2, "user", "第二条时间线")

    sessions = list_sessions()

    assert {s["id"] for s in sessions} == {sid1, sid2}
    assert any(s["preview"] == "第一条时间线" for s in sessions)
    assert any(s["preview"] == "第二条时间线" for s in sessions)


def test_get_or_create_session_accepts_existing(tmp_db):
    from app.memory.store import create_session, get_or_create_session

    sid = create_session()

    assert get_or_create_session(sid) == sid


def test_get_or_create_session_falls_back_for_unknown(tmp_db):
    from app.memory.store import create_session, get_or_create_session

    sid = create_session()

    assert get_or_create_session(9999) == sid


def test_messages_are_separated_by_session(tmp_db):
    from app.memory.store import add_message, create_session, get_messages

    sid1 = create_session()
    sid2 = create_session()
    add_message(sid1, "user", "旧任务")
    add_message(sid2, "user", "新任务")

    assert [m["content"] for m in get_messages(sid1)] == ["旧任务"]
    assert [m["content"] for m in get_messages(sid2)] == ["新任务"]
