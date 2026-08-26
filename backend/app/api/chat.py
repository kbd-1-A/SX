"""WebSocket 对话：收消息 → 选面具 → 流式回。

协议（V1）：
  客户端 →  { "type": "message", "content": "今天好累啊" }
  服务端 →  { "type": "chunk", "content": "听起来" }   ×N
           { "type": "done", "assistant_id": 123, "mask": "love_guide" }
           { "type": "error", "message": "..." }     失败时
"""

import json
import logging
import re
from datetime import date
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.agents.action_guard import detect_action_request, guard_action_reply
from app.agents.emotion import adjust_reply_mode, detect_emotion_state
from app.agents.emotion_tag import EmotionStreamFilter
from app.agents.errors import AgentError, AgentEmptyResponseError
from app.agents.mask import DEFAULT_MASK
from app.agents.reply_mode import detect_reply_mode
from app.agents.router import analyze_reply_emotion, choose_mask, stream_reply
from app.memory import inner_world
from app.config import MAX_USER_MESSAGE_CHARS
from app.memory.anchors import add_anchors_from_text
from app.memory.behavior import observe_behavior
from app.memory.companion import create_follow_ups_from_text
from app.memory.observations import (
    apply_implicit_learning,
    record_continuation_signal,
    record_interrupt_signal,
    record_turn,
)
from app.memory.self import add_mask_milestone
from app.memory.store import add_message, get_or_create_session
from app.agents.quick_react import pick_quick_react
from app.services.weather import (
    WeatherError,
    default_city,
    extract_city_name,
    fetch_weather_summary,
)
from app.tools.files import (
    MarkdownArtifact,
    MarkdownFileToolError,
    create_markdown_file,
    derive_markdown_filename,
    parse_file_creation_request,
)
from app.tools.music import (
    MusicToolError,
    parse_music_query,
    select_local_music_track,
)
from app.tools.research import (
    ResearchError,
    ResearchResult,
    build_research_framework,
    finalize_research_markdown,
    parse_research_request,
    research_public_sources,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 面具切换冷却：距上次切换不足 2 轮则不切，避免「跳脸」
SWITCH_COOLDOWN = 2


def _session_id_from_ws(ws: WebSocket) -> int:
    raw = ws.query_params.get("session_id")
    if raw:
        try:
            return get_or_create_session(int(raw))
        except ValueError:
            pass
    return get_or_create_session()


async def _send_error(ws: WebSocket, message: str, code: str) -> bool:
    """向仍在线的客户端发送可展示错误；断线时不再二次抛错。"""
    try:
        await ws.send_text(
            json.dumps(
                {"type": "error", "message": message, "code": code},
                ensure_ascii=False,
            )
        )
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


def _socket_is_closed(ws: WebSocket) -> bool:
    return (
        ws.client_state == WebSocketState.DISCONNECTED
        or ws.application_state == WebSocketState.DISCONNECTED
    )


def _format_artifact_success(artifact: MarkdownArtifact) -> str:
    kind = "文本文件" if artifact.display_name.lower().endswith(".txt") else "Markdown 文件"
    return (
        f"已创建 {kind}：{artifact.display_name}\n"
        f"位置：{artifact.path}\n"
        f"已校验：{_format_file_size(artifact.size_bytes)}，SHA-256 {artifact.sha256[:12]}..."
    )


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    return f"{size_bytes / 1024:.1f} KB"


_ACTION_RESULT_PREFIXES = ("已创建", "文档文件没有创建成功", "已读取", "联网检索未完成")
_POLLUTED_DRAFT_PATTERN = re.compile(
    r"已创建.{0,12}(?:Markdown|文本)文件|位置：[^\n]*(?:桌面|时序-output)|SHA-256"
)


def _draft_unusable(draft: str) -> bool:
    """草稿不可直接落盘的情形：空、模仿行动结果、无 Markdown 结构或只有元描述。

    模型可能受历史里“已创建 Markdown 文件：…SHA-256…”影响输出编造的创建提示，
    也可能只输出“我准备了一份…草稿”这类元描述而没有正文。这两类都不能写入文件。
    """
    text = draft.strip()
    if not text:
        return True
    if _POLLUTED_DRAFT_PATTERN.search(text[:200]):
        return True
    if not re.search(r"^\s*#\s+\S", text, re.MULTILINE):
        return True
    if len(text) < 120:
        return True
    if re.search(r"我准备了一份|这是一份.{0,8}草稿|以下是(?:内容|整理)", text[:150]):
        return True
    return False


async def _retry_draft(*, research_result, **stream_kwargs) -> tuple[str, str] | None:
    """再次生成文档草稿；成功返回 (finalized, body)，仍不可用返回 None。"""
    chunks: list[str] = []
    async for chunk in stream_reply(**stream_kwargs):
        if chunk:
            chunks.append(chunk)
    retry = "".join(chunks).strip()
    if not retry:
        return None
    body = retry
    if research_result is not None:
        retry = finalize_research_markdown(retry, research_result)
    if _draft_unusable(retry):
        return None
    return retry, body


def _format_body_preview(body: str) -> str:
    """把文档正文（或摘要）展示在聊天里，而不是只给来源列表。"""
    text = body.strip()
    if not text:
        return ""
    if len(text) <= 600:
        return text
    return text[:600].rstrip() + "\n\n……（完整内容已保存到文件）"


def _derive_query_filename(query: str | None, *, want_txt: bool) -> str | None:
    """从研究主题生成有意义的默认文件名，避免退化为“时叙文档”。"""
    if not query:
        return None
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    if not cleaned or len(cleaned) > 60:
        return None
    day = date.today().isoformat()
    ext = ".txt" if want_txt else ".md"
    return f"{cleaned}_{day}{ext}"


def _format_artifact_failure(error: MarkdownFileToolError, draft: str) -> str:
    return (
        f"文档文件没有创建成功：{error.message}\n"
        "下面保留了尚未保存的草稿：\n\n"
        f"{draft}"
    )


def _format_research_event_message(result: ResearchResult) -> str:
    count = len(result.sources)
    return f"已读取 {count} 个公开来源，正在整理带引用的文档。"


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        session_id = _session_id_from_ws(ws)
    except Exception:
        logger.exception("chat_session_initialization_failed")
        await _send_error(ws, "时叙暂时打不开这段对话，请刷新后再试。", "session_error")
        await ws.close()
        return

    current_mask: str | None = None  # None = 本会话还没定过面具
    turns_since_switch = 0
    active_playback_id: str | None = None

    while True:
        try:
            raw = await ws.receive_text()
        except WebSocketDisconnect:
            logger.info("chat_client_disconnected session_id=%s", session_id)
            break
        except RuntimeError:
            logger.info("chat_socket_closed session_id=%s", session_id)
            break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if not await _send_error(ws, "这条消息没有读懂，请再发一次。", "invalid_json"):
                break
            continue
        if data.get("type") == "media.status":
            playback_id = data.get("playback_id")
            status = data.get("status")
            if playback_id != active_playback_id:
                continue
            event_by_status = {
                "playing": "media.playing",
                "paused": "media.paused",
                "stopped": "media.stopped",
                "autoplay_blocked": "media.autoplay_blocked",
                "failed": "media.failed",
            }
            event_type = event_by_status.get(status)
            if not event_type:
                continue
            event = {"type": event_type, "playback_id": playback_id}
            if status == "autoplay_blocked":
                event["message"] = "浏览器需要你点击一次播放。"
            elif status == "failed":
                event["code"] = data.get("code", "media_playback_failed")
                event["message"] = data.get("message", "音频播放失败。")
            await ws.send_text(json.dumps(event, ensure_ascii=False))
            if status == "stopped":
                active_playback_id = None
            continue
        if data.get("type") == "media.command":
            playback_id = data.get("playback_id")
            command = data.get("command")
            if playback_id == active_playback_id and command in {"play", "pause", "stop"}:
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "media.command",
                            "playback_id": playback_id,
                            "command": command,
                        },
                        ensure_ascii=False,
                    )
                )
            continue
        if data.get("type") != "message":
            if not await _send_error(ws, "暂时只支持发送文字消息。", "unsupported_message"):
                break
            continue

        content = (data.get("content") or "").strip()
        if not content:
            if not await _send_error(ws, "这句话是空的，换个说法发给我吧。", "empty_message"):
                break
            continue
        if len(content) > MAX_USER_MESSAGE_CHARS:
            if not await _send_error(
                ws,
                f"这条消息有点长，请控制在 {MAX_USER_MESSAGE_CHARS} 个字符以内。",
                "message_too_long",
            ):
                break
            continue

        request_id = uuid4().hex[:12]
        started_at = perf_counter()
        action_kind = detect_action_request(content)
        media_command = None
        normalized_content = "".join(content.split())
        if normalized_content in {"停止音乐", "停止播放", "停一下音乐", "暂停音乐", "暂停播放"}:
            media_command = "stop" if normalized_content.startswith("停止") or normalized_content.startswith("停") else "pause"
        file_request = (
            parse_file_creation_request(content) if action_kind == "file" else None
        )
        research_request = (
            parse_research_request(content) if file_request is not None else None
        )
        logger.info(
            "chat_started request_id=%s session_id=%s chars=%s",
            request_id,
            session_id,
            len(content),
        )

        try:
            user_id = add_message(session_id, "user", content)
        except Exception:
            logger.exception(
                "chat_user_message_store_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )
            if not await _send_error(ws, "这句话没有保存成功，请再发一次。", "message_store_error"):
                break
            continue

        # 记忆提取与自主学习副作用是非关键副作用，失败不能阻断主对话。
        try:
            # 姓名/称呼已由结构化锚点统一记录，确保可在记忆管理页编辑和删除。
            add_anchors_from_text(content, user_id)
            observe_behavior(content, user_id)
            create_follow_ups_from_text(content, user_id)
            inner_world.decay_current()
            # P2 隐式反馈：紧接着上一条回复继续聊 → 正向续聊信号；并消费未处理的中断信号
            record_continuation_signal(session_id)
            apply_implicit_learning()
        except Exception:
            logger.exception(
                "chat_memory_enrichment_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )

        try:
            # 面具选择 + 冷却锁定（首次直接采用，之后 2 轮内不跳）
            new_mask = await choose_mask(content)
            if current_mask is None:
                current_mask = new_mask
            elif new_mask != current_mask:
                if turns_since_switch < SWITCH_COOLDOWN:
                    new_mask = current_mask
                else:
                    current_mask = new_mask
                    turns_since_switch = 0
            turns_since_switch += 1
            mask = current_mask or DEFAULT_MASK
            emotion_state = detect_emotion_state(content)
            reply_mode = adjust_reply_mode(detect_reply_mode(content, mask=mask), emotion_state)
        except Exception:
            logger.exception(
                "chat_routing_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )
            if not await _send_error(ws, "时叙这会儿没想好怎么接，稍后再试。", "routing_error"):
                break
            continue

        full: list[str] = []
        chunk_count = 0
        emo_filter: EmotionStreamFilter | None = None
        try:
            research_result: ResearchResult | None = None
            research_error: ResearchError | None = None
            if media_command:
                if active_playback_id:
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "media.command",
                                "playback_id": active_playback_id,
                                "command": media_command,
                            },
                            ensure_ascii=False,
                        )
                    )
                    reply = "好，先把音乐停一下。" if media_command == "stop" else "好，先暂停。"
                else:
                    reply = "现在没有正在播放的音乐。"
                await ws.send_text(json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False))
                assistant_id = add_message(session_id, "assistant", reply)
            elif action_kind == "media":
                await ws.send_text(json.dumps({"type": "media.loading"}, ensure_ascii=False))
                try:
                    track = select_local_music_track(parse_music_query(content))
                except MusicToolError as exc:
                    await ws.send_text(
                        json.dumps(
                            {"type": "media.failed", "code": exc.code, "message": exc.message},
                            ensure_ascii=False,
                        )
                    )
                    reply = f"我还没能开始播放：{exc.message}"
                else:
                    playback_id = f"playback_{uuid4().hex[:12]}"
                    active_playback_id = playback_id
                    await ws.send_text(
                        json.dumps(
                            {"type": "media.ready", "media": track.as_event(playback_id)},
                            ensure_ascii=False,
                        )
                    )
                    reply = f"我找到一首：{track.title} - {track.artist}。浏览器如果拦住自动播放，点一下播放就好。"
                await ws.send_text(json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False))
                assistant_id = add_message(session_id, "assistant", reply)
            elif file_request and research_request and not file_request.unsupported_reason:
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "research.started",
                            "query": research_request.query,
                        },
                        ensure_ascii=False,
                    )
                )
                try:
                    research_result = await research_public_sources(research_request.query)
                except ResearchError as exc:
                    research_error = exc
                    logger.warning(
                        "research_failed request_id=%s session_id=%s code=%s",
                        request_id,
                        session_id,
                        exc.code,
                    )
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "research.failed",
                                "code": exc.code,
                                "message": exc.message,
                            },
                            ensure_ascii=False,
                        )
                    )
                except Exception:
                    logger.exception(
                        "research_unexpected_failed request_id=%s session_id=%s",
                        request_id,
                        session_id,
                    )
                    research_error = ResearchError(
                        "联网研究暂时不可用。", "research_unexpected_error"
                    )
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "research.failed",
                                "code": research_error.code,
                                "message": research_error.message,
                            },
                            ensure_ascii=False,
                        )
                    )
                else:
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "research.completed",
                                "research": research_result.as_event(),
                            },
                            ensure_ascii=False,
                        )
                    )

            if media_command or action_kind == "media":
                # 媒体请求已经在上面的受控 Provider 分支处理，不再进入 LLM。
                pass
            elif action_kind == "weather":
                city = extract_city_name(content) or default_city()
                if not city:
                    reply = "想帮你看天气，先告诉我你在哪个城市呀，比如「北京今天天气怎么样」。"
                    await ws.send_text(
                        json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
                    )
                else:
                    try:
                        weather_result = await fetch_weather_summary(city)
                    except WeatherError as exc:
                        logger.warning(
                            "weather_failed request_id=%s session_id=%s code=%s",
                            request_id,
                            session_id,
                            exc.code,
                        )
                        reply = f"天气暂时查不到：{exc.message}"
                        await ws.send_text(
                            json.dumps(
                                {"type": "chunk", "content": reply}, ensure_ascii=False
                            )
                        )
                    else:
                        emo_filter = EmotionStreamFilter()
                        async for chunk in stream_reply(
                            session_id,
                            content,
                            mask=mask,
                            reply_mode=reply_mode,
                            emotion_state=emotion_state,
                            weather_result=weather_result,
                        ):
                            if not chunk:
                                continue
                            filtered = emo_filter.feed(chunk)
                            if filtered:
                                await ws.send_text(
                                    json.dumps(
                                        {"type": "chunk", "content": filtered}, ensure_ascii=False
                                    )
                                )
                        remaining = emo_filter.flush()
                        if remaining:
                            await ws.send_text(
                                json.dumps(
                                    {"type": "chunk", "content": remaining}, ensure_ascii=False
                                )
                            )
                        reply = emo_filter.clean_text
                        if not reply:
                            raise AgentEmptyResponseError()
                assistant_id = add_message(session_id, "assistant", reply)

            elif file_request and file_request.unsupported_reason:
                reply = file_request.unsupported_reason
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "artifact.failed",
                            "code": "unsupported_destination",
                            "message": reply,
                        },
                        ensure_ascii=False,
                    )
                )
                await ws.send_text(
                    json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
                )
                assistant_id = add_message(session_id, "assistant", reply)
            elif research_error is not None and file_request is not None:
                reply = build_research_framework(
                    research_request.query if research_request else content,
                    research_error.message,
                )
                filename = file_request.filename or derive_markdown_filename(reply)
                try:
                    artifact = create_markdown_file(
                        target=file_request.target,
                        filename=filename,
                        content=reply,
                    )
                except MarkdownFileToolError as exc:
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "artifact.failed",
                                "code": exc.code,
                                "message": exc.message,
                            },
                            ensure_ascii=False,
                        )
                    )
                    reply = _format_artifact_failure(exc, reply)
                else:
                    await ws.send_text(
                        json.dumps(
                            {"type": "artifact.created", "artifact": artifact.as_event()},
                            ensure_ascii=False,
                        )
                    )
                    preview = _format_body_preview(reply)
                    if preview:
                        await ws.send_text(
                            json.dumps({"type": "chunk", "content": preview}, ensure_ascii=False)
                        )
                    reply = _format_artifact_success(artifact)
                await ws.send_text(
                    json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
                )
                assistant_id = add_message(session_id, "assistant", reply)
            else:
                if action_kind is None:
                    qr = pick_quick_react()
                    if qr:
                        await ws.send_text(
                            json.dumps({"type": "quick_react", "content": qr}, ensure_ascii=False)
                        )
                emo_filter = EmotionStreamFilter()
                async for chunk in stream_reply(
                    session_id,
                    content,
                    mask=mask,
                    reply_mode=reply_mode,
                    emotion_state=emotion_state,
                    document_draft=file_request is not None,
                    research_result=research_result,
                    research_failed=research_error is not None,
                ):
                    if not chunk:
                        continue
                    chunk_count += 1
                    filtered = emo_filter.feed(chunk)
                    if filtered:
                        full.append(filtered)
                    if action_kind is None and filtered:
                        await ws.send_text(
                            json.dumps({"type": "chunk", "content": filtered}, ensure_ascii=False)
                        )

                remaining = emo_filter.flush()
                if remaining:
                    full.append(remaining)
                    if action_kind is None:
                        await ws.send_text(
                            json.dumps({"type": "chunk", "content": remaining}, ensure_ascii=False)
                        )

                reply = emo_filter.clean_text
                if not reply:
                    raise AgentEmptyResponseError()

                if file_request:
                    body_text = reply
                    if research_result is not None:
                        reply = finalize_research_markdown(reply, research_result)
                    if _draft_unusable(reply):
                        retried = await _retry_draft(
                            session_id=session_id,
                            user_msg=content,
                            mask=mask,
                            reply_mode=reply_mode,
                            emotion_state=emotion_state,
                            document_draft=True,
                            research_result=research_result,
                            research_failed=research_error is not None,
                        )
                        if retried is not None:
                            reply, body_text = retried
                            logger.warning(
                                "chat_draft_retry_succeeded request_id=%s session_id=%s",
                                request_id,
                                session_id,
                            )
                        else:
                            logger.warning(
                                "chat_draft_unusable_after_retry request_id=%s session_id=%s",
                                request_id,
                                session_id,
                            )
                            reply = build_research_framework(
                                research_request.query if research_request else content,
                                "正文内容生成异常，已为你保存研究框架，可重新发起生成。",
                            )
                            body_text = reply
                    filename = (
                        file_request.filename
                        or _derive_query_filename(
                            research_request.query if research_request else None,
                            want_txt=("txt" in content.lower() or "文本文件" in content),
                        )
                        or derive_markdown_filename(reply)
                    )
                    try:
                        artifact = create_markdown_file(
                            target=file_request.target,
                            filename=filename,
                            content=reply,
                        )
                    except MarkdownFileToolError as exc:
                        logger.warning(
                            "file_create_failed request_id=%s session_id=%s code=%s",
                            request_id,
                            session_id,
                            exc.code,
                        )
                        await ws.send_text(
                            json.dumps(
                                {
                                    "type": "artifact.failed",
                                    "code": exc.code,
                                    "message": exc.message,
                                },
                                ensure_ascii=False,
                            )
                        )
                        reply = _format_artifact_failure(exc, reply)
                    else:
                        await ws.send_text(
                            json.dumps(
                                {"type": "artifact.created", "artifact": artifact.as_event()},
                                ensure_ascii=False,
                            )
                        )
                        preview = _format_body_preview(body_text)
                        if preview:
                            await ws.send_text(
                                json.dumps(
                                    {"type": "chunk", "content": preview}, ensure_ascii=False
                                )
                            )
                        reply = _format_artifact_success(artifact)
                    await ws.send_text(
                        json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
                    )
                else:
                    reply, blocked_claim = guard_action_reply(reply, action_kind)
                    if blocked_claim:
                        logger.warning(
                            "chat_unverified_action_claim_blocked request_id=%s session_id=%s action_kind=%s",
                            request_id,
                            session_id,
                            action_kind,
                        )
                    if action_kind is not None:
                        await ws.send_text(
                            json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
                        )

                assistant_id = add_message(session_id, "assistant", reply)
        except WebSocketDisconnect:
            logger.info(
                "chat_interrupted request_id=%s session_id=%s elapsed_ms=%s",
                request_id,
                session_id,
                round((perf_counter() - started_at) * 1000),
            )
            try:
                record_interrupt_signal(session_id, "".join(full))
            except Exception:
                logger.exception(
                    "chat_interrupt_observation_failed request_id=%s session_id=%s",
                    request_id,
                    session_id,
                )
            break
        except AgentError as exc:
            logger.warning(
                "chat_failed request_id=%s session_id=%s code=%s elapsed_ms=%s",
                request_id,
                session_id,
                exc.code,
                round((perf_counter() - started_at) * 1000),
            )
            if not await _send_error(ws, exc.public_message, exc.code):
                break
            continue
        except RuntimeError:
            if _socket_is_closed(ws):
                logger.info(
                    "chat_interrupted request_id=%s session_id=%s elapsed_ms=%s",
                    request_id,
                    session_id,
                    round((perf_counter() - started_at) * 1000),
                )
                try:
                    record_interrupt_signal(session_id, "".join(full))
                except Exception:
                    logger.exception(
                        "chat_interrupt_observation_failed request_id=%s session_id=%s",
                        request_id,
                        session_id,
                    )
                break
            logger.exception(
                "chat_runtime_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )
            if not await _send_error(
                ws,
                "时叙刚刚没接住这句话，请稍后再试。",
                "unexpected_error",
            ):
                break
            continue
        except Exception:
            logger.exception(
                "chat_failed request_id=%s session_id=%s code=unexpected_error",
                request_id,
                session_id,
            )
            if not await _send_error(
                ws,
                "时叙刚刚没接住这句话，请稍后再试。",
                "unexpected_error",
            ):
                break
            continue

        shixu_emotion: dict | None = None
        try:
            parsed = emo_filter.emotion if emo_filter else None
            if parsed is None and emo_filter is not None:
                prev_state = inner_world.get_current()
                parsed = await analyze_reply_emotion(
                    content, reply,
                    prev_emotion=prev_state.emotion,
                    prev_streak=prev_state.streak,
                )
            if parsed:
                state = inner_world.record_emotion(
                    emotion=parsed["emotion"],
                    intensity=parsed["intensity"],
                    cause=parsed["cause"],
                    source_message_id=assistant_id,
                )
            else:
                state = inner_world.get_current()
            shixu_emotion = {
                "emotion": state.emotion,
                "intensity": state.intensity,
                "cause": state.cause,
                "subtitle_color": inner_world.get_subtitle_color(state.emotion),
            }
        except Exception:
            logger.exception(
                "chat_emotion_record_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )

        try:
            record_turn(
                session_id=session_id,
                user_message_id=user_id,
                assistant_message_id=assistant_id,
                mask=mask,
                reply_mode=reply_mode,
                emotion=emotion_state.get("emotion") if emotion_state else None,
                user_chars=len(content),
                reply_chars=len(reply),
                reply_seconds=round((perf_counter() - started_at) * 1000) / 1000.0,
            )
        except Exception:
            logger.exception(
                "chat_turn_observation_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )

        try:
            add_mask_milestone(mask)
        except Exception:
            logger.exception(
                "chat_milestone_update_failed request_id=%s session_id=%s",
                request_id,
                session_id,
            )

        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "done",
                        "assistant_id": assistant_id,
                        "mask": mask,
                        "reply_mode": reply_mode,
                        "emotion_state": emotion_state,
                        "shixu_emotion": shixu_emotion,
                    },
                    ensure_ascii=False,
                )
            )
        except (WebSocketDisconnect, RuntimeError):
            logger.info(
                "chat_disconnected_before_done request_id=%s session_id=%s",
                request_id,
                session_id,
            )
            break

        logger.info(
            "chat_completed request_id=%s session_id=%s mask=%s reply_mode=%s "
            "chunks=%s response_chars=%s elapsed_ms=%s shixu_emotion=%s",
            request_id,
            session_id,
            mask,
            reply_mode,
            chunk_count,
            len(reply),
            round((perf_counter() - started_at) * 1000),
            shixu_emotion.get("emotion") if shixu_emotion else "unknown",
        )
