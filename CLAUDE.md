# CLAUDE.md

此文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目概述

一个中文 RAG（检索增强生成）智能客服应用。用户上传文档到知识库，然后与 AI 助手聊天，助手通过 Function Calling 自主决定调用工具（知识库搜索、联网搜索、计算器）来回答问题。

## 技术栈

- **语言**: Python 3.12（`.python-version`）
- **Agent 框架**: LangChain（`bind_tools` + 自定义 Agent 循环）
- **向量数据库**: Chroma（本地持久化）
- **嵌入模型**: DashScopeEmbeddings（`text-embedding-v4`，阿里云）
- **对话模型**: ChatTongyi（`qwen3-max-preview`，阿里云通义），必须传 `streaming=True` 否则 `stream()` 降级为非流式
- **UI（开发）**: Streamlit（两个独立应用）
- **UI（生产）**: 静态 HTML/CSS/JS（nginx serving），marked.js Markdown 渲染，SSE 流式消费
- **API**: FastAPI
- **流式响应**: SSE（Server-Sent Events），nginx `proxy_buffering off`
- **认证**: Bearer Token 双角色认证（`ADMIN_TOKEN` / `GUEST_TOKEN` 环境变量，密码只在 `.env` 中配置，Python 代码零硬编码）
- **角色隔离**: admin / guest 功能完全一致，仅限流（guest 每小时 10 次）和数据隔离不同
- **聊天历史**: 基于 JSON 文件存储 + `sessions_metadata.json` 会话元数据
- **容器化**: Docker + docker-compose（Dockerfile 使用 `python:3.11-slim`，源码卷挂载 + `--reload` 热重载）

## 项目结构

| 文件 / 目录 | 用途 |
|------|------|
| `rag_agent.py` | **核心 Agent** — 自定义 Function Calling 循环，3 个工具（知识库搜索 / 联网搜索 / 计算器），对话轮次截断（`MAX_HISTORY_ROUNDS=5`），Token 用量追踪（持久化到会话元数据）；`stream()` 方法实现 SSE 流式生成；`_generate_title()` LLM 自动标题 |
| `knowledge_base.py` | 知识库服务 — 文本分割、MD5 去重、嵌入向量化 + 存入 Chroma，支持多格式文档，时间戳使用北京时间（UTC+8） |
| `file_parser.py` | 多格式文档解析器 — TXT / MD / PDF（PyMuPDF）/ DOCX（python-docx）/ 图片 OCR（RapidOCR，ONNX Runtime） |
| `vector_stores.py` | Chroma 薄封装，提供 `get_retriever()` 和 `get_retriever_with_score()`（带相似度阈值检索） |
| `config_data.py` | 所有配置常量（模型名称、分块参数、Agent 配置、API 配置、双角色 token） |
| `file_history_store.py` | `FileChatMessageHistory`（LangChain 兼容）+ `SessionsMetadata`（会话元数据注册表，角色化存储路径） |
| `evaluation.py` | RAG 评估体系 — Hit Rate、MRR、检索延迟 |
| `api/` | FastAPI 后端 — `server.py`（入口 + Auth 中间件）、`chat.py`（角色化聊天端点 + 输入内容前置拦截）、`knowledge_base.py`（角色化 KB 管理）、`auth.py`（角色认证）、`rate_limit.py`（guest IP 限流）、`middleware.py`（认证中间件）、`deps.py`（角色服务工厂） |
| `tests/` | 测试脚本 — `test_api.py`（API 冒烟，覆盖全部端点 + 认证 + 限流）、`locustfile.py`（Locust 压测）、`test_rag_precision_grid.py`（RAG 参数遍历）、`prod_verify.sh`（生产环境巡检）、`data/`（测试用文档） |
| `bug_and_fix.md` | Bug 修复记录（Token 截断 bug、Agent 空回答 bug） |
| `docker/` | Docker 配置 — `Dockerfile`（apt 阿里云镜像 + build-essential）+ `docker-compose.yml`（127.0.0.1:8000 + 1GB 内存限制） |
| `web/` | 生产环境静态前端 — `index.html`（聊天界面）、`upload.html`（知识库管理），部署时复制到 nginx serving 目录 |
| `docs/` | 项目文档 — `diagrams/` 包含 4 张 Mermaid 架构图（架构总览/模块依赖/数据流/部署） |
| `/etc/nginx/sites-available/<project>` | nginx 反代配置 — `/rag/api/` → Docker、`/rag/` → `web/` 静态文件 |
| `/etc/systemd/system/rag-agent.service` | systemd 服务 — 管理 Docker 容器生命周期 |
| `data/` | 运行时数据 — `chroma_db/{admin,guest}/`（角色化向量库）、`chat_history/{admin,guest}/`（角色化聊天记录 + 元数据）、`md5_{admin,guest}.txt`（角色化 MD5 去重）、`rate_limit.json`（guest 限流计数） |
| `requirements.txt` | Python 依赖清单 |
| `TESTING.md` | 6 层结果类测试体系指南（API 冒烟 / Docker 构建 / RAG 评估 / 压测 / 参数遍历 / 生产验证） |
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

所有 API 端点需要 `Authorization: Bearer <password>` 请求头（密码在 `docker/.env` 中配置）。
- **admin**（`admin2026`）：完全访问，不限次数
- **guest**（`guest123`）：功能完全一致，每小时 10 次 IP 限流，数据与 admin 隔离

| 方法 | 路径 | 角色 | 说明 |
|------|------|------|------|
| `POST` | `/api/chat` | admin/guest | 发送消息，返回 Agent 回复（非流式，含累计 token_usage） |
| `POST` | `/api/chat/stream` | admin/guest | 发送消息（SSE 流式，`text/event-stream`，含累计 token_usage） |
| `GET` | `/api/chat/history?session_id=` | admin/guest | 获取会话聊天历史 |
| `GET` | `/api/chat/sessions` | admin/guest | 列出所有会话（按更新时间倒序） |
| `PUT` | `/api/chat/sessions/{session_id}` | admin/guest | 重命名会话 |
| `DELETE` | `/api/chat/sessions/{session_id}` | admin/guest | 删除会话（消息文件 + 元数据） |
| `POST` | `/api/knowledge-base/upload` | admin/guest | 上传文档到知识库 |
| `GET` | `/api/knowledge-base/documents` | admin/guest | 列出知识库所有文档 |
| `DELETE` | `/api/knowledge-base/documents/{source}` | admin/guest | 删除指定来源的文档 |

## 关键配置（`config_data.py`）

文本分割：
- `chunk_size`（256）/ `chunk_overlap`（32）/ `separators`：文本分割参数
- `min_split_char_number`（1000）：文档小于此字符数不触发分割

检索：
- `retriever_k`（15）：每次查询检索的文档数量（调优推荐）

Agent：
- `AGENT_SYSTEM_PROMPT`：Agent 系统提示词（工具使用规则 + 拒答规则）
- `agent_max_iterations`（5）：Agent 最大工具调用轮数
- `agent_verbose`（True）：是否打印每次工具调用的日志
- `MAX_HISTORY_ROUNDS`（5）：保留最近 5 轮对话上下文

搜索：
- `web_search_max_results`（5）：联网搜索返回的最大结果数

模型：
- 嵌入：`text-embedding-v4`
- 对话：`qwen3-max`

OCR：
- `ocr_language`（`"ch"`）：RapidOCR 语言参数（支持中英文）
- `ocr_confidence_threshold`（0.5）：RapidOCR 置信度阈值

Auth：
- `admin_token`（通过 `ADMIN_TOKEN` 环境变量配置）：管理员密码
- `guest_token`（通过 `GUEST_TOKEN` 环境变量配置）：访客密码
- `guest_daily_limit`（10）：访客每小时提问次数上限

## 常用命令

所有命令从仓库根目录执行：

```bash
# 启动 FastAPI 后端（端口 8000）
python -m uvicorn api.server:app --reload

# Docker 全量启动
cd docker && docker-compose up --build

# API 冒烟测试（需服务运行）
python -m pytest tests/test_api.py -v

# RAG 评估
python evaluation.py

# Locust 压测
locust -f tests/locustfile.py --host=http://localhost:8000

# RAG 参数遍历
python -m pytest tests/test_rag_precision_grid.py -v

# 生产环境巡检
bash tests/prod_verify.sh
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
- 需要 `libgl1`、`libglib2.0-0`、`libxcb1`（OpenCV/RapidOCR 运行时依赖）
- 生产环境使用 `requirements-prod.txt`（不含 streamlit/pytest）
- 容器内存限制 1GB（`docker-compose.yml` 中 `mem_limit: 1g`）
- **pip 层永久缓存**：只要 `requirements-prod.txt` 不变，pip 安装层永久缓存。不要手动 `docker builder prune`

### 环境变量

存储在 `docker/.env`，docker-compose 自动读取：
- `DASHSCOPE_API_KEY`：阿里云 DashScope API Key
- `ADMIN_TOKEN`：管理员密码（完全访问所有功能）
- `GUEST_TOKEN`：访客密码（功能与 admin 一致，每小时 10 次 IP 限流，数据隔离）
- `RAG_PROD_URL`：冒烟测试生产地址（`https://yellowduck.top/rag`）
- `RAG_TEST_TOKEN`：冒烟测试 Bearer token（`guest123`）

### 访问地址

| 页面 | URL |
|------|-----|
| 聊天界面 | `https://<your-domain.com>/rag/` |
| 知识库管理 | `https://<your-domain.com>/rag/upload.html` |
| 导航页 | `https://<your-domain.com>/` |
| API（内部） | `http://127.0.0.1:8000` |
