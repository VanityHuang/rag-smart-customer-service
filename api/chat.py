"""聊天 API 路由 — 角色化版本"""
import datetime
import glob
import json
import logging
import os as _os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from file_history_store import get_history, get_metadata_store
from api.deps import get_rag_service
from api.rate_limit import check_rate_limit, get_client_ip, RATE_LIMIT_MESSAGE

router = APIRouter()
logger = logging.getLogger(__name__)

# ── 输入内容前置拦截 ──

_REJECT_MESSAGE = (
    "抱歉，我无法处理这条消息。请输入至少 2 个字的有效问题，"
    "我才能为你提供帮助。"
)


def validate_input(message: str) -> str | None:
    """校验用户输入，返回拒绝理由；通过则返回 None"""
    msg = message.strip()

    # 长度不足
    if len(msg) < 2:
        return _REJECT_MESSAGE

    # 不含任何中文字符或英文单词（纯标点/表情/空格）
    if not re.search(r'[一-鿿]|[a-zA-Z]+', msg):
        return _REJECT_MESSAGE

    # 去除常见语气词/填充词后，剩余内容不足 2 字 → 无实质内容
    filler = re.sub(r'[啊哈嗯哦嘿呀吧呢嘛啦嘻唉哎噢呃额]', '', msg)
    meaningful = re.sub(r'[^\w]', '', filler)  # 再去标点
    if len(meaningful) < 2:
        return _REJECT_MESSAGE

    return None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "user_001"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    token_usage: dict = {}


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, req: Request):
    """发送消息给 RAG Agent 并获取回答（非流式）"""
    role = req.state.role

    # guest 限流
    if role == "guest":
        ip = get_client_ip(req)
        allowed, remaining = check_rate_limit(ip)
        if not allowed:
            raise HTTPException(status_code=429, detail=RATE_LIMIT_MESSAGE)

    # 输入内容前置拦截
    reject_reason = validate_input(request.message)
    if reject_reason:
        return ChatResponse(
            response=reject_reason,
            session_id=request.session_id,
            token_usage={"input_tokens": 0, "output_tokens": 0},
        )

    try:
        rag_service = get_rag_service(role)
        result = rag_service.invoke(request.message, request.session_id)
        usage = rag_service.token_usage
        # 累加到会话元数据（持久化）
        store = get_metadata_store(role)
        store.add_token_usage(
            request.session_id,
            usage["input_tokens"],
            usage["output_tokens"],
        )
        cumulative = store.get_token_usage(request.session_id)
        logger.info(
            f"[{role}] session={request.session_id} "
            f"tokens=in:{usage['input_tokens']}/out:{usage['output_tokens']} "
            f"(cumulative: in:{cumulative['input_tokens']}/out:{cumulative['output_tokens']})"
        )
        return ChatResponse(
            response=result,
            session_id=request.session_id,
            token_usage=cumulative,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
def chat_stream(request: ChatRequest, req: Request):
    """发送消息并以 SSE 流式返回 Agent 回答"""
    role = req.state.role

    # guest 限流
    if role == "guest":
        ip = get_client_ip(req)
        allowed, remaining = check_rate_limit(ip)
        if not allowed:
            raise HTTPException(status_code=429, detail=RATE_LIMIT_MESSAGE)

    # 输入内容前置拦截
    reject_reason = validate_input(request.message)
    if reject_reason:
        def reject_stream():
            yield f"data: {json.dumps({'token': reject_reason, 'done': False}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True, 'token_usage': {'input_tokens': 0, 'output_tokens': 0}}, ensure_ascii=False)}\n\n"
        return StreamingResponse(reject_stream(), media_type="text/event-stream")

    rag_service = get_rag_service(role)

    def generate():
        try:
            for token in rag_service.stream(request.message, request.session_id):
                yield f"data: {json.dumps({'token': token, 'done': False}, ensure_ascii=False)}\n\n"
            usage = rag_service.token_usage
            # 累加到会话元数据（持久化）
            store = get_metadata_store(role)
            store.add_token_usage(
                request.session_id,
                usage["input_tokens"],
                usage["output_tokens"],
            )
            cumulative = store.get_token_usage(request.session_id)
            yield f"data: {json.dumps({'done': True, 'token_usage': cumulative}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/history")
def get_chat_history(session_id: str, req: Request):
    """获取指定 session 的聊天历史（仅返回 human/ai 消息）"""
    role = req.state.role
    try:
        history = get_history(session_id, role)
        messages = []
        for msg in history.messages:
            if msg.type == "human":
                messages.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                messages.append({"role": "assistant", "content": msg.content})
        # 返回累计 token 用量
        store = get_metadata_store(role)
        token_usage = store.get_token_usage(session_id)
        return {"session_id": session_id, "messages": messages, "token_usage": token_usage}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 会话管理 ──

class SessionItem(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str


class SessionUpdateRequest(BaseModel):
    title: str


def _scan_sessions_from_files(role: str):
    """降级方案：扫描 chat_history 目录获取会话列表"""
    storage = f"./data/chat_history/{role}"
    results = []
    if not _os.path.exists(storage):
        return results
    for fpath in glob.glob(_os.path.join(storage, "*")):
        fname = _os.path.basename(fpath)
        if fname == "sessions_metadata.json":
            continue
        if not _os.path.isfile(fpath):
            continue
        mtime = _os.path.getmtime(fpath)
        results.append({
            "session_id": fname,
            "title": "历史对话",
            "created_at": datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat(),
            "updated_at": datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat(),
        })
    results.sort(key=lambda x: x["updated_at"], reverse=True)
    return results


@router.get("/sessions", response_model=list[SessionItem])
def list_sessions(req: Request):
    """列出所有会话，按更新时间倒序"""
    role = req.state.role
    store = get_metadata_store(role)
    try:
        items = store.list_sessions()
        if not items:
            items = _scan_sessions_from_files(role)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}")
def update_session(session_id: str, req: SessionUpdateRequest, request: Request):
    """重命名会话"""
    role = request.state.role
    store = get_metadata_store(role)
    if not store.session_exists(session_id):
        # 也许是旧会话，先注册
        store.create_session(session_id)
    title = req.title.strip()
    if len(title) > 40:
        title = title[:40] + "..."
    store.update_session(session_id, title=title)
    return {"session_id": session_id, "title": title}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, req: Request):
    """删除会话（移除消息文件和元数据）"""
    role = req.state.role
    store = get_metadata_store(role)
    file_path = _os.path.join(f"./data/chat_history/{role}", session_id)
    if _os.path.exists(file_path):
        _os.remove(file_path)
    store.delete_session(session_id)
    return {"message": "已删除", "session_id": session_id}
