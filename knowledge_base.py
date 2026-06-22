"""
知识库
"""
import os
import config_data as config
import hashlib
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from datetime import datetime


def check_md5(md5_str: str, md5_path: str = None):
    """检查内容是否已处理过（按 MD5 去重）"""
    md5_path = md5_path or config.md5_path
    if not os.path.exists(md5_path):
        open(md5_path, 'w', encoding='utf-8').close()
        return False
    for line in open(md5_path, 'r', encoding='utf-8').readlines():
        line = line.strip()
        # 兼容新旧格式: md5|source 或 md5
        stored_md5 = line.split("|")[0]
        if stored_md5 == md5_str:
            return True
    return False


def save_md5(md5_str: str, source: str = "", md5_path: str = None):
    """记录 MD5，关联到来源文档"""
    md5_path = md5_path or config.md5_path
    with open(md5_path, 'a', encoding='utf-8') as f:
        line = f"{md5_str}|{source}" if source else md5_str
        f.write(line + '\n')


def clear_md5_by_source(source: str, md5_path: str = None):
    """删除指定来源文档关联的所有 MD5 记录"""
    md5_path = md5_path or config.md5_path
    if not os.path.exists(md5_path):
        return
    with open(md5_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    remaining = [l for l in lines if not l.strip().endswith(f"|{source}")]
    with open(md5_path, 'w', encoding='utf-8') as f:
        f.writelines(remaining)


def get_string_md5(input_str: str, encoding='utf-8'):
    """将传入的字符串转换为md5格式"""
    str_bytes = input_str.encode(encoding=encoding)
    md5_obj = hashlib.md5()
    md5_obj.update(str_bytes)
    md5_hex = md5_obj.hexdigest()
    return md5_hex


class KnowledgeBaseService(object):
    def __init__(self, persist_directory=None, md5_path=None, collection_name=None):
        self.persist_directory = persist_directory or config.persist_directory
        self.md5_path = md5_path or config.md5_path
        self.collection_name = collection_name or config.collection_name

        os.makedirs(self.persist_directory, exist_ok=True)

        self.chroma = Chroma(
            collection_name=self.collection_name,
            embedding_function=DashScopeEmbeddings(model=config.embedding_model_name),
            persist_directory=self.persist_directory,
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=config.separators,
            length_function=len,
        )

    def upload_by_str(self, data: str, filename):
        """将传入的字符串进行向量化, 存入向量数据库中"""
        md5_hex = get_string_md5(data)

        if check_md5(md5_hex, self.md5_path):
            return "[跳过]内容已经存在知识库中"

        if len(data) > config.min_split_char_number:
            knowledge_chunks: list[str] = self.spliter.split_text(data)
        else:
            knowledge_chunks = [data]

        meta = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": "小孙",
        }

        self.chroma.add_texts(
            knowledge_chunks,
            metadatas=[meta for _ in knowledge_chunks],
        )

        save_md5(md5_hex, filename, md5_path=self.md5_path)

        return f"[成功]内容已经成功载入向量库: {filename}"

    def upload_by_file(self, file_bytes: bytes, filename: str):
        """解析并上传文件（支持多格式）到知识库"""
        from file_parser import parse_bytes
        text = parse_bytes(file_bytes, filename)
        return self.upload_by_str(text, filename)

    def list_documents(self):
        """列出知识库中所有唯一的源文档"""
        all_data = self.chroma.get(include=["metadatas"])
        seen = {}
        for meta in all_data.get("metadatas", []):
            if meta is None:
                continue
            src = meta.get("source", "unknown")
            if src not in seen:
                seen[src] = {
                    "source": src,
                    "create_time": meta.get("create_time", ""),
                    "chunk_count": 0,
                }
            seen[src]["chunk_count"] += 1
        return list(seen.values())

    def delete_document(self, source: str):
        """删除指定源文档的所有向量块"""
        all_data = self.chroma.get(include=["metadatas"])
        ids_to_delete = []
        for i, meta in enumerate(all_data.get("metadatas", [])):
            if meta is None:
                continue
            if meta.get("source") == source:
                ids_to_delete.append(all_data["ids"][i])
        if ids_to_delete:
            self.chroma.delete(ids=ids_to_delete)
            clear_md5_by_source(source, self.md5_path)
            return True
        return False


if __name__ == '__main__':
    service = KnowledgeBaseService()
    r = service.upload_by_str("孙佳乐", "testfile")
    print(r)
