import math

import pytest

from app.rag.embeddings import HashingTextEmbedder


def test_hashing_embedder_returns_fixed_dimension_vector() -> None:
    embedder = HashingTextEmbedder(dimension=16)

    vector = embedder.embed("GMV 最近 6 个月趋势")

    assert len(vector) == 16
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, rel_tol=1e-6)


def test_hashing_embedder_is_deterministic() -> None:
    embedder = HashingTextEmbedder(dimension=32)

    left = embedder.embed("客单价最高的地区")
    right = embedder.embed("客单价最高的地区")

    assert left == right


def test_hashing_embedder_rejects_invalid_dimension() -> None:
    embedder = HashingTextEmbedder(dimension=0)

    with pytest.raises(ValueError, match="dimension"):
        embedder.embed("GMV")
