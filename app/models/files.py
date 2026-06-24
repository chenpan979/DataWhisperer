from pydantic import BaseModel, Field


class ManagedFile(BaseModel):
    """控制台里展示的一个已上传文件。"""

    id: str = Field(description="服务端生成的文件 ID，用于预览和删除。")
    name: str = Field(description="用户上传时的原始文件名。")
    size_bytes: int = Field(description="文件大小，单位字节。")
    extension: str = Field(description="文件扩展名。")
    uploaded_at: str = Field(description="上传时间，ISO 8601 字符串。")
    previewable: bool = Field(description="当前文件是否支持文本预览。")
    sync_status: str | None = Field(default=None, description="RAG 文件同步到向量库的状态。")
    sync_message: str | None = Field(default=None, description="最近一次同步说明或失败原因。")
    sync_collection: str | None = Field(default=None, description="RAG 文件写入的 Milvus collection。")
    sync_chunk_count: int | None = Field(default=None, description="最近一次同步写入的切片数量。")
    synced_at: str | None = Field(default=None, description="最近一次同步完成时间。")


class ManagedFileList(BaseModel):
    """文件列表响应。"""

    category: str
    files: list[ManagedFile]


class FilePreview(BaseModel):
    """文件预览响应。"""

    id: str
    name: str
    preview: str | None
    previewable: bool
