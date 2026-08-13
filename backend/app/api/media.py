"""本地媒体流：只允许从音乐 Provider 解析出的 track id 读取文件。"""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.tools.music import (
    get_local_music_capability,
    get_local_music_path,
    get_media_type,
    MusicToolError,
)

router = APIRouter()


@router.get("/api/media/capabilities")
def media_capabilities() -> dict[str, object]:
    return {"providers": [get_local_music_capability().as_event()]}


@router.get("/api/media/local/{track_id}")
def local_media(track_id: str):
    try:
        path = get_local_music_path(track_id)
    except MusicToolError as exc:
        # 不向客户端暴露目录结构。
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=exc.message) from exc
    return FileResponse(path, media_type=get_media_type(path))
