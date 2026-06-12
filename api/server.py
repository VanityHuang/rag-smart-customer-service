"""FastAPI 应用入口"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api import chat, knowledge_base
import config_data as config

app = FastAPI(
    title="RAG Agent API",
    description="RAG Agent with knowledge base search, web search, and calculator",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 单密码认证 ──
security = HTTPBearer(auto_error=False)


async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """简单的共享密钥认证。auto_error=False 允许 OPTIONS 预检通过。"""
    if credentials is None or credentials.credentials != config.auth_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")


app.include_router(
    chat.router,
    prefix="/api/chat",
    tags=["Chat"],
    dependencies=[Depends(verify_auth)],
)
app.include_router(
    knowledge_base.router,
    prefix="/api/knowledge-base",
    tags=["Knowledge Base"],
    dependencies=[Depends(verify_auth)],
)


if __name__ == "__main__":
    import uvicorn
    import config_data as config
    uvicorn.run(app, host=config.api_host, port=config.api_port)
