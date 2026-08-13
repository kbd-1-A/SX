"""受控的本地音乐 Provider。

第一版只读取用户明确配置的音乐目录，并通过不可猜测的 track id 暴露音频。
模型和前端都不会获得本机绝对路径；是否真的开始播放由浏览器回传状态确认。
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import MUSIC_LIBRARY_DIR, MUSIC_MAX_TRACKS

LOCAL_PROVIDER_ID = "local_library"
MAX_LOCAL_MUSIC_TRACKS = MUSIC_MAX_TRACKS
_MIME_BY_SUFFIX = {
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}
_SUPPORTED_SUFFIXES = frozenset(_MIME_BY_SUFFIX)


class MusicToolError(Exception):
    """可安全展示给用户的媒体工具错误。"""

    def __init__(self, message: str, code: str = "music_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class MusicCapability:
    provider_id: str
    status: str
    track_count: int
    message: str | None = None

    def as_event(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "track_count": self.track_count,
            **({"message": self.message} if self.message else {}),
        }


@dataclass(frozen=True)
class LocalMusicTrack:
    id: str
    title: str
    artist: str
    mime_type: str
    _path: Path | None = None

    def as_event(self, playback_id: str) -> dict[str, str]:
        return {
            "playback_id": playback_id,
            "track_id": self.id,
            "title": self.title,
            "artist": self.artist,
            "provider_id": LOCAL_PROVIDER_ID,
            "mime_type": self.mime_type,
            "stream_url": f"/api/media/local/{self.id}",
        }


def get_local_music_capability() -> MusicCapability:
    root = _library_root()
    if root is None:
        return MusicCapability(
            LOCAL_PROVIDER_ID,
            "unavailable",
            0,
            "尚未配置用户授权的本地音乐目录。",
        )
    count = sum(1 for _ in _iter_tracks(root))
    return MusicCapability(LOCAL_PROVIDER_ID, "available", count)


def search_local_music(query: str | None, *, limit: int = 8) -> list[LocalMusicTrack]:
    root = _library_root()
    if root is None:
        raise MusicToolError(
            "还没有配置可用的本地音乐目录。请在设置中授权一个音乐文件夹。",
            "music_library_unavailable",
        )
    normalized = (query or "").strip().casefold()
    tracks = list(_iter_tracks(root))
    if normalized:
        filtered = [
            track
            for track in tracks
            if normalized in track.title.casefold()
            or normalized in track.artist.casefold()
            or normalized in f"{track.artist} - {track.title}".casefold()
        ]
        tracks = filtered
    return tracks[: max(1, min(limit, MAX_LOCAL_MUSIC_TRACKS))]


def select_local_music_track(query: str | None = None) -> LocalMusicTrack:
    tracks = search_local_music(query, limit=1)
    if not tracks:
        raise MusicToolError(
            "授权的本地音乐目录里没有找到合适的歌曲。",
            "track_not_found",
        )
    return tracks[0]


def resolve_local_music_track(track_id: str) -> LocalMusicTrack:
    if not isinstance(track_id, str) or not track_id:
        raise MusicToolError("歌曲标识无效。", "track_not_found")
    root = _library_root()
    if root is None:
        raise MusicToolError("本地音乐目录当前不可用。", "music_library_unavailable")
    for track in _iter_tracks(root):
        if track.id == track_id:
            return track
    raise MusicToolError("这首歌曲已经不可用。", "track_not_found")


def get_local_music_path(track_id: str) -> Path:
    track = resolve_local_music_track(track_id)
    if track._path is None:
        raise MusicToolError("歌曲文件无法读取。", "track_not_found")
    return track._path


def get_media_type(path: Path) -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def parse_music_query(text: str) -> str | None:
    """提取明确的歌名；情绪型“放一首歌”不把整句当搜索词。"""
    stripped = " ".join(text.strip().split())
    for marker in ("播放", "放", "来一首", "来首"):
        if marker not in stripped:
            continue
        tail = stripped.split(marker, 1)[1].strip(" ：:，,。.!！")
        for suffix in ("音乐", "歌曲", "歌", "歌单"):
            if tail.endswith(suffix):
                tail = tail[: -len(suffix)].strip(" ：:，,。.!！")
        if tail and tail not in {"一首", "点", "一首歌"} and len(tail) <= 80:
            return tail
    return None


def _library_root() -> Path | None:
    configured = MUSIC_LIBRARY_DIR
    if configured is None:
        return None
    try:
        root = Path(configured).expanduser().resolve(strict=True)
        return root if root.is_dir() else None
    except (OSError, RuntimeError):
        return None


def _iter_tracks(root: Path):
    count = 0
    try:
        candidates = sorted(root.rglob("*"), key=lambda item: str(item).casefold())
    except OSError:
        return
    for candidate in candidates:
        if count >= MAX_LOCAL_MUSIC_TRACKS or not candidate.is_file():
            continue
        suffix = candidate.suffix.casefold()
        if suffix not in _SUPPORTED_SUFFIXES:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            if resolved.stat().st_size <= 0:
                continue
        except (OSError, RuntimeError, ValueError):
            continue
        yield _track_from_path(root, resolved)
        count += 1


def _track_from_path(root: Path, path: Path) -> LocalMusicTrack:
    relative = path.relative_to(root).as_posix()
    track_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
    stem = path.stem
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
    else:
        artist, title = "本地音乐", stem
    return LocalMusicTrack(
        id=track_id,
        title=title.strip() or "未命名歌曲",
        artist=artist.strip() or "本地音乐",
        mime_type=_MIME_BY_SUFFIX[path.suffix.casefold()],
        _path=path,
    )
