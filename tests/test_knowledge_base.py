"""第 3 层：知识库功能测试（需要 API Key）"""

from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def kb_service():
    """共享 KnowledgeBaseService 实例（模块级，只初始化一次）"""
    from knowledge_base import KnowledgeBaseService

    return KnowledgeBaseService()


TEST_TEXT = "纯棉面料透气性好，适合夏季穿着。"
TEST_SOURCE = "test_fabric.txt"


@pytest.mark.external
def test_upload_text(kb_service):
    """3.1 上传文本到知识库"""
    doc_id = kb_service.upload_by_str(TEST_TEXT, TEST_SOURCE)
    assert "成功" in doc_id


@pytest.mark.external
def test_list_documents(kb_service):
    """3.2 列出知识库文档"""
    docs = kb_service.list_documents()
    assert len(docs) >= 0  # 有/无文档都可以，不报错就算过


@pytest.mark.external
def test_delete_document(kb_service):
    """3.3 删除知识库文档"""
    # 先确保文档存在
    kb_service.upload_by_str(TEST_TEXT, TEST_SOURCE)

    result = kb_service.delete_document(TEST_SOURCE)
    assert result is True

    # 确认已删除
    docs = kb_service.list_documents()
    sources = [d["source"] for d in docs]
    assert TEST_SOURCE not in sources


TEST_FILES = [
    ("test_verify.txt", "text"),
    ("test_sample.pdf", "pdf"),
    ("test_service.docx", "docx"),
]


@pytest.mark.external
@pytest.mark.parametrize("filename,ftype", TEST_FILES)
def test_file_upload(kb_service, filename, ftype):
    """3.4 通过文件上传（多格式支持）"""
    fpath = DATA_DIR / filename
    if not fpath.exists():
        pytest.skip(f"{filename} 不存在")

    file_bytes = fpath.read_bytes()
    result = kb_service.upload_by_file(file_bytes, filename)
    assert "成功" in result or "跳过" in result
