from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


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
