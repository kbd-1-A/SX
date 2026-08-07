"""对话动作选择测试。"""

from app.agents.reply_mode import detect_reply_mode, format_reply_mode


def test_detect_close_loop():
    assert detect_reply_mode("先这样，我睡了") == "close_loop"


def test_detect_play_before_daily():
    assert detect_reply_mode("哈哈哈这个太好玩了") == "play"


def test_detect_comfort():
    assert detect_reply_mode("今天好累，压力好大") == "comfort"


def test_detect_vent():
    assert detect_reply_mode("这甲方也太离谱了") == "vent_with_user"


def test_detect_work_from_mask():
    assert detect_reply_mode("开始执行", mask="work_advisor") == "work_think"


def test_detect_advice():
    assert detect_reply_mode("你觉得我要不要去") == "advise"


def test_detect_default_catch_up():
    assert detect_reply_mode("今天天气还行") == "catch_up"


def test_format_reply_mode_fallback():
    text = format_reply_mode("not_exist")
    assert "日常接话" in text
    assert "catch_up" in text
