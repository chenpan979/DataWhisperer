from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DataSourcePayload(BaseModel):
    """前端系统设置页展示的默认数据源信息。

    注意：接口永远不返回真实密码，只返回是否已经保存过密码。
    """

    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    status: str
    password_saved: bool
    last_checked_at: datetime | None = None
    schema_synced_at: datetime | None = None
    schema_table_count: int = 0


class DataSourceUpdateRequest(BaseModel):
    """保存默认数据源配置。

    password 为空或为 ****** 时表示沿用后端已保存的密码，不做覆盖。
    """

    name: str = Field(min_length=1, max_length=128)
    db_type: str = Field(default="mysql", min_length=2, max_length=32)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class DataSourceConnectionTestResponse(BaseModel):
    """数据源连接检测结果。"""

    ok: bool
    message: str
    status: str
    table_count: int = 0
    latency_ms: int
    checked_at: datetime


class DataSourceSyncResponse(BaseModel):
    """系统设置页展示的 schema 同步状态。"""

    data_source: DataSourcePayload
    message: str
