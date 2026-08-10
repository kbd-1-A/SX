"""模型流式适配层测试：不需要真实模型 Key。"""

import asyncio
from types import SimpleNamespace

import pytest

import app.agents.router as router_mod
from app.agents.errors import AgentEmptyResponseError, AgentTimeoutError


class FakeCompletions:
    def __init__(self, result):
        self.result = result
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeClient:
    def __init__(self, result):
        self.chat = SimpleNamespace(completions=FakeCompletions(result))


class FakeStream:
    def __init__(self, contents):
        self.contents = contents

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for content in self.contents:
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(delta=SimpleNamespace(content=content)),
                ]
            )


async def collect_reply():
    return [
        chunk
        async for chunk in router_mod.stream_reply(
            session_id=1,
            user_msg="今天好累",
            mask="daily_companion",
            reply_mode="comfort",
        )
    ]


def test_stream_reply_yields_content_and_uses_streaming(monkeypatch):
    fake_client = FakeClient(FakeStream(["先缓一缓。", None, "我在。"]))
    monkeypatch.setattr(router_mod, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(router_mod, "get_client", lambda: fake_client)
    monkeypatch.setattr(router_mod, "build_messages", lambda *args, **kwargs: [{"role": "system", "content": "x"}])

    assert asyncio.run(collect_reply()) == ["先缓一缓。", "我在。"]
    assert fake_client.chat.completions.last_kwargs["stream"] is True


def test_stream_reply_passes_document_draft_mode_to_message_builder(monkeypatch):
    fake_client = FakeClient(FakeStream(["# 文档\n"]))
    observed = {}
    monkeypatch.setattr(router_mod, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(router_mod, "get_client", lambda: fake_client)

    def fake_build_messages(*args, **kwargs):
        observed.update(kwargs)
        return [{"role": "system", "content": "x"}]

    monkeypatch.setattr(router_mod, "build_messages", fake_build_messages)

    result = asyncio.run(
        _collect_document_draft()
    )

    assert result == ["# 文档\n"]
    assert observed["document_draft"] is True


async def _collect_document_draft():
    return [
        chunk
        async for chunk in router_mod.stream_reply(
            session_id=1,
            user_msg="创建一个 md 文件",
            document_draft=True,
        )
    ]


def test_stream_reply_rejects_empty_stream(monkeypatch):
    monkeypatch.setattr(router_mod, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(router_mod, "get_client", lambda: FakeClient(FakeStream([])))
    monkeypatch.setattr(router_mod, "build_messages", lambda *args, **kwargs: [])

    with pytest.raises(AgentEmptyResponseError):
        asyncio.run(collect_reply())


def test_stream_reply_maps_timeout_to_agent_error(monkeypatch):
    monkeypatch.setattr(router_mod, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(router_mod, "get_client", lambda: FakeClient(asyncio.TimeoutError()))
    monkeypatch.setattr(router_mod, "build_messages", lambda *args, **kwargs: [])

    with pytest.raises(AgentTimeoutError):
        asyncio.run(collect_reply())
