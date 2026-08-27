"""DashScope 云语音合成（Qwen-TTS 指令控制）。

非流式：POST 文本+指令 → 返回音频 URL → 下载为 WAV bytes。
指令控制（instructions）与 emotion_map.yaml 的 cosyvoice_instruct 对接，
由上层（api/tts.py）传入自然的语气指令，例如「用温柔轻声的语气说」。
"""

from __future__ import annotations

import json
import logging
import urllib.request

from app.config import (
    TTS_API_KEY,
    TTS_BASE_URL,
    TTS_MODEL,
    TTS_TIMEOUT_SECONDS,
    TTS_VOICE,
)

logger = logging.getLogger(__name__)


class TtsError(RuntimeError):
    pass


def _post(payload: dict) -> bytes:
    req = urllib.request.Request(
        TTS_BASE_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TTS_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise TtsError(f"TTS 合成请求失败（{e.code}）：{detail[:300]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TtsError(f"TTS 合成超时或网络错误：{e}") from e


def _extract_url(response_body: bytes) -> str:
    try:
        data = json.loads(response_body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise TtsError("TTS 响应不是有效 JSON") from e

    if data.get("code") and data.get("message"):
        raise TtsError(f"TTS 接口报错：{data.get('message')}")

    audio = (data.get("output") or {}).get("audio") or {}
    url = audio.get("url")
    if not url:
        raise TtsError(f"TTS 响应缺少音频 URL：{json.dumps(data, ensure_ascii=False)[:300]}")
    return url


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        raise TtsError(f"TTS 音频下载失败：{e}") from e


def synthesize(text: str, instruct: str = "", voice: str | None = None) -> bytes:
    """合成一段文本为 WAV bytes。

    instruct 为空则不带指令（用默认语气）。
    voice 为空则用配置里的默认音色 TTS_VOICE。
    """
    if not TTS_API_KEY:
        raise TtsError("TTS_API_KEY 未配置（可留空复用 DEEPSEEK_API_KEY）")
    text = (text or "").strip()
    if not text:
        raise TtsError("合成文本为空")

    source = {
        "text": text,
        "voice": voice or TTS_VOICE,
        "language_type": "Chinese",
    }
    if instruct:
        source["instructions"] = instruct

    body = _post({"model": TTS_MODEL, "input": source})
    url = _extract_url(body)
    return _download(url)


def synthesize_with_emotion(
    text: str,
    emotion: str,
    instruct_override: str | None = None,
    voice: str | None = None,
) -> bytes:
    """按情绪合成：instruct 来自 emotion_map 的 cosyvoice_instruct。

    从 inner_world 取 instruct，处理情绪→语气映射，保持与 persona 注入一致。
    """
    from app.memory.inner_world import get_instruct

    instruct = instruct_override if instruct_override is not None else get_instruct(emotion)
    return synthesize(text, instruct=instruct, voice=voice)