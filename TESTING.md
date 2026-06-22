# RAG Agent 验证指南

> **测试体系说明**：本项目测试以**结果类测试**为主，验证系统在真实环境下的表现（性能、精度、成本），而非仅验证代码能否运行。

## 前置条件

```bash
echo $DASHSCOPE_API_KEY   # 必须设置
# 或写入 ./docker/.env
```

---

## 测试一览

| 层级 | 命令 | 测试内容 | 需 API Key |
|------|------|----------|:----------:|
| ① API 冒烟 | `pytest tests/test_api.py -v` | 全端点 + 认证 + 限流 | 是 |
| ② Docker 构建 | `docker-compose up --build` | 镜像构建 + 容器启动 | 是 |
| ③ RAG 评估 | `python evaluation.py` | 命中率/MRR/延迟指标 | 是 |
| ④ Locust 压测 | `locust -f tests/locustfile.py` | 系统稳定性与性能 | 是 |
| ⑤ RAG 参数遍历 | `pytest tests/test_rag_precision_grid.py -v` | 分块参数调优对比 | 是 |
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

## 第 ③ 层：RAG 评估

对当前生产配置执行检索质量评估（自动播种测试文档，评估后清理）。

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

## 第 ④ 层：Locust 压测

### 安装

```bash
pip install locust
```

### 执行

```bash
# Web UI（推荐）
locust -f tests/locustfile.py --host=http://localhost:8000
# 打开 http://localhost:8089，设置 10 并发用户，跑 3 分钟

# 命令行（适合 CI）
locust -f tests/locustfile.py --host=http://localhost:8000 \
  --headless -u 10 -r 2 --run-time 3m \
  --csv=results/load_test
```

关注指标：

| 指标 | 目标 |
|------|------|
| Average Response Time | < 5s |
| P95 Response Time | < 10s |
| Failure Rate | **0.00%** |

---

## 第 ⑤ 层：RAG 参数遍历

暴力遍历 `chunk_size × overlap` 的 9 种组合，对比 Hit Rate / MRR / 域外误召回率。

```bash
python -m pytest tests/test_rag_precision_grid.py -v -s
```

| 参数 | 候选值 |
|------|--------|
| chunk_size | 256, 512, 1024 |
| overlap | 0, 64, 128 |

产出 Markdown 对比表 + `results/rag_precision_grid.csv`。

> 与第 ③ 层的区别：③ 测当前配置的绝对值，⑤ 遍历参数找最优组合。

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
├── test_api.py                  # API 冒烟（本地 + 生产）
├── locustfile.py                # Locust 压测
├── test_rag_precision_grid.py   # RAG 参数遍历
├── prod_verify.sh               # 生产环境巡检
└── data/                        # 测试文档
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
