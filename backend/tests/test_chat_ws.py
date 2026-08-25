"""WebSocket 协议测试：验证流式完成和用户可读错误。"""

from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.chat as chat_mod
from app.agents.errors import AgentTimeoutError
from app.services.weather import WeatherError, WeatherForecast, WeatherResult
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


async def _async_return(value):
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
        yield (
            "# 行业分析\n\n"
            "## 一、行业现状\n基于非实时知识整理，公开资料显示相关工具持续更新，"
            "企业采购以成本与集成为主。\n\n"
            "## 二、主要趋势\n工具化与平台化并行，厂商加速推出可验证的落地产品，"
            "采购方重点关注 ROI 与集成能力。\n\n"
            "## 三、结论\n建议优先验证核心场景，再规模化扩展。"
        )

    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)
    monkeypatch.setattr(chat_mod, "create_markdown_file", lambda **kwargs: artifact)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "帮我创建一个 md 文件"})
        created = ws.receive_json()
        preview = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert created == {"type": "artifact.created", "artifact": artifact.as_event()}
    assert preview["type"] == "chunk"
    assert "# 行业分析" in preview["content"]
    assert chunk["type"] == "chunk"
    assert "已创建 Markdown 文件：行业分析.md" in chunk["content"]
    assert r"E:\\Kairos-output\\行业分析.md" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_keeps_draft_when_file_creation_fails(monkeypatch):
    patch_chat_dependencies(monkeypatch)

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        yield (
            "# 没有保存的草稿\n\n"
            "## 内容\n这段草稿不会保存，但创建失败后仍应完整保留给用户查看，避免内容丢失。\n\n"
            "## 说明\n目标文件夹不可用时，草稿内容不能丢失，用户应能看到完整正文与失败原因，并支持重试。\n\n"
            "## 补充\n这是补充说明段落，用来确保草稿内容完整可读。"
        )

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
        query="agent 行业行情",
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
        assert query == "agent 行业行情"
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
        preview = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert started == {"type": "research.started", "query": "agent 行业行情"}
    assert completed["type"] == "research.completed"
    assert completed["research"]["source_count"] == 2
    assert completed["research"]["sources"][0]["url"] == "https://example.com/a"
    assert created["type"] == "artifact.created"
    assert "## 检索范围与来源" in captured["content"]
    assert "https://example.com/a" in captured["content"]
    assert preview["type"] == "chunk"
    assert "# Agent 行业行情" in preview["content"]
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
        preview = ws.receive_json()
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
    assert preview["type"] == "chunk"
    assert "研究框架" in preview["content"]
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


def test_ws_chat_degrades_polluted_draft_to_research_framework(monkeypatch):
    """模型把历史里的成功提示当成草稿输出时，不得落盘，应降级为研究框架。"""
    patch_chat_dependencies(monkeypatch)
    research = ResearchResult(
        query="AI 销售行情",
        retrieved_at="2026-08-25 14:32:00 +0800",
        sources=(
            ResearchSource(1, "来源一", "https://example.com/a", "example.com", "正文"),
            ResearchSource(2, "来源二", "https://example.org/b", "example.org", "正文"),
        ),
    )
    artifact = MarkdownArtifact(
        id="framework-artifact",
        path=r"E:\时序-output\AI 销售行情_2026-08-25.txt",
        display_name="AI 销售行情_2026-08-25.txt",
        target="output",
        mime_type="text/plain",
        size_bytes=500,
        sha256="d" * 64,
    )
    captured = {}

    async def fake_research(query):
        return research

    async def polluted_stream(*args, **kwargs) -> AsyncIterator[str]:
        yield (
            "已创建 Markdown 文件：AI销售行情分析_2026-08-25.md\n"
            "位置：C:\\Users\\x\\Desktop\\AI销售行情分析_2026-08-25.md\n"
            "已校验：3.4 KB，SHA-256 c6b1b58c60e6..."
        )

    def fake_create(**kwargs):
        captured.update(kwargs)
        return artifact

    monkeypatch.setattr(chat_mod, "research_public_sources", fake_research)
    monkeypatch.setattr(chat_mod, "stream_reply", polluted_stream)
    monkeypatch.setattr(chat_mod, "create_markdown_file", fake_create)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json(
            {
                "type": "message",
                "content": "帮我分析一下 AI 销售行情，创建 txt 文件放到桌面",
            }
        )
        started = ws.receive_json()
        completed = ws.receive_json()
        created = ws.receive_json()
        preview = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert started["type"] == "research.started"
    assert completed["type"] == "research.completed"
    assert created["type"] == "artifact.created"
    # 写入文件的是研究框架，不是被污染的"已创建"草稿
    assert "研究框架" in captured["content"]
    assert "待核实问题" in captured["content"]
    assert not captured["content"].startswith("已创建 Markdown 文件")
    # 用户明确要 txt → 默认文件名使用 .txt 且来自研究主题
    assert captured["filename"].endswith(".txt")
    assert "销售行情" in captured["filename"]
    # 聊天里展示的是框架正文预览 + 成功提示
    assert preview["type"] == "chunk"
    assert "研究框架" in preview["content"]
    assert "已创建" not in preview["content"]
    assert "已创建 文本文件" in chunk["content"]
    assert done["type"] == "done"


def test_draft_unusable_detects_metadata_only_and_polluted_drafts():
    assert chat_mod._draft_unusable("") is True
    assert chat_mod._draft_unusable("好的，我准备了一份关于 AI 销售行情的分析文档草稿。") is True
    assert chat_mod._draft_unusable(
        "已创建 Markdown 文件：x.md\n位置：C:\\Users\\x\\Desktop\\x.md\nSHA-256 abc"
    ) is True
    assert chat_mod._draft_unusable("没有标题的一段话" * 10) is True
    assert (
        chat_mod._draft_unusable("# AI 销售行情分析\n\n## 核心结论\n这是正文内容。" * 20)
        is False
    )
    framework = (
        "# AI 销售行情 研究框架\n\n"
        "## 检索状态\n联网检索未完成：网络不可用。本文件不包含实时行情、最新数据或来源结论，"
        "以下内容仅是待补充的研究框架。\n\n"
        "## 待核实问题\n- 当前市场规模、增长数据与统计口径\n- 代表企业、产品更新与发布时间\n\n"
        "## 建议来源\n- 官方产品文档、公司公告和监管/行业组织资料"
    )
    assert chat_mod._draft_unusable(framework) is False


def test_ws_chat_retries_when_first_draft_is_metadata_only(monkeypatch):
    """第一次草稿只有元描述时自动重试，落盘第二次生成的真实正文。"""
    patch_chat_dependencies(monkeypatch)
    research = ResearchResult(
        query="AI 销售行情",
        retrieved_at="2026-08-25 15:28:41 +0800",
        sources=(
            ResearchSource(1, "来源一", "https://example.com/a", "example.com", "正文"),
            ResearchSource(2, "来源二", "https://example.org/b", "example.org", "正文"),
        ),
    )
    artifact = MarkdownArtifact(
        id="retry-artifact",
        path=r"E:\时序-output\AI 销售行情_2026-08-25.txt",
        display_name="AI 销售行情_2026-08-25.txt",
        target="output",
        mime_type="text/plain",
        size_bytes=600,
        sha256="e" * 64,
    )
    captured = {}
    calls = {"n": 0}

    async def fake_research(query):
        return research

    async def fake_stream(*args, **kwargs) -> AsyncIterator[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            yield "好的，我准备了一份关于 AI 销售行情的分析文档草稿，内容基于你提供的公开资料整理。"
        else:
            yield (
                "# AI 销售行情分析（2026-08-25）\n\n"
                "## 核心结论\n2026 年 AI 销售进入上游扩散、下游洗牌阶段 [S2]。\n\n"
                "## 风险与挑战\n部署费用具体区间待核实 [S1]。"
            )

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
                "content": "帮我分析一下 AI 销售行情，创建 txt 文件放到桌面",
            }
        )
        started = ws.receive_json()
        completed = ws.receive_json()
        created = ws.receive_json()
        preview = ws.receive_json()
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert started["type"] == "research.started"
    assert completed["type"] == "research.completed"
    assert created["type"] == "artifact.created"
    assert calls["n"] == 2  # 自动重试了一次
    # 落盘的是第二次生成的真实正文，不是第一次的元描述
    assert "# AI 销售行情分析（2026-08-25）" in captured["content"]
    assert "我准备了一份" not in captured["content"]
    assert "上游扩散" in captured["content"]
    # 聊天展示正文预览 + 成功提示
    assert preview["type"] == "chunk"
    assert "# AI 销售行情分析（2026-08-25）" in preview["content"]
    assert "已创建 文本文件" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_weather_reply_uses_real_data(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    weather = WeatherResult(
        city="北京",
        province="北京市",
        obs_time="2026-08-25 16:55",
        temp="28",
        feels_like="32",
        text="大雨",
        wind_dir="西北风",
        wind_scale="3",
        humidity="93",
        pressure="1005",
        forecast=(WeatherForecast("2026-08-25", "22", "29", "雷阵雨", "小雨"),),
    )

    captured_stream = {}

    async def fake_stream(*args, **kwargs):
        captured_stream.update(kwargs)
        yield "北京现在大雨，28℃，体感 32℃，出门记得带伞。"

    async def fake_weather(city):
        assert city == "北京"
        return weather

    monkeypatch.setattr(chat_mod, "fetch_weather_summary", fake_weather)
    monkeypatch.setattr(chat_mod, "extract_city_name", lambda text: "北京")
    monkeypatch.setattr(chat_mod, "stream_reply", fake_stream)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "北京今天天气怎么样"})
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert captured_stream.get("weather_result") is weather
    assert captured_stream.get("document_draft", False) is False
    assert chunk["type"] == "chunk"
    assert "北京现在大雨" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_weather_missing_city_asks_user(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    monkeypatch.setattr(chat_mod, "extract_city_name", lambda text: None)
    monkeypatch.setattr(chat_mod, "default_city", lambda: None)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "今天天气怎么样"})
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert chunk["type"] == "chunk"
    assert "哪个城市" in chunk["content"]
    assert done["type"] == "done"


def test_ws_chat_weather_api_failure_is_honest(monkeypatch):
    patch_chat_dependencies(monkeypatch)
    monkeypatch.setattr(chat_mod, "extract_city_name", lambda text: "北京")

    async def fail_weather(city):
        raise WeatherError("天气服务暂时连不上，稍后再试。", "weather_unavailable")

    monkeypatch.setattr(chat_mod, "fetch_weather_summary", fail_weather)

    with TestClient(make_app()).websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "content": "北京天气怎么样"})
        chunk = ws.receive_json()
        done = ws.receive_json()

    assert chunk["type"] == "chunk"
    assert "天气暂时查不到" in chunk["content"]
    assert "连不上" in chunk["content"]
    assert done["type"] == "done"
