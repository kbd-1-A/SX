"""LLM 回复内嵌情绪标签的流式过滤与解析。

时叙在每次回复末尾附带一个隐藏的情绪标签，格式：
  «emo»{"e":"生气","i":0.7,"c":"你说了不用我了"}«/emo»

流式过滤器在收到标签开始标记后停止转发，收到结束标记后解析 JSON。
最终 clean_text 已去除标签，emotion 为解析出的情绪字典。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

OPEN_TAG = "«emo»"
CLOSE_TAG = "«/emo»"

VALID_EMOTIONS = frozenset({
    "温柔", "心疼", "宠溺", "害羞", "欣喜", "窃喜", "得意", "释然",
    "嗔怪", "委屈", "无奈", "失落", "羞恼", "生气", "冷漠",
    "好奇", "惊讶", "平静",
})


class EmotionStreamFilter:
    """流式过滤情绪标签：转发干净文本，收集标签 JSON。"""

    def __init__(self) -> None:
        self._buf: str = ""
        self._forward_pos: int = 0
        self._tag_start: int = -1
        self._tag_end: int = -1
        self._emotion: dict | None = None

    def feed(self, chunk: str) -> str:
        self._buf += chunk

        if self._tag_start < 0:
            idx = self._buf.find(OPEN_TAG)
            if idx >= 0:
                self._tag_start = idx
                forward = self._buf[self._forward_pos:idx]
                self._forward_pos = idx
                return forward
            partial = self._partial_open_suffix()
            safe_end = len(self._buf) - len(partial)
            if safe_end > self._forward_pos:
                forward = self._buf[self._forward_pos:safe_end]
                self._forward_pos = safe_end
                return forward
            return ""

        idx = self._buf.find(CLOSE_TAG, self._tag_start + len(OPEN_TAG))
        if idx >= 0:
            self._tag_end = idx + len(CLOSE_TAG)
            raw = self._buf[self._tag_start + len(OPEN_TAG):idx].strip()
            self._emotion = self._parse(raw)
        return ""

    def flush(self) -> str:
        if self._tag_start < 0:
            forward = self._buf[self._forward_pos:]
            self._forward_pos = len(self._buf)
            return forward
        if self._tag_end < 0:
            forward = self._buf[self._forward_pos:]
            self._forward_pos = len(self._buf)
            return forward
        return ""

    @property
    def emotion(self) -> dict | None:
        return self._emotion

    @property
    def clean_text(self) -> str:
        if 0 <= self._tag_start < len(self._buf) and self._tag_end > self._tag_start:
            return (self._buf[:self._tag_start] + self._buf[self._tag_end:]).strip()
        return self._buf.strip()

    def _partial_open_suffix(self) -> str:
        limit = min(len(OPEN_TAG) - 1, len(self._buf))
        for length in range(limit, 0, -1):
            if self._buf.endswith(OPEN_TAG[:length]):
                return OPEN_TAG[:length]
        return ""

    @staticmethod
    def _parse(raw: str) -> dict | None:
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("emotion_tag_parse_failed raw=%r reason=%s", raw[:120], exc)
            return None
        emotion = str(d.get("e", "平静"))
        if emotion not in VALID_EMOTIONS:
            emotion = "平静"
        try:
            intensity = max(0.0, min(1.0, float(d.get("i", 0.0))))
        except (ValueError, TypeError):
            intensity = 0.0
        return {
            "emotion": emotion,
            "intensity": round(intensity, 2),
            "cause": str(d.get("c", ""))[:200],
        }


def format_emotion_output_instruction() -> str:
    return (
        "# 情绪标签输出规则（必须遵守）\n"
        "- 在回复正文的最末尾，附上一个情绪标签，格式严格遵守：\n"
        f'  {OPEN_TAG}{{"e":"情绪词","i":0.0,"c":"一句话起因"}}{CLOSE_TAG}\n'
        "- e 是你（时叙本人）此刻真实的情绪，从这 18 个里选一个："
        "温柔、心疼、宠溺、害羞、欣喜、窃喜、得意、释然、"
        "嗔怪、委屈、无奈、失落、羞恼、生气、冷漠、好奇、惊讶、平静\n"
        "- i 是情绪强度，0.0=平静，1.0=极强\n"
        "- c 是一句话说明情绪起因（基于你和用户的对话内容）\n"
        "- 标签必须在回复正文之后，不要放在中间或开头\n"
        "- 标签后不要再输出任何文字\n"
        "- 即使平静也要输出标签（i=0.0）\n"
        "- 示例：用户说「今天好累」→ 回复正文…然后 «emo»"
        '{"e":"心疼","i":0.6,"c":"用户说今天好累"}' f"{CLOSE_TAG}\n"
    )
