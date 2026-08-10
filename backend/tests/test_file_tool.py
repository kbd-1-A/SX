"""Markdown 文件工具：路径边界、排重和落盘校验。"""

import hashlib
from datetime import date
from pathlib import Path

import pytest

import app.tools.files as files_mod
from app.tools.files import MarkdownFileToolError


def patch_roots(monkeypatch, tmp_path):
    desktop = tmp_path / "desktop"
    output = tmp_path / "output"
    desktop.mkdir()
    monkeypatch.setattr(files_mod, "ARTIFACT_OUTPUT_DIR", output)
    monkeypatch.setattr(files_mod, "get_desktop_directory", lambda: desktop)
    return desktop, output


def test_creates_utf8_markdown_and_returns_verified_artifact(monkeypatch, tmp_path):
    _, output = patch_roots(monkeypatch, tmp_path)
    content = "# 今日记录\n\n时叙会如实说明文件是否创建成功。\n"

    artifact = files_mod.create_markdown_file(
        target="output", filename="今日记录.md", content=content
    )

    path = output / "今日记录.md"
    assert path.read_text(encoding="utf-8") == content
    assert artifact.path == str(path.resolve())
    assert artifact.target == "output"
    assert artifact.size_bytes == len(content.encode("utf-8"))
    assert artifact.sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert artifact.as_event()["mime_type"] == "text/markdown"


def test_desktop_target_uses_resolved_desktop_root(monkeypatch, tmp_path):
    desktop, _ = patch_roots(monkeypatch, tmp_path)

    artifact = files_mod.create_markdown_file(
        target="desktop", filename="桌面文档.md", content="# 桌面文档\n"
    )

    assert Path(artifact.path) == desktop.resolve() / "桌面文档.md"
    assert artifact.target == "desktop"


@pytest.mark.parametrize("filename", ["notes.txt", "../notes.md", "folder/notes.md", r"folder\notes.md"])
def test_rejects_non_markdown_and_path_traversal(monkeypatch, tmp_path, filename):
    patch_roots(monkeypatch, tmp_path)

    with pytest.raises(MarkdownFileToolError):
        files_mod.create_markdown_file(target="output", filename=filename, content="# 内容\n")


@pytest.mark.parametrize("filename", ["CON.md", "lpt1.md", "bad?.md", ".hidden.md"])
def test_rejects_invalid_windows_names(monkeypatch, tmp_path, filename):
    patch_roots(monkeypatch, tmp_path)

    with pytest.raises(MarkdownFileToolError):
        files_mod.create_markdown_file(target="output", filename=filename, content="# 内容\n")


def test_duplicate_filename_gets_suffix_without_overwrite(monkeypatch, tmp_path):
    _, output = patch_roots(monkeypatch, tmp_path)
    (output / "计划.md").parent.mkdir(parents=True)
    (output / "计划.md").write_text("旧内容", encoding="utf-8")

    artifact = files_mod.create_markdown_file(
        target="output", filename="计划.md", content="# 新计划\n"
    )

    assert (output / "计划.md").read_text(encoding="utf-8") == "旧内容"
    assert artifact.display_name == "计划 (2).md"
    assert (output / "计划 (2).md").read_text(encoding="utf-8") == "# 新计划\n"


def test_rejects_empty_or_oversized_content(monkeypatch, tmp_path):
    patch_roots(monkeypatch, tmp_path)
    with pytest.raises(MarkdownFileToolError) as empty:
        files_mod.create_markdown_file(target="output", filename="空.md", content="  \n")
    assert empty.value.code == "empty_content"

    monkeypatch.setattr(files_mod, "MAX_MARKDOWN_ARTIFACT_BYTES", 4)
    with pytest.raises(MarkdownFileToolError) as too_large:
        files_mod.create_markdown_file(target="output", filename="大.md", content="# 超过\n")
    assert too_large.value.code == "content_too_large"


def test_desktop_falls_back_to_output_when_no_desktop(monkeypatch, tmp_path):
    _, output = patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(files_mod, "get_desktop_directory", lambda: None)

    artifact = files_mod.create_markdown_file(
        target="desktop", filename="回退.md", content="# 回退\n"
    )

    assert artifact.target == "output"
    assert Path(artifact.path) == output.resolve() / "回退.md"


def test_derives_filename_from_h1_and_sanitizes_it():
    filename = files_mod.derive_markdown_filename(
        "# Agent: 行业 / 观察\n\n内容", today=date(2026, 8, 10)
    )

    assert filename == "Agent_ 行业 _ 观察_2026-08-10.md"


def test_parse_file_creation_request_has_explicit_creation_boundary():
    request = files_mod.parse_file_creation_request(
        "帮我创建 Agent行业行情分析_2026-08-10.md 放在桌面"
    )

    assert request is not None
    assert request.target == "desktop"
    assert request.filename == "Agent行业行情分析_2026-08-10.md"
    assert files_mod.parse_file_creation_request("帮我写一份行业分析") is None
    assert files_mod.parse_file_creation_request("现在可以创建 md 文件了吗？") is None
    assert files_mod.parse_file_creation_request("可以帮我创建一个 md 文件吗？") is not None


def test_parse_rejects_unapproved_path_and_non_markdown_format():
    outside = files_mod.parse_file_creation_request("创建一份文档保存到 C:\\temp")
    non_markdown = files_mod.parse_file_creation_request("创建 report.pdf 文件放在桌面")

    assert outside is not None and outside.unsupported_reason
    assert non_markdown is not None
    assert non_markdown.unsupported_reason == "第一版文件工具只支持创建 .md Markdown 文件。"
