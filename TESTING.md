# RAG Agent 验证指南

一键运行即可，不用复制粘贴长命令。

## 前置条件

```bash
# 确认环境变量已设置（必须有）
echo $DASHSCOPE_API_KEY

# Windows PowerShell:
# echo $env:DASHSCOPE_API_KEY
```

> **没有 API Key？** 去 [阿里云 DashScope](https://dashscope.aliyun.com/) 创建，然后 `export DASHSCOPE_API_KEY=sk-xxxxxx`。

---

## 测试脚本一览

| 层级 | 命令 | 测试内容 | 需 API Key |
|------|------|----------|:----------:|
| ① 模块级 | `python -m pytest tests/test_modules.py -v` | 导入 + 文件解析（含 .md） | 否 |
| ② Agent 对话 | `python rag_agent.py` | 命令行聊天互动 | 是 |
| ③ 知识库 CRUD | `python -m pytest tests/test_knowledge_base.py -v` | 上传/列表/删除 | 是 |
| ④ API 接口 | `python -m pytest tests/test_api.py -v` | 自动启停 + 测接口 | 是 |
| ⑤ Streamlit UI | `streamlit run ui/app_qa.py` | 问答界面（手动操作） | 是 |
| ⑥ Docker | `cd docker && docker-compose up --build` | 容器化全量测试 | 是 |
| ⑦ RAG 评估 | `python evaluation.py` | 命中率/延迟指标 | 是 |
| ⑧ 生产验证 | 见下方 curl 命令 | yellowduck.top 线上 API + 前端 | 是 |

---

## 第 ① 层：模块级验证（无需 API Key）

```bash
python -m pytest tests/test_modules.py -v
```

可选参数（只跑特定项）：

```bash
python -m pytest tests/test_modules.py -v -k "txt"
python -m pytest tests/test_modules.py -v -k "md"
python -m pytest tests/test_modules.py -v -k "pdf"
```

测试项：
- 所有模块能否正常导入
- TXT 解析（自动创建临时文件，测完删除）
- MD（Markdown）解析
- PDF / DOCX 解析（需在 `tests/data/` 下有对应文件）
- 图片 OCR 解析（需 `tests/data/test_ocr.png`）

---

## 第 ② 层：Agent 对话测试

```bash
python rag_agent.py
```

| 输入 | 预期 |
|------|------|
| `你好` | 基础对话 |
| `计算 25 * 4 + 100` | 调用计算器，返回 200 |
| `我刚才问了什么？` | 检查对话记忆 |
| `今天有什么新闻？` | 联网搜索 |
| `福建杨梅有什么新闻？` | 百度新闻搜索 |
| `q` | 退出 |

---

## 第 ③ 层：知识库功能测试

```bash
python -m pytest tests/test_knowledge_base.py -v
```

自动测试：
1. 上传一段文本到 Chroma
2. 列出知识库所有文档
3. 删除刚上传的文档并确认
4. 如 `tests/data/` 下有 `test_sample.pdf` 等，也会测试文件上传

---

## 第 ④ 层：API 接口测试

```bash
python -m pytest tests/test_api.py -v
```

> **注意**：API 测试需要带 `Authorization: Bearer <token>` 请求头，默认 token 为 `guest`。端口 8000 被占用？修改 `tests/test_api.py` 中的 `BASE_URL` 和 port。

自动完成：启动服务器 → 测聊天接口 → 测上传 → 测列表 → 关闭服务器

---

## 第 ⑤ 层：Streamlit UI 测试

```bash
# 终端 1：问答界面（端口 8501）
streamlit run ui/app_qa.py --server.port 8501

# 终端 2：知识库管理（端口 8502）
streamlit run ui/app_file_uploader.py --server.port 8502
```

测试流程：
1. 知识库管理界面上传文件（含 .md 文件）
2. 问答界面提问文件内容
3. 提问 `25*4+100 等于多少` → 应调计算器
4. 提问 `今天有什么新闻` → 应联网搜索

---

## 第 ⑥ 层：Docker 全量测试

```bash
cd docker && docker-compose up --build
```

新开终端测试：

```bash
# 需带 Auth header
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer guest" \
  -d '{"message": "你好"}'

# SSE 流式测试
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer guest" \
  -d '{"message": "1+1=?"}'
```

---

## 第 ⑦ 层：RAG 评估

```bash
python evaluation.py
```

输出示例：
```
  Hit Rate: 66.67%
  MRR:      55.56%
  Latency:  145.2ms avg | p50=138.1ms | p95=210.5ms
```

---

## 目录结构

```
├── ui/                        # Streamlit 界面
├── api/                       # FastAPI 后端
├── tests/                     # 测试脚本
│   └── data/                  # 测试用文档（.txt/.md/.pdf/.docx/.png）
├── docker/                    # Docker 配置
├── data/                      # 运行时数据
│   ├── chroma_db/             # 向量数据库
│   ├── chat_history/          # 聊天记录 + sessions_metadata.json
│   └── md5.text               # MD5 去重记录
├── config_data.py             # 配置（含 auth_token）
├── file_parser.py             # 文档解析（支持 TXT/MD/PDF/DOCX/图片）
├── file_history_store.py      # 聊天历史存储（文件 + 会话元数据）
├── knowledge_base.py          # 知识库服务
├── rag_agent.py               # Agent 核心（Function Calling + SSE 流式）
├── vector_stores.py           # 向量检索
├── evaluation.py              # RAG 评估
└── requirements.txt           # 依赖
```

---

## 第 ⑧ 层：生产环境验证（yellowduck.top/rag）

以下命令在服务器上执行，验证 Docker 部署后的 API 和前端。**所有 API 请求需带 `Authorization: Bearer guest`。**

```bash
AUTH="Authorization: Bearer guest"

# API 聊天测试（非流式）
curl -X POST https://yellowduck.top/rag/api/chat \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{"message": "你好", "session_id": "test_verify"}'

# API 聊天测试（SSE 流式）
curl -N -X POST https://yellowduck.top/rag/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{"message": "1+1=?", "session_id": "test_verify"}'

# 获取聊天历史
curl -H "$AUTH" "https://yellowduck.top/rag/api/chat/history?session_id=test_verify"

# 知识库列表
curl -H "$AUTH" https://yellowduck.top/rag/api/knowledge-base/documents

# 知识库上传（含 .md 文件支持）
echo "# 测试标题\n\n测试内容" > /tmp/test_rag.md
curl -X POST https://yellowduck.top/rag/api/knowledge-base/upload \
  -H "$AUTH" \
  -F "file=@/tmp/test_rag.md"

# Auth 验证（无 token 应返回 401）
curl -o /dev/null -w "HTTP %{http_code}" https://yellowduck.top/rag/api/chat/history?session_id=test

# 前端页面可达
curl -o /dev/null -w "HTTP %{http_code}" https://yellowduck.top/rag/
curl -o /dev/null -w "HTTP %{http_code}" https://yellowduck.top/rag/upload.html

# 容器状态
sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml ps
```

---

## 快速排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `ImportError: No module named 'api'` | 目录不对 | 确保在仓库根目录下运行 |
| `Authentication Error` | API Key 无效 | `echo $DASHSCOPE_API_KEY` 检查 |
| `Address already in use` | 端口被占 | 关掉占用进程或改端口 |
| 中文乱码 | 终端编码问题 | Windows 执行 `chcp 65001` |
| `curl: (7) Failed to connect` | Docker 未启动 | `sudo systemctl start rag-agent` |
| 知识库为空 | 数据目录未挂载 | 检查 `data/chroma_db/` 是否在 compose volumes 中 |
| PaddleOCR segfault | 内存不足 | 容器仅 1GB，大图 OCR 可能 OOM；改 `pytesseract` 后端 |
| Docker 构建 OOM | 构建时内存不够 | `docker compose build --memory=1g` |
| API 返回 401 | 缺少或错误的 Auth token | 添加 `Authorization: Bearer guest` 请求头 |
| SSE 流式被缓冲 | nginx 未配置 `proxy_buffering off` | 检查 nginx 是否有 `/rag/api/chat/stream` location |
| Docker 构建很慢 | pip 缓存被清理 | 不要运行 `docker builder prune`；pip 层永久缓存 |
