"""全局配置：.env 加载 + 路径常量。

坑（自第十人迁移）：.env 相对 CWD 生效。这里用绝对路径显式加载 backend/.env，
避免"在别的目录启动 uvicorn 导致 .env 读不到"的问题。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录（app/config.py 的上两级）
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "45"))
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "1"))
MASK_CLASSIFY_TIMEOUT_SECONDS = float(
    os.getenv("MASK_CLASSIFY_TIMEOUT_SECONDS", "5")
)
MAX_USER_MESSAGE_CHARS = int(os.getenv("MAX_USER_MESSAGE_CHARS", "4000"))
ARTIFACT_OUTPUT_DIR = Path(os.getenv("ARTIFACT_OUTPUT_DIR", r"E:\时序-output"))
MAX_MARKDOWN_ARTIFACT_BYTES = int(
    os.getenv("MAX_MARKDOWN_ARTIFACT_BYTES", "500000")
)
RESEARCH_ENABLED = os.getenv("RESEARCH_ENABLED", "true").lower() == "true"
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "bing_html")
SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "https://cn.bing.com/search")
RESEARCH_TIMEOUT_SECONDS = float(os.getenv("RESEARCH_TIMEOUT_SECONDS", "12"))
RESEARCH_MAX_SEARCH_RESULTS = int(os.getenv("RESEARCH_MAX_SEARCH_RESULTS", "8"))
RESEARCH_MAX_SOURCES = int(os.getenv("RESEARCH_MAX_SOURCES", "4"))
RESEARCH_MIN_SOURCES = int(os.getenv("RESEARCH_MIN_SOURCES", "2"))
RESEARCH_MAX_SOURCE_CHARS = int(os.getenv("RESEARCH_MAX_SOURCE_CHARS", "4000"))
RESEARCH_MAX_RESPONSE_BYTES = int(os.getenv("RESEARCH_MAX_RESPONSE_BYTES", "1000000"))
RESEARCH_USER_AGENT = os.getenv(
    "RESEARCH_USER_AGENT", "Mozilla/5.0 (compatible; ShixuResearch/1.0)"
)

ASR_MODEL = os.getenv(
    "ASR_MODEL",
    str(BASE_DIR / "models" / "faster-whisper-base"),
)
ASR_DEVICE = os.getenv("ASR_DEVICE", "cpu")
ASR_COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "int8")
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "zh")

PORT = int(os.getenv("PORT", "8000"))

# SQLite 数据文件
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "shishu.db")))
