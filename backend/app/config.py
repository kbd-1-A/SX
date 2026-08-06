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

PORT = int(os.getenv("PORT", "8000"))

# SQLite 数据文件
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "shishu.db")))
