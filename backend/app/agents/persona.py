"""灵魂加载：shisu.md 是核心真源，masks/ 是面具层。

每次对话把「核心 + 命中的面具」拼成 system prompt 注入。
核心永远第一段——无论戴哪个面具，时叙都记得自己是谁。
"""

from pathlib import Path

PERSONA_DIR = Path(__file__).resolve().parents[2] / "persona"
MASKS_DIR = PERSONA_DIR / "masks"

# 默认面具（没有命中任何场景时用）
DEFAULT_MASK = "daily_companion"


def load_core() -> str:
    return (PERSONA_DIR / "shisu.md").read_text(encoding="utf-8")


def load_mask(mask: str | None) -> str | None:
    """读面具文件；不存在或为默认面具时返回 None（核心已覆盖默认姿态）。"""
    if not mask or mask == DEFAULT_MASK:
        return None
    path = MASKS_DIR / f"{mask}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def load_persona(mask: str | None = None) -> str:
    """核心 + 命中面具，拼成完整 system prompt。"""
    parts = [load_core()]
    mask_text = load_mask(mask)
    if mask_text:
        parts.append("# 本次对话的面具\n\n" + mask_text)
    return "\n\n".join(parts)
