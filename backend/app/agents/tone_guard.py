"""去 AI 味的轻量规则。

这里不做二次改写，只提供：
1. 可注入 system prompt 的输出约束；
2. 可测试的文本问题扫描，给回归测试用。
"""

from app.agents.reply_mode import MODES

AI_TELLS = (
    "我理解你的感受",
    "我完全理解",
    "作为AI",
    "作为 AI",
    "希望这能帮助你",
    "以下是几点",
    "从某种程度上",
    "总的来说",
    "综上",
    "首先，其次，最后",
)

_CASUAL_MODES = {"catch_up", "vent_with_user", "comfort", "play", "close_loop"}


def format_tone_rules(mode: str) -> str:
    """按对话动作给模型一段短规则。规则短、靠前，遵守率更高。"""
    if mode not in MODES:
        mode = "catch_up"
    rules = [
        "# 输出气质",
        "- 像熟人聊天，不像客服、心理咨询师或任务助手。",
        "- 不要开场复述用户问题，不要泛泛总结。",
        "- 不说无证据的“我记得”；引用记忆必须来自「关于我们」或「相关记忆」。",
        "- 普通聊天最多问一个问题；用户低落时可以不问。",
    ]
    if mode in _CASUAL_MODES:
        rules.extend(
            [
                "- 这一轮尽量短，1-3 句优先。",
                "- 不用标题，不列清单，除非用户明确要方案。",
            ]
        )
    else:
        rules.extend(
            [
                "- 可以有结构，但先给结论。",
                "- 列表只放关键项，不为了整齐而铺开。",
            ]
        )
    return "\n".join(rules)


def scan_ai_tells(text: str, mode: str = "catch_up") -> list[str]:
    """返回命中的 AI 味问题，供测试/回归脚本使用。"""
    issues: list[str] = []
    for tell in AI_TELLS:
        if tell in text:
            issues.append(f"套话：{tell}")
    question_count = text.count("？") + text.count("?")
    if question_count > 1:
        issues.append("问题过多")
    if mode in _CASUAL_MODES:
        if text.lstrip().startswith(("#", "##", "###")):
            issues.append("日常模式不应使用标题")
        if "\n-" in text or "\n1." in text:
            issues.append("日常模式不应使用列表")
        if len(text) > 220:
            issues.append("日常模式过长")
    return issues
