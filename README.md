# RAG Smart Customer Service

基于 **LangChain Function Calling** 的中文 RAG 智能客服系统。支持本地知识库检索、联网搜索、数学计算，提供 Streamlit 交互界面和 FastAPI 后端，可 Docker 容器化部署。

## 技术栈

| 层 | 技术 |
|------|------|
| Agent 框架 | LangChain（`bind_tools` + 自定义 Agent 循环） |
| 对话模型 | 通义千问 `qwen3-max`（阿里云 DashScope） |
| 嵌入模型 | `text-embedding-v4`（阿里云 DashScope） |
| 向量数据库 | Chroma（本地持久化） |
| 文档解析 | PyMuPDF（PDF）、python-docx（DOCX）、PaddleOCR（图片，可切换 Tesseract） |
| UI | Streamlit（问答界面 + 知识库管理） |
| API | FastAPI + uvicorn |
| 容器化 | Docker + docker-compose |

## 功能

- **多格式知识库** — 上传 TXT / PDF / DOCX / 图片到知识库，自动分割 + 向量化 + MD5 去重
- **Function Calling Agent** — 三个工具：
  - `knowledge_base_search` — 从本地知识库检索相关内容
  - `web_search` — 联网搜索（百度新闻 + Bing 备用）
  - `calculator` — 安全数学计算
- **多轮对话记忆** — 基于 JSON 文件的 `BaseChatMessageHistory`
- **双 Streamlit 界面** — 问答聊天 + 知识库文件管理
- **RESTful API** — FastAPI 提供 `/api/chat`、`/api/knowledge` 接口
- **Docker 部署** — 一键容器化启动
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
├── ui/                    # Streamlit 界面
│   ├── app_qa.py          # 问答聊天界面
│   └── app_file_uploader.py  # 知识库管理界面
├── api/                   # FastAPI 后端
│   ├── server.py          # 入口
│   ├── chat.py            # 聊天 API
│   └── knowledge_base.py  # 知识库 API
├── docker/                # 容器配置
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/                 # 测试
│   └── data/              # 测试文档
├── data/                  # 运行时数据（git ignored）
│   ├── chroma_db/         # 向量数据库
│   ├── chat_history/      # 聊天记录
│   └── md5.text           # MD5 去重记录
├── rag_agent.py           # Agent 核心（Function Calling 循环）
├── knowledge_base.py      # 知识库服务（分割 / 嵌入 / 去重）
├── vector_stores.py       # Chroma 检索封装
├── file_parser.py         # 多格式文档解析器
├── file_history_store.py  # 聊天历史存储
├── evaluation.py          # RAG 评估（Hit Rate / MRR / 延迟）
├── config_data.py         # 全局配置
└── requirements.txt
```

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

## License

MIT
