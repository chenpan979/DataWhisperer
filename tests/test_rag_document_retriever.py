from app.rag.document_retriever import RagDocumentRetriever, RagKnowledgeScope
from app.rag.milvus_document_store import MilvusRagDocumentStore, MilvusRagSearchHit


class FakeClient:
    def __init__(self) -> None:
        self.search_kwargs = {}

    def has_collection(self, collection_name: str) -> bool:
        return collection_name == "datawhisperer_rag_documents"

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        return [
            [
                {
                    "entity": {
                        "id": "chunk-1",
                        "tenant_id": "10",
                        "workspace_id": "20",
                        "knowledge_base_id": "30",
                        "document_id": "40",
                        "file_id": "file-1",
                        "file_name": "metrics.md",
                        "chunk_index": 2,
                        "content": "GMV 指标口径：订单明细金额合计。",
                    },
                    "distance": 0.87,
                }
            ]
        ]


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        assert "GMV" in text
        return [0.1, 0.2, 0.3, 0.4]


class FakeStore:
    def __init__(self) -> None:
        self.scope = {}

    def search(self, vector, *, tenant_id, workspace_id, knowledge_base_id=None, top_k=4):
        self.scope = {
            "vector": vector,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "knowledge_base_id": knowledge_base_id,
            "top_k": top_k,
        }
        return [
            MilvusRagSearchHit(
                chunk_id="chunk-1",
                tenant_id=str(tenant_id),
                workspace_id=str(workspace_id),
                knowledge_base_id=str(knowledge_base_id),
                document_id="40",
                file_id="file-1",
                file_name="metrics.md",
                chunk_index=0,
                content="GMV 指标口径：订单明细金额合计。",
                score=0.91,
            )
        ]


class FailingStore:
    def search(self, *args, **kwargs):
        raise RuntimeError("Milvus unavailable")


def test_milvus_rag_document_store_search_adds_scope_filter() -> None:
    store = MilvusRagDocumentStore(
        uri="http://127.0.0.1:19530",
        collection_name="datawhisperer_rag_documents",
        dimension=4,
    )
    fake_client = FakeClient()
    store._client = lambda: fake_client  # type: ignore[method-assign]

    hits = store.search(
        [0.1, 0.2, 0.3, 0.4],
        tenant_id=10,
        workspace_id=20,
        knowledge_base_id=30,
        top_k=3,
    )

    assert fake_client.search_kwargs["filter"] == (
        'tenant_id == "10" and workspace_id == "20" and knowledge_base_id == "30"'
    )
    assert fake_client.search_kwargs["limit"] == 3
    assert hits[0].file_name == "metrics.md"
    assert hits[0].score == 0.87


def test_rag_document_retriever_returns_prompt_context_with_scope() -> None:
    store = FakeStore()
    retriever = RagDocumentRetriever(
        store=store,  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        auto_fallback=True,
    )

    result = retriever.retrieve(
        "请解释 GMV",
        scope=RagKnowledgeScope(tenant_id=10, workspace_id=20, knowledge_base_id=30),
        top_k=2,
    )

    assert result.sources == ["metrics.md#0"]
    assert "知识库资料：metrics.md" in result.prompt_context
    assert "订单明细金额合计" in result.prompt_context
    assert store.scope == {
        "vector": [0.1, 0.2, 0.3, 0.4],
        "tenant_id": 10,
        "workspace_id": 20,
        "knowledge_base_id": 30,
        "top_k": 2,
    }


def test_rag_document_retriever_falls_back_to_empty_result() -> None:
    retriever = RagDocumentRetriever(
        store=FailingStore(),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        auto_fallback=True,
    )

    result = retriever.retrieve(
        "请解释 GMV",
        scope=RagKnowledgeScope(tenant_id=10, workspace_id=20),
    )

    assert result.sources == []
    assert result.retrieval_mode == "milvus_rag_vector_v1_fallback"
