# RAG Smart Customer Service

基于 **LangChain Function Calling** 的中文 RAG 智能客服系统。支持本地知识库检索、联网搜索、数学计算，提供静态前端 + FastAPI 后端，Docker 容器化部署。

## 技术栈

| 层 | 技术 |
|------|------|
| Agent 框架 | LangChain（`bind_tools` + 自定义 Agent 循环） |
| 对话模型 | 通义千问 `qwen3-max`（阿里云 DashScope） |
| 嵌入模型 | `text-embedding-v4`（阿里云 DashScope） |
| 向量数据库 | Chroma（本地持久化） |
| 文档解析 | PyMuPDF（PDF）、python-docx（DOCX）、PaddleOCR（图片，可切换 Tesseract） |
| 前端（开发） | Streamlit（问答界面 + 知识库管理） |
| 前端（生产） | 静态 HTML/CSS/JS（nginx 直接 serving） |
| API | FastAPI + uvicorn |
| 流式响应 | SSE（Server-Sent Events） |
| Markdown 渲染 | marked.js + DOMPurify（前端） |
| 认证 | Bearer Token 单密码保护 |
| 容器化 | Docker + docker-compose |

## 功能

- **多格式知识库** — 上传 TXT / MD / PDF / DOCX / 图片到知识库，自动分割 + 向量化 + MD5 去重
- **Function Calling Agent** — 三个工具：
  - `knowledge_base_search` — 从本地知识库检索相关内容
  - `web_search` — 联网搜索（百度新闻 + Bing 备用）
  - `calculator` — 安全数学计算
- **流式打字机效果** — SSE 实时流式输出，token 逐字渲染
- **Markdown 渲染** — 表格、代码块、列表等格式正确展示
- **多轮对话记忆** — 基于 JSON 文件的 `BaseChatMessageHistory`，刷新页面后自动加载历史
- **会话管理** — 侧边栏对话列表，支持新建/切换/重命名/删除，LLM 自动生成标题
- **用户认证** — Bearer Token 单密码保护（API + 前端）
- **RESTful API** — FastAPI 提供聊天、流式、历史、知识库接口
- **Docker 部署** — 源码卷挂载 + uvicorn `--reload` 热重载，代码改动秒级生效
- **评估体系** — Hit Rate / MRR / 检索延迟指标

## 快速开始

### 前置条件

```bash
# 安装依赖
cd RAG
pip install -r requirements.txt

# 设置阿里云 DashScope API Key
export DASHSCOPE_API_KEY=sk-xxxxxx
```

### 启动 UI 界面

```bash
# 终端 1：问答界面（端口 8501）
streamlit run ui/app_qa.py --server.port 8501

# 终端 2：知识库管理（端口 8502）
streamlit run ui/app_file_uploader.py --server.port 8502
```

### 启动 API 服务

```bash
python -m uvicorn api.server:app --reload
```

### Docker 部署

```bash
cd docker
docker-compose up --build
```

### 命令行测试

```bash
python rag_agent.py
```

## 项目结构

```
RAG/
├── ui/                    # Streamlit 界面（开发用）
│   ├── app_qa.py          # 问答聊天界面
│   └── app_file_uploader.py  # 知识库管理界面
├── api/                   # FastAPI 后端
│   ├── server.py          # 入口（含 Auth 中间件）
│   ├── chat.py            # 聊天 API（含流式 + 历史端点）
│   └── knowledge_base.py  # 知识库 API
├── docker/                # 容器配置
│   ├── Dockerfile
│   └── docker-compose.yml
├── web/                   # 生产环境静态前端
│   ├── index.html         # 聊天界面
│   └── upload.html        # 知识库管理
├── tests/                 # 测试
│   └── data/              # 测试文档（.txt/.pdf/.docx/.png/.md）
├── data/                  # 运行时数据（git ignored）
│   ├── chroma_db/         # 向量数据库
│   ├── chat_history/      # 聊天记录 + sessions_metadata.json
│   └── md5.text           # MD5 去重记录
├── rag_agent.py           # Agent 核心（Function Calling 循环 + 流式生成）
├── knowledge_base.py      # 知识库服务（分割 / 嵌入 / 去重）
├── vector_stores.py       # Chroma 检索封装
├── file_parser.py         # 多格式文档解析器（支持 TXT/MD/PDF/DOCX/图片）
├── file_history_store.py  # 聊天历史存储（文件 + 会话元数据）
├── evaluation.py          # RAG 评估（Hit Rate / MRR / 延迟）
├── config_data.py         # 全局配置（含 auth_token）
└── requirements.txt
```

## API 端点

所有 API 端点需要 `Authorization: Bearer <token>` 请求头（token 通过 `AUTH_TOKEN` 环境变量配置）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 发送消息（非流式） |
| `POST` | `/api/chat/stream` | 发送消息（SSE 流式） |
| `GET` | `/api/chat/history?session_id=` | 获取会话聊天历史 |
| `GET` | `/api/chat/sessions` | 列出所有会话 |
| `PUT` | `/api/chat/sessions/{session_id}` | 重命名会话 |
| `DELETE` | `/api/chat/sessions/{session_id}` | 删除会话 |
| `POST` | `/api/knowledge-base/upload` | 上传文档到知识库 |
| `GET` | `/api/knowledge-base/documents` | 列出知识库所有文档 |
| `DELETE` | `/api/knowledge-base/documents/{source}` | 删除指定来源的文档 |

## 评估

```bash
cd RAG
python evaluation.py
```

评估自动播种测试文档、运行检索评估、清理数据，不干扰已有知识库。

输出示例：
```
查询                           难度           命中       RR
----------------------------------------------------
毛衣怎么保养                       easy         OK 1.00
实木家具保养方法有哪些                  easy         OK 1.00
冬天的厚外套怎么清洗                   hard         OK 1.00

  [easy] Hit Rate: 3/3 (100%)  MRR: 100.00%
  [medium] Hit Rate: 3/3 (100%)  MRR: 100.00%
  [hard] Hit Rate: 3/3 (100%)  MRR: 100.00%

  [总计] Hit Rate: 100.00%  (9/9)
  [总计] MRR:      100.00%
```

## 生产部署

项目已部署在 `<your-domain.com>/rag`，通过 Docker + nginx 反向代理运行。

```
浏览器 ──https──→ nginx (<your-domain.com>)
                   │
                   ├── /rag/               → web/ 静态前端（聊天 + 知识库管理）
                   ├── /rag/api/chat/stream→ SSE 流式端点（proxy_buffering off）
                   └── /rag/api/*          → FastAPI Docker 容器 (127.0.0.1:8000)
```

### 服务器配置

| 组件 | 位置 |
|------|------|
| 静态前端 | `web/`（复制到 nginx serving 目录） |
| Docker 镜像 | `docker-rag-agent:latest` (~1.3 GB) |
| systemd 服务 | `rag-agent.service` |
| API Key 配置 | `/home/admin/my_projects/RAG/docker/.env` |
| nginx 配置 | `/etc/nginx/sites-available/&lt;project&gt;` |

### 常用运维命令

```bash
# 启动 / 停止 / 重启
sudo systemctl start rag-agent.service
sudo systemctl stop rag-agent.service
sudo systemctl restart rag-agent.service   # 代码更新后

# 查看日志
sudo journalctl -u rag-agent.service -f
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml logs -f

# 更新代码（源码已卷挂载，restart 即可，无需重建）
cd ~/my_projects/RAG && git pull
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml restart

# 重建镜像（仅 requirements.txt 或 Dockerfile 变更时需要）
cd ~/my_projects/RAG/docker
sudo docker compose build
sudo docker compose up -d
```

### Docker 构建说明

- Dockerfile 已将 apt 源替换为阿里云镜像，pip 使用阿里云 PyPI 镜像
- 安装 `build-essential`（`stringzilla` 等包需要 C 编译）
- PaddleOCR 模型不在构建时预下载（服务器内存限制），首次运行时会自动拉取
- 构建前确保 `data/md5.text` 文件存在（`touch` 即可），否则 Docker 会将其创建为目录
- 容器内存限制 1GB（`docker-compose.yml` 中 `mem_limit: 1g`）
- **pip 层缓存**：只要 `requirements.txt` 不变，pip 安装层永久缓存。不要主动运行 `docker builder prune`
- **源码卷挂载**：`docker-compose.yml` 已将 Python 源码目录挂载进容器，配合 uvicorn `--reload`，代码改动无需重建镜像（仅重启 ~2 秒）

### 环境变量

需要两个：`DASHSCOPE_API_KEY` 和 `AUTH_TOKEN`，存储在 `docker/.env`，docker-compose 自动读取。

### 访问地址

| 页面 | URL |
|------|-----|
| 聊天界面 | `https://<your-domain.com>/rag/` |
| 知识库管理 | `https://<your-domain.com>/rag/upload.html` |
| 导航页 | `https://<your-domain.com>/` |
| API（内部） | `http://127.0.0.1:8000` |

## License

MIT
