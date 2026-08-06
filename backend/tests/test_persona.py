"""persona 拼装测试：核心永远第一段，面具按需追加。"""

from app.agents.persona import load_mask, load_persona


def test_default_persona_contains_core():
    p = load_persona()
    assert "你是谁" in p
    assert "面具是口吻，不是换人" in p


def test_default_does_not_append_mask():
    assert load_persona() == load_persona("daily_companion")


def test_mask_persona_appends_mask():
    p = load_persona("old_bestie")
    assert "本次对话的面具" in p
    assert "老闺蜜" in p
    # 核心仍然第一段
    assert p.startswith("你是「时叙」")


def test_load_mask_unknown_returns_none():
    assert load_mask("not_exist") is None
    assert load_mask("daily_companion") is None
