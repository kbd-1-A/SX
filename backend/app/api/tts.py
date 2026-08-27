"""TTS HTTP 端点：把文本合成带情绪语气的语音，返回 WAV bytes。

前端 BackendSpeechOutput 调此端点；情绪默认取自 inner_world 当前状态，
与 persona 注入的「时叙此刻情绪」保持一致。
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import TTS_ENABLED
from app.memory.inner_world import get_current, get_instruct
from app.services.tts import TtsError, synthesize

router = APIRouter()
logger = logging.getLogger(__name__)


class TtsRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    emotion: str | None = None
    instruct: str | None = None
    voice: str | None = None


@router.post("/api/tts")
async def synth(req: TtsRequest) -> Response:
    if not TTS_ENABLED:
        raise HTTPException(status_code=503, detail="语音合成未启用")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="合成文本为空")

    emotion = req.emotion or get_current().emotion
    instruct = req.instruct if req.instruct is not None else get_instruct(emotion)

    try:
        audio = await _run_synth(text, instruct, req.voice)
    except TtsError as e:
        logger.warning("tts_synth_failed emotion=%s reason=%s", emotion, e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Emotion": quote(emotion, safe=""),
            "X-Instruct": quote(instruct, safe=""),
            "Content-Disposition": 'inline; filename="shixu.wav"',
        },
    )


async def _run_synth(text: str, instruct: str, voice: str | None) -> bytes:
    import asyncio

    return await asyncio.to_thread(synthesize, text, instruct=instruct, voice=voice)