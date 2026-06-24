# 服务层 + 基础设施 + 外部服务

```mermaid
flowchart TD
  agent["RagAgentService\nAgent Loop + Tools + Stream"]
  kb_svc["KnowledgeBaseService\n分块 嵌入 去重"]
  parser["file_parser\nTXT/MD/PDF/DOCX/图片OCR"]
  history["FileChatMessageHistory\nJSON + SessionsMetadata"]
  vs["VectorStoreService\nChroma retriever_k=15"]
  deps["api/deps.py\n角色服务工厂"]
  auth["api/auth.py\nBearer Token 角色识别"]
  mw["api/middleware.py\nAuthRoleMiddleware"]
  rl["api/rate_limit.py\nguest IP 每小时限流"]

  docker["Docker python:3.11-slim"]
  chroma["Chroma 向量库"]
  chat_f["聊天历史文件"]
  systemd_s["systemd 服务管理"]

  dash["DashScope qwen3.5-flash\nChatOpenAI 兼容接口"]
  sf["SiliconFlow\nBAAI/bge-large-zh-v1.5 嵌入"]
  search["联网搜索 baidu bing"]

  agent --> docker
  agent --> dash
  agent --> search
  deps --> agent
  deps --> kb_svc
  auth --> mw
  mw --> rl
  kb_svc --> chroma
  kb_svc --> sf
  parser --> kb_svc
  history --> agent
  vs --> agent
  history --> chat_f
  docker --> systemd_s

  classDef svc fill:#E1BEE7,stroke:#6A1B9A,stroke-width:2px
  classDef infra fill:#FFCCBC,stroke:#BF360C,stroke-width:2px
  classDef ext fill:#B2EBF2,stroke:#006064,stroke-width:2px
  class agent,kb_svc,parser,history,vs,deps,auth,mw,rl svc
  class docker,chroma,chat_f,systemd_s infra
  class dash,sf,search ext
```
