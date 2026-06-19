from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from threading import Lock

from app.models.conversations import (
    Conversation,
    ConversationCreate,
    ConversationTurn,
    ConversationUpdate,
)
from app.tools.file_store import STORAGE_ROOT


class ConversationStore:
    """本地会话持久化仓库。

    V3.11.4 先用 JSON 文件解决“刷新页面或重启后端后对话丢失”的问题。
    这个实现刻意保持简单：单机演示稳定、代码容易讲清楚，也不会影响示例 MySQL 数据库。
    """

    def __init__(self, path: Path | None = None):
        self.path = path or STORAGE_ROOT / "chat_conversations.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def list_conversations(self) -> list[Conversation]:
        """按更新时间倒序返回会话列表。"""

        with self._lock:
            conversations = self._read_unlocked()
        return sorted(conversations, key=lambda item: item.updatedAt, reverse=True)

    def create(self, payload: ConversationCreate | None = None) -> Conversation:
        """创建一个新会话并写入磁盘。"""

        data = payload or ConversationCreate()
        conversation = Conversation(
            id=f"conversation-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            title=data.title.strip() or "新对话",
            subtitle=data.subtitle.strip() or "等待数据问题",
            preview=data.preview.strip() or "等待数据问题",
            customTitle=False,
            updatedAt=_now_ms(),
            turns=[],
        )
        with self._lock:
            conversations = self._read_unlocked()
            conversations.insert(0, conversation)
            self._write_unlocked(conversations)
        return conversation

    def update(self, conversation_id: str, payload: ConversationUpdate) -> Conversation | None:
        """更新会话标题、摘要、是否自定义标题等元信息。"""

        with self._lock:
            conversations = self._read_unlocked()
            conversation = _find_conversation(conversations, conversation_id)
            if conversation is None:
                return None
            update_data = payload.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    setattr(conversation, key, value)
            conversation.updatedAt = _now_ms()
            self._write_unlocked(conversations)
            return conversation

    def append_turn(self, conversation_id: str, turn: ConversationTurn) -> Conversation | None:
        """给指定会话追加一轮问答。

        如果前端重复提交同一个 traceId，这里会做幂等处理，避免刷新或重试造成重复轮次。
        """

        with self._lock:
            conversations = self._read_unlocked()
            conversation = _find_conversation(conversations, conversation_id)
            if conversation is None:
                return None
            if not any(item.traceId == turn.traceId for item in conversation.turns):
                conversation.turns.append(turn)
            conversation.preview = turn.insight or turn.question or conversation.preview
            conversation.updatedAt = _now_ms()
            self._write_unlocked(conversations)
            return conversation

    def delete(self, conversation_id: str) -> bool:
        """删除指定会话。"""

        with self._lock:
            conversations = self._read_unlocked()
            next_conversations = [item for item in conversations if item.id != conversation_id]
            if len(next_conversations) == len(conversations):
                return False
            self._write_unlocked(next_conversations)
            return True

    def _read_unlocked(self) -> list[Conversation]:
        if not self.path.exists():
            return []
        try:
            raw_items = json.loads(self.path.read_text("utf-8"))
            if not isinstance(raw_items, list):
                return []
            return [Conversation.model_validate(item) for item in raw_items]
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return []

    def _write_unlocked(self, conversations: list[Conversation]) -> None:
        payload = [conversation.model_dump() for conversation in conversations]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def _find_conversation(
    conversations: list[Conversation],
    conversation_id: str,
) -> Conversation | None:
    return next((item for item in conversations if item.id == conversation_id), None)


def _now_ms() -> int:
    return int(time.time() * 1000)


def get_conversation_store() -> ConversationStore:
    return ConversationStore()

