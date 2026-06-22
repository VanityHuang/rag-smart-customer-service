# CLAUDE.md

此文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目概述

一个中文 RAG（检索增强生成）智能客服应用。用户上传文档到知识库，然后与 AI 助手聊天，助手通过 Function Calling 自主决定调用工具（知识库搜索、联网搜索、计算器）来回答问题。

## 技术栈

- **语言**: Python 3.12（`.python-version`）
- **Agent 框架**: LangChain（`bind_tools` + 自定义 Agent 循环）
- **向量数据库**: Chroma（本地持久化）
- **嵌入模型**: DashScopeEmbeddings（`text-embedding-v4`，阿里云）
- **对话模型**: ChatTongyi（`qwen3-max`，阿里云通义），必须传 `streaming=True` 否则 `stream()` 降级为非流式
- **UI（开发）**: Streamlit（两个独立应用）
- **UI（生产）**: 静态 HTML/CSS/JS（nginx serving），marked.js Markdown 渲染，SSE 流式消费
- **API**: FastAPI
- **流式响应**: SSE（Server-Sent Events），nginx `proxy_buffering off`
- **认证**: Bearer Token 单密码保护（通过 `AUTH_TOKEN` 环境变量配置，默认 `"guest"`）
- **聊天历史**: 基于 JSON 文件存储 + `sessions_metadata.json` 会话元数据
- **容器化**: Docker + docker-compose（Dockerfile 使用 `python:3.11-slim`，源码卷挂载 + `--reload` 热重载）

## 项目结构

| 文件 / 目录 | 用途 |
|------|------|
| `rag_agent.py` | **核心 Agent** — 自定义 Function Calling 循环，3 个工具（知识库搜索 / 联网搜索 / 计算器），对话历史管理；`stream()` 方法实现 SSE 流式生成；`_generate_title()` LLM 自动标题 |
| `knowledge_base.py` | 知识库服务 — 文本分割、MD5 去重、嵌入向量化 + 存入 Chroma，支持多格式文档 |
| `file_parser.py` | 多格式文档解析器 — TXT / MD / PDF（PyMuPDF）/ DOCX（python-docx）/ 图片 OCR（PaddleOCR，可切换 pytesseract） |
| `vector_stores.py` | Chroma 薄封装，提供 `get_retriever()` 和 `get_retriever_with_score()`（带相似度阈值检索） |
| `config_data.py` | 所有配置常量（模型名称、分块参数、Agent 配置、API 配置、OCR 后端、auth_token） |
| `file_history_store.py` | `FileChatMessageHistory`（LangChain 兼容）+ `SessionsMetadata`（会话元数据注册表，UTC 时区感知时间戳） |
| `evaluation.py` | RAG 评估体系 — Hit Rate、MRR、检索延迟 |
| `ui/` | Streamlit 界面 — `app_qa.py`（问答，支持 Direct/API 双模式）、`app_file_uploader.py`（知识库管理） |
| `api/` | FastAPI 后端 — `server.py`（入口 + Auth 中间件）、`chat.py`（非流式/流式/历史/会话管理端点）、`knowledge_base.py`（上传/列表/删除） |
| `tests/` | 测试脚本 — `test_modules.py`（模块级，含 .md 解析 + 会话元数据测试）、`test_knowledge_base.py`（知识库 CRUD）、`test_api.py`（API 端到端），`data/`（测试用文档含 test_markdown.md） |
| `docker/` | Docker 配置 — `Dockerfile`（apt 阿里云镜像 + build-essential）+ `docker-compose.yml`（127.0.0.1:8000 + 1GB 内存限制） |
| `web/` | 生产环境静态前端 — `index.html`（聊天界面）、`upload.html`（知识库管理），部署时复制到 nginx serving 目录 |
| `docs/` | 项目文档 — `diagrams/` 包含 4 张 Mermaid 架构图（架构总览/模块依赖/数据流/部署） |
| `/etc/nginx/sites-available/<project>` | nginx 反代配置 — `/rag/api/` → Docker、`/rag/` → `web/` 静态文件 |
| `/etc/systemd/system/rag-agent.service` | systemd 服务 — 管理 Docker 容器生命周期 |
| `data/` | 运行时数据 — `chroma_db/`（向量库）、`chat_history/`（聊天记录 + `sessions_metadata.json` 会话注册表）、`md5.text`（MD5 去重） |
| `requirements.txt` | Python 依赖清单 |
| `TESTING.md` | 7 层验证体系指南（从模块级到 Docker 全量测试） |
| `pytest.ini` | Pytest 配置（`addopts = -v --tb=short`，定义 `external` 标记） |

## 架构流程

1. **知识库导入**：`ui/app_file_uploader.py` → `file_parser.py`（多格式解析）→ `knowledge_base.py`（文本分割、MD5 去重、嵌入 + 存入 Chroma）

2. **会话管理**：前端自动创建 session_id → 首次对话后 LLM 生成标题 → `SessionsMetadata` 注册 → 侧边栏显示列表，支持重命名/删除/切换

3. **对话问答**：`ui/app_qa.py` 支持两种运行模式（`USE_API` 开关）：
   - **Direct Mode**（默认，`USE_API = False`）：直接 import `RagAgentService`，本地调用
   - **API Mode**（`USE_API = True`）：通过 `requests` 调用 FastAPI 后端（需先启动 API 服务）
   
   Agent 循环：SystemPrompt + 历史消息 + 用户输入 → `ChatTongyi.bind_tools([kb_search, web_search, calc])`
   - 有 tool_calls → 执行工具 → ToolMessage 追加 → 继续循环（最多 `agent_max_iterations` 轮）
   - 无 tool_calls → 返回最终回答 → 保存到 FileChatMessageHistory

## Agent 工具

| 工具 | 触发条件 | 实现 |
|------|----------|------|
| `knowledge_base_search` | 优先使用，查询本地知识库 | Chroma 向量检索 |
| `web_search` | 知识库无结果或需实时信息 | 百度新闻优先 + Bing（cn.bing.com）备用 |
| `calculator` | 数学计算需求 | `ast.parse` 安全求值白名单 |

## API 端点

所有 API 端点需要 `Authorization: Bearer guest` 请求头。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 发送消息，返回 Agent 回复（非流式） |
| `POST` | `/api/chat/stream` | 发送消息（SSE 流式，`text/event-stream`） |
| `GET` | `/api/chat/history?session_id=` | 获取会话聊天历史 |
| `GET` | `/api/chat/sessions` | 列出所有会话（按更新时间倒序） |
| `PUT` | `/api/chat/sessions/{session_id}` | 重命名会话 |
| `DELETE` | `/api/chat/sessions/{session_id}` | 删除会话（消息文件 + 元数据） |
| `POST` | `/api/knowledge-base/upload` | 上传文档到知识库 |
| `GET` | `/api/knowledge-base/documents` | 列出知识库所有文档 |
| `DELETE` | `/api/knowledge-base/documents/{source}` | 删除指定来源的文档 |

## 关键配置（`config_data.py`）

文本分割：
- `chunk_size`（100）/ `chunk_overlap`（20）/ `separators`：文本分割参数
- `min_split_char_number`（1000）：文档小于此字符数不触发分割

检索：
- `retriever_k`（3）：每次查询检索的文档数量

Agent：
- `AGENT_SYSTEM_PROMPT`：Agent 系统提示词（工具使用规则）
- `agent_max_iterations`（5）：Agent 最大工具调用轮数
- `agent_verbose`（True）：是否打印每次工具调用的日志

搜索：
- `web_search_max_results`（5）：联网搜索返回的最大结果数

模型：
- 嵌入：`text-embedding-v4`
- 对话：`qwen3-max`

OCR（双后端可配置）：
- `ocr_backend`（`"paddleocr"`）：OCR 后端 — `"paddleocr"` | `"pytesseract"`
- `ocr_language`（`"ch"`）/ `pytesseract_language`（`"chi_sim+eng"`）：各自语言参数
- `ocr_confidence_threshold`（0.5）：PaddleOCR 置信度阈值

Auth：
- `auth_token`（默认 `"guest"`，可通过 `AUTH_TOKEN` 环境变量覆盖）：API 认证共享密钥

## 常用命令

所有命令从仓库根目录执行：

```bash
# 启动问答聊天界面（Direct Mode, 端口 8501）
streamlit run ui/app_qa.py --server.port 8501

# 启动知识库管理界面（端口 8502）
streamlit run ui/app_file_uploader.py --server.port 8502

# 启动 FastAPI 后端（端口 8000）
python -m uvicorn api.server:app --reload

# Docker 全量启动
cd docker && docker-compose up --build

# 模块级验证（无需 API Key）
python -m pytest tests/test_modules.py -v

# 全部测试（需 API Key，自动跳过缺 Key 的测试）
python -m pytest tests/ -v

# 仅跑无需 API Key 的测试
python -m pytest tests/ -v -m "not external"

# Agent 命令行交互测试
python rag_agent.py

# RAG 评估
python evaluation.py

# 运行特定测试
python -m pytest tests/test_modules.py -v -k "txt"
python -m pytest tests/test_knowledge_base.py -v
python -m pytest tests/test_api.py -v
```

## 生产部署（<your-domain.com>/rag）

项目通过 Docker + nginx 反向代理部署在 `<your-domain.com>/rag`。

### 架构

```
https://<your-domain.com>/rag/               → web/ 静态文件 (nginx serving HTML/JS)
https://<your-domain.com>/rag/api/chat/stream→ nginx proxy_buffering off → 127.0.0.1:8000 (SSE)
https://<your-domain.com>/rag/api/*          → nginx rewrite → 127.0.0.1:8000 (FastAPI Docker)
```

### 热重载开发

`docker-compose.yml` 已将 Python 源码卷挂载到容器，配合 uvicorn `--reload`：
- 改 Python 代码 → docker compose restart（~2 秒生效）
- 改前端 HTML → 直接保存（nginx 直接 serve，0 秒生效）
- 只有 `requirements.txt` 或 `Dockerfile` 变更才需重建镜像

### 运维命令

```bash
# 服务管理
sudo systemctl start rag-agent.service    # 启动
sudo systemctl stop rag-agent.service     # 停止
sudo systemctl restart rag-agent.service  # 重启（代码更新后）

# 源码已卷挂载，restart 即可，无需重建
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml restart

# 查看日志
sudo journalctl -u rag-agent.service -f
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml logs -f

# 更新代码
cd ~/my_projects/RAG && git pull
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml restart

# 重建镜像（仅 requirements.txt 或 Dockerfile 变更时需要）
cd ~/my_projects/RAG/docker
sudo docker compose build
sudo docker compose up -d
```

### Docker 构建注意事项

- Dockerfile 将 apt 源换为阿里云镜像（国内服务器加速）
- pip 使用阿里云 PyPI 镜像（`-i https://mirrors.aliyun.com/pypi/simple/`）
- 需要 `build-essential`（`stringzilla` 编译需要 gcc + libc6-dev）
- PaddleOCR 模型**不在构建时预下载**（服务器内存不足导致 segfault），首次 OCR 调用时自动拉取
- 构建前确保 `data/md5.text` 文件存在，否则 Docker 会创建同名目录
- 容器内存限制 1GB（`docker-compose.yml` 中 `mem_limit: 1g`）
- **pip 层永久缓存**：只要 `requirements.txt` 不变，pip 安装层永久缓存。不要手动 `docker builder prune`

### 环境变量

需要两个：`DASHSCOPE_API_KEY` 和 `AUTH_TOKEN`，存储在 `docker/.env`，docker-compose 自动读取。

### 访问地址

| 页面 | URL |
|------|-----|
| 聊天界面 | `https://<your-domain.com>/rag/` |
| 知识库管理 | `https://<your-domain.com>/rag/upload.html` |
| 导航页 | `https://<your-domain.com>/` |
| API（内部） | `http://127.0.0.1:8000` |
