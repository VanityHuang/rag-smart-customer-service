"""聊天 API 路由"""
import datetime
import glob
import json
import os as _os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rag_agent import RagAgentService
from file_history_store import get_history, get_metadata_store

router = APIRouter()

rag_service = RagAgentService()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "user_001"


class ChatResponse(BaseModel):
    response: str
    session_id: str


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest):
    """发送消息给 RAG Agent 并获取回答（非流式）"""
    try:
        result = rag_service.invoke(request.message, request.session_id)
        return ChatResponse(response=result, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
def chat_stream(request: ChatRequest):
    """发送消息并以 SSE 流式返回 Agent 回答"""
    def generate():
        try:
            for token in rag_service.stream(request.message, request.session_id):
                yield f"data: {json.dumps({'token': token, 'done': False}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"
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
def get_chat_history(session_id: str):
    """获取指定 session 的聊天历史（仅返回 human/ai 消息）"""
    try:
        history = get_history(session_id)
        messages = []
        for msg in history.messages:
            if msg.type == "human":
                messages.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                messages.append({"role": "assistant", "content": msg.content})
        return {"session_id": session_id, "messages": messages}
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


def _scan_sessions_from_files():
    """降级方案：扫描 chat_history 目录获取会话列表"""
    storage = "./data/chat_history"
    results = []
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
def list_sessions():
    """列出所有会话，按更新时间倒序"""
    store = get_metadata_store()
    try:
        items = store.list_sessions()
        if not items:
            items = _scan_sessions_from_files()
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}")
def update_session(session_id: str, req: SessionUpdateRequest):
    """重命名会话"""
    store = get_metadata_store()
    if not store.session_exists(session_id):
        # 也许是旧会话，先注册
        store.create_session(session_id)
    title = req.title.strip()
    if len(title) > 40:
        title = title[:40] + "..."
    store.update_session(session_id, title=title)
    return {"session_id": session_id, "title": title}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """删除会话（移除消息文件和元数据）"""
    store = get_metadata_store()
    file_path = _os.path.join("./data/chat_history", session_id)
    if _os.path.exists(file_path):
        _os.remove(file_path)
    store.delete_session(session_id)
    return {"message": "已删除", "session_id": session_id}
