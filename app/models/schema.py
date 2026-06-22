from pydantic import BaseModel, Field


class SchemaSyncResponse(BaseModel):
    """Schema 同步结果。"""

    data_source_id: int = Field(description="本次同步的数据源 ID。")
    data_source_name: str = Field(description="本次同步的数据源名称。")
    table_count: int = Field(description="同步后的表数量。")
    column_count: int = Field(description="同步后的字段数量。")
    relationship_count: int = Field(description="同步后的表关系数量。")
    synced_at: str = Field(description="同步完成时间。")
    source: str = Field(default="database", description="同步来源。")
