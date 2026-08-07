"""对话动作选择：判断这一轮该怎么接话。

面具解决「像谁说」，reply_mode 解决「这一句该做什么」。
V2 先用窄规则，保持可预测；拿不准就日常接话。
"""

from app.agents.mask import DEFAULT_MASK

MODES = (
    "catch_up",
    "vent_with_user",
    "comfort",
    "advise",
    "work_think",
    "play",
    "clarify",
    "close_loop",
)

MODE_LABELS: dict[str, str] = {
    "catch_up": "日常接话",
    "vent_with_user": "一起吐槽",
    "comfort": "低落陪伴",
    "advise": "给出建议",
    "work_think": "工作参谋",
    "play": "轻松玩梗",
    "clarify": "自然澄清",
    "close_loop": "温和收束",
}

MODE_GUIDANCE: dict[str, str] = {
    "catch_up": "像熟人一样接住这句话。短一点，可以顺着说，也可以轻轻追问一个点。",
    "vent_with_user": "先站在用户这边，允许有一点口语化情绪。不要急着讲道理或列方案。",
    "comfort": "先稳住用户的感受。少分析，少追问，不输出鸡汤；可以给一个很小的当下动作。",
    "advise": "用户在要判断或建议。直接说你的看法，再给最少必要的理由和下一步。",
    "work_think": "进入参谋状态。结构清楚，但不要变成模板化报告；先给结论，再给关键步骤。",
    "play": "轻松接梗，有一点活气。不要解释笑点，不要突然严肃总结。",
    "clarify": "信息不足时只问一个最关键的问题，不要连环追问。",
    "close_loop": "顺着用户收束，留一个稳定、轻的结尾，不强行开启新话题。",
}

_ADVICE_SIGNALS = (
    "怎么办",
    "怎么做",
    "咋办",
    "帮我",
    "给我建议",
    "给个建议",
    "你觉得",
    "要不要",
    "怎么选",
    "方案",
    "计划",
    "分析一下",
)

_WORK_SIGNALS = (
    "代码",
    "bug",
    "项目",
    "需求",
    "排期",
    "上线",
    "测试",
    "后端",
    "前端",
    "接口",
    "数据库",
    "产品",
    "方案",
    "实现",
)

_VENT_SIGNALS = (
    "气死",
    "烦死",
    "吐槽",
    "无语",
    "离谱",
    "服了",
    "麻了",
    "受够了",
    "什么玩意",
    "破防",
)

_COMFORT_SIGNALS = (
    "难过",
    "不开心",
    "委屈",
    "难受",
    "崩溃",
    "撑不住",
    "想哭",
    "焦虑",
    "压力好大",
    "好累",
    "累死",
    "孤独",
)

_PLAY_SIGNALS = ("哈哈", "笑死", "乐死", "绷不住", "好玩", "梗", "整活")

_CLOSE_SIGNALS = ("晚安", "睡了", "先这样", "回头聊", "下次聊", "先不说", "我走了")

_CLARIFY_SIGNALS = ("什么意思", "没懂", "你说呢", "这咋弄", "这个呢")


def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(sig in text for sig in signals)


def detect_reply_mode(text: str, mask: str = DEFAULT_MASK) -> str:
    """用窄规则选择对话动作。

    优先级体现真实聊天：结束 > 玩梗 > 低落 > 吐槽 > 工作/建议 > 澄清 > 日常。
    """
    stripped = text.strip()
    if not stripped:
        return "catch_up"
    if _has_any(stripped, _CLOSE_SIGNALS):
        return "close_loop"
    if _has_any(stripped, _PLAY_SIGNALS):
        return "play"
    if _has_any(stripped, _COMFORT_SIGNALS):
        return "comfort"
    if mask == "old_bestie" or _has_any(stripped, _VENT_SIGNALS):
        return "vent_with_user"
    if mask == "work_advisor" or _has_any(stripped, _WORK_SIGNALS):
        return "work_think"
    if _has_any(stripped, _ADVICE_SIGNALS):
        return "advise"
    if _has_any(stripped, _CLARIFY_SIGNALS):
        return "clarify"
    return "catch_up"


def format_reply_mode(mode: str) -> str:
    """把本轮对话动作格式化为 system prompt 片段。"""
    if mode not in MODES:
        mode = "catch_up"
    return (
        "# 本轮对话动作\n"
        f"- 动作：{MODE_LABELS[mode]}（{mode}）\n"
        f"- 回复目标：{MODE_GUIDANCE[mode]}"
    )
