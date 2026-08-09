"""实时语音基础协议。

这一阶段只负责会话、音频帧、状态和取消语义，不接 ASR/TTS。
后续语音服务应继续沿用这里的 turn_id、seq 和错误格式。
"""

import asyncio
import base64
import binascii
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.asr import transcribe_pcm

router = APIRouter()
logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MAX_EVENT_CHARS = 256_000
MAX_AUDIO_BYTES = 12 * 1024 * 1024
SUPPORTED_SOURCES = {
    "microphone",
    "conversation_memory",
    "time_context",
    "app_activity",
}


async def _send(ws: WebSocket, event_type: str, **payload) -> None:
    await ws.send_text(
        json.dumps({"type": event_type, **payload}, ensure_ascii=False)
    )


async def _error(
    ws: WebSocket,
    code: str,
    message: str,
    *,
    turn_id: str | None = None,
) -> None:
    payload = {"code": code, "message": message}
    if turn_id:
        payload["turn_id"] = turn_id
    await _send(ws, "turn.error", **payload)


def _turn_id(data: dict) -> str:
    value = data.get("turn_id")
    return value.strip() if isinstance(value, str) else ""


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    session_id = f"voice_{uuid4().hex[:12]}"
    sources = {
        "microphone": True,
        "conversation_memory": True,
        "time_context": True,
        "app_activity": False,
    }
    active_turn_id: str | None = None
    last_seq = -1
    active_sample_rate = 16_000
    audio_buffer = bytearray()
    closed_turn_ids: list[str] = []

    await _send(
        ws,
        "session.ready",
        session_id=session_id,
        protocol_version=PROTOCOL_VERSION,
        state="idle",
        sources=sources,
        asr={"provider": "faster-whisper", "location": "local", "language": "zh"},
    )

    while True:
        try:
            raw = await ws.receive_text()
        except WebSocketDisconnect:
            logger.info(
                "voice_client_disconnected session_id=%s active_turn_id=%s",
                session_id,
                active_turn_id,
            )
            break

        if len(raw) > MAX_EVENT_CHARS:
            await _error(ws, "event_too_large", "语音事件超过大小限制。")
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await _error(ws, "invalid_json", "语音事件不是有效 JSON。")
            continue

        if not isinstance(data, dict):
            await _error(ws, "invalid_event", "语音事件必须是对象。")
            continue

        event_type = data.get("type")

        if event_type == "session.configure":
            requested = data.get("sources")
            if not isinstance(requested, dict):
                await _error(ws, "invalid_sources", "数据来源配置格式不正确。")
                continue
            for name, enabled in requested.items():
                if name in SUPPORTED_SOURCES and isinstance(enabled, bool):
                    sources[name] = enabled
            await _send(ws, "session.configured", sources=sources)
            continue

        if event_type == "audio.start":
            turn_id = _turn_id(data)
            sample_rate = data.get("sample_rate")
            channels = data.get("channels")
            if not turn_id:
                await _error(ws, "missing_turn_id", "audio.start 缺少 turn_id。")
                continue
            if not isinstance(sample_rate, int) or sample_rate < 8_000 or sample_rate > 96_000:
                await _error(ws, "invalid_sample_rate", "音频采样率不受支持。", turn_id=turn_id)
                continue
            if channels != 1:
                await _error(ws, "invalid_channels", "当前只支持单声道音频。", turn_id=turn_id)
                continue
            if active_turn_id and active_turn_id != turn_id:
                await _error(ws, "turn_active", "上一轮语音还没有结束。", turn_id=turn_id)
                continue

            active_turn_id = turn_id
            active_sample_rate = sample_rate
            audio_buffer.clear()
            last_seq = -1
            await _send(
                ws,
                "agent.state",
                turn_id=turn_id,
                state="listening",
                emotion="neutral",
            )
            continue

        if event_type == "audio.chunk":
            turn_id = _turn_id(data)
            seq = data.get("seq")
            payload = data.get("pcm_s16le_base64")
            if turn_id in closed_turn_ids:
                continue
            if not active_turn_id or turn_id != active_turn_id:
                await _error(ws, "stale_turn", "音频块不属于当前语音轮次。", turn_id=turn_id or None)
                continue
            if not isinstance(seq, int) or seq <= last_seq:
                await _error(ws, "invalid_seq", "音频块序号必须单调递增。", turn_id=turn_id)
                continue
            if not isinstance(payload, str) or not payload:
                await _error(ws, "missing_audio", "音频块没有有效载荷。", turn_id=turn_id)
                continue
            try:
                decoded = base64.b64decode(payload, validate=True)
            except (binascii.Error, ValueError):
                await _error(ws, "invalid_audio", "音频块不是有效的 PCM 数据。", turn_id=turn_id)
                continue
            if len(audio_buffer) + len(decoded) > MAX_AUDIO_BYTES:
                await _error(ws, "audio_too_long", "单轮语音超过长度限制。", turn_id=turn_id)
                continue
            audio_buffer.extend(decoded)
            last_seq = seq
            if seq == 0 or seq % 10 == 0:
                await _send(ws, "audio.ack", turn_id=turn_id, seq=seq)
            continue

        if event_type == "audio.end":
            turn_id = _turn_id(data)
            if not active_turn_id or turn_id != active_turn_id:
                await _error(ws, "stale_turn", "结束事件不属于当前语音轮次。", turn_id=turn_id or None)
                continue
            await _send(ws, "agent.state", turn_id=turn_id, state="thinking", emotion="neutral")
            try:
                result = await asyncio.to_thread(
                    transcribe_pcm,
                    bytes(audio_buffer),
                    active_sample_rate,
                )
            except Exception:
                logger.exception(
                    "voice_asr_failed session_id=%s turn_id=%s audio_bytes=%s",
                    session_id,
                    turn_id,
                    len(audio_buffer),
                )
                await _error(ws, "asr_failed", "本地语音转写失败，请再说一次。", turn_id=turn_id)
            else:
                if result.text:
                    await _send(
                        ws,
                        "asr.final",
                        turn_id=turn_id,
                        text=result.text,
                        language=result.language,
                        confidence=result.confidence,
                        duration_ms=result.duration_ms,
                    )
                else:
                    await _error(ws, "no_speech", "没有识别到有效语音，请检查麦克风输入。", turn_id=turn_id)
            await _send(
                ws,
                "turn.done",
                turn_id=turn_id,
                reason=data.get("reason") or "vad_end",
                received_chunks=last_seq + 1,
            )
            await _send(ws, "agent.state", turn_id=turn_id, state="idle", emotion="neutral")
            closed_turn_ids.append(turn_id)
            del closed_turn_ids[:-8]
            active_turn_id = None
            audio_buffer.clear()
            last_seq = -1
            continue

        if event_type in {"turn.interrupt", "session.cancel"}:
            turn_id = _turn_id(data) or active_turn_id
            if active_turn_id and turn_id != active_turn_id:
                await _error(ws, "stale_turn", "取消事件不属于当前语音轮次。", turn_id=turn_id)
                continue
            if active_turn_id:
                closed_turn_ids.append(active_turn_id)
                del closed_turn_ids[:-8]
                await _send(
                    ws,
                    "turn.done",
                    turn_id=active_turn_id,
                    reason="interrupted" if event_type == "turn.interrupt" else "cancelled",
                    received_chunks=last_seq + 1,
                )
                await _send(
                    ws,
                    "agent.state",
                    turn_id=active_turn_id,
                    state="idle",
                    emotion="neutral",
                )
            active_turn_id = None
            audio_buffer.clear()
            last_seq = -1
            continue

        await _error(ws, "unsupported_event", "暂不支持这个语音事件。")
