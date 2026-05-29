"""聊天 API 路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from rag_agent import RagAgentService

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
    """发送消息给 RAG Agent 并获取回答"""
    try:
        result = rag_service.invoke(request.message, request.session_id)
        return ChatResponse(response=result, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
