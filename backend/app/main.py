"""时叙后端入口。

启动：cd backend && uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, memory, voice
from app.db.init import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="时叙 · 陪伴 Agent", version="0.1.0", lifespan=lifespan)

# V1 开发期放开 CORS；上线前收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(memory.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "connected"}
