from types import SimpleNamespace

from app.rag.document_indexer import split_text_into_chunks, sync_rag_file_to_milvus
from app.tools.file_store import FileStoreConfig, ManagedFileStore


class FakeEmbedder:
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.file_id = ""
        self.documents = []

    def replace_file_documents(self, file_id, documents):
        self.file_id = file_id
        self.documents = documents
        return len(documents)


def test_split_text_into_chunks_keeps_overlap_and_limits_size() -> None:
    text = "\n".join(f"第 {index} 条业务规则：销售额需要按订单明细金额汇总。" for index in range(30))

    chunks = split_text_into_chunks(text, chunk_size=120, overlap=20)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= 140 for chunk in chunks)


def test_sync_rag_file_to_milvus_builds_documents(tmp_path) -> None:
    file_store = ManagedFileStore(
        FileStoreConfig(
            category="rag",
            directory=tmp_path,
            allowed_extensions=frozenset({".md"}),
        )
    )
    saved = file_store.save(
        original_name="business_rules.md",
        content=("GMV 是订单明细金额合计。\n" * 20).encode("utf-8"),
    )
    vector_store = FakeVectorStore()
    settings = SimpleNamespace(
        rag_chunk_size=120,
        rag_chunk_overlap=20,
        milvus_rag_collection="datawhisperer_rag_documents",
        milvus_uri="http://127.0.0.1:19530",
        rag_embedding_dimension=4,
    )

    result = sync_rag_file_to_milvus(
        saved.id,
        file_store=file_store,
        settings=settings,
        embedder=FakeEmbedder(),
        vector_store=vector_store,
        tenant_id=10,
        workspace_id=20,
        knowledge_base_id=30,
        document_id=40,
    )

    assert result.status == "synced"
    assert result.collection == "datawhisperer_rag_documents"
    assert result.chunk_count == len(vector_store.documents)
    assert vector_store.file_id == saved.id
    assert vector_store.documents[0].file_id == saved.id
    assert vector_store.documents[0].file_name == "business_rules.md"
    assert vector_store.documents[0].tenant_id == "10"
    assert vector_store.documents[0].workspace_id == "20"
    assert vector_store.documents[0].knowledge_base_id == "30"
    assert vector_store.documents[0].document_id == "40"
    assert vector_store.documents[0].vector == [1.0, 0.0, 0.0, 0.0]
    assert result.chunks[0].vector_collection == "datawhisperer_rag_documents"
