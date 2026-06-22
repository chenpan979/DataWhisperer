from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.db.product_models import Conversation as ConversationRecord
from app.models.conversations import (
    Conversation,
    ConversationCreate,
    ConversationTurn,
    ConversationUpdate,
)
from app.repositories.product import (
    AnalysisRunRepository,
    AuditLogRepository,
    ConversationRepository,
    DataSourceRepository,
)
from app.tools.conversation_store import ConversationStore as LegacyConversationStore

SUMMARY_PREFIX = "json:"
TURN_MESSAGE_TYPE = "analysis_turn"
LEGACY_MIGRATION_ACTION = "conversation.legacy_json.migrated"


class DatabaseConversationStore:
    """数据库版 AI 查数会话仓库。

    V3.11 阶段先用 `storage/chat_conversations.json` 解决会话丢失问题。
    V3.13.4 开始，会话真正落到 `datawhisperer_product`：
    - `conversations` 保存会话标题、摘要和归属；
    - `chat_messages` 保存用户消息和前端完整回答快照；
    - `analysis_runs` 保存 SQL、表格、图表、trace 等结构化分析结果。
    """

    def __init__(self, session: Session, auth_context: AuthContext):
        self.session = session
        self.auth = auth_context
        self.conversations = ConversationRepository(session)
        self.analysis_runs = AnalysisRunRepository(session)
        self.audit_logs = AuditLogRepository(session)

    def list_conversations(self) -> list[Conversation]:
        """按当前工作空间列出最近会话。"""

        records = self.conversations.list_recent(workspace_id=self.auth.workspace.id)
        if not records:
            self._migrate_legacy_json_if_needed()
            records = self.conversations.list_recent(workspace_id=self.auth.workspace.id)
        return [self._to_response(record) for record in records]

    def create(self, payload: ConversationCreate | None = None) -> Conversation:
        """创建新会话。"""

        data = payload or ConversationCreate()
        record = self.conversations.create(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            title=data.title.strip() or "新对话",
            summary=_pack_summary(
                subtitle=data.subtitle.strip() or "等待数据问题",
                preview=data.preview.strip() or "等待数据问题",
                custom_title=False,
            ),
        )
        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action="conversation.created",
            target_type="conversation",
            target_id=str(record.id),
        )
        self.session.commit()
        return self._to_response(record)

    def update(self, conversation_id: str, payload: ConversationUpdate) -> Conversation | None:
        """更新会话元信息。"""

        record = self._get_owned_record(conversation_id)
        if record is None:
            return None

        current_meta = _unpack_summary(record.summary)
        next_title = payload.title.strip() if payload.title is not None else record.title
        next_meta = {
            "subtitle": payload.subtitle if payload.subtitle is not None else current_meta["subtitle"],
            "preview": payload.preview if payload.preview is not None else current_meta["preview"],
            "customTitle": (
                payload.customTitle
                if payload.customTitle is not None
                else current_meta["customTitle"]
            ),
        }
        self.conversations.update_metadata(
            record,
            title=next_title or "新对话",
            summary=_pack_summary(
                subtitle=next_meta["subtitle"] or "等待数据问题",
                preview=next_meta["preview"] or "等待数据问题",
                custom_title=bool(next_meta["customTitle"]),
            ),
        )
        for turn in payload.turns or []:
            self._save_turn_snapshot(record, turn)
        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action="conversation.updated",
            target_type="conversation",
            target_id=str(record.id),
        )
        self.session.commit()
        return self._to_response(record)

    def append_turn(self, conversation_id: str, turn: ConversationTurn) -> Conversation | None:
        """追加一轮问答，并拆分保存到消息表和分析运行表。"""

        record = self._get_owned_record(conversation_id)
        if record is None:
            return None

        self._save_turn_snapshot(record, turn)
        meta = _unpack_summary(record.summary)
        self.conversations.update_metadata(
            record,
            summary=_pack_summary(
                subtitle=meta["subtitle"],
                preview=turn.insight or turn.question or meta["preview"],
                custom_title=meta["customTitle"],
            ),
        )
        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action="analysis_run.saved",
            target_type="conversation",
            target_id=str(record.id),
            detail={"trace_id": turn.traceId},
        )
        self.session.commit()
        return self._to_response(record)

    def _save_turn_snapshot(self, record: ConversationRecord, turn: ConversationTurn) -> None:
        """把一轮完整回答拆成消息快照和结构化分析结果。

        前端需要恢复“当时看到的卡片”，所以 `chat_messages` 保存完整
        `ConversationTurn` JSON；后续做审计、评测和结果复盘时，再从
        `analysis_runs` 读取 SQL、图表、表格和 trace 等结构化字段。
        """

        if self.analysis_runs.get_by_trace_id(turn.traceId) is not None:
            return

        self.conversations.append_message(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            conversation_id=record.id,
            role="user",
            content=turn.question,
        )
        assistant_message = self.conversations.append_message(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            conversation_id=record.id,
            role="assistant",
            content=turn.model_dump_json(),
            content_type=TURN_MESSAGE_TYPE,
        )
        data_source = DataSourceRepository(self.session).get_default_for_workspace(self.auth.workspace)
        self.analysis_runs.create(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            conversation_id=record.id,
            message_id=assistant_message.id,
            data_source_id=data_source.id if data_source else None,
            trace_id=turn.traceId,
            question=turn.question,
            generated_sql=turn.generatedSql,
            sql_explanation=turn.sqlExplanation,
            result_columns=turn.columns,
            result_rows_preview=turn.rows,
            chart_option=turn.chart,
            insight=turn.insight,
            trace_steps=turn.traceSteps,
            warnings=turn.warnings,
            prompt_versions={},
            status="success",
        )

    def delete(self, conversation_id: str) -> bool:
        """软删除会话。"""

        record = self._get_owned_record(conversation_id)
        if record is None:
            return False
        self.conversations.archive(record)
        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action="conversation.deleted",
            target_type="conversation",
            target_id=str(record.id),
        )
        self.session.commit()
        return True

    def _get_owned_record(self, conversation_id: str) -> ConversationRecord | None:
        try:
            record_id = int(conversation_id)
        except ValueError:
            return None
        record = self.conversations.get_by_id(record_id)
        if record is None:
            return None
        if record.tenant_id != self.auth.tenant.id or record.workspace_id != self.auth.workspace.id:
            return None
        if record.status != "active":
            return None
        return record

    def _to_response(self, record: ConversationRecord) -> Conversation:
        meta = _unpack_summary(record.summary)
        turns = self._load_turns(record.id)
        preview = meta["preview"]
        if turns and (not preview or preview == "等待数据问题"):
            preview = turns[-1].insight or turns[-1].question
        return Conversation(
            id=str(record.id),
            title=record.title,
            subtitle=meta["subtitle"],
            preview=preview,
            customTitle=meta["customTitle"],
            updatedAt=_datetime_to_ms(record.updated_at),
            turns=turns,
        )

    def _load_turns(self, conversation_id: int) -> list[ConversationTurn]:
        messages = self.conversations.list_messages(conversation_id=conversation_id)
        turns: list[ConversationTurn] = []
        for message in messages:
            if message.role != "assistant" or message.content_type != TURN_MESSAGE_TYPE:
                continue
            try:
                turns.append(ConversationTurn.model_validate_json(message.content))
            except ValueError:
                continue
        return turns

    def _migrate_legacy_json_if_needed(self) -> None:
        """把旧 JSON 会话一次性迁移到 demo 管理员的产品库会话中。"""

        if self.auth.tenant.tenant_key != "demo":
            return
        if self.audit_logs.exists(
            tenant_id=self.auth.tenant.id,
            user_id=self.auth.user.id,
            action=LEGACY_MIGRATION_ACTION,
        ):
            return

        legacy_conversations = LegacyConversationStore().list_conversations()
        for legacy in reversed(legacy_conversations):
            record = self.conversations.create(
                tenant_id=self.auth.tenant.id,
                workspace_id=self.auth.workspace.id,
                user_id=self.auth.user.id,
                title=legacy.title,
                summary=_pack_summary(
                    subtitle=legacy.subtitle,
                    preview=legacy.preview,
                    custom_title=legacy.customTitle,
                ),
            )
            for turn in legacy.turns:
                self.append_turn(str(record.id), turn)

        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action=LEGACY_MIGRATION_ACTION,
            target_type="user",
            target_id=str(self.auth.user.id),
            detail={"count": len(legacy_conversations)},
        )
        self.session.commit()


def _pack_summary(*, subtitle: str, preview: str, custom_title: bool) -> str:
    """把前端会话摘要字段压缩存到 conversations.summary。"""

    payload = {
        "subtitle": subtitle[:160],
        "preview": preview[:240],
        "customTitle": custom_title,
    }
    return f"{SUMMARY_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def _unpack_summary(summary: str | None) -> dict[str, Any]:
    """读取 conversations.summary 中的前端摘要信息。"""

    if not summary:
        return {"subtitle": "等待数据问题", "preview": "等待数据问题", "customTitle": False}
    if summary.startswith(SUMMARY_PREFIX):
        try:
            payload = json.loads(summary[len(SUMMARY_PREFIX) :])
            return {
                "subtitle": payload.get("subtitle") or "等待数据问题",
                "preview": payload.get("preview") or "等待数据问题",
                "customTitle": bool(payload.get("customTitle")),
            }
        except (TypeError, json.JSONDecodeError):
            pass
    return {"subtitle": summary, "preview": summary, "customTitle": False}


def _datetime_to_ms(value: datetime | None) -> int:
    if value is None:
        return int(time.time() * 1000)
    return int(value.timestamp() * 1000)
