# RAG Agent 验证指南

> **测试体系说明**：本项目测试以**结果类测试**为主，验证系统在真实环境下的表现（性能、精度、成本），而非仅验证代码能否运行。

## 前置条件

```bash
echo $DASHSCOPE_API_KEY   # 必须设置
```

---

## 测试一览

| 层级 | 命令 | 测试内容 | 需 API Key |
|------|------|----------|:----------:|
| ① API 冒烟 | `pytest tests/test_api.py -v` | 全端点 + 认证 + 限流 | 是 |
| ② Docker 构建 | `docker-compose up --build` | 镜像构建 + 容器启动 | 是 |
| ③ 离线评估 | `pytest tests/test_rag_retriever.py -v -s` | 检索侧能力：Hit Rate / MRR / 相似度 | 否 |
| ④ 在线评估 | `pytest tests/test_rag_agent.py -v -s` | Agent 行为：联网兜底 / 拒答比例 | 是 |
| ⑤ Locust 压测 | `locust -f tests/locustfile.py` | 系统稳定性与性能 | 是 |
| ⑥ 生产验证 | `bash tests/prod_verify.sh` | 线上 API + 前端 + 容器 | 否 |

---

## 第 ① 层：API 冒烟测试

覆盖全部 API 端点 + 认证 + guest 限流，分别对 local 和 prod 两个目标执行。

```bash
# 测本地服务
python -m pytest tests/test_api.py -v

# 同时测本地和生产环境
RAG_PROD_URL=https://yellowduck.top/rag python -m pytest tests/test_api.py -v

# 用 admin token 测
RAG_TEST_TOKEN=$ADMIN_TOKEN python -m pytest tests/test_api.py -v
```

测试项：

| 测试 | 端点 | 验证内容 |
|------|------|----------|
| 无 token 访问 | 任意 | 返回 401 |
| 错误 token | 任意 | 返回 401 |
| 聊天 | `POST /api/chat` | 200 + response 非空 + token_usage 字段 |
| 流式聊天 | `POST /api/chat/stream` | 200 + `text/event-stream` 头 |
| 聊天历史 | `GET /api/chat/history` | 200 + messages 列表 |
| 会话列表 | `GET /api/chat/sessions` | 200 + list |
| 重命名会话 | `PUT /api/chat/sessions/{id}` | 200 |
| 删除会话 | `DELETE /api/chat/sessions/{id}` | 200 |
| 上传文档 | `POST /api/knowledge-base/upload` | 200 |
| 文档列表 | `GET /api/knowledge-base/documents` | 200 + list |
| guest 限流 | `POST /api/chat` × 11 | 第 11 次返回 429 |

> ⚠️ **限流测试副作用**：会消耗 guest 每小时 10 次配额中的 11 次。同一小时内重复运行会因配额耗尽而失败。解决方法：等待配额重置，或用 `RAG_TEST_TOKEN=$ADMIN_TOKEN` 跳过限流测试。

环境变量（已写入 `docker/.env`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_LOCAL_URL` | `http://localhost:8000` | 本地服务地址 |
| `RAG_PROD_URL` | `https://yellowduck.top/rag` | 生产环境（不设置则跳过） |
| `RAG_TEST_TOKEN` | `guest123` | 测试用 Bearer token |

---

## 第 ② 层：Docker 构建验证

验证镜像构建成功、容器正常启动。

```bash
cd docker && docker-compose up --build
```

构建成功后用 ① 或 ⑥ 验证服务功能。

---

## 第 ③ 层：离线评估（检索侧能力）

纯向量检索评估，不调用 LLM，无需 API Key。基于 5 个鸭鸭知识文档的 82 条测试集（`retriever_k=15`）。

```bash
python -m pytest tests/test_rag_retriever.py -v -s
```

测试集：36 显式 + 26 隐式 + 20 噪声 = 82 题

产出报告：

```
测试集    数量  命中  Hit Rate@15  MRR       平均最高相似度
显式      36    34    94%          89%       0.65
隐式      26    26    100%         79%       0.60
噪声      20    0     0%           0%        0.35
```

- **Hit Rate@15**：top-15 检索结果中是否包含标准答案关键词（k=15）
- **MRR**：第一个相关结果的排名倒数
- **平均最高相似度**：top-1 结果的余弦相似度

报告保存到 `results/rag_retriever_report.json`。

---

## 第 ④ 层：在线评估（Agent 行为检测）

通过完整 Agent 链路（Retriever + LLM + 工具路由），统计联网搜索和拒答行为。需要 API Key。

```bash
python -m pytest tests/test_rag_agent.py -v -s
```

精选测试集：10 显式 + 10 隐式 + 10 噪声 = 30 题

产出报告：

```
测试集    数量  直接回答  联网兜底  拒答
显式      10    8        2        0
隐式      10    6        3        1
噪声      10    0        1        9

显式: 直接回答 80% | 联网兜底 20% | 拒答 0%
隐式: 直接回答 60% | 联网兜底 30% | 拒答 10%
噪声: 直接回答 0% | 联网兜底 10% | 拒答 90%
```

- **直接回答**：Agent 仅用知识库内容回答
- **联网兜底**：Agent 调用了 web_search 补充信息
- **拒答**：Agent 拒绝回答

报告保存到 `results/rag_agent_report.json`。

---

## 第 ⑤ 层：Locust 压测

### 安装

```bash
pip install locust
```

### 执行

```bash
# 不消耗 Token：仅测 API 吞吐（文档列表 + 会话列表）
locust -f tests/locustfile.py --host=http://localhost:8000
# 打开 http://localhost:8089，设置 10 并发用户，跑 3 分钟

# 全量测试（消耗 Token）：需手动启用聊天任务
# 编辑 tests/locustfile.py，将 chat() 和 chat_stream() 的 @task(0) 改为 @task(1~5)

# 命令行模式（适合 CI）
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --headless -u 10 -r 2 --run-time 3m \
  --csv=results/load_test
```

关注指标：

| 指标 | 目标 |
|------|------|
| Average Response Time | < 5s（API 端点）/ < 10s（聊天端点） |
| P95 Response Time | < 10s |
| Failure Rate | **0.00%** |

---

## 第 ⑥ 层：生产环境自动化验证

快速巡检线上服务（前端 + API + Docker 容器），输出可视化结果。

```bash
bash tests/prod_verify.sh
```

验证项：前端页面（2）+ 认证（2）+ 聊天 API（2）+ 会话管理（2）+ 知识库（2）+ Docker 容器（1）= 共 11 项。

---

## 目录结构

```
tests/
├── conftest.py                  # external 标记自动跳过
├── test_api.py                  # ① API 冒烟（本地 + 生产）
├── test_rag_retriever.py        # ③ 离线评估（检索侧，无需 Key）
├── test_rag_agent.py            # ④ 在线评估（Agent 行为，需 Key）
├── locustfile.py                # ⑤ Locust 压测
├── prod_verify.sh               # ⑥ 生产环境巡检
└── data/                        # 测试文档（5 个鸭鸭知识文档）
```

---

## 环境变量一览

| 变量 | 位置 | 用途 | 默认值 |
|------|------|------|--------|
| `DASHSCOPE_API_KEY` | `docker/.env` | 阿里云 DashScope API Key | 必填 |
| `ADMIN_TOKEN` | `docker/.env` | 管理员密码 | 必填 |
| `GUEST_TOKEN` | `docker/.env` | 访客密码 | 必填 |
| `RAG_PROD_URL` | `docker/.env` | 冒烟测试生产地址 | `https://yellowduck.top/rag` |
| `RAG_TEST_TOKEN` | `docker/.env` | 冒烟测试 Bearer token | `guest123` |
| `RAG_LOCAL_URL` | shell 环境 | 冒烟测试本地地址 | `http://localhost:8000` |

---

## 快速排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `Authentication Error` | API Key 无效 | `echo $DASHSCOPE_API_KEY` 检查 |
| 限流测试失败（非 429） | guest 配额已耗尽 | 等待配额重置或用 admin token |
| `curl: (7) Failed to connect` | Docker 未启动 | `sudo systemctl start rag-agent` |
| API 返回 401 | 缺少或错误的 Auth token | 添加 `Authorization: Bearer guest` 头 |
| SSE 流式被缓冲 | nginx 未配置 `proxy_buffering off` | 检查 `/rag/api/chat/stream` location |
| Locust 报 ConnectionError | 服务未启动 | 先启动服务或调整 `--host` |
| prod_verify.sh 报错 | 域名不可达 | 检查 DNS 和 nginx 配置 |
