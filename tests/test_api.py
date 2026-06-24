"""API 冒烟测试 — 覆盖全部端点 + 认证 + 限流

双目标测试：同一套用例分别对 local 和 prod 执行。
通过环境变量配置：
  RAG_LOCAL_URL  — 本地服务地址（默认 http://localhost:8000）
  RAG_PROD_URL   — 生产环境地址（不设置则跳过生产测试）
  RAG_TEST_TOKEN — Bearer token（默认 guest）
"""

import os
import uuid

import pytest
import requests

LOCAL_URL = os.environ.get("RAG_LOCAL_URL", "http://localhost:8000")
PROD_URL = os.environ.get("RAG_PROD_URL", "")
TOKEN = os.environ.get("RAG_TEST_TOKEN", "")  # 非空 Token 请在 RAG_TEST_TOKEN 环境变量中设置

# ── 构建测试目标列表 ──
_TARGETS = [("local", LOCAL_URL)]
if PROD_URL:
    _TARGETS.append(("prod", PROD_URL))


def _headers(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


# ── 可用的 pytest marker ──
pytestmark = pytest.mark.external


# ── 参数化 fixture：分别对 local/prod 执行 ──
@pytest.fixture(params=_TARGETS, ids=[t[0] for t in _TARGETS])
def target(request):
    """返回 (name, base_url) 元组"""
    name, base_url = request.param
    # 生产环境可达性检查
    if name == "prod":
        try:
            r = requests.get(f"{base_url}/", timeout=5)
            if r.status_code >= 500:
                pytest.skip(f"生产环境不可达: {base_url}")
        except requests.ConnectionError:
            pytest.skip(f"生产环境无法连接: {base_url}")
    return name, base_url


# ── 认证测试 ──

class TestAuth:
    def test_no_auth_returns_401(self, target):
        """无 token 访问 → 401"""
        _, base = target
        resp = requests.get(f"{base}/api/chat/sessions")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, target):
        """错误 token → 401"""
        _, base = target
        resp = requests.get(
            f"{base}/api/chat/sessions",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert resp.status_code == 401


# ── 聊天端点 ──

class TestChat:
    def test_chat_endpoint(self, target):
        """POST /api/chat → 200 + response 非空"""
        _, base = target
        sid = f"test_smoke_{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{base}/api/chat",
            json={"message": "你好", "session_id": sid},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        assert "response" in data or "reply" in data or "answer" in data
        reply = data.get("response") or data.get("reply") or data.get("answer", "")
        assert len(reply) > 0

    def test_chat_stream(self, target):
        """POST /api/chat/stream → 200 + text/event-stream"""
        _, base = target
        sid = f"test_smoke_{uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{base}/api/chat/stream",
            json={"message": "1+1=?", "session_id": sid},
            headers=_headers(),
            stream=True,
            timeout=30,
        )
        resp.raise_for_status()
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        # 读取第一个 SSE 事件
        lines = []
        for line in resp.iter_lines(decode_unicode=True):
            lines.append(line)
            if len(lines) >= 3:
                break
        assert any("data:" in line for line in lines)


# ── 会话管理端点 ──

class TestSessions:
    def test_list_sessions(self, target):
        """GET /api/chat/sessions → 200 + list"""
        _, base = target
        resp = requests.get(f"{base}/api/chat/sessions", headers=_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, list)

    def test_chat_history(self, target):
        """GET /api/chat/history → 200 + messages 列表"""
        _, base = target
        sid = f"test_smoke_{uuid.uuid4().hex[:8]}"
        # 先发一条消息确保会话存在
        requests.post(
            f"{base}/api/chat",
            json={"message": "测试历史记录", "session_id": sid},
            headers=_headers(),
            timeout=30,
        )
        resp = requests.get(
            f"{base}/api/chat/history",
            params={"session_id": sid},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)

    def test_session_rename(self, target):
        """PUT /api/chat/sessions/{id} → 200"""
        _, base = target
        sid = f"test_rename_{uuid.uuid4().hex[:8]}"
        # 先创建会话
        requests.post(
            f"{base}/api/chat",
            json={"message": "用于重命名测试", "session_id": sid},
            headers=_headers(),
            timeout=30,
        )
        resp = requests.put(
            f"{base}/api/chat/sessions/{sid}",
            json={"title": "重命名测试会话"},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        assert data.get("title") == "重命名测试会话"

    def test_session_delete(self, target):
        """DELETE /api/chat/sessions/{id} → 200"""
        _, base = target
        sid = f"test_delete_{uuid.uuid4().hex[:8]}"
        # 先创建会话
        requests.post(
            f"{base}/api/chat",
            json={"message": "用于删除测试", "session_id": sid},
            headers=_headers(),
            timeout=30,
        )
        resp = requests.delete(
            f"{base}/api/chat/sessions/{sid}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        assert "已删除" in data.get("message", "")


# ── 知识库端点 ──

class TestKnowledgeBase:
    def test_list_documents(self, target):
        """GET /api/knowledge-base/documents → 200 + list"""
        _, base = target
        resp = requests.get(
            f"{base}/api/knowledge-base/documents",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        assert isinstance(data, list)

    def test_upload_document(self, target):
        """POST /api/knowledge-base/upload → 200"""
        _, base = target
        content = f"冒烟测试文档 {uuid.uuid4().hex[:8]}"
        resp = requests.post(
            f"{base}/api/knowledge-base/upload",
            files={"file": ("_smoke_test.txt", content.encode(), "text/plain")},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        assert "message" in data or "filename" in data


# ── 限流测试（仅 guest） ──

class TestRateLimit:
    @pytest.mark.skipif(TOKEN != "guest", reason="限流测试仅针对 guest token")
    def test_guest_rate_limit(self, target):
        """连续发 11 次，第 11 次返回 429"""
        _, base = target
        sid = f"test_ratelimit_{uuid.uuid4().hex[:8]}"
        responses = []
        for i in range(11):
            resp = requests.post(
                f"{base}/api/chat",
                json={"message": f"限流测试 {i+1}", "session_id": sid},
                headers=_headers(),
                timeout=30,
            )
            responses.append(resp.status_code)

        # 前 10 次应成功（200），第 11 次应被限流（429）
        assert responses[-1] == 429, f"第 11 次请求应返回 429，实际返回 {responses[-1]}"
        assert all(code == 200 for code in responses[:-1]), \
            f"前 10 次应全部 200，实际: {responses[:-1]}"
