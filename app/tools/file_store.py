from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.models.files import FilePreview, ManagedFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"

TEXT_PREVIEW_EXTENSIONS = {".csv", ".json", ".md", ".sql", ".txt", ".yaml", ".yml"}


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


class ManagedFileStore:
    """本地文件管理工具。

    V3.5 的页面上传先落到本地 storage 目录，形成一个稳定的“资料管理台”。
    后续可以在这个基础上继续做 CSV 入库、schema 自动解析、RAG 切片和 Milvus 索引同步。
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
        }
        self._meta_path(file_id).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return ManagedFile(**{key: metadata[key] for key in ManagedFile.model_fields})

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

    def _load_metadata(self, meta_path: Path) -> ManagedFile | None:
        try:
            metadata = json.loads(meta_path.read_text("utf-8"))
            file_path = self._resolve_file(metadata["stored_name"])
            if not file_path.exists():
                return None
            metadata["size_bytes"] = file_path.stat().st_size
            return ManagedFile(**{key: metadata[key] for key in ManagedFile.model_fields})
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def _read_metadata(self, file_id: str) -> dict | None:
        if not _is_safe_file_id(file_id):
            return None
        meta_path = self._meta_path(file_id)
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _meta_path(self, file_id: str) -> Path:
        return self._resolve_file(f"{file_id}.meta.json")

    def _resolve_file(self, filename: str) -> Path:
        path = (self.config.directory / filename).resolve()
        if not path.is_relative_to(self.config.directory.resolve()):
            raise ValueError("文件路径不安全。")
        return path


def _sanitize_filename(filename: str) -> str:
    """清理文件名，避免路径穿越和奇怪控制字符。"""

    name = Path(filename).name.strip()
    name = re.sub(r"[\x00-\x1f]", "", name)
    return name or "untitled"


def _is_safe_file_id(file_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", file_id))


def get_schema_file_store() -> ManagedFileStore:
    return ManagedFileStore(SCHEMA_FILE_STORE)


def get_rag_file_store() -> ManagedFileStore:
    return ManagedFileStore(RAG_FILE_STORE)
