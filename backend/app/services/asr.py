"""本地 Faster-Whisper 语音转写。"""

from dataclasses import dataclass
from functools import lru_cache
from math import exp
from pathlib import Path
from threading import Lock

import numpy as np
from faster_whisper import WhisperModel

from app.config import ASR_COMPUTE_TYPE, ASR_DEVICE, ASR_LANGUAGE, ASR_MODEL

TARGET_SAMPLE_RATE = 16_000
_transcribe_lock = Lock()


@dataclass(frozen=True)
class AsrResult:
    text: str
    language: str
    confidence: float
    duration_ms: int


def _resolve_model_ref(model_ref: str) -> str:
    """把 ASR_MODEL 解析为 faster-whisper 可接受的模型引用。

    支持两种形态：

    - 本地模型目录（存在时按路径加载，例如 `backend/models/faster-whisper-base`）
    - HF 模型名（不存在对应本地路径时原样透传，例如 `base`/`tiny`，
      由 faster-whisper 配合 `local_files_only=True` 从本地 HF 缓存解析）
    """
    value = model_ref.strip()
    if not value:
        raise RuntimeError("ASR_MODEL is empty")
    path = Path(value)
    if path.exists():
        return str(path)
    looks_like_path = (
        "/" in value
        or "\\" in value
        or value.startswith(".")
        or (len(value) > 2 and value[1] == ":")
    )
    if looks_like_path:
        raise RuntimeError(f"local ASR model path not found: {value}")
    return value


@lru_cache(maxsize=1)
def _model() -> WhisperModel:
    model_ref = _resolve_model_ref(ASR_MODEL)
    return WhisperModel(
        model_ref,
        device=ASR_DEVICE,
        compute_type=ASR_COMPUTE_TYPE,
        local_files_only=True,
    )


def _waveform(pcm_s16le: bytes, sample_rate: int) -> np.ndarray:
    if sample_rate < 8_000 or sample_rate > 96_000:
        raise ValueError("unsupported sample rate")
    if len(pcm_s16le) < 2:
        return np.empty(0, dtype=np.float32)

    audio = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
    if sample_rate == TARGET_SAMPLE_RATE or audio.size == 0:
        return audio

    target_size = max(1, round(audio.size * TARGET_SAMPLE_RATE / sample_rate))
    source_positions = np.arange(audio.size, dtype=np.float64) / sample_rate
    target_positions = np.arange(target_size, dtype=np.float64) / TARGET_SAMPLE_RATE
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def transcribe_pcm(pcm_s16le: bytes, sample_rate: int) -> AsrResult:
    audio = _waveform(pcm_s16le, sample_rate)
    duration_ms = round(audio.size / TARGET_SAMPLE_RATE * 1000)
    if duration_ms < 180:
        return AsrResult("", ASR_LANGUAGE, 0.0, duration_ms)

    with _transcribe_lock:
        segments_iter, info = _model().transcribe(
            audio,
            language=ASR_LANGUAGE or None,
            beam_size=5,
            best_of=5,
            temperature=0,
            condition_on_previous_text=False,
            vad_filter=False,
            initial_prompt="以下是用户与名为时叙的陪伴 Agent 之间的普通话简体中文对话。",
            hotwords="时叙 小叙 陪伴 Agent",
        )
        segments = list(segments_iter)

    text = "".join(segment.text for segment in segments).strip()
    probabilities = [exp(segment.avg_logprob) for segment in segments]
    confidence = sum(probabilities) / len(probabilities) if probabilities else 0.0
    return AsrResult(
        text=text,
        language=getattr(info, "language", None) or ASR_LANGUAGE,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        duration_ms=duration_ms,
    )
