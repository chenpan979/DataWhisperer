import pytest

fastapi = pytest.importorskip("fastapi")

from app.api import files as files_api  # noqa: E402
from app.main import create_app  # noqa: E402
from app.rag.document_indexer import RagFileSyncResult  # noqa: E402
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
