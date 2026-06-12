import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
基于Streamlit完成WEB网页上传服务
支持格式: .txt, .md, .pdf, .docx, .png, .jpg, .jpeg, .bmp, .tiff
"""
import streamlit as st
from knowledge_base import KnowledgeBaseService

st.title("知识库管理")

if "kb_service" not in st.session_state:
    st.session_state["kb_service"] = KnowledgeBaseService()

service = st.session_state["kb_service"]

# --- 上传区域 ---
st.subheader("上传文档")

uploaded_file = st.file_uploader(
    "请选择文件",
    type=['txt', 'md', 'pdf', 'docx', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
    accept_multiple_files=False,
)

if uploaded_file is not None:
    file_name = uploaded_file.name
    file_size_kb = uploaded_file.size / 1024

    st.write(f"文件名: {file_name} | 大小: {file_size_kb:.2f} KB")

    if st.button("载入知识库"):
        with st.spinner("解析并载入知识库中......"):
            file_bytes = uploaded_file.getvalue()
            res = service.upload_by_file(file_bytes, file_name)
            st.success(res)

# --- 文档管理区域 ---
st.divider()
st.subheader("已有文档")

if st.button("刷新文档列表"):
    docs = service.list_documents()
    st.session_state["docs"] = docs

if "docs" in st.session_state and st.session_state["docs"]:
    for doc in st.session_state["docs"]:
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{doc['source']}**")
        col2.write(f"{doc['chunk_count']} 片段")
        if col3.button("删除", key=f"del_{doc['source']}"):
            service.delete_document(doc["source"])
            st.success(f"已删除: {doc['source']}")
            st.session_state.pop("docs", None)
            st.rerun()
else:
    st.info("知识库为空")
