"""受控本地音乐库：只公开已授权目录中的可播放文件。"""

from pathlib import Path

import pytest

import app.tools.music as music_mod
from app.tools.music import MusicToolError


def configure_library(monkeypatch, directory: Path) -> None:
    monkeypatch.setattr(music_mod, "MUSIC_LIBRARY_DIR", directory)
    monkeypatch.setattr(music_mod, "MAX_LOCAL_MUSIC_TRACKS", 20)


def test_local_music_library_returns_safe_track_metadata(monkeypatch, tmp_path):
    library = tmp_path / "music"
    library.mkdir()
    (library / "夜晚 - 慢慢来.mp3").write_bytes(b"ID3 test audio")
    (library / "notes.txt").write_text("not media", encoding="utf-8")
    configure_library(monkeypatch, library)

    capability = music_mod.get_local_music_capability()
    tracks = music_mod.search_local_music("慢慢")

    assert capability.status == "available"
    assert capability.track_count == 1
    assert len(tracks) == 1
    assert tracks[0].title == "慢慢来"
    assert tracks[0].artist == "夜晚"
    event = tracks[0].as_event("playback-1")
    assert event["stream_url"].startswith("/api/media/local/")
    assert str(library) not in str(event)
    assert "path" not in event


def test_local_music_rejects_missing_or_unrecognized_track(monkeypatch, tmp_path):
    library = tmp_path / "music"
    library.mkdir()
    (library / "安静.mp3").write_bytes(b"ID3 test audio")
    configure_library(monkeypatch, library)

    with pytest.raises(MusicToolError) as exc_info:
        music_mod.resolve_local_music_track("not-a-track")

    assert exc_info.value.code == "track_not_found"


def test_local_music_requires_an_explicitly_configured_directory(monkeypatch, tmp_path):
    configure_library(monkeypatch, tmp_path / "missing")

    capability = music_mod.get_local_music_capability()

    assert capability.status == "unavailable"
    assert capability.track_count == 0
    with pytest.raises(MusicToolError) as exc_info:
        music_mod.search_local_music(None)
    assert exc_info.value.code == "music_library_unavailable"
