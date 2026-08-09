"""本地 ASR 音频预处理测试。"""

import numpy as np

from app.services.asr import _waveform, transcribe_pcm


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
