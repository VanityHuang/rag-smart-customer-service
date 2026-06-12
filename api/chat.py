"""聊天 API 路由"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rag_agent import RagAgentService
from file_history_store import get_history

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
