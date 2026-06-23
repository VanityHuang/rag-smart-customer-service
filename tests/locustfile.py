"""
Locust 压测脚本 — 系统稳定性与性能测试

注意：聊天请求会消耗 DashScope Token（每次约 3000 input + 300 output）。
建议先用 --mock-host 指向 mock 服务，或仅跑会话/文档端点估算 API 吞吐。

用法:
    # 仅测非 LLM 端点（不消耗 Token，推荐）
    locust -f tests/locustfile.py --host=http://localhost:8000
    # 打开 http://localhost:8089，只勾选 list_documents 和 list_sessions

    # 全量测试（消耗 Token）
    locust -f tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 10 -r 2 --run-time 3m --csv=results/load_test

环境变量:
    RAG_LOCUST_TOKEN — Bearer token（默认 guest）
"""

import os
import uuid

from locust import HttpUser, task, between, events


class RAGUser(HttpUser):
    """模拟 RAG 智能客服用户"""

    wait_time = between(1, 3)  # 每次请求间隔 1-3 秒

    def on_start(self):
        """用户启动时获取 token"""
        self.token = os.environ.get("RAG_LOCUST_TOKEN", "guest")
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}
        self.session_id = f"locust_{uuid.uuid4().hex[:8]}"

    @task(3)
    def list_documents(self):
        """查看知识库文档（权重 3）"""
        self.client.get(
            "/api/knowledge-base/documents",
            headers=self.auth_headers,
            name="/api/knowledge-base/documents",
        )

    @task(2)
    def list_sessions(self):
        """查看会话列表（权重 2）"""
        self.client.get(
            "/api/chat/sessions",
            headers=self.auth_headers,
            name="/api/chat/sessions",
        )

    # ── 以下任务会消耗 LLM Token，默认关闭。
    # 将 @task(0) 改为 @task(1~5) 启用。
    # @task(0)
    def chat(self):
        """聊天（消耗 Token，默认关闭）"""
        self.client.post(
            "/api/chat",
            json={"message": "你好", "session_id": self.session_id},
            headers=self.auth_headers,
            name="/api/chat [你好]",
        )

    # @task(0)
    def chat_stream(self):
        """流式聊天（消耗 Token，默认关闭）"""
        self.client.post(
            "/api/chat/stream",
            json={"message": "1+1=?", "session_id": self.session_id},
            headers=self.auth_headers,
            name="/api/chat/stream [1+1=?]",
        )
