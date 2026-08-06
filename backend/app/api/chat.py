"""WebSocket 对话：收消息 → 选面具 → 流式回。

协议（V1）：
  客户端 →  { "type": "message", "content": "今天好累啊" }
  服务端 →  { "type": "chunk", "content": "听起来" }   ×N
           { "type": "done", "assistant_id": 123, "mask": "love_guide" }
           { "type": "error", "message": "..." }     失败时
"""

import json

from fastapi import APIRouter, WebSocket

from app.agents.mask import DEFAULT_MASK
from app.agents.router import choose_mask, stream_reply
from app.memory.self import add_mask_milestone, add_nickname, extract_nickname
from app.memory.store import add_message, get_or_create_session

router = APIRouter()

# 面具切换冷却：距上次切换不足 2 轮则不切，避免「跳脸」
SWITCH_COOLDOWN = 2


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    session_id = get_or_create_session()
    current_mask: str | None = None  # None = 本会话还没定过面具
    turns_since_switch = 0

    while True:
        try:
            raw = await ws.receive_text()
        except Exception:
            # 客户端断开
            break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "message":
            continue

        content = (data.get("content") or "").strip()
        if not content:
            continue

        add_message(session_id, "user", content)

        # 面具选择 + 冷却锁定（首次直接采用，之后 2 轮内不跳）
        new_mask = await choose_mask(content)
        if current_mask is None:
            current_mask = new_mask
        elif new_mask != current_mask:
            if turns_since_switch < SWITCH_COOLDOWN:
                new_mask = current_mask
            else:
                current_mask = new_mask
                turns_since_switch = 0
        turns_since_switch += 1
        mask = current_mask

        full = []
        try:
            async for chunk in stream_reply(session_id, content, mask=mask):
                full.append(chunk)
                await ws.send_text(
                    json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)
                )
        except Exception as exc:
            await ws.send_text(
                json.dumps(
                    {"type": "error", "message": f"时叙暂时没法回话：{exc}"},
                    ensure_ascii=False,
                )
            )
            continue

        if full:
            assistant_id = add_message(session_id, "assistant", "".join(full))
            # 自我记忆：昵称（规则）+ 场景里程碑（首次出现）
            nick = extract_nickname(content)
            if nick:
                add_nickname(nick)
            add_mask_milestone(mask)
            await ws.send_text(
                json.dumps(
                    {
                        "type": "done",
                        "assistant_id": assistant_id,
                        "mask": mask,
                    },
                    ensure_ascii=False,
                )
            )
