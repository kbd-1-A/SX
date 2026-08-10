"""假执行防线：没有工具结果时不得把外部动作说成已完成。"""

import pytest

from app.agents.action_guard import (
    detect_action_request,
    format_action_capability_rules,
    guard_action_reply,
    has_unverified_completion_claim,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("帮我创建一个 md 文件放在桌面", "file"),
        ("放在桌面就行", "file"),
        ("我今天很难受，帮我放一首歌", "media"),
        ("请帮我打开汽水音乐", "external"),
        ("今天好累", None),
    ],
)
def test_detect_action_request(message, expected):
    assert detect_action_request(message) == expected


@pytest.mark.parametrize(
    "reply",
    [
        "好，写好了，文件在桌面。",
        "我已经帮你创建了 Markdown 文件。",
        "我已经把文件放到桌面了。",
        "正在播放一首舒缓的歌。",
        "歌已经放好了。",
    ],
)
def test_detects_unverified_completion_claims(reply):
    assert has_unverified_completion_claim(reply) is True


def test_file_claim_is_replaced_with_current_capability_boundary():
    reply, blocked = guard_action_reply("好，写好了，文件在桌面。", "file")

    assert blocked is True
    assert "还不能直接" in reply
    assert "桌面" in reply
    assert "写好了" not in reply


def test_media_claim_is_replaced_with_current_capability_boundary():
    reply, blocked = guard_action_reply("我已经开始播放了。", "media")

    assert blocked is True
    assert "不能直接控制音乐软件" in reply


def test_user_fact_is_not_treated_as_assistant_completion_claim():
    reply, blocked = guard_action_reply("你昨天已经创建过这个文件了。", "file")

    assert blocked is False
    assert reply == "你昨天已经创建过这个文件了。"


def test_capability_rules_explicitly_forbid_fake_execution():
    rules = format_action_capability_rules()

    assert "支持在用户明确要求时创建新的 .md 文件" in rules
    assert "没有系统返回的成功结果" in rules
