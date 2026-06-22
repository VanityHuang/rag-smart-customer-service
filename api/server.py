"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import chat, knowledge_base
from api.middleware import AuthRoleMiddleware
import config_data as config

app = FastAPI(
    title="RAG Agent API",
    description="RAG Agent with knowledge base search, web search, and calculator",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 双角色认证中间件 ──
app.add_middleware(AuthRoleMiddleware)

app.include_router(
    chat.router,
    prefix="/api/chat",
    tags=["Chat"],
)
app.include_router(
    knowledge_base.router,
    prefix="/api/knowledge-base",
    tags=["Knowledge Base"],
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.api_host, port=config.api_port)
