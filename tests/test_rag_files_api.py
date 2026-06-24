import pytest
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")

from app.api import files as files_api  # noqa: E402
from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.db.product_models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument  # noqa: E402
from app.main import create_app  # noqa: E402
from app.rag.document_indexer import RagFileSyncResult, RagIndexedChunk  # noqa: E402
from app.tools.file_store import FileStoreConfig, ManagedFileStore  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_upload_rag_file_writes_sync_status(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = ManagedFileStore(
        FileStoreConfig(
            category="rag",
            directory=tmp_path,
            allowed_extensions=frozenset({".md"}),
        )
    )

    def fake_sync(file_id: str, *, file_store: ManagedFileStore) -> RagFileSyncResult:
        assert file_store is store
        return RagFileSyncResult(
            status="synced",
            message="已切分 2 个片段并同步到 Milvus。",
            collection="datawhisperer_rag_documents",
            chunk_count=2,
            synced_at="2026-06-24T00:00:00+00:00",
        )

    monkeypatch.setattr(files_api, "get_rag_file_store", lambda: store)
    monkeypatch.setattr(files_api, "sync_rag_file_to_milvus", fake_sync)

    client = TestClient(create_app())
    response = client.post(
        "/api/files/rag",
        files={"file": ("metrics.md", "GMV 指标说明", "text/markdown")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sync_status"] == "synced"
    assert payload["sync_chunk_count"] == 2

    list_response = client.get("/api/files/rag")
    assert list_response.status_code == 200
    assert list_response.json()["files"][0]["sync_collection"] == "datawhisperer_rag_documents"


def test_manual_rag_file_sync_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = ManagedFileStore(
        FileStoreConfig(
            category="rag",
            directory=tmp_path,
            allowed_extensions=frozenset({".txt"}),
        )
    )
    saved = store.save(original_name="faq.txt", content=b"faq content")

    monkeypatch.setattr(files_api, "get_rag_file_store", lambda: store)
    monkeypatch.setattr(
        files_api,
        "sync_rag_file_to_milvus",
        lambda file_id, *, file_store: RagFileSyncResult(
            status="failed",
            message="Milvus 暂不可用",
            collection="datawhisperer_rag_documents",
            chunk_count=1,
            synced_at="2026-06-24T00:00:00+00:00",
        ),
    )

    client = TestClient(create_app())
    response = client.post(f"/api/files/rag/{saved.id}/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sync_status"] == "failed"
    assert payload["sync_message"] == "Milvus 暂不可用"


def test_authenticated_rag_upload_records_workspace_document(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """登录后上传 RAG 文件时，文件归属和切片元数据要写入当前租户/工作空间。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def override_product_session():
        with session_factory() as session:
            yield session

    store = ManagedFileStore(
        FileStoreConfig(
            category="rag",
            directory=tmp_path,
            allowed_extensions=frozenset({".md"}),
        )
    )
    observed_scope: dict[str, object] = {}

    def fake_sync(
        file_id: str,
        *,
        file_store: ManagedFileStore,
        tenant_id: int | str | None = None,
        workspace_id: int | str | None = None,
        knowledge_base_id: int | str | None = None,
        document_id: int | str | None = None,
    ) -> RagFileSyncResult:
        observed_scope.update(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        assert file_store is store
        return RagFileSyncResult(
            status="synced",
            message="已切分 1 个片段并同步到 Milvus。",
            collection="datawhisperer_rag_documents",
            chunk_count=1,
            synced_at="2026-06-24T00:00:00+00:00",
            chunks=(
                RagIndexedChunk(
                    chunk_id=f"{file_id}_0_test",
                    chunk_index=0,
                    content="GMV 指标口径：订单明细金额合计。",
                    content_hash="test-content-hash",
                    vector_collection="datawhisperer_rag_documents",
                    synced_at="2026-06-24T00:00:00+00:00",
                ),
            ),
        )

    monkeypatch.setattr(files_api, "get_rag_file_store", lambda: store)
    monkeypatch.setattr(files_api, "sync_rag_file_to_milvus", fake_sync)

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    try:
        with TestClient(app) as client:
            register_response = client.post(
                "/api/auth/register",
                json={
                    "tenant_name": "知识库租户",
                    "tenant_key": "kb-test",
                    "display_name": "tester",
                    "email": "tester@example.com",
                    "password": "12345678",
                },
            )
            assert register_response.status_code == 200
            headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}

            response = client.post(
                "/api/files/rag",
                headers=headers,
                files={"file": ("metrics.md", "GMV 指标口径说明", "text/markdown")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["sync_status"] == "synced"
    assert payload["sync_chunk_count"] == 1

    with session_factory() as session:
        knowledge_base = session.scalar(select(KnowledgeBase))
        document = session.scalar(select(KnowledgeDocument))
        chunk = session.scalar(select(KnowledgeChunk))

    assert knowledge_base is not None
    assert knowledge_base.name == "默认知识库"
    assert document is not None
    assert document.tenant_id == knowledge_base.tenant_id
    assert document.workspace_id == knowledge_base.workspace_id
    assert document.knowledge_base_id == knowledge_base.id
    assert document.sync_status == "synced"
    assert chunk is not None
    assert chunk.document_id == document.id
    assert chunk.tenant_id == document.tenant_id
    assert chunk.workspace_id == document.workspace_id
    assert observed_scope == {
        "tenant_id": document.tenant_id,
        "workspace_id": document.workspace_id,
        "knowledge_base_id": knowledge_base.id,
        "document_id": document.id,
    }
