"""WebSocket 协议测试：验证流式完成和用户可读错误。"""

from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.chat as chat_mod
from app.agents.errors import AgentTimeoutError


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_mod.router)
    return app


def patch_chat_dependencies(monkeypatch):
    counter = {"message_id": 0}

    def add_message(session_id: int, role: str, content: str) -> int:
        counter["message_id"] += 1
        return counter["message_id"]

    monkeypatch.setattr(chat_mod, "get_or_create_session", lambda session_id=None: 1)
    monkeypatch.setattr(chat_mod, "add_message", add_message)
    monkeypatch.setattr(chat_mod, "add_anchors_from_text", lambda content, message_id: [])
    monkeypatch.setattr(chat_mod, "observe_behavior", lambda content, message_id: {})
    monkeypatch.setattr(chat_mod, "create_follow_ups_from_text", lambda content, message_id: [])
    monkeypatch.setattr(chat_mod, "add_mask_milestone", lambda mask: None)
    monkeypatch.setattr(chat_mod, "choose_mask", lambda content: _return("daily_companion"))
    monkeypatch.setattr(chat_mod, "detect_reply_mode", lambda content, mask: "catch_up")


async def _return(value: str) -> str:
    return value


def test_ws_chat_streams_done_event(monkeypatch):
    patch_chat_dependencies(monkeypatch)

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        yield "我在。"
        yield "慢慢说。"

    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "今天有点乱"})
        assert ws.receive_json() == {"type": "chunk", "content": "我在。"}
        assert ws.receive_json() == {"type": "chunk", "content": "慢慢说。"}
        done = ws.receive_json()

    assert done["type"] == "done"
    assert done["assistant_id"] == 2
    assert done["mask"] == "daily_companion"
    assert done["reply_mode"] == "catch_up"


def test_ws_chat_maps_agent_error_without_internal_detail(monkeypatch):
    patch_chat_dependencies(monkeypatch)

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        raise AgentTimeoutError("provider stack trace must stay internal")
        yield ""

    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "还在吗"})
        error = ws.receive_json()

    assert error == {
        "type": "error",
        "message": "时叙想得有点久，这句话先没等到回复。请再试一次。",
        "code": "agent_timeout",
    }
