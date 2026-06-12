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


def test_md_parse():
    """1.5 Markdown (.md) 文件解析"""
    md_path = DATA_DIR / "test_markdown.md"
    if not md_path.exists():
        pytest.skip("test_markdown.md 不存在")

    from file_parser import parse_file

    text = parse_file(str(md_path))
    assert len(text) > 0
    assert "产品使用手册" in text
    assert "智能客服系统" in text
    assert "```python" in text  # 代码块应保留


def test_image_parse():
    """1.6 图片 OCR 文件解析（默认后端）"""
    img_path = DATA_DIR / "test_ocr.png"
    if not img_path.exists():
        pytest.skip("test_ocr.png 不存在")

    from file_parser import parse_file, _parse_image_paddleocr, _parse_image_pytesseract
    import config_data as config

    # 测试默认调度路径
    try:
        text = parse_file(str(img_path))
        assert len(text) > 0
        assert any(ord(c) > 127 or c.isalpha() for c in text), \
            "OCR 输出应包含可识别的文本"
    except (RuntimeError, ImportError) as e:
        if "paddlepaddle" in str(e) or "paddle" in str(e).lower():
            pytest.skip(f"PaddleOCR 不可用: {e}")
        raise
    except Exception as e:
        # pytesseract: 缺少系统 tesseract 二进制也会失败
        if "tesseract" in str(e).lower():
            pytest.skip(f"pytesseract 不可用: {e}")
        raise

    # 尝试 PaddleOCR 后端（如果当前环境支持）
    try:
        paddle_text = _parse_image_paddleocr(str(img_path))
        assert isinstance(paddle_text, str)
    except (RuntimeError, ImportError) as e:
        # PaddleOCR 可能缺少 paddlepaddle 或 Python 版本过高
        print(f"PaddleOCR 后端跳过: {e}")
    else:
        assert len(paddle_text) > 0

    # 尝试 pytesseract 备胎后端（如果系统安装了 tesseract 二进制）
    try:
        tesseract_text = _parse_image_pytesseract(str(img_path))
        assert isinstance(tesseract_text, str)
    except Exception as e:
        # pytesseract 可能缺少系统级 tesseract 二进制
        print(f"pytesseract 后端跳过: {e}")
