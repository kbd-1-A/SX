"""即时反应层：在 LLM 流式回复前，先吐一个情绪语气词。

基于时叙当前情绪（inner_world），从 emotion_map 的 quick_react 池中
随机取一个词，立刻推给前端。用户看到的是一个「先反应、再说话」的节奏，
而不是干等 LLM 出第一个 chunk。

用法（chat.py 主链路）：
    word = pick_quick_react()
    if word:
        await ws.send_text(json.dumps({"type": "quick_react", "content": word}))

前端收到 quick_react 后可以：
- 在字幕区先闪一下这个词
- 或在聊天气泡里先显示一个小气泡
- 等 chunk 开始流式到达后，quick_react 消融、正文接管
"""

from __future__ import annotations

import random

from app.memory import inner_world


def pick_quick_react(emotion: str | None = None) -> str | None:
    """根据当前情绪取一个即时反应词。情绪为空或平静时返回 None。"""
    if emotion is None:
        state = inner_world.get_current()
        emotion = state.emotion
        if state.intensity <= 0 or emotion == "平静":
            return None
    pool = inner_world.get_quick_react(emotion)
    if not pool:
        return None
    return random.choice(pool)
