"""WebSocket 协议测试：验证流式完成和用户可读错误。"""

from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.chat as chat_mod
from app.agents.errors import AgentTimeoutError
from app.tools.files import MarkdownArtifact, MarkdownFileToolError
from app.tools.music import LocalMusicTrack
from app.tools.research import ResearchError, ResearchResult, ResearchSource

EMOTION_STATE = {
    "emotion": "tired",
    "emotion_label": "疲惫",
    "intensity": 1,
    "confidence": 0.67,
    "user_need": "rest",
    "user_need_label": "需要减负休息",
    "strategy": "reduce_load",
    "strategy_label": "减负陪伴",
    "risk_level": "none",
    "sensitive_scene": "none",
}


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
    monkeypatch.setattr(chat_mod, "detect_emotion_state", lambda content: EMOTION_STATE)


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
    assert done["reply_mode"] == "comfort"
    assert done["emotion_state"] == EMOTION_STATE


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


def test_ws_chat_creates_verified_markdown_artifact(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    artifact = MarkdownArtifact(
        id="artifact-1",
        path=r"E:\\Kairos-output\\行业分析.md",
        display_name="行业分析.md",
        target="output",
        mime_type="text/markdown",
        size_bytes=42,
        sha256="a" * 64,
    )

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        assert kwargs["document_draft"] is True
        yield "# 行业分析\n\n基于非实时知识整理。"

    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)
    monkeypatch.setattr(chat_mod, "create_markdown_file", lambda **kwargs: artifact)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "帮我创建一个 md 文件"})
        created = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert created == {"type": "artifact.created", "artifact": artifact.as_event()}
    assert chunk["type"] == "chunk"
    assert "已创建 Markdown 文件：行业分析.md" in chunk["content"]
    assert r"E:\\Kairos-output\\行业分析.md" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_keeps_draft_when_file_creation_fails(monkeypatch):
    patch_chat_dependencies(monkeypatch)

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        yield "# 没有保存的草稿\n\n内容还在。"

    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)
    monkeypatch.setattr(
        chat_mod,
        "create_markdown_file",
        lambda **kwargs: (_ for _ in ()).throw(
            MarkdownFileToolError("目标文件夹无法使用。", "destination_unavailable")
        ),
    )

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "帮我创建一个 md 文件"})
        failed = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert failed == {
        "type": "artifact.failed",
        "code": "destination_unavailable",
        "message": "目标文件夹无法使用。",
    }
    assert "没有创建成功" in chunk["content"]
    assert "# 没有保存的草稿" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_researches_sources_before_creating_document(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    research = ResearchResult(
        query="现在的 agent 行业行情",
        retrieved_at="2026-08-10 15:00:00 +0800",
        sources=(
            ResearchSource(1, "官方资料", "https://example.com/a", "example.com", "正文" * 100),
            ResearchSource(2, "行业资料", "https://example.org/b", "example.org", "正文" * 100),
        ),
    )
    artifact = MarkdownArtifact(
        id="research-artifact",
        path=r"E:\Kairos-output\agent行业.md",
        display_name="agent行业.md",
        target="output",
        mime_type="text/markdown",
        size_bytes=1000,
        sha256="b" * 64,
    )
    captured = {}

    async def fake_research(query):
        assert query == "现在的 agent 行业行情"
        return research

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        assert kwargs["research_result"] is research
        yield "# Agent 行业行情\n\n公开资料显示相关工具持续更新。[S1]"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return artifact

    monkeypatch.setattr(chat_mod, "research_public_sources", fake_research)
    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)
    monkeypatch.setattr(chat_mod, "create_markdown_file", fake_create)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json(
            {
                "type": "message",
                "content": "我想了解一下现在的 agent 行业行情，创建 agent行业.md 文件",
            }
        )
        started = ws.receive_json()
        completed = ws.receive_json()
        created = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert started == {"type": "research.started", "query": "现在的 agent 行业行情"}
    assert completed["type"] == "research.completed"
    assert completed["research"]["source_count"] == 2
    assert completed["research"]["sources"][0]["url"] == "https://example.com/a"
    assert created["type"] == "artifact.created"
    assert "## 检索范围与来源" in captured["content"]
    assert "https://example.com/a" in captured["content"]
    assert "已创建 Markdown 文件" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_creates_research_framework_when_search_fails(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    artifact = MarkdownArtifact(
        id="framework-artifact",
        path=r"E:\Kairos-output\研究框架.md",
        display_name="研究框架.md",
        target="output",
        mime_type="text/markdown",
        size_bytes=500,
        sha256="c" * 64,
    )
    captured = {}

    async def fake_research(query):
        raise ResearchError("联网搜索暂时不可用。", "search_unavailable")

    async def unexpected_stream(*args, **kwargs) -> AsyncIterator[str]:
        raise AssertionError("检索失败后不应由模型编造研究结论")
        yield ""

    def fake_create(**kwargs):
        captured.update(kwargs)
        return artifact

    monkeypatch.setattr(chat_mod, "research_public_sources", fake_research)
    monkeypatch.setattr(chat_mod, "stream_reply", unexpected_stream)
    monkeypatch.setattr(chat_mod, "create_markdown_file", fake_create)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json(
            {
                "type": "message",
                "content": "了解现在的 agent 行业行情，创建 研究框架.md 文件",
            }
        )
        started = ws.receive_json()
        failed = ws.receive_json()
        created = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert started["type"] == "research.started"
    assert failed == {
        "type": "research.failed",
        "code": "search_unavailable",
        "message": "联网搜索暂时不可用。",
    }
    assert created["type"] == "artifact.created"
    assert "不包含实时行情" in captured["content"]
    assert "待核实问题" in captured["content"]
    assert "已创建 Markdown 文件" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_only_reports_music_playing_after_browser_confirmation(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    track = LocalMusicTrack(
        id="track-1",
        title="慢慢来",
        artist="夜晚",
        mime_type="audio/mpeg",
    )

    async def unexpected_stream(*args, **kwargs) -> AsyncIterator[str]:
        raise AssertionError("音乐请求不应由模型伪造播放结果")
        yield ""

    monkeypatch.setattr(chat_mod, "stream_reply", unexpected_stream)
    monkeypatch.setattr(chat_mod, "select_local_music_track", lambda query: track)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "我今天很难受，帮我放一首歌"})
        loading = ws.receive_json()
        ready = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

        ws.send_json(
            {
                "type": "media.status",
                "playback_id": ready["media"]["playback_id"],
                "status": "playing",
            }
        )
        playing = ws.receive_json()

    assert loading["type"] == "media.loading"
    assert ready["type"] == "media.ready"
    assert ready["media"]["title"] == "慢慢来"
    assert "正在播放" not in chunk["content"]
    assert done["type"] == "done"
    assert playing == {
        "type": "media.playing",
        "playback_id": ready["media"]["playback_id"],
    }


def test_ws_chat_keeps_autoplay_blocked_as_an_actionable_state(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    track = LocalMusicTrack(
        id="track-1",
        title="慢慢来",
        artist="夜晚",
        mime_type="audio/mpeg",
    )
    monkeypatch.setattr(chat_mod, "select_local_music_track", lambda query: track)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "放一首歌"})
        ws.receive_json()
        ready = ws.receive_json()
        ws.receive_json()
        ws.receive_json()
        ws.send_json(
            {
                "type": "media.status",
                "playback_id": ready["media"]["playback_id"],
                "status": "autoplay_blocked",
            }
        )
        blocked = ws.receive_json()

    assert blocked == {
        "type": "media.autoplay_blocked",
        "playback_id": ready["media"]["playback_id"],
        "message": "浏览器需要你点击一次播放。",
    }
