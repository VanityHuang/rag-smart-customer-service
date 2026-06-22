"""角色感知服务工厂 — 按角色返回独立的 RAG / KB 服务实例"""
from rag_agent import RagAgentService
from knowledge_base import KnowledgeBaseService
from vector_stores import VectorStoreService
from langchain_community.embeddings import DashScopeEmbeddings
import config_data as config

_role_rag = {}
_role_kb = {}

# 每个角色的存储路径
_ROLE_CONFIG = {
    "admin": {
        "collection_name": "rag_admin",
        "persist_directory": "./data/chroma_db/admin",
        "md5_path": "./data/md5_admin.txt",
        "chat_history": "./data/chat_history/admin",
    },
    "guest": {
        "collection_name": "rag_guest",
        "persist_directory": "./data/chroma_db/guest",
        "md5_path": "./data/md5_guest.txt",
        "chat_history": "./data/chat_history/guest",
    },
}


def get_role_config(role: str) -> dict:
    return _ROLE_CONFIG.get(role, _ROLE_CONFIG["admin"])


def get_rag_service(role: str) -> RagAgentService:
    if role not in _role_rag:
        cfg = get_role_config(role)
        vs = VectorStoreService(
            embedding=DashScopeEmbeddings(model=config.embedding_model_name),
            collection_name=cfg["collection_name"],
            persist_directory=cfg["persist_directory"],
        )
        _role_rag[role] = RagAgentService(vector_service=vs, role=role)
    return _role_rag[role]


def get_kb_service(role: str) -> KnowledgeBaseService:
    if role not in _role_kb:
        cfg = get_role_config(role)
        _role_kb[role] = KnowledgeBaseService(
            persist_directory=cfg["persist_directory"],
            md5_path=cfg["md5_path"],
            collection_name=cfg["collection_name"],
        )
    return _role_kb[role]
