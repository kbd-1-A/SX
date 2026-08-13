"""Phase 1 的 Markdown 文件创建工具。

模型不会获得本机路径或任意文件系统权限。调用方只能传递受控的目标枚举、
文件名和内容；本模块负责路径解析、排重、原子写入与最终校验。
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.config import ARTIFACT_OUTPUT_DIR, MAX_MARKDOWN_ARTIFACT_BYTES

FileTarget = Literal["desktop", "output"]

MAX_FILENAME_CHARS = 120
MAX_DUPLICATE_SUFFIX_ATTEMPTS = 1_000
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CREATE_ACTION = re.compile(r"创建|新建|保存|导出|生成", re.IGNORECASE)
_FILE_NOUN = re.compile(r"\.md\b|markdown|md\s*(?:文件|文档)?|文件|文档", re.IGNORECASE)
_NAMED_MARKDOWN = re.compile(
    r"(?P<filename>[\w\u3400-\u9fff()（） _-]{1,120}\.md)\b",
    re.IGNORECASE,
)
_OTHER_EXTENSION = re.compile(r"\.([A-Za-z]{1,8})(?=$|[\s'\"，。；、）】])")
_UNSAFE_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)")
_UNSUPPORTED_DESTINATION = re.compile(
    r"(?:放(?:在|到)|保存(?:到|在)|导出(?:到|至)).{0,80}(?:目录|文件夹|路径|盘)",
    re.IGNORECASE,
)
_CAPABILITY_QUESTION = re.compile(
    r"(?:现在)?(?:可以|能|会|支持).{0,16}(?:创建|新建|保存|导出).{0,16}"
    r"(?:md|markdown|文档|文件).*(?:吗|么|了吗|没有|\?|？)$",
    re.IGNORECASE,
)
_EXPLICIT_REQUEST_MARKER = re.compile(r"帮我|请|麻烦|我要|我想要|给我|替我", re.IGNORECASE)


class MarkdownFileToolError(Exception):
    """可安全展示给用户的文件工具失败。"""

    def __init__(self, message: str, code: str = "file_create_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class FileCreationRequest:
    """从用户文字提取的受限创建意图，而非任意工具参数。"""

    target: FileTarget
    filename: str | None = None
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class MarkdownArtifact:
    id: str
    path: str
    display_name: str
    target: FileTarget
    mime_type: str
    size_bytes: int
    sha256: str

    def as_event(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "path": self.path,
            "display_name": self.display_name,
            "target": self.target,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def parse_file_creation_request(text: str) -> FileCreationRequest | None:
    """仅接受明确创建 Markdown/文档的请求。

    未指定位置时保存到项目配置的输出目录。若用户明确要求其他目录，绝不
    擅自改写到默认目录，而是将失败原因交给聊天层如实说明。
    """
    normalized = " ".join(text.strip().split())
    if not _CREATE_ACTION.search(normalized) or not _FILE_NOUN.search(normalized):
        return None
    if _CAPABILITY_QUESTION.search(normalized) and not _EXPLICIT_REQUEST_MARKER.search(normalized):
        return None

    target: FileTarget = "output"
    lowered = normalized.lower()
    if "桌面" in normalized or "desktop" in lowered:
        target = "desktop"
    elif "kairos-output" in lowered or "输出目录" in normalized:
        target = "output"

    unsupported_reason: str | None = None
    extension = _OTHER_EXTENSION.search(normalized)
    if extension and extension.group(1).lower() != "md":
        unsupported_reason = "第一版文件工具只支持创建 .md Markdown 文件。"
    elif _UNSAFE_ABSOLUTE_PATH.search(normalized) and "kairos-output" not in lowered:
        unsupported_reason = "目前只能保存到 Windows 桌面或 E:\\Kairos-output，不能写入其他路径。"
    elif target == "output" and _UNSUPPORTED_DESTINATION.search(normalized):
        unsupported_reason = "目前只能保存到 Windows 桌面或 E:\\Kairos-output，其他目录需要后续授权。"

    match = _NAMED_MARKDOWN.search(normalized)
    filename = _clean_extracted_filename(match.group("filename")) if match else None
    return FileCreationRequest(
        target=target,
        filename=filename,
        unsupported_reason=unsupported_reason,
    )


def _clean_extracted_filename(filename: str) -> str:
    """去掉自然语言中紧贴文件名的常见动作词。"""
    result = filename.strip(" '\"")
    for prefix in ("帮我创建", "创建", "新建", "保存", "导出", "生成", "一个", "一份"):
        if result.startswith(prefix) and len(result) > len(prefix) + 3:
            result = result[len(prefix) :].lstrip(" _-")
            break
    return result


def create_markdown_file(
    *,
    target: FileTarget,
    filename: str,
    content: str,
) -> MarkdownArtifact:
    """在允许的根目录创建一个新的 UTF-8 Markdown 文件并验证结果。"""
    safe_filename = validate_markdown_filename(filename)
    encoded_content = validate_markdown_content(content)
    resolved_target, root = resolve_destination_root(target)

    try:
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
    except OSError as exc:
        raise MarkdownFileToolError(
            "目标文件夹无法使用，文件没有创建。", "destination_unavailable"
        ) from exc

    for suffix_number in range(1, MAX_DUPLICATE_SUFFIX_ATTEMPTS + 1):
        candidate_name = _filename_with_suffix(safe_filename, suffix_number)
        candidate = (root / candidate_name).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise MarkdownFileToolError("文件名不在允许的保存范围内。", "path_escape") from exc

        try:
            with candidate.open("xb") as file:
                file.write(encoded_content)
        except FileExistsError:
            continue
        except OSError as exc:
            raise MarkdownFileToolError("写入文件失败，文件没有创建。", "write_failed") from exc

        return verify_markdown_artifact(candidate, target=resolved_target)

    raise MarkdownFileToolError(
        "同名文件过多，无法安全生成新的文件名。", "duplicate_limit_reached"
    )


def validate_markdown_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise MarkdownFileToolError("文件名无效。", "invalid_filename")
    normalized = filename.strip()
    if not normalized or len(normalized) > MAX_FILENAME_CHARS:
        raise MarkdownFileToolError("文件名为空或过长。", "invalid_filename")
    if normalized.startswith(".") or ".." in normalized:
        raise MarkdownFileToolError("文件名不能包含隐藏名或路径片段。", "invalid_filename")
    if "/" in normalized or "\\" in normalized or _INVALID_FILENAME_CHARS.search(normalized):
        raise MarkdownFileToolError("文件名不能包含路径或 Windows 非法字符。", "invalid_filename")
    if normalized.endswith((" ", ".")):
        raise MarkdownFileToolError("文件名不能以空格或句点结尾。", "invalid_filename")
    if not normalized.lower().endswith(".md"):
        raise MarkdownFileToolError("第一版文件工具只支持 .md 文件。", "unsupported_extension")

    stem = normalized[:-3]
    if not stem or stem.rstrip(". ").upper() in _WINDOWS_RESERVED_NAMES:
        raise MarkdownFileToolError("文件名不能使用 Windows 保留名称。", "invalid_filename")
    return normalized


def validate_markdown_content(content: str) -> bytes:
    if not isinstance(content, str) or not content.strip():
        raise MarkdownFileToolError("文档内容为空，文件没有创建。", "empty_content")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_MARKDOWN_ARTIFACT_BYTES:
        raise MarkdownFileToolError("文档内容过大，文件没有创建。", "content_too_large")
    return encoded


def derive_markdown_filename(content: str, today: date | None = None) -> str:
    """从 Markdown H1 导出一个安全的默认文件名。"""
    title = ""
    for line in content.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            title = match.group(1)
            break
    title = _INVALID_FILENAME_CHARS.sub("_", title)
    title = re.sub(r"\s+", " ", title).strip(" ._")
    if not title:
        title = "时叙文档"
    day = (today or date.today()).isoformat()
    suffix = f"_{day}.md"
    title = title[: MAX_FILENAME_CHARS - len(suffix)].rstrip(" ._") or "时叙文档"
    return f"{title}{suffix}"


def resolve_destination_root(target: FileTarget) -> tuple[FileTarget, Path]:
    if target not in {"desktop", "output"}:
        raise MarkdownFileToolError("保存位置不受支持。", "invalid_target")
    if target == "desktop":
        desktop = get_desktop_directory()
        if desktop is not None:
            return "desktop", desktop
    return "output", ARTIFACT_OUTPUT_DIR


def get_desktop_directory() -> Path | None:
    """优先读取 Windows Known Folder，兼容 OneDrive 等桌面重定向。"""
    known_folder = _get_windows_known_desktop_directory()
    if _is_existing_directory(known_folder):
        return known_folder
    fallback = Path.home() / "Desktop"
    return fallback if _is_existing_directory(fallback) else None


def _is_existing_directory(path: Path | None) -> bool:
    try:
        return path is not None and path.is_dir()
    except OSError:
        return False


def _get_windows_known_desktop_directory() -> Path | None:
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        desktop_id = GUID(
            0xB4BFCC3A,
            0xDB2C,
            0x424C,
            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
        )
        value = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(desktop_id), 0, None, ctypes.byref(value)
        )
        if result != 0 or not value.value:
            return None
        try:
            return Path(value.value)
        finally:
            ole32.CoTaskMemFree(value)
    except (AttributeError, OSError):
        return None


def _filename_with_suffix(filename: str, suffix_number: int) -> str:
    if suffix_number == 1:
        return filename
    stem, suffix = filename[:-3], filename[-3:]
    candidate = f"{stem} ({suffix_number}){suffix}"
    if len(candidate) > MAX_FILENAME_CHARS:
        raise MarkdownFileToolError("文件名加序号后过长。", "invalid_filename")
    return candidate


def verify_markdown_artifact(path: Path, *, target: FileTarget) -> MarkdownArtifact:
    try:
        if not path.is_file():
            raise MarkdownFileToolError("文件写入后未找到，无法确认创建成功。", "verify_failed")
        size_bytes = path.stat().st_size
        if size_bytes <= 0:
            raise MarkdownFileToolError("文件写入后为空，无法确认创建成功。", "verify_failed")
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(64 * 1024), b""):
                digest.update(chunk)
    except MarkdownFileToolError:
        raise
    except OSError as exc:
        raise MarkdownFileToolError("文件无法重新读取，无法确认创建成功。", "verify_failed") from exc

    return MarkdownArtifact(
        id=uuid4().hex,
        path=str(path),
        display_name=path.name,
        target=target,
        mime_type="text/markdown",
        size_bytes=size_bytes,
        sha256=digest.hexdigest(),
    )
