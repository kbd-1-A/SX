"""对话路由：面具切换（规则 + LLM 兜底）→ 人格 + 历史注入 DeepSeek。

防幻觉（自第十人迁移）：用户的记忆/上下文必须从数据库读，
构造 prompt 时以数据库历史为准，禁止模型凭训练数据编造。
"""

from openai import AsyncOpenAI

from app.agents.mask import DEFAULT_MASK, MASKS, detect_mask_by_keywords
from app.agents.persona import load_persona
from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.memory.self import format_self_memory
from app.memory.store import get_messages

# 对话历史注入上限（token，近似估算）。从最新往前累计，超出即丢最旧。
MAX_HISTORY_TOKENS = 5000

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
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
    except Exception:
        return DEFAULT_MASK


async def choose_mask(user_msg: str) -> str:
    """规则优先；规则判定不了（模糊/弱信号）→ LLM 兜底。"""
    decided = detect_mask_by_keywords(user_msg)
    if decided:
        return decided
    return await llm_classify(user_msg)


def build_messages(
    session_id: int, user_msg: str, mask: str = DEFAULT_MASK
) -> list[dict]:
    system = load_persona(mask) + "\n\n# 关于我们\n" + format_self_memory()
    messages: list[dict] = [{"role": "system", "content": system}]
    history = truncate_history(get_messages(session_id, limit=200), MAX_HISTORY_TOKENS)
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    return messages


async def stream_reply(
    session_id: int, user_msg: str, mask: str = DEFAULT_MASK
):
    """异步生成回复文本，逐块 yield。"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 里填写")
    stream = await get_client().chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=build_messages(session_id, user_msg, mask=mask),
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
