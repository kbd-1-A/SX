"""记忆管理 REST 接口测试。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    import app.api.memory as memory_api
    import app.db.init as init_mod
    from app.memory import anchors as anchors_mod
    from app.memory import companion as companion_mod
    from app.memory import self as self_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(anchors_mod, "DB_PATH", db)
    monkeypatch.setattr(companion_mod, "DB_PATH", db)
    monkeypatch.setattr(self_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()

    app = FastAPI()
    app.include_router(memory_api.router)
    with TestClient(app) as client:
        yield client


def test_memory_management_endpoints(api_client):
    from app.memory.anchors import add_anchors_from_text

    [anchor_id] = add_anchors_from_text("以后你可以直接一点，别太客套", 1)

    listed = api_client.get("/api/memory/anchors?status=pending").json()
    assert listed[0]["id"] == anchor_id
    assert listed[0]["status"] == "pending"

    confirmed = api_client.post(f"/api/memory/anchors/{anchor_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "active"

    updated = api_client.patch(
        f"/api/memory/anchors/{anchor_id}",
        json={
            "content": "以后回答直接一点",
            "kind": "preference",
            "tags": ["表达偏好"],
            "clear_expiry": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "以后回答直接一点"
    assert updated.json()["tags"] == ["表达偏好"]

    deleted = api_client.delete(f"/api/memory/anchors/{anchor_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": anchor_id, "deleted": True}
    assert api_client.delete(f"/api/memory/anchors/{anchor_id}").status_code == 404


def test_legacy_nickname_memory_endpoints(api_client):
    from app.memory.self import add_nickname

    assert add_nickname("卡布达") is True
    listed = api_client.get("/api/memory/self")
    assert listed.status_code == 200
    assert listed.json()["nicknames"] == ["卡布达"]

    deleted = api_client.delete("/api/memory/self/nicknames/卡布达")
    assert deleted.status_code == 200
    assert deleted.json() == {"nickname": "卡布达", "deleted": True}
    assert api_client.delete("/api/memory/self/nicknames/卡布达").status_code == 404


def test_companion_endpoints(api_client):
    settings = api_client.patch("/api/companion/settings", json={"frequency": "active"})
    assert settings.status_code == 200
    assert settings.json()["frequency"] == "active"

    created = api_client.post(
        "/api/companion/follow-ups",
        json={
            "title": "明天复盘项目进度",
            "category": "work",
            "due_at": "2026-08-08 09:00:00",
            "importance": 2,
        },
    )
    assert created.status_code == 200
    follow_up_id = created.json()["id"]

    overview = api_client.get("/api/companion/overview")
    assert overview.status_code == 200
    assert overview.json()["settings"]["frequency"] == "active"
    assert overview.json()["follow_ups"][0]["id"] == follow_up_id

    done = api_client.patch(
        f"/api/companion/follow-ups/{follow_up_id}",
        json={"status": "done"},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"
