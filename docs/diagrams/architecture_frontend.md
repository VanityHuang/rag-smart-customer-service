# 前端 + 反代 + API 层

```mermaid
flowchart TD
  index["index.html 聊天 SSE"]
  upload_p["upload.html 知识库管理"]

  nginx_s["/rag/ 静态文件"]
  nginx_api["/rag/api/* proxy_pass :8000"]
  nginx_sse["/rag/api/chat/stream SSE"]

  chat["/api/chat + /api/chat/stream"]
  sessions["/api/chat/sessions CRUD"]
  kb_api["/api/knowledge-base CRUD"]
  auth["Auth HTTPBearer"]

  index --> nginx_s
  index --> nginx_sse
  upload_p --> nginx_api

  nginx_sse --> chat
  nginx_api --> sessions & kb_api & auth

  classDef ui fill:#BBDEFB,stroke:#1565C0,stroke-width:2px
  classDef proxy fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px
  classDef api fill:#FFE0B2,stroke:#E65100,stroke-width:2px
  class index,upload_p ui
  class nginx_s,nginx_api,nginx_sse proxy
  class chat,sessions,kb_api,auth api
```
