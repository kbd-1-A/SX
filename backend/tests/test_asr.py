"""本地 ASR 音频预处理与模型引用解析测试。"""

import numpy as np
import pytest

from app.services.asr import (
    _resolve_model_ref,
    _waveform,
    transcribe_pcm,
)


def test_waveform_converts_pcm_and_resamples_to_16khz():
    source = (np.sin(np.linspace(0, 8 * np.pi, 48_000)) * 12_000).astype("<i2")

    waveform = _waveform(source.tobytes(), 48_000)

    assert waveform.dtype == np.float32
    assert 15_990 <= waveform.size <= 16_010
    assert float(np.max(np.abs(waveform))) > 0.2


def test_transcribe_skips_too_short_audio_without_loading_model():
    result = transcribe_pcm(b"\x00\x00" * 100, 16_000)

    assert result.text == ""
    assert result.duration_ms < 180


def test_resolve_model_ref_passes_through_hf_model_name():
    # "base" 是 HF 模型名，本地不存在对应路径 → 原样透传给 faster-whisper
    assert _resolve_model_ref("base") == "base"


def test_resolve_model_ref_keeps_existing_local_path(tmp_path):
    model_dir = tmp_path / "faster-whisper-base"
    model_dir.mkdir()

    assert _resolve_model_ref(str(model_dir)) == str(model_dir)


def test_resolve_model_ref_rejects_missing_local_path():
    with pytest.raises(RuntimeError, match="local ASR model path not found"):
        _resolve_model_ref(r"E:\no\such\faster-whisper-base")


def test_resolve_model_ref_rejects_empty():
    with pytest.raises(RuntimeError, match="ASR_MODEL is empty"):
        _resolve_model_ref("   ")
