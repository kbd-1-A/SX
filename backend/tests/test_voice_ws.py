"""实时语音基础协议测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.voice as voice_mod
from app.services.asr import AsrResult


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(voice_mod.router)
    return app


def test_voice_ws_accepts_monotonic_audio_and_completes_turn(monkeypatch):
    monkeypatch.setattr(
        voice_mod,
        "transcribe_pcm",
        lambda _audio, _rate: AsrResult("你好时叙", "zh", 0.91, 320),
    )
    with TestClient(make_app()).websocket_connect("/ws/voice") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "session.ready"
        assert ready["protocol_version"] == 1
        assert ready["state"] == "idle"

        ws.send_json(
            {
                "type": "audio.start",
                "turn_id": "turn_1",
                "sample_rate": 48000,
                "channels": 1,
                "format": "pcm_s16le",
            }
        )
        assert ws.receive_json() == {
            "type": "agent.state",
            "turn_id": "turn_1",
            "state": "listening",
            "emotion": "neutral",
        }

        ws.send_json(
            {
                "type": "audio.chunk",
                "turn_id": "turn_1",
                "seq": 0,
                "pcm_s16le_base64": "AAA=",
            }
        )
        assert ws.receive_json() == {"type": "audio.ack", "turn_id": "turn_1", "seq": 0}

        ws.send_json({"type": "audio.end", "turn_id": "turn_1", "reason": "vad_end"})
        assert ws.receive_json()["state"] == "thinking"
        assert ws.receive_json() == {
            "type": "asr.final",
            "turn_id": "turn_1",
            "text": "你好时叙",
            "language": "zh",
            "confidence": 0.91,
            "duration_ms": 320,
        }
        done = ws.receive_json()
        assert done == {
            "type": "turn.done",
            "turn_id": "turn_1",
            "reason": "vad_end",
            "received_chunks": 1,
        }
        assert ws.receive_json()["state"] == "idle"

        # ASR 期间已进入网络队列的尾帧应被静默丢弃，不能污染下一条响应。
        ws.send_json(
            {
                "type": "audio.chunk",
                "turn_id": "turn_1",
                "seq": 1,
                "pcm_s16le_base64": "AAA=",
            }
        )
        ws.send_json({"type": "session.configure", "sources": {"time_context": True}})
        assert ws.receive_json()["type"] == "session.configured"


def test_voice_ws_rejects_non_monotonic_sequence():
    with TestClient(make_app()).websocket_connect("/ws/voice") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "audio.start",
                "turn_id": "turn_1",
                "sample_rate": 16000,
                "channels": 1,
            }
        )
        ws.receive_json()
        chunk = {
            "type": "audio.chunk",
            "turn_id": "turn_1",
            "seq": 0,
            "pcm_s16le_base64": "AAA=",
        }
        ws.send_json(chunk)
        ws.receive_json()
        ws.send_json(chunk)
        error = ws.receive_json()

    assert error["type"] == "turn.error"
    assert error["code"] == "invalid_seq"
    assert error["turn_id"] == "turn_1"


def test_voice_ws_interrupts_active_turn():
    with TestClient(make_app()).websocket_connect("/ws/voice") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "audio.start",
                "turn_id": "turn_interrupt",
                "sample_rate": 16000,
                "channels": 1,
            }
        )
        ws.receive_json()
        ws.send_json(
            {"type": "turn.interrupt", "turn_id": "turn_interrupt", "played_ms": 0}
        )
        done = ws.receive_json()
        state = ws.receive_json()

    assert done["type"] == "turn.done"
    assert done["reason"] == "interrupted"
    assert state["state"] == "idle"


def test_voice_ws_configures_supported_sources_only():
    with TestClient(make_app()).websocket_connect("/ws/voice") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "session.configure",
                "sources": {
                    "conversation_memory": False,
                    "app_activity": True,
                    "unknown_source": True,
                },
            }
        )
        configured = ws.receive_json()

    assert configured["type"] == "session.configured"
    assert configured["sources"]["conversation_memory"] is False
    assert configured["sources"]["app_activity"] is True
    assert "unknown_source" not in configured["sources"]
