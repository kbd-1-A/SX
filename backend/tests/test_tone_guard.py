"""AI 味扫描测试。"""

from app.agents.tone_guard import format_tone_rules, scan_ai_tells


def test_scan_ai_tells_detects_stock_phrase():
    issues = scan_ai_tells("我理解你的感受，希望这能帮助你。")
    assert "套话：我理解你的感受" in issues
    assert "套话：希望这能帮助你" in issues


def test_scan_ai_tells_catches_casual_list():
    issues = scan_ai_tells("可以。\n- 第一条\n- 第二条", mode="catch_up")
    assert "日常模式不应使用列表" in issues


def test_scan_ai_tells_allows_work_list():
    issues = scan_ai_tells("结论：先做测试。\n- 修后端\n- 跑验证", mode="work_think")
    assert "日常模式不应使用列表" not in issues


def test_format_tone_rules_casual_shortness():
    assert "1-3 句" in format_tone_rules("comfort")


def test_format_tone_rules_work_structure():
    assert "先给结论" in format_tone_rules("work_think")
