"""知识库 API 路由"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List
from knowledge_base import KnowledgeBaseService

router = APIRouter()
kb_service = KnowledgeBaseService()


class DocumentInfo(BaseModel):
    source: str
    create_time: str = ""
    chunk_count: int = 0


class UploadResponse(BaseModel):
    message: str
    filename: str


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传文档到知识库"""
    try:
        file_bytes = await file.read()
        result = kb_service.upload_by_file(file_bytes, file.filename)
        return UploadResponse(message=result, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents", response_model=List[DocumentInfo])
def list_documents():
    """列出知识库中所有文档"""
    return kb_service.list_documents()


@router.delete("/documents/{source:path}")
def delete_document(source: str):
    """删除知识库中的文档"""
    success = kb_service.delete_document(source)
    if not success:
        raise HTTPException(status_code=404, detail="文档未找到")
    return {"message": f"已删除: {source}"}
