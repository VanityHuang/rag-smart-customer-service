"""第 4 层：FastAPI 端到端测试（需要 API Key）"""

from pathlib import Path

import pytest
import requests

API_DIR = Path(__file__).parent.parent
BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def server():
    """启动 FastAPI 服务（session 级，所有测试共享）"""
    import subprocess
    import sys
    import time

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.server:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(API_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 等待服务器就绪（最多 15 秒）
    for i in range(15):
        time.sleep(1)
        try:
            r = requests.get(f"{BASE_URL}/docs", timeout=3)
            if r.status_code < 500:
                yield
                return
        except requests.ConnectionError:
            continue

    proc.kill()
    pytest.fail("服务器启动超时")

    # teardown
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.external
class TestAPI:
    """API 端到端测试"""

    def test_chat(self, server):
        """4.1 聊天 API — POST /api/chat"""
        resp = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "你好"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("response") or data.get("reply") or data.get("answer", "")
        assert len(reply) > 0

    def test_upload(self, server, tmp_path):
        """4.2 知识库上传 — POST /api/knowledge-base/upload"""
        upload_file = tmp_path / "_tmp_upload.txt"
        upload_file.write_text("测试内容，这是一段用于上传的文本。", encoding="utf-8")

        with open(upload_file, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/api/knowledge-base/upload",
                files={"file": ("_tmp_upload.txt", f, "text/plain")},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        assert data is not None

    def test_list_documents(self, server):
        """4.3 文档列表 — GET /api/knowledge-base/documents"""
        resp = requests.get(f"{BASE_URL}/api/knowledge-base/documents", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        docs = data if isinstance(data, list) else data.get("documents", [])
        assert isinstance(docs, list)
