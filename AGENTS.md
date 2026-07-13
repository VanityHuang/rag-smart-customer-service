# AGENTS.md — RAG Smart Customer Service

## 项目结构

单包 Python 项目（非 monorepo）。扁平布局，`api/` 子包。

| 入口 | 用途 |
|---|---|
| `api/server.py` | FastAPI 应用 — 导入路由、添加认证中间件 |
| `rag_agent.py` | `RagAgentService` — 自定义 Agent 循环（非 LangChain AgentExecutor） |
| `config_data.py` | 所有可调参数集中管理（chunk_size、retriever_k、阈值、系统提示词） |

## 开发者命令

```bash
pip install -r requirements.txt          # 完整依赖（含 pytest、streamlit）
python -m uvicorn api.server:app --reload  # 开发服务器（本地，无 Docker）
cd docker && docker-compose up --build     # Docker 开发（卷挂载热重载）
python -m pytest tests/test_api.py -v     # API 冒烟测试
python -m pytest tests/test_rag_retriever.py -v -s  # 离线评估（无需 API Key）
python -m pytest tests/test_rag_agent.py -v -s      # 在线评估（需要 API Key）
python rag_agent.py                       # CLI 交互模式（手动测试用）
```

## 测试注意事项

- **`@pytest.mark.external`** — 需要 `DASHSCOPE_API_KEY` 的测试；缺 Key 时自动跳过。
- **`conftest.py`** 自动加载 `docker/.env`，因此本地运行时无需手动 `export` 环境变量。
- **限流测试**（`test_api.py`）会消耗 11 次 guest 请求。同一小时内重复运行，guest 配额耗尽 → 测试失败。解决方法：`RAG_TEST_TOKEN=$ADMIN_TOKEN`。
- **Locust 压测**：使用 Mock 模式（`RAG_MOCK_LLM=1`）以避免消耗 Token。
- **`external` 标记** 定义在 `pytest.ini` 中，非自动注册。

## 角色隔离（双租户）

`ADMIN_TOKEN` / `GUEST_TOKEN` 在 `docker/.env` 中。所有数据按角色隔离：

- Chroma：`./data/chroma_db/{admin,guest}/`
- 聊天记录：`./data/chat_history/{admin,guest}/`
- MD5 去重：`./data/md5_{admin,guest}.txt`

`api/deps.py` 中的服务工厂按角色分配正确路径。`config_data.py` 的 fallback 值在**运行时不会被使用**——API 层始终传递明确按角色区分的路径。

## Agent 架构

- **自定义循环**（非 LangChain AgentExecutor）：手动 `for` 循环调用 `model_with_tools.invoke()` → 检查 `response.tool_calls` → 执行 → 重复。
- **两阶段 SSE 流式**：第一阶段同步（工具调用），第二阶段流式（`chat_model.stream()` 输出最终回答）。
- **工具**：`knowledge_base_search`（Chroma k=15，余弦距离阈值 0.45/0.55）、`web_search`（百度新闻 → Bing 爬虫）、`calculator`（ast.parse 白名单 eval）。
- **系统提示词** 位于 `config_data.py:AGENT_SYSTEM_PROMPT` — 修改 Agent 行为的主要位置。
- **Mock 模式**：设置 `RAG_MOCK_LLM=1` — 绕过所有 LLM 调用，返回预设的"（Mock 回答）"字符串。

## 模型配置

| 服务 | 模型 | 提供商端点 | 环境变量 |
|---|---|---|---|
| 对话 | `qwen3.5-flash` | `dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| 嵌入 | `BAAI/bge-large-zh-v1.5` | `api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` |

## Chroma 搜索说明

Chroma 使用 `hnsw:space=cosine` → 分数是**余弦距离**（越小越相似）。配置中的阈值（`score_high=0.45`、`score_low=0.55`）是距离阈值，而非相似度阈值。

## 关键配置参数（`config_data.py`）

| 参数 | 默认值 | 影响 |
|---|---|---|
| `chunk_size` / `chunk_overlap` | 256 / 32 | 文本分割粒度 |
| `retriever_k` | 15 | 每次检索返回的文档数 |
| `score_high` / `score_low` | 0.45 / 0.55 | 余弦距离阈值（越小越相似） |
| `agent_max_iterations` | 5 | 最大工具调用轮数 |
| `guest_daily_limit` | 10 | 访客每小时每 IP 请求次数 |

## Docker 热重载

- 源码通过 `docker-compose.yml` 中的**卷挂载**映射到容器内 — 代码修改后执行 `docker compose restart` 生效（约 2 秒）。
- 仅当 `requirements-prod.txt` 或 `Dockerfile` 变更时才需重建镜像（`docker compose build`）。
- 容器以 `user: "1000:1000"` 运行（与宿主机 UID/GID 一致）。
- `mem_limit: 1g`。只要 `requirements-prod.txt` 不变，pip 层即永久缓存 — 不要执行 `docker builder prune`。

## 生产部署

- nginx 将 `/rag/api/*` 代理到 Docker 容器 `127.0.0.1:8000`。
- SSE 端点 `/rag/api/chat/stream` 需要在 nginx 配置中设置 `proxy_buffering off`。
- systemd 服务：`rag-agent.service` 管理 Docker 生命周期。
- 前端为静态文件：`web/index.html` 和 `web/upload.html` 由 nginx 直接 serve。
