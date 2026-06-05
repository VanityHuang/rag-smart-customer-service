# CLAUDE.md

此文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 项目概述

一个中文 RAG（检索增强生成）智能客服应用。用户上传文档到知识库，然后与 AI 助手聊天，助手通过 Function Calling 自主决定调用工具（知识库搜索、联网搜索、计算器）来回答问题。

## 技术栈

- **语言**: Python 3.12（`.python-version`）
- **Agent 框架**: LangChain（`bind_tools` + 自定义 Agent 循环）
- **向量数据库**: Chroma（本地持久化）
- **嵌入模型**: DashScopeEmbeddings（`text-embedding-v4`，阿里云）
- **对话模型**: ChatTongyi（`qwen3-max`，阿里云通义）
- **UI**: Streamlit（两个独立应用）
- **API**: FastAPI
- **聊天历史**: 基于 JSON 文件存储
- **容器化**: Docker + docker-compose（Dockerfile 使用 `python:3.11-slim`）

## 项目结构

| 文件 / 目录 | 用途 |
|------|------|
| `rag_agent.py` | **核心 Agent** — 自定义 Function Calling 循环，3 个工具（知识库搜索 / 联网搜索 / 计算器），对话历史管理 |
| `knowledge_base.py` | 知识库服务 — 文本分割、MD5 去重、嵌入向量化 + 存入 Chroma，支持多格式文档 |
| `file_parser.py` | 多格式文档解析器 — TXT / PDF（PyMuPDF）/ DOCX（python-docx）/ 图片 OCR（PaddleOCR，可切换 pytesseract） |
| `vector_stores.py` | Chroma 薄封装，提供 `get_retriever()` 和 `get_retriever_with_score()`（带相似度阈值检索） |
| `config_data.py` | 所有配置常量（模型名称、分块参数、Agent 配置、API 配置、OCR 后端） |
| `file_history_store.py` | 基于文件的 `BaseChatMessageHistory` 实现（每个 session_id 对应一个 JSON 文件） |
| `evaluation.py` | RAG 评估体系 — Hit Rate、MRR、检索延迟 |
| `ui/` | Streamlit 界面 — `app_qa.py`（问答，支持 Direct/API 双模式）、`app_file_uploader.py`（知识库管理） |
| `api/` | FastAPI 后端 — `server.py`（入口）、`chat.py`（`POST /api/chat`）、`knowledge_base.py`（上传/列表/删除） |
| `tests/` | 测试脚本 — `test_modules.py`（模块级）、`test_knowledge_base.py`（知识库 CRUD）、`test_api.py`（API 端到端），`data/`（测试用文档） |
| `docker/` | Docker 配置 — `Dockerfile` + `docker-compose.yml` |
| `data/` | 运行时数据 — `chroma_db/`（向量库）、`chat_history/`（聊天记录）、`md5.text`（MD5 去重） |
| `requirements.txt` | Python 依赖清单 |
| `TESTING.md` | 7 层验证体系指南（从模块级到 Docker 全量测试） |
| `pytest.ini` | Pytest 配置（`addopts = -v --tb=short`，定义 `external` 标记） |

## 架构流程

1. **知识库导入**：`ui/app_file_uploader.py` → `file_parser.py`（多格式解析）→ `knowledge_base.py`（文本分割、MD5 去重、嵌入 + 存入 Chroma）

2. **对话问答**：`ui/app_qa.py` 支持两种运行模式（`USE_API` 开关）：
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

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 发送消息，返回 Agent 回复 |
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
