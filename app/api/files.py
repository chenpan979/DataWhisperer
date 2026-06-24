from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.files import FilePreview, ManagedFile, ManagedFileList
from app.rag.document_indexer import delete_rag_file_vectors, sync_rag_file_to_milvus
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
    """上传 RAG 知识库资料文件，并自动尝试同步到 Milvus。"""

    store = get_rag_file_store()
    saved_file = await _upload_file(store, file)
    return _sync_rag_file(store, saved_file.id)


@router.post("/rag/{file_id}/sync", response_model=ManagedFile)
def sync_rag_file(file_id: str) -> ManagedFile:
    """手动重试 RAG 文件向量同步。"""

    return _sync_rag_file(get_rag_file_store(), file_id)


@router.delete("/rag/{file_id}")
def delete_rag_file(file_id: str) -> dict[str, bool]:
    """删除 RAG 知识库资料文件，并尽力清理 Milvus 向量切片。"""

    store = get_rag_file_store()
    vector_deleted = delete_rag_file_vectors(file_id)
    deleted = store.delete(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return {"deleted": True, "vectors_deleted": vector_deleted}


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



def _sync_rag_file(store: ManagedFileStore, file_id: str) -> ManagedFile:
    """执行 RAG 文件同步并把结果写回本地元数据。

    上传文件是主流程，Milvus 同步是增强流程：同步失败时仍然返回文件，
    但 sync_status 会变成 failed，前端可提示用户稍后重试。
    """

    if not store.get(file_id):
        raise HTTPException(status_code=404, detail="文件不存在。")
    sync_result = sync_rag_file_to_milvus(file_id, file_store=store)
    updated_file = store.update_metadata(file_id, sync_result.to_metadata())
    if not updated_file:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return updated_file


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
