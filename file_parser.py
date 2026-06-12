"""
多格式文档解析器
支持格式: .txt, .md, .pdf, .docx, .png, .jpg, .jpeg, .bmp, .tiff
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
        '.md': _parse_txt,
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
    import config_data as config

    backend = config.ocr_backend
    if backend == "paddleocr":
        return _parse_image_paddleocr(path)
    elif backend == "pytesseract":
        return _parse_image_pytesseract(path)
    else:
        raise ValueError(
            f"未知的 OCR 后端 '{backend}'。支持的选项: 'paddleocr', 'pytesseract'。"
        )


# --- PaddleOCR 后端 ---

_ocr_instance = None


def _get_paddleocr():
    """懒加载 PaddleOCR 单例，首次调用后缓存复用。"""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        import config_data as config
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang=config.ocr_language,
            show_log=False,         # 抑制框架日志
        )
    return _ocr_instance


def _parse_image_paddleocr(path: str) -> str:
    """使用 PaddleOCR 后端识别图片文字。

    PaddleOCR 2.x 返回格式: [[[bbox, (text, confidence)], ...], ...]
    按置信度阈值 (config.ocr_confidence_threshold) 过滤低质量结果。
    """
    import config_data as config
    ocr = _get_paddleocr()
    result = ocr.ocr(path, cls=True)
    if not result or not result[0]:
        return ""

    lines = []
    for detection in result[0]:
        # detection: [bbox, (text, confidence)]
        _, (text, confidence) = detection
        if confidence >= config.ocr_confidence_threshold:
            lines.append(text)

    return "\n".join(lines)


def _parse_image_pytesseract(path: str) -> str:
    """使用 pytesseract 后端识别图片文字（备胎方案）。"""
    from PIL import Image
    import pytesseract
    import config_data as config

    image = Image.open(path)
    text = pytesseract.image_to_string(image, lang=config.pytesseract_language)
    if not text.strip():
        text = pytesseract.image_to_string(image, lang="eng")
    return text
