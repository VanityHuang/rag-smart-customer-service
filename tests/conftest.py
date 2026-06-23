import sys
from pathlib import Path

# 确保能从 RAG/ 目录导入模块
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pytest


def _load_docker_env():
    """从 docker/.env 加载环境变量（宿主机运行测试时自动读取）"""
    env_path = Path(__file__).parent.parent / "docker" / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 不覆盖已有的环境变量
                if key and key not in os.environ:
                    os.environ[key] = value


# 启动时自动加载 docker/.env
_load_docker_env()


def pytest_collection_modifyitems(items):
    """没有 DASHSCOPE_API_KEY 时自动跳过 external 标记的测试"""
    if os.environ.get("DASHSCOPE_API_KEY"):
        return  # 有 Key，所有测试正常跑
    for item in items:
        if item.get_closest_marker("external"):
            item.add_marker(
                pytest.mark.skip(reason="需要 DASHSCOPE_API_KEY 环境变量")
            )
