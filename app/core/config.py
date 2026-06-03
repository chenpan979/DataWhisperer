from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用运行配置。

    所有会随环境变化的内容都放到配置里，而不是写死在业务代码中。
    例如数据库地址、模型地址、API Key、最大查询行数等。
    """

    app_name: str = "DataWhisperer"
    app_env: str = "dev"
    log_level: str = "INFO"

    database_url: str = Field(
        default="mysql+pymysql://root:password@127.0.0.1:3306/datawhisperer_demo?charset=utf8mb4"
    )
    query_timeout_seconds: int = 20
    max_query_rows: int = 100

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = "replace-me"
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.1

    dashscope_api_key: str = "replace-me"
    dashscope_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_embedding_model: str = "text-embedding-v4"
    dashscope_embedding_dimension: int = 1024

    embedding_provider: str = "dashscope"
    embedding_auto_fallback: bool = True

    metric_retrieval_provider: str = "local"
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_metric_collection: str = "datawhisperer_metrics"
    milvus_embedding_dim: int = 1024
    milvus_auto_fallback: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def llm_enabled(self) -> bool:
        """判断当前是否真的配置了可用的大模型 API Key。"""

        return bool(self.effective_llm_api_key)

    @property
    def dashscope_enabled(self) -> bool:
        """判断当前是否配置了 DashScope API Key。"""

        return bool(self.dashscope_api_key and self.dashscope_api_key != "replace-me")

    @property
    def effective_llm_api_key(self) -> str | None:
        """返回聊天模型实际使用的 API Key。

        兼容两种写法：
        - `LLM_API_KEY`：通用 OpenAI-compatible 配置；
        - `DASHSCOPE_API_KEY`：DashScope 专用配置。
        """

        if self.llm_api_key and self.llm_api_key != "replace-me":
            return self.llm_api_key
        if self.dashscope_enabled:
            return self.dashscope_api_key
        return None

    @property
    def effective_llm_base_url(self) -> str:
        """返回聊天模型实际使用的 base URL。"""

        if self.llm_api_key and self.llm_api_key != "replace-me":
            return self.llm_base_url
        return self.dashscope_api_base

    @property
    def effective_llm_model(self) -> str:
        """返回聊天模型实际使用的模型名。"""

        if self.llm_api_key and self.llm_api_key != "replace-me":
            return self.llm_model
        return self.dashscope_model

    @property
    def metric_embedding_dimension(self) -> int:
        """返回指标向量索引使用的维度。

        Milvus collection 的维度必须和 embedding 模型输出维度一致。
        V3.4 默认使用 DashScope `text-embedding-v4` 的 1024 维配置。
        """

        if self.embedding_provider.casefold() == "dashscope":
            return self.dashscope_embedding_dimension
        return self.milvus_embedding_dim


@lru_cache
def get_settings() -> Settings:
    """读取并缓存配置。

    配置对象在进程内复用，避免每次请求都重复解析 .env。
    修改 .env 后需要重启服务才能生效。
    """

    return Settings()
