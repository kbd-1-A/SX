"""面具选择：话题词表（纯函数，可单测）。

返回三态：
  - 面具名：词表高置信命中唯一场景 → 直接用
  - DEFAULT_MASK：完全无信号 → 直接默认，不浪费一次 LLM 调用
  - None：模糊（多场景命中）或有情绪但无场景 → 走 LLM 兜底

词表刻意「窄而准」：只放高置信信号词。拿不准宁可默认，不要切错。
"""

DEFAULT_MASK = "daily_companion"

MASKS = ("daily_companion", "old_bestie", "love_guide", "work_advisor")

# 高置信场景词表（命中即强信号）
SCENE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "love_guide": (
        "男朋友", "女朋友", "对象", "分手", "复合", "结婚", "离婚",
        "相亲", "暧昧", "心动", "表白", "失恋", "出轨", "劈腿",
        "前男友", "前女友", "异地恋", "恋爱", "感情", "婚姻", "喜欢的人",
    ),
    "old_bestie": (
        "气死", "烦死", "无语", "吐槽", "太离谱", "离谱", "服了",
        "什么玩意", "什么鬼", "绝了", "麻了", "破防", "受够了",
    ),
    "work_advisor": (
        "加班", "面试", "跳槽", "需求", "排期", "代码", "bug", "技术",
        "方案", "升职", "涨薪", "裁员", "绩效", "hc", "kpi", "产品",
        "迭代", "上线", "架构", "工作", "项目",
    ),
}

# 弱情绪信号：有情绪但定不了场景 → 触发 LLM 兜底
EMOTION_SIGNALS = (
    "烦", "累", "难过", "不开心", "焦虑", "压力", "委屈", "生气",
    "郁闷", "难受", "崩溃", "糟心", "心情",
)


def has_emotion_signal(text: str) -> bool:
    return any(sig in text for sig in EMOTION_SIGNALS)


def detect_mask_by_keywords(text: str) -> str | None:
    """规则判定：唯一命中返回面具；无信号返回默认；模糊/弱信号返回 None（走 LLM）。"""
    hits = [
        scene for scene, kws in SCENE_KEYWORDS.items() if any(k in text for k in kws)
    ]
    if len(hits) == 1:
        return hits[0]
    if not hits and not has_emotion_signal(text):
        return DEFAULT_MASK
    return None
