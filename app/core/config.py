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

    metric_retrieval_provider: str = "local"
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_metric_collection: str = "datawhisperer_metrics"
    milvus_embedding_dim: int = 128
    milvus_auto_fallback: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def llm_enabled(self) -> bool:
        """判断当前是否真的配置了可用的大模型 API Key。"""

        return bool(self.llm_api_key and self.llm_api_key != "replace-me")


@lru_cache
def get_settings() -> Settings:
    """读取并缓存配置。

    配置对象在进程内复用，避免每次请求都重复解析 .env。
    修改 .env 后需要重启服务才能生效。
    """

    return Settings()
