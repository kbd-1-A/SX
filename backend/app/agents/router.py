"""对话路由：面具切换（规则 + LLM 兜底）→ 人格 + 历史注入 DeepSeek。

防幻觉（自第十人迁移）：用户的记忆/上下文必须从数据库读，
构造 prompt 时以数据库历史为准，禁止模型凭训练数据编造。
"""

import asyncio
import logging

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.agents.errors import (
    AgentConfigurationError,
    AgentEmptyResponseError,
    AgentProviderError,
    AgentTimeoutError,
)
from app.agents.mask import DEFAULT_MASK, MASKS, detect_mask_by_keywords
from app.agents.persona import load_persona
from app.agents.reply_mode import format_reply_mode
from app.agents.tone_guard import format_tone_rules
from app.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_RETRIES,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT_SECONDS,
    MASK_CLASSIFY_TIMEOUT_SECONDS,
)
from app.memory.anchors import format_recalled_anchors
from app.memory.behavior import format_behavior_profile
from app.memory.self import format_self_memory
from app.memory.store import get_messages

# 对话历史注入上限（token，近似估算）。从最新往前累计，超出即丢最旧。
MAX_HISTORY_TOKENS = 5000

_client: AsyncOpenAI | None = None
logger = logging.getLogger(__name__)


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=DEEPSEEK_TIMEOUT_SECONDS,
            max_retries=DEEPSEEK_MAX_RETRIES,
        )
    return _client


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数，不引入 tiktoken（避免下载编码文件的网络问题）。

    规则：中日韩/全角宽字符按 1 token/字，ASCII 按 4 字符/token。
    只是近似——DeepSeek 自己的 tokenizer 才精确，这里用于截断量级判断。
    """
    wide = sum(1 for ch in text if ord(ch) >= 0x2E80)
    narrow = len(text) - wide
    return wide + narrow // 4


def truncate_history(history: list[dict], max_tokens: int) -> list[dict]:
    """按 token 上限截断历史，返回时间升序（最旧在前）。

    从最新的一条往前累计，一旦累计超过 max_tokens 就停止，
    更旧的丢弃；至少保留最新一条，即使它自身超限。
    """
    budget = max_tokens
    kept: list[dict] = []
    for m in reversed(history):
        tokens = estimate_tokens(m["content"])
        # 最新一条无条件保留；之后超预算就停，累计不超过 max_tokens
        if kept and budget - tokens < 0:
            break
        budget -= tokens
        kept.append(m)
    return list(reversed(kept))


async def llm_classify(text: str) -> str:
    """LLM 兜底：判断场景。任何失败回退默认面具，不影响主对话。"""
    if not DEEPSEEK_API_KEY:
        return DEFAULT_MASK
    try:
        async with asyncio.timeout(MASK_CLASSIFY_TIMEOUT_SECONDS):
            resp = await get_client().chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "判断用户这句话属于哪个场景，只回一个词：\n"
                            "love_guide=聊感情/亲密关系\n"
                            "old_bestie=吐槽/发泄/抱怨\n"
                            "work_advisor=工作/职场/技术\n"
                            "daily_companion=日常闲聊\n"
                            "拿不准回 daily_companion。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                max_tokens=8,
                temperature=0,
            )
        label = (resp.choices[0].message.content or "").strip().lower()
        return label if label in MASKS else DEFAULT_MASK
    except (asyncio.TimeoutError, APIError, OSError) as exc:
        logger.info("mask_classification_fallback reason=%s", type(exc).__name__)
        return DEFAULT_MASK


async def choose_mask(user_msg: str) -> str:
    """规则优先；规则判定不了（模糊/弱信号）→ LLM 兜底。"""
    decided = detect_mask_by_keywords(user_msg)
    if decided:
        return decided
    return await llm_classify(user_msg)


def build_messages(
    session_id: int,
    user_msg: str,
    mask: str = DEFAULT_MASK,
    reply_mode: str = "catch_up",
) -> list[dict]:
    system = "\n\n".join(
        [
            load_persona(mask),
            format_reply_mode(reply_mode),
            format_tone_rules(reply_mode),
            "# 关于我们\n" + format_self_memory(),
            format_behavior_profile(),
            "# 相关记忆\n" + format_recalled_anchors(user_msg),
        ]
    )
    messages: list[dict] = [{"role": "system", "content": system}]
    history = _normalize_history(get_messages(session_id, limit=200))
    history = truncate_history(history, MAX_HISTORY_TOKENS)
    history = _drop_orphaned_assistant_prefix(history)
    messages.extend(history)
    # chat.py 会先把当前用户消息落库。若历史最后一条已经是当前消息，
    # 不再 append 一次，避免模型听见同一句两遍。
    if not (
        history
        and history[-1].get("role") == "user"
        and history[-1].get("content") == user_msg
    ):
        messages.append({"role": "user", "content": user_msg})
    return messages


def _normalize_history(history: list[dict]) -> list[dict]:
    """只向模型发送合法 role/content，移除数据库字段和空消息。"""
    normalized: list[dict] = []
    for message in history:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            normalized.append({"role": role, "content": content})
    return normalized


def _drop_orphaned_assistant_prefix(history: list[dict]) -> list[dict]:
    """避免 token 截断后让模型先看到一段没有提问来源的 assistant 回复。"""
    start = 0
    while start < len(history) and history[start]["role"] == "assistant":
        start += 1
    return history[start:]


async def stream_reply(
    session_id: int,
    user_msg: str,
    mask: str = DEFAULT_MASK,
    reply_mode: str = "catch_up",
):
    """异步生成回复文本，逐块 yield。"""
    if not DEEPSEEK_API_KEY:
        raise AgentConfigurationError()

    yielded = False
    try:
        stream = await get_client().chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=build_messages(
                session_id,
                user_msg,
                mask=mask,
                reply_mode=reply_mode,
            ),
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yielded = True
                yield delta.content
    except AgentConfigurationError:
        raise
    except (asyncio.TimeoutError, APITimeoutError) as exc:
        raise AgentTimeoutError(type(exc).__name__) from exc
    except (APIConnectionError, RateLimitError, APIError, OSError) as exc:
        logger.warning("agent_provider_error reason=%s", type(exc).__name__)
        raise AgentProviderError(type(exc).__name__) from exc
    except Exception as exc:
        logger.exception("agent_stream_unexpected_error reason=%s", type(exc).__name__)
        raise AgentProviderError(type(exc).__name__) from exc

    if not yielded:
        raise AgentEmptyResponseError()
