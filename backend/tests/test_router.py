"""router 纯函数测试。

测 router.py 里的 estimate_tokens / truncate_history / build_messages。
"""

import app.agents.router as router_mod
from app.agents.router import build_messages, estimate_tokens, truncate_history


def make(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_estimate_tokens_chinese():
    # 中文按约 1 token/字
    assert estimate_tokens("你好") == 2


def test_estimate_tokens_ascii():
    # 英文按约 4 字符/token
    assert estimate_tokens("hello") == 1


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_truncate_below_limit_keeps_all():
    history = [make("user", "你好"), make("assistant", "好的")]
    out = truncate_history(history, max_tokens=5000)
    assert out == history


def test_truncate_empty():
    assert truncate_history([], max_tokens=5000) == []


def test_truncate_drops_oldest_when_over():
    # 4 条 × 3000 token，上限 5000 → 只能保留最新 1 条
    history = [make("user", "最旧")] + [
        make("assistant", "段" * 3000)
    ] + [make("user", "段" * 3000)] + [make("assistant", "最新")]
    out = truncate_history(history, max_tokens=5000)
    assert out[-1]["content"] == "最新"
    assert out[0]["content"] == "段" * 3000
    # 顺序仍是最旧在前
    assert [m["content"] for m in out] == ["段" * 3000, "最新"]


def test_truncate_single_over_limit_keeps_newest():
    history = [make("user", "旧"), make("assistant", "段" * 6000)]
    out = truncate_history(history, max_tokens=5000)
    # 至少保留最新一条，即使它自身超限
    assert [m["content"] for m in out] == ["段" * 6000]


def test_build_messages_does_not_duplicate_current_user(monkeypatch):
    monkeypatch.setattr(router_mod, "load_persona", lambda mask: "core")
    monkeypatch.setattr(router_mod, "format_self_memory", lambda: "self")
    monkeypatch.setattr(router_mod, "format_behavior_profile", lambda: "behavior")
    monkeypatch.setattr(router_mod, "format_recalled_anchors", lambda query: "anchors")
    monkeypatch.setattr(
        router_mod,
        "get_messages",
        lambda session_id, limit=200: [make("user", "今天好累")],
    )

    messages = build_messages(1, "今天好累")

    assert [m for m in messages if m["role"] == "user"] == [
        {"role": "user", "content": "今天好累"}
    ]


def test_build_messages_appends_user_when_not_yet_saved(monkeypatch):
    monkeypatch.setattr(router_mod, "load_persona", lambda mask: "core")
    monkeypatch.setattr(router_mod, "format_self_memory", lambda: "self")
    monkeypatch.setattr(router_mod, "format_behavior_profile", lambda: "behavior")
    monkeypatch.setattr(router_mod, "format_recalled_anchors", lambda query: "anchors")
    monkeypatch.setattr(
        router_mod,
        "get_messages",
        lambda session_id, limit=200: [make("assistant", "我在")],
    )

    messages = build_messages(1, "今天好累")

    assert messages[-1] == {"role": "user", "content": "今天好累"}


def test_build_messages_injects_behavior_profile(monkeypatch):
    monkeypatch.setattr(router_mod, "load_persona", lambda mask: "core")
    monkeypatch.setattr(router_mod, "format_self_memory", lambda: "self")
    monkeypatch.setattr(router_mod, "format_behavior_profile", lambda: "behavior")
    monkeypatch.setattr(router_mod, "format_recalled_anchors", lambda query: "anchors")
    monkeypatch.setattr(router_mod, "get_messages", lambda session_id, limit=200: [])

    messages = build_messages(1, "继续聊吧")

    assert "behavior" in messages[0]["content"]


def test_build_messages_strips_storage_fields_and_orphaned_assistant(monkeypatch):
    monkeypatch.setattr(router_mod, "load_persona", lambda mask: "core")
    monkeypatch.setattr(router_mod, "format_self_memory", lambda: "self")
    monkeypatch.setattr(router_mod, "format_behavior_profile", lambda: "behavior")
    monkeypatch.setattr(router_mod, "format_recalled_anchors", lambda query: "anchors")
    monkeypatch.setattr(
        router_mod,
        "get_messages",
        lambda session_id, limit=200: [
            {
                "id": 1,
                "role": "assistant",
                "content": "没有对应提问的旧回复",
                "created_at": "2026-08-07T10:00:00",
            },
            {
                "id": 2,
                "role": "user",
                "content": "我还在吗",
                "created_at": "2026-08-07T10:01:00",
            },
        ],
    )

    messages = build_messages(1, "继续聊吧")

    assert messages[1:] == [
        {"role": "user", "content": "我还在吗"},
        {"role": "user", "content": "继续聊吧"},
    ]
    assert all(set(message) <= {"role", "content"} for message in messages)
