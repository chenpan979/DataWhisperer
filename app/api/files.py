from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.product_database import get_product_session
from app.db.product_models import KnowledgeDocument
from app.models.files import FilePreview, ManagedFile, ManagedFileList
from app.rag.document_indexer import delete_rag_file_vectors, sync_rag_file_to_milvus
from app.repositories.product import AuditLogRepository, KnowledgeRepository
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
def list_rag_files(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> ManagedFileList:
    """列出 RAG 知识库资料文件。

    登录后读取当前租户/工作空间的产品库知识库；未登录时保留本地 demo 文件列表，
    方便开发调试和 API 文档试用。
    """

    auth_context = _resolve_optional_auth_context(authorization=authorization, session=session)
    if auth_context is None:
        return _list_files(get_rag_file_store())
    documents = KnowledgeRepository(session).list_documents(workspace_id=auth_context.workspace.id)
    return ManagedFileList(category="rag", files=[_document_to_managed_file(item) for item in documents])


@router.post("/rag", response_model=ManagedFile)
async def upload_rag_file(
    file: UploadFile = File(...),
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> ManagedFile:
    """上传 RAG 知识库资料文件，并自动尝试同步到 Milvus。"""

    store = get_rag_file_store()
    saved_file = await _upload_file(store, file)
    auth_context = _resolve_optional_auth_context(authorization=authorization, session=session)
    if auth_context is None:
        return _sync_local_rag_file(store, saved_file.id)

    repository = KnowledgeRepository(session)
    knowledge_base = repository.ensure_default_base(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        created_by=auth_context.user.id,
    )
    metadata = store.metadata(saved_file.id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="文件不存在。")
    document = repository.create_document(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_id=saved_file.id,
        name=saved_file.name,
        stored_name=str(metadata["stored_name"]),
        extension=saved_file.extension,
        size_bytes=saved_file.size_bytes,
        previewable=saved_file.previewable,
        uploaded_by=auth_context.user.id,
    )
    updated_document = _sync_workspace_rag_document(
        store=store,
        repository=repository,
        document=document,
    )
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="knowledge.document.uploaded",
        target_type="knowledge_document",
        target_id=str(updated_document.id),
    )
    session.commit()
    return _document_to_managed_file(updated_document)


@router.post("/rag/{file_id}/sync", response_model=ManagedFile)
def sync_rag_file(
    file_id: str,
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> ManagedFile:
    """手动重试 RAG 文件向量同步。"""

    store = get_rag_file_store()
    auth_context = _resolve_optional_auth_context(authorization=authorization, session=session)
    if auth_context is None:
        return _sync_local_rag_file(store, file_id)

    repository = KnowledgeRepository(session)
    document = repository.get_document_by_file(
        workspace_id=auth_context.workspace.id,
        file_id=file_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="文件不存在。")
    updated_document = _sync_workspace_rag_document(
        store=store,
        repository=repository,
        document=document,
    )
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="knowledge.document.synced",
        target_type="knowledge_document",
        target_id=str(updated_document.id),
    )
    session.commit()
    return _document_to_managed_file(updated_document)


@router.delete("/rag/{file_id}")
def delete_rag_file(
    file_id: str,
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> dict[str, bool]:
    """删除 RAG 知识库资料文件，并尽力清理 Milvus 向量切片。"""

    store = get_rag_file_store()
    auth_context = _resolve_optional_auth_context(authorization=authorization, session=session)
    if auth_context is None:
        vector_deleted = delete_rag_file_vectors(file_id)
        deleted = store.delete(file_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="文件不存在。")
        return {"deleted": True, "vectors_deleted": vector_deleted}

    repository = KnowledgeRepository(session)
    document = repository.get_document_by_file(
        workspace_id=auth_context.workspace.id,
        file_id=file_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="文件不存在。")
    vector_deleted = delete_rag_file_vectors(file_id)
    store.delete(file_id)
    repository.delete_document(document)
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="knowledge.document.deleted",
        target_type="knowledge_document",
        target_id=str(document.id),
    )
    session.commit()
    return {"deleted": True, "vectors_deleted": vector_deleted}


@router.get("/rag/{file_id}/preview", response_model=FilePreview)
def preview_rag_file(
    file_id: str,
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> FilePreview:
    """预览 RAG 知识库资料文件。"""

    auth_context = _resolve_optional_auth_context(authorization=authorization, session=session)
    if auth_context is not None:
        document = KnowledgeRepository(session).get_document_by_file(
            workspace_id=auth_context.workspace.id,
            file_id=file_id,
        )
        if document is None:
            raise HTTPException(status_code=404, detail="文件不存在。")
    return _preview_file(get_rag_file_store(), file_id)


def _resolve_optional_auth_context(*, authorization: str | None, session: Session) -> AuthContext | None:
    """解析可选登录态。"""

    if not authorization:
        return None
    return require_auth_context(authorization=authorization, session=session)


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


def _sync_local_rag_file(store: ManagedFileStore, file_id: str) -> ManagedFile:
    """未登录 demo 模式下同步 RAG 文件。"""

    if not store.get(file_id):
        raise HTTPException(status_code=404, detail="文件不存在。")
    sync_result = sync_rag_file_to_milvus(file_id, file_store=store)
    updated_file = store.update_metadata(file_id, sync_result.to_metadata())
    if not updated_file:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return updated_file


def _sync_workspace_rag_document(
    *,
    store: ManagedFileStore,
    repository: KnowledgeRepository,
    document: KnowledgeDocument,
) -> KnowledgeDocument:
    """同步当前工作空间文档，并把状态写入产品库和本地元数据。"""

    sync_result = sync_rag_file_to_milvus(
        document.file_id,
        file_store=store,
        tenant_id=document.tenant_id,
        workspace_id=document.workspace_id,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
    )
    store.update_metadata(document.file_id, sync_result.to_metadata())
    updated_document = repository.update_document_sync(
        document,
        status=sync_result.status,
        message=sync_result.message,
        collection=sync_result.collection,
        chunk_count=sync_result.chunk_count,
        synced_at=_parse_sync_time(sync_result.synced_at),
    )
    if sync_result.status == "synced":
        repository.replace_chunks(updated_document, sync_result.chunks)
    return updated_document


def _document_to_managed_file(document: KnowledgeDocument) -> ManagedFile:
    return ManagedFile(
        id=document.file_id,
        name=document.name,
        size_bytes=document.size_bytes,
        extension=document.extension,
        uploaded_at=_format_datetime(document.created_at),
        previewable=document.previewable,
        sync_status=document.sync_status,
        sync_message=document.sync_message,
        sync_collection=document.sync_collection,
        sync_chunk_count=document.sync_chunk_count,
        synced_at=_format_datetime(document.synced_at),
    )


def _parse_sync_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


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
