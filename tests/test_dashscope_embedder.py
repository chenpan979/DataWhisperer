from types import SimpleNamespace

from app.core.config import Settings
from app.rag.embeddings import (
    DashScopeTextEmbedder,
    HashingTextEmbedder,
    create_text_embedder,
)


class FakeEmbeddingEndpoint:
    def __init__(self) -> None:
        self.request = {}

    def create(self, *, model: str, input: list[str], dimensions: int):
        self.request = {
            "model": model,
            "input": input,
            "dimensions": dimensions,
        }
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[3.0, 4.0]),
                SimpleNamespace(embedding=[0.0, 5.0]),
            ]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddingEndpoint()


def test_dashscope_embedder_calls_openai_compatible_embeddings_api() -> None:
    client = FakeOpenAIClient()
    embedder = DashScopeTextEmbedder(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="text-embedding-v4",
        dimension=1024,
        client=client,
    )

    vectors = embedder.embed_batch(["GMV 趋势", "客单价最高的地区"])

    assert client.embeddings.request == {
        "model": "text-embedding-v4",
        "input": ["GMV 趋势", "客单价最高的地区"],
        "dimensions": 1024,
    }
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]


def test_create_text_embedder_uses_dashscope_when_key_exists() -> None:
    settings = Settings(
        dashscope_api_key="test-key",
        embedding_provider="dashscope",
        dashscope_embedding_dimension=1024,
    )

    embedder = create_text_embedder(settings)

    assert isinstance(embedder, DashScopeTextEmbedder)


def test_create_text_embedder_falls_back_to_hashing_without_key() -> None:
    settings = Settings(
        dashscope_api_key="replace-me",
        embedding_provider="dashscope",
        embedding_auto_fallback=True,
        dashscope_embedding_dimension=16,
    )

    embedder = create_text_embedder(settings)

    assert isinstance(embedder, HashingTextEmbedder)
    assert len(embedder.embed("GMV 趋势")) == 16
