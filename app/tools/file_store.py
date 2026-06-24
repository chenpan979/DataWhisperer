from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.files import FilePreview, ManagedFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"

TEXT_PREVIEW_EXTENSIONS = {".csv", ".json", ".jsonl", ".md", ".sql", ".txt", ".yaml", ".yml"}


@dataclass(frozen=True)
class FileStoreConfig:
    """文件管理目录配置。"""

    category: str
    directory: Path
    allowed_extensions: frozenset[str]
    max_bytes: int = 10 * 1024 * 1024


SCHEMA_FILE_STORE = FileStoreConfig(
    category="schema",
    directory=STORAGE_ROOT / "schema_files",
    allowed_extensions=frozenset({".csv", ".json", ".md", ".sql", ".txt", ".xlsx", ".xls"}),
)

RAG_FILE_STORE = FileStoreConfig(
    category="rag",
    directory=STORAGE_ROOT / "rag_knowledge",
    allowed_extensions=frozenset({".csv", ".json", ".md", ".pdf", ".sql", ".txt", ".xlsx", ".xls"}),
)

EVALUATION_DATASET_STORE = FileStoreConfig(
    category="evaluation_dataset",
    directory=STORAGE_ROOT / "evaluation_datasets",
    allowed_extensions=frozenset({".csv", ".json", ".jsonl", ".txt", ".yaml", ".yml"}),
)


class ManagedFileStore:
    """本地文件管理工具。

    V3.5 的页面上传先落到本地 storage 目录，形成一个稳定的“资料管理台”。
    V3.13.11 开始，RAG 知识库文件上传后会把同步状态写回元数据，
    前端可以直接看到文件是否已经完成 Milvus 向量索引。
    """

    def __init__(self, config: FileStoreConfig):
        self.config = config
        self.config.directory.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> list[ManagedFile]:
        """按上传时间倒序列出文件。"""

        files = []
        for meta_path in sorted(self.config.directory.glob("*.meta.json")):
            file = self._load_metadata(meta_path)
            if file:
                files.append(file)
        return sorted(files, key=lambda item: item.uploaded_at, reverse=True)

    def save(self, *, original_name: str, content: bytes) -> ManagedFile:
        """保存上传文件并写入元数据。"""

        if not original_name:
            raise ValueError("文件名不能为空。")
        if not content:
            raise ValueError("不能上传空文件。")
        if len(content) > self.config.max_bytes:
            raise ValueError(f"文件不能超过 {self.config.max_bytes // 1024 // 1024} MB。")

        extension = Path(original_name).suffix.casefold()
        if extension not in self.config.allowed_extensions:
            allowed = ", ".join(sorted(self.config.allowed_extensions))
            raise ValueError(f"不支持的文件类型：{extension or '无扩展名'}。允许类型：{allowed}")

        file_id = uuid.uuid4().hex
        safe_name = _sanitize_filename(original_name)
        stored_name = f"{file_id}{extension}"
        file_path = self._resolve_file(stored_name)
        file_path.write_bytes(content)

        metadata = {
            "id": file_id,
            "name": safe_name,
            "size_bytes": len(content),
            "extension": extension,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "stored_name": stored_name,
            "previewable": extension in TEXT_PREVIEW_EXTENSIONS,
            "sync_status": None,
            "sync_message": None,
            "sync_collection": None,
            "sync_chunk_count": None,
            "synced_at": None,
        }
        self._meta_path(file_id).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return _managed_file_from_metadata(metadata)

    def delete(self, file_id: str) -> bool:
        """删除文件和元数据。"""

        metadata = self._read_metadata(file_id)
        if not metadata:
            return False
        file_path = self._resolve_file(metadata["stored_name"])
        meta_path = self._meta_path(file_id)
        if file_path.exists():
            file_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        return True

    def preview(self, file_id: str, max_chars: int = 4000) -> FilePreview | None:
        """返回文本文件预览。"""

        metadata = self._read_metadata(file_id)
        if not metadata:
            return None
        if not metadata.get("previewable"):
            return FilePreview(
                id=metadata["id"],
                name=metadata["name"],
                preview=None,
                previewable=False,
            )
        file_path = self._resolve_file(metadata["stored_name"])
        text = file_path.read_text("utf-8", errors="replace")
        return FilePreview(
            id=metadata["id"],
            name=metadata["name"],
            preview=text[:max_chars],
            previewable=True,
        )

    def get(self, file_id: str) -> ManagedFile | None:
        """读取单个文件元数据。"""

        metadata = self._read_metadata(file_id)
        if not metadata:
            return None
        file_path = self._resolve_file(metadata["stored_name"])
        if not file_path.exists():
            return None
        metadata["size_bytes"] = file_path.stat().st_size
        return _managed_file_from_metadata(metadata)

    def update_metadata(self, file_id: str, values: dict[str, Any]) -> ManagedFile | None:
        """更新文件展示元数据。

        目前主要给 RAG 同步流程写入 sync_status、chunk_count 等字段。
        只允许更新 ManagedFile 暴露的字段，避免误把内部路径信息改坏。
        """

        metadata = self._read_metadata(file_id)
        if not metadata:
            return None
        for key, value in values.items():
            if key in ManagedFile.model_fields:
                metadata[key] = value
        self._meta_path(file_id).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return _managed_file_from_metadata(metadata)

    def read_text_file(self, file_id: str) -> tuple[ManagedFile, str] | None:
        """读取文本文件完整内容，用于后续解析评测集或知识库资料。"""

        metadata = self._read_metadata(file_id)
        if not metadata or not metadata.get("previewable"):
            return None
        file_path = self._resolve_file(metadata["stored_name"])
        file = _managed_file_from_metadata(metadata)
        return file, file_path.read_text("utf-8-sig", errors="replace")

    def _load_metadata(self, meta_path: Path) -> ManagedFile | None:
        try:
            metadata = json.loads(meta_path.read_text("utf-8"))
            file_path = self._resolve_file(metadata["stored_name"])
            if not file_path.exists():
                return None
            metadata["size_bytes"] = file_path.stat().st_size
            metadata["previewable"] = _is_previewable(metadata)
            return _managed_file_from_metadata(metadata)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def _read_metadata(self, file_id: str) -> dict | None:
        if not _is_safe_file_id(file_id):
            return None
        meta_path = self._meta_path(file_id)
        if not meta_path.exists():
            return None
        try:
            metadata = json.loads(meta_path.read_text("utf-8"))
            metadata["previewable"] = _is_previewable(metadata)
            return metadata
        except (OSError, json.JSONDecodeError):
            return None

    def _meta_path(self, file_id: str) -> Path:
        return self._resolve_file(f"{file_id}.meta.json")

    def _resolve_file(self, filename: str) -> Path:
        path = (self.config.directory / filename).resolve()
        if not path.is_relative_to(self.config.directory.resolve()):
            raise ValueError("文件路径不安全。")
        return path



def _managed_file_from_metadata(metadata: dict[str, Any]) -> ManagedFile:
    """把元数据转换成前端响应模型。

    旧版本已经上传的文件没有 sync_* 字段，这里统一使用 `dict.get`，
    让历史元数据可以无缝升级，不需要额外迁移本地 JSON 文件。
    """

    return ManagedFile(**{key: metadata.get(key) for key in ManagedFile.model_fields})

def _sanitize_filename(filename: str) -> str:
    """清理文件名，避免路径穿越和奇怪控制字符。"""

    name = Path(filename).name.strip()
    name = re.sub(r"[\x00-\x1f]", "", name)
    return name or "untitled"


def _is_safe_file_id(file_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", file_id))


def _is_previewable(metadata: dict) -> bool:
    extension = str(metadata.get("extension") or Path(str(metadata.get("stored_name", ""))).suffix)
    return extension.casefold() in TEXT_PREVIEW_EXTENSIONS


def get_schema_file_store() -> ManagedFileStore:
    return ManagedFileStore(SCHEMA_FILE_STORE)


def get_rag_file_store() -> ManagedFileStore:
    return ManagedFileStore(RAG_FILE_STORE)


def get_evaluation_dataset_store() -> ManagedFileStore:
    return ManagedFileStore(EVALUATION_DATASET_STORE)
