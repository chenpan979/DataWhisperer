from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings, get_settings


class TextEmbedder(Protocol):
    """文本向量化器接口。

    Milvus 检索层只关心“给我一段文本，我拿到一个向量”。
    至于向量来自 DashScope、OpenAI、bge-m3，还是本地 hashing，都不应该影响
    Milvus 同步和检索流程。
    """

    def embed(self, text: str) -> list[float]:
        """把文本转换为向量。"""


@dataclass(frozen=True)
class HashingTextEmbedder:
    """轻量文本向量化器。

    V3.3 的重点是把“指标口径检索”接入 Milvus 向量数据库，而不是一开始就绑定
    某个收费 embedding 模型。因此这里先使用 hashing trick 做一个稳定、可重复、
    零外部依赖的本地向量化器。

    它的定位可以理解成：
    - 适合本地开发、测试、面试演示；
    - 能把文本转换成 Milvus 需要的固定维度向量；
    - 后续可以替换成 Qwen Embedding、OpenAI Embedding 或 bge-m3 等真实向量模型。
    """

    dimension: int = 128

    def embed(self, text: str) -> list[float]:
        """把一段文本转换成归一化向量。

        Milvus 的向量字段要求每条数据维度一致，所以这里固定输出 `dimension`
        个浮点数。最后做 L2 归一化，方便使用余弦相似度或内积类检索。
        """

        if self.dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")

        vector = [0.0] * self.dimension
        for token in _tokenize(text):
            index = _stable_hash(token) % self.dimension
            sign = 1.0 if _stable_hash(f"{token}:sign") % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]


def _tokenize(text: str) -> list[str]:
    """把中英文混合文本切成适合 hashing 的 token。

    中文用单字和 bigram，英文/数字用单词 token。这样做虽然比不上真实 embedding，
    但对“GMV、客单价、订单数、复购率”这类短指标文档已经足够形成可检索向量。
    """

    normalized = text.casefold()
    tokens = re.findall(r"[a-z0-9_]+", normalized)

    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
    return tokens


def _stable_hash(value: str) -> int:
    """生成跨进程稳定的哈希值。

    Python 内置 hash 会受随机种子影响，不适合做可复现向量；这里用 md5 只作为
    稳定散列，不用于安全场景。
    """

    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest, 16)


class DashScopeTextEmbedder:
    """DashScope OpenAI-compatible embedding 客户端。

    V3.4 开始，DataWhisperer 使用 DashScope `text-embedding-v4` 作为指标口径的
    真实语义向量模型。它通过 OpenAI-compatible `/embeddings` 接口调用，
    所以项目不需要额外引入厂商专用 SDK。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        client: Any | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.dimension = dimension
        self._client = client

    def embed(self, text: str) -> list[float]:
        """调用 DashScope embedding 模型生成向量。"""

        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量，供 Milvus 索引同步使用。"""

        if not texts:
            return []
        if not self.api_key or self.api_key == "replace-me":
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法调用 DashScope embedding。")

        response = self._get_client().embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimension,
            encoding_format="float",
        )
        vectors = [item.embedding for item in response.data]
        return [_normalize_vector(vector) for vector in vectors]

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment setup guard
            raise RuntimeError("未安装 openai，无法调用 DashScope embedding。") from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client


def create_text_embedder(settings: Settings | None = None) -> TextEmbedder:
    """根据配置创建文本向量化器。

    默认优先使用 DashScope `text-embedding-v4`。
    如果没有配置 Key 且允许兜底，则使用本地 hashing 向量器，保证项目仍可运行。
    """

    settings = settings or get_settings()
    provider = settings.embedding_provider.casefold()

    if provider == "dashscope":
        if settings.dashscope_enabled:
            return DashScopeTextEmbedder(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_api_base,
                model=settings.dashscope_embedding_model,
                dimension=settings.dashscope_embedding_dimension,
            )
        if settings.embedding_auto_fallback:
            return HashingTextEmbedder(dimension=settings.metric_embedding_dimension)
        raise RuntimeError("EMBEDDING_PROVIDER=dashscope 时必须配置 DASHSCOPE_API_KEY。")

    if provider in {"hashing", "local"}:
        return HashingTextEmbedder(dimension=settings.metric_embedding_dimension)

    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")


def _normalize_vector(vector: list[float]) -> list[float]:
    """对远程 embedding 返回值做一次 L2 归一化。"""

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]
