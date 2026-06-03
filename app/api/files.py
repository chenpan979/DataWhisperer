from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.files import FilePreview, ManagedFile, ManagedFileList
from app.tools.file_store import (
    ManagedFileStore,
    get_rag_file_store,
    get_schema_file_store,
)

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/schema", response_model=ManagedFileList)
def list_schema_files() -> ManagedFileList:
    """列出数据结构资料文件。"""

    return _list_files(get_schema_file_store())


@router.post("/schema", response_model=ManagedFile)
async def upload_schema_file(file: UploadFile = File(...)) -> ManagedFile:
    """上传数据结构资料文件。"""

    return await _upload_file(get_schema_file_store(), file)


@router.delete("/schema/{file_id}")
def delete_schema_file(file_id: str) -> dict[str, bool]:
    """删除数据结构资料文件。"""

    return _delete_file(get_schema_file_store(), file_id)


@router.get("/schema/{file_id}/preview", response_model=FilePreview)
def preview_schema_file(file_id: str) -> FilePreview:
    """预览数据结构资料文件。"""

    return _preview_file(get_schema_file_store(), file_id)


@router.get("/rag", response_model=ManagedFileList)
def list_rag_files() -> ManagedFileList:
    """列出 RAG 知识库资料文件。"""

    return _list_files(get_rag_file_store())


@router.post("/rag", response_model=ManagedFile)
async def upload_rag_file(file: UploadFile = File(...)) -> ManagedFile:
    """上传 RAG 知识库资料文件。"""

    return await _upload_file(get_rag_file_store(), file)


@router.delete("/rag/{file_id}")
def delete_rag_file(file_id: str) -> dict[str, bool]:
    """删除 RAG 知识库资料文件。"""

    return _delete_file(get_rag_file_store(), file_id)


@router.get("/rag/{file_id}/preview", response_model=FilePreview)
def preview_rag_file(file_id: str) -> FilePreview:
    """预览 RAG 知识库资料文件。"""

    return _preview_file(get_rag_file_store(), file_id)


def _list_files(store: ManagedFileStore) -> ManagedFileList:
    return ManagedFileList(category=store.config.category, files=store.list_files())


async def _upload_file(store: ManagedFileStore, file: UploadFile) -> ManagedFile:
    try:
        content = await file.read()
        return store.save(original_name=file.filename or "", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


def _delete_file(store: ManagedFileStore, file_id: str) -> dict[str, bool]:
    deleted = store.delete(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return {"deleted": True}


def _preview_file(store: ManagedFileStore, file_id: str) -> FilePreview:
    preview = store.preview(file_id)
    if not preview:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return preview
