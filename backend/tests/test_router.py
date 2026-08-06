"""token 截断纯函数测试。

测 router.py 里的 estimate_tokens / truncate_history，不碰 DB 与 persona。
"""

from app.agents.router import estimate_tokens, truncate_history


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
