"""第 1 层：模块级验证（不需要 API Key）"""

import importlib
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent / "data"

MODULES = [
    "config_data",
    "file_parser",
    "file_history_store",
    "vector_stores",
    "knowledge_base",
    "rag_agent",
    "evaluation",
]


@pytest.mark.parametrize("mod_name", MODULES)
def test_imports(mod_name):
    """1.1 验证所有模块可以正常导入"""
    importlib.import_module(mod_name)


@pytest.fixture
def tmp_txt_file(tmp_path):
    """创建临时 TXT 文件，测试后自动清理"""
    f = tmp_path / "_tmp_test.txt"
    f.write_text("你好，这是一段测试文本。", encoding="utf-8")
    return str(f)


def test_txt_parse(tmp_txt_file):
    """1.2 TXT 文件解析"""
    from file_parser import parse_file

    text = parse_file(tmp_txt_file)
    assert "测试文本" in text
    assert len(text) > 0


def test_pdf_parse():
    """1.3 PDF 文件解析"""
    pdf_path = DATA_DIR / "test_sample.pdf"
    if not pdf_path.exists():
        pytest.skip("test_sample.pdf 不存在")

    from file_parser import parse_file

    text = parse_file(str(pdf_path))
    assert len(text) > 0


def test_docx_parse():
    """1.4 DOCX 文件解析"""
    docx_path = DATA_DIR / "test_service.docx"
    if not docx_path.exists():
        pytest.skip("test_service.docx 不存在")

    from file_parser import parse_file

    text = parse_file(str(docx_path))
    assert len(text) > 0
