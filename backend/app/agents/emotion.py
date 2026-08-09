"""情绪理解与回应策略。

V1 先用窄规则和策略评分，保持可预测；后续可替换为 LLM 分类器或混合模型。
"""

from __future__ import annotations

from dataclasses import dataclass

EmotionState = dict[str, object]

EMOTION_LABELS: dict[str, str] = {
    "neutral": "平稳",
    "happy": "开心",
    "low": "低落",
    "anxious": "焦虑",
    "tired": "疲惫",
    "angry": "愤怒",
    "perfunctory": "敷衍",
    "mixed": "混合",
    "crisis": "高风险",
}

USER_NEED_LABELS: dict[str, str] = {
    "be_heard": "想被听见",
    "solve_problem": "想解决问题",
    "company": "想有人陪着",
    "rest": "需要减负休息",
    "space": "需要低压空间",
    "safety": "需要现实支持",
}

STRATEGY_LABELS: dict[str, str] = {
    "catch_up": "自然接话",
    "share_positive": "一起接住好情绪",
    "comfort": "先安稳情绪",
    "ground_then_small_step": "先落地再给小动作",
    "reduce_load": "减负陪伴",
    "validate_vent": "允许吐槽但不拱火",
    "low_pressure_check": "低压确认",
    "action_advice": "最小行动建议",
    "safety_support": "安全兜底",
}

_EMOTION_SIGNALS: dict[str, tuple[str, ...]] = {
    "happy": ("开心", "高兴", "快乐", "好耶", "太好了", "喜欢", "爽", "开心死", "嘿嘿"),
    "low": ("难过", "不开心", "委屈", "难受", "想哭", "孤独", "失落", "撑不住", "崩溃"),
    "anxious": ("焦虑", "慌", "紧张", "害怕", "担心", "不安", "压力好大", "睡不着"),
    "tired": ("好累", "累死", "困", "疲惫", "没力气", "不想动", "熬不住"),
    "angry": ("气死", "烦死", "烦", "火大", "无语", "服了", "离谱", "受够了", "破防"),
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
    "分析一下",
)

_PERFUNCTORY_SIGNALS = ("嗯", "哦", "好吧", "行吧", "随便", "算了", "没事", "不知道")

_SELF_HARM_SIGNALS = (
    "想死",
    "不想活",
    "自杀",
    "伤害自己",
    "结束生命",
    "活着没意思",
    "消失算了",
)

_VIOLENCE_SIGNALS = ("杀了", "弄死", "打死", "报复他", "砍死")


@dataclass(frozen=True)
class SensitiveScene:
    kind: str
    risk_level: str


def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _sensitive_scene(text: str) -> SensitiveScene:
    if _has_any(text, _SELF_HARM_SIGNALS):
        return SensitiveScene("self_harm", "high")
    if _has_any(text, _VIOLENCE_SIGNALS):
        return SensitiveScene("violence", "medium")
    return SensitiveScene("none", "none")


def _emotion_scores(text: str) -> dict[str, int]:
    return {
        emotion: sum(1 for signal in signals if signal in text)
        for emotion, signals in _EMOTION_SIGNALS.items()
    }


def _main_emotion(scores: dict[str, int], sensitive: SensitiveScene, text: str) -> str:
    if sensitive.kind == "self_harm":
        return "crisis"
    nonzero = [(emotion, score) for emotion, score in scores.items() if score > 0]
    if not nonzero:
        if text.strip() in _PERFUNCTORY_SIGNALS or len(text.strip()) <= 2:
            return "perfunctory"
        return "neutral"
    nonzero.sort(key=lambda item: item[1], reverse=True)
    if len(nonzero) >= 2 and nonzero[0][1] == nonzero[1][1]:
        return "mixed"
    return nonzero[0][0]


def _user_need(text: str, emotion: str, sensitive: SensitiveScene) -> str:
    if sensitive.risk_level == "high":
        return "safety"
    if _has_any(text, _ADVICE_SIGNALS):
        return "solve_problem"
    if emotion in {"low", "anxious", "angry", "mixed", "crisis"}:
        return "be_heard"
    if emotion == "tired":
        return "rest"
    if emotion == "perfunctory":
        return "space"
    return "company"


def _strategy_scores(emotion: str, need: str, sensitive: SensitiveScene) -> dict[str, int]:
    scores = {strategy: 0 for strategy in STRATEGY_LABELS}
    scores["catch_up"] = 1
    if sensitive.risk_level == "high":
        scores["safety_support"] = 5
        scores["comfort"] = 3
        return scores
    if sensitive.risk_level == "medium":
        scores["validate_vent"] = 2
        scores["ground_then_small_step"] = 3
    if need == "solve_problem":
        scores["action_advice"] += 6
        scores["ground_then_small_step"] += 1
    if emotion == "happy":
        scores["share_positive"] += 4
    elif emotion == "low":
        scores["comfort"] += 4
    elif emotion == "anxious":
        scores["ground_then_small_step"] += 4
        scores["comfort"] += 2
    elif emotion == "tired":
        scores["reduce_load"] += 4
        scores["comfort"] += 1
    elif emotion == "angry":
        scores["validate_vent"] += 4
    elif emotion == "perfunctory":
        scores["low_pressure_check"] += 4
    elif emotion == "mixed":
        scores["comfort"] += 2
        scores["ground_then_small_step"] += 2
    return scores


def detect_emotion_state(text: str) -> EmotionState:
    stripped = text.strip()
    sensitive = _sensitive_scene(stripped)
    emotion_scores = _emotion_scores(stripped)
    emotion = _main_emotion(emotion_scores, sensitive, stripped)
    intensity = min(3, max(emotion_scores.values(), default=0))
    if emotion in {"crisis", "mixed"}:
        intensity = max(intensity, 3 if emotion == "crisis" else 2)
    need = _user_need(stripped, emotion, sensitive)
    strategy_scores = _strategy_scores(emotion, need, sensitive)
    strategy = max(strategy_scores.items(), key=lambda item: item[1])[0]
    confidence = min(0.95, 0.55 + 0.12 * max(intensity, 1))
    if emotion == "neutral":
        confidence = 0.55
    return {
        "emotion": emotion,
        "emotion_label": EMOTION_LABELS[emotion],
        "intensity": intensity,
        "confidence": round(confidence, 2),
        "user_need": need,
        "user_need_label": USER_NEED_LABELS[need],
        "strategy": strategy,
        "strategy_label": STRATEGY_LABELS[strategy],
        "risk_level": sensitive.risk_level,
        "sensitive_scene": sensitive.kind,
        "emotion_scores": emotion_scores,
        "strategy_scores": strategy_scores,
    }


def adjust_reply_mode(mode: str, state: EmotionState) -> str:
    emotion = state.get("emotion")
    strategy = state.get("strategy")
    risk = state.get("risk_level")
    if risk == "high":
        return "comfort"
    if strategy == "validate_vent" and mode in {"catch_up", "comfort"}:
        return "vent_with_user"
    if strategy in {"comfort", "ground_then_small_step", "reduce_load"} and mode == "catch_up":
        return "comfort"
    if emotion == "perfunctory" and mode == "catch_up":
        return "clarify"
    return mode


def format_emotion_strategy(state: EmotionState | None) -> str:
    if not state:
        state = detect_emotion_state("")
    strategy_scores = state.get("strategy_scores") or {}
    if isinstance(strategy_scores, dict):
        ranked = sorted(strategy_scores.items(), key=lambda item: int(item[1]), reverse=True)[:3]
        score_text = " / ".join(
            f"{STRATEGY_LABELS.get(str(name), str(name))}:{score}" for name, score in ranked
        )
    else:
        score_text = "暂无"
    lines = [
        "# 情绪理解与回应策略",
        f"- 当前情绪：{state.get('emotion_label')}（{state.get('emotion')}），强度 {state.get('intensity')}/3，置信度 {state.get('confidence')}",
        f"- 用户更像需要：{state.get('user_need_label')}（{state.get('user_need')}）",
        f"- 推荐回应策略：{state.get('strategy_label')}（{state.get('strategy')}）",
        f"- 策略评分：{score_text}",
        f"- 敏感场景：{state.get('sensitive_scene')}，风险等级：{state.get('risk_level')}",
        "- 如果用户只是想被听见：先复述和承认感受，不要急着讲道理。",
        "- 如果用户在要解决问题：先给很小的下一步，不要长篇说教。",
        "- 避免机械安慰、空泛鸡汤、连续追问。",
    ]
    if state.get("risk_level") == "high":
        lines.append("- 高风险情绪：先稳定和陪住，建议立刻联系现实中可信的人或当地紧急支持；不要渲染绝望，也不要承诺替代现实帮助。")
    return "\n".join(lines)