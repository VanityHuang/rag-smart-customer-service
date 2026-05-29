"""
多格式文档解析器
支持格式: .txt, .pdf, .docx, .png, .jpg, .jpeg, .bmp, .tiff
"""
import os
import tempfile


def parse_file(file_path: str) -> str:
    """从文件路径解析文档"""
    ext = os.path.splitext(file_path)[1].lower()
    return _dispatch(ext, file_path)


def parse_bytes(file_bytes: bytes, filename: str) -> str:
    """从字节数据解析文档（如 Streamlit / FastAPI 上传）"""
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        return _dispatch(ext, tmp_path)
    finally:
        os.unlink(tmp_path)


def _dispatch(ext: str, path: str) -> str:
    parsers = {
        '.txt': _parse_txt,
        '.pdf': _parse_pdf,
        '.docx': _parse_docx,
        '.png': _parse_image,
        '.jpg': _parse_image,
        '.jpeg': _parse_image,
        '.bmp': _parse_image,
        '.tiff': _parse_image,
    }
    parser = parsers.get(ext)
    if not parser:
        raise ValueError(f"不支持的文件格式: {ext}")
    return parser(path)


def _parse_txt(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def _parse_pdf(path: str) -> str:
    import fitz
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n---\n".join(pages)


def _parse_docx(path: str) -> str:
    import docx
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _parse_image(path: str) -> str:
    from PIL import Image
    import pytesseract
    image = Image.open(path)
    text = pytesseract.image_to_string(image, lang='chi_sim+eng')
    if not text.strip():
        text = pytesseract.image_to_string(image, lang='eng')
    return text
