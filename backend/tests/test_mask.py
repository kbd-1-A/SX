"""面具选择器纯函数测试。"""

from app.agents.mask import detect_mask_by_keywords


def test_love_guide_single_hit():
    assert detect_mask_by_keywords("我不知道要不要分手") == "love_guide"


def test_work_advisor_single_hit():
    assert detect_mask_by_keywords("今天加班到十点") == "work_advisor"


def test_old_bestie_single_hit():
    assert detect_mask_by_keywords("这系统写的什么玩意") == "old_bestie"


def test_no_signal_returns_default():
    # 完全无信号 → 默认面具，不浪费一次 LLM 调用
    assert detect_mask_by_keywords("今天天气不错") == "daily_companion"


def test_weak_emotion_signal_returns_none():
    # 有情绪但定不了场景 → None，走 LLM 兜底
    assert detect_mask_by_keywords("好烦") is None


def test_multi_scene_returns_none():
    # 工作+感情双命中 → 模糊 → None，走 LLM 兜底
    assert detect_mask_by_keywords("加班烦死了，对象也不理我") is None
