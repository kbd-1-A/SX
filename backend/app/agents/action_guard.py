"""行动能力事实与假执行防线。

当前已接入受限 Markdown 创建、公开网页研究与本地音乐播放，外部软件控制
仍未实现。这里集中声明每轮真实可用的能力，并拦截无依据的“已完成”表述。
"""

from __future__ import annotations

import re
from typing import Literal

ActionKind = Literal["file", "media", "external"]

_FILE_REQUEST = re.compile(
    r"(?:帮(?:我|忙)|请|麻烦|能(?:不)?能|可以|我要|我想|替我)?"
    r".{0,24}(?:创建|新建|保存|写入|导出|生成).{0,24}"
    r"(?:md|markdown|文档|文件|桌面|目录|文件夹)"
    r"|(?:写|整理).{0,24}(?:md|markdown|文档|文件)"
    r"|放在.{0,16}(?:桌面|目录|文件夹)"
    r"|(?:桌面|目录|文件夹).{0,16}(?:就行|可以|保存|创建)",
    re.IGNORECASE,
)
_MEDIA_REQUEST = re.compile(
    r"(?:播放|放).{0,16}(?:音乐|歌|歌曲|歌单)"
    r"|(?:来|推荐).{0,12}(?:一首|点).{0,8}(?:音乐|歌|歌曲|歌单)",
    re.IGNORECASE,
)
_EXTERNAL_REQUEST = re.compile(
    r"(?:帮(?:我|忙)|请|麻烦|能(?:不)?能|可以|我要|我想|替我)?"
    r".{0,20}(?:发送|发给|打开|启动|安装|下载|删除|移动|重命名|购买|下单|预约)"
    r"|(?:邮件|消息).{0,12}(?:发|发送)",
    re.IGNORECASE,
)

_UNVERIFIED_COMPLETION_PATTERNS = (
    re.compile(
        r"(?:我|时叙|这边|系统).{0,10}(?:已经|已|刚刚|正在).{0,24}"
        r"(?:创建|新建|生成|保存|写入|导出|下载|删除|移动|重命名|发送|发出|播放|打开|启动|安装|购买|下单|预约|放到|放在)"
    ),
    re.compile(
        r"(?:已经|已)(?:帮你|替你|为你).{0,24}"
        r"(?:创建|新建|生成|保存|写入|导出|下载|删除|移动|重命名|发送|发出|播放|打开|启动|安装|购买|下单|预约)"
    ),
    re.compile(r"(?:写好了|弄好了|整理好了|处理好了|搞定了|放好了)"),
    re.compile(
        r"(?:文件|文档).{0,16}(?:在(?:桌面|文件夹|目录)|(?:已|已经).{0,12}"
        r"(?:创建|新建|生成|保存|写入|导出))"
    ),
    re.compile(r"(?:歌曲|音乐).{0,16}(?:(?:已|已经|正在).{0,8}(?:播放|开始)|开始播放)"),
    re.compile(r"(?:正在播放|已经播放)"),
)

_SAFE_FALLBACKS: dict[ActionKind, str] = {
    "file": (
        "我目前还不能直接在你的设备上创建、保存或修改文件，所以不能说文件已经生成。"
        "我可以先把完整的 Markdown 内容整理在这里，等文件工具接入后再保存到桌面。"
    ),
    "media": (
        "我播放音乐需要先由你授权本地音乐目录，而且实际播放由服务端完成，我不能替它声称已经在播放。"
        "你想听什么可以直接说，我帮你从本地音乐库里找。"
    ),
    "external": (
        "我目前还不能直接操作外部软件、发送内容或修改设备上的资料，所以不能把这件事说成已经完成。"
        "我可以先帮你整理好内容和下一步。"
    ),
}


def detect_action_request(text: str) -> ActionKind | None:
    """识别需要真实外部执行的当前用户请求或其路径续句。"""
    normalized = "".join(text.split())
    if not normalized:
        return None
    if _MEDIA_REQUEST.search(normalized):
        return "media"
    if _FILE_REQUEST.search(normalized):
        return "file"
    if _EXTERNAL_REQUEST.search(normalized):
        return "external"
    return None


def format_action_capability_rules(
    *, file_creation_available: bool = False, web_research_available: bool = False
) -> str:
    """提供给模型的当前能力边界。

    只有文件创建编排已经决定执行时，模型才会收到 Markdown 草稿任务；模型
    本身仍不能声称写入完成，最终结果只能由服务端工具返回。
    """
    if file_creation_available:
        rules = [
            "# 行动能力与执行事实",
            "- 本轮正在准备一个 Markdown 文档草稿；服务端随后最多只能在 Windows 桌面或 E:\\Kairos-output 创建新的 .md 文件。",
            "- 你只负责生成文档内容，不能选择任意路径、覆盖文件、删除文件或声称文件已经创建。",
            "- 文件是否创建成功、最终文件名和保存位置只能以服务端返回的工具结果为准。",
            "- 当前仍没有外部软件控制、发送或购买工具。",
            "- 不要用“写好了”“弄好了”“文件在桌面”“正在播放”等话术模拟执行结果。",
        ]
        if web_research_available:
            rules.append("- 服务端已为本轮提供公开网页研究资料；只能依据附带的 [S#] 来源写时效结论。")
        else:
            rules.append("- 当前没有可调用的网页检索工具，不能把内容说成实时、最新或已联网核实。")
        return "\n".join(rules)
    return "\n".join(
        [
            "# 行动能力与执行事实",
            "- 当前支持在用户明确要求时创建新的 .md 文件，位置仅限 Windows 桌面或 E:\\Kairos-output；默认不覆盖同名文件。",
            "- 当前支持为研究型 Markdown 请求检索公开网页并附上真实来源；普通聊天不会自动联网。",
            "- 当前支持在用户明确点歌时播放本地音乐库中的歌曲；音乐由服务端本地音乐库实际播放，你只识别点歌意图，不直接播放、也不声称已经在播放。",
            "- 当前仍不支持文件修改、覆盖、删除、移动、外部软件控制、发送或购买。",
            "- 没有系统返回的成功结果时，绝不能说文件已创建、内容已保存、歌曲已播放、软件已打开、消息已发送或其他外部动作已完成。",
            "- 只有本轮收到真实文件、研究或播放结果时才能报告对应动作成功；其他能力按当前边界如实说明。",
            "- 不要用“写好了”“弄好了”“文件在桌面”“正在播放”等话术模拟执行结果。",
        ]
    )


def has_unverified_completion_claim(reply: str) -> bool:
    """检测行动请求中的无依据完成承诺。"""
    normalized = "".join(reply.split())
    return any(pattern.search(normalized) for pattern in _UNVERIFIED_COMPLETION_PATTERNS)


def guard_action_reply(reply: str, kind: ActionKind | None) -> tuple[str, bool]:
    """将假完成回复替换为当前真实能力说明。"""
    if kind is None or not has_unverified_completion_claim(reply):
        return reply, False
    return _SAFE_FALLBACKS[kind], True
