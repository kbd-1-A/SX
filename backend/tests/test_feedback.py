"""消息级反馈（自主学习）测试。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    import app.api.feedback as feedback_api
    import app.db.init as init_mod
    from app.memory import behavior as behavior_mod
    from app.memory import feedback as feedback_mod
    from app.memory import store as store_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(feedback_mod, "DB_PATH", db)
    monkeypatch.setattr(behavior_mod, "DB_PATH", db)
    monkeypatch.setattr(store_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()

    app = FastAPI()
    app.include_router(feedback_api.router)
    with TestClient(app) as client:
        yield client


def _assistant_message(content: str) -> int:
    from app.memory.store import add_message, create_session

    session_id = create_session()
    return add_message(session_id, "assistant", content)


def test_feedback_rejects_non_assistant_message(api_client):
    from app.memory.store import add_message, create_session

    session_id = create_session()
    user_id = add_message(session_id, "user", "这是用户说的话")

    res = api_client.put(f"/api/messages/{user_id}/feedback", json={"rating": "positive"})
    assert res.status_code == 400

    res = api_client.put("/api/messages/999999/feedback", json={"rating": "positive"})
    assert res.status_code == 400


def test_feedback_upsert_and_optimistic_concurrency(api_client):
    mid = _assistant_message("时叙的正常回复")

    created = api_client.put(
        f"/api/messages/{mid}/feedback", json={"rating": "positive", "note": "很自然"}
    )
    assert created.status_code == 200
    body = created.json()
    assert body["rating"] == "positive"
    assert body["version"] == 1

    conflict = api_client.put(
        f"/api/messages/{mid}/feedback",
        json={"rating": "negative", "if_version": 0},
    )
    assert conflict.status_code == 409
    assert conflict.json()["version"] == 1
    assert conflict.json()["rating"] == "positive"

    updated = api_client.put(
        f"/api/messages/{mid}/feedback",
        json={"rating": "negative", "if_version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["rating"] == "negative"
    assert updated.json()["version"] == 2


def test_feedback_get_list_delete_and_stats(api_client):
    mid = _assistant_message("另一条回复")

    api_client.put(f"/api/messages/{mid}/feedback", json={"rating": "positive"})

    assert api_client.get(f"/api/messages/{mid}/feedback").status_code == 200

    listed = api_client.get("/api/feedback").json()
    assert any(item["message_id"] == mid for item in listed)

    stats = api_client.get("/api/feedback/stats").json()
    assert stats["positive"] >= 1

    deleted = api_client.delete(f"/api/messages/{mid}/feedback")
    assert deleted.status_code == 200
    assert api_client.get(f"/api/messages/{mid}/feedback").status_code == 404


def test_negative_feedback_on_long_reply_nudges_short_reply(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import behavior as behavior_mod
    from app.memory import feedback as feedback_mod
    from app.memory import store as store_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(feedback_mod, "DB_PATH", db)
    monkeypatch.setattr(behavior_mod, "DB_PATH", db)
    monkeypatch.setattr(store_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()

    from app.memory.store import add_message, create_session

    session_id = create_session()
    long_reply = "我理解你的感受。" + "这段回复写得特别长，希望这能帮助到你。" * 20
    mid = add_message(session_id, "assistant", long_reply)

    feedback_mod.set_feedback(mid, "negative")

    styles = behavior_mod.get_behavior_profile()["styles"]
    assert styles["short_reply"]["observations"] == 1
    assert styles["less_cliche"]["observations"] == 1
    # 单次踩不应立即改变人格（保守），需要连续累计才激活
    assert styles["short_reply"]["status"] == "candidate"


def test_positive_feedback_does_not_rewrite_behavior(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import behavior as behavior_mod
    from app.memory import feedback as feedback_mod
    from app.memory import store as store_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(feedback_mod, "DB_PATH", db)
    monkeypatch.setattr(behavior_mod, "DB_PATH", db)
    monkeypatch.setattr(store_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()

    from app.memory.store import add_message, create_session

    session_id = create_session()
    mid = add_message(session_id, "assistant", "短而稳的一句回复")

    feedback_mod.set_feedback(mid, "positive")

    styles = behavior_mod.get_behavior_profile()["styles"]
    # 正向反馈不改写人格，也不应新建任何表达偏好条目
    assert "short_reply" not in styles
    assert "less_cliche" not in styles
