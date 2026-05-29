import sys
from pathlib import Path

# 确保能从 RAG/ 目录导入模块
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pytest


def pytest_collection_modifyitems(items):
    """没有 DASHSCOPE_API_KEY 时自动跳过 external 标记的测试"""
    if os.environ.get("DASHSCOPE_API_KEY"):
        return  # 有 Key，所有测试正常跑
    for item in items:
        if item.get_closest_marker("external"):
            item.add_marker(
                pytest.mark.skip(reason="需要 DASHSCOPE_API_KEY 环境变量")
            )
