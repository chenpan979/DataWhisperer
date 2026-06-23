from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.agent.orchestrator import DataAnalysisOrchestrator
from app.core.database import get_engine
from app.core.llm import get_llm_client
from app.core.product_database import get_product_session
from app.models.conversations import (
    Conversation,
    ConversationCreate,
    ConversationList,
    ConversationTurn,
    ConversationUpdate,
)
from app.models.query import QueryRequest, QueryResponse
from app.tools.data_source_engine import get_default_data_source_engine
from app.tools.database_conversation_store import DatabaseConversationStore

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=QueryResponse)
async def query_data(
    request: QueryRequest,
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> QueryResponse:
    """执行一次自然语言数据分析请求。

    API 层保持薄层设计：只负责接收请求、组装依赖、调用 Orchestrator、
    把异常转换成 HTTP 响应。具体业务流程放在 agent/tools 层。
    """

    try:
        engine = _build_query_engine(authorization=authorization, session=session)
        orchestrator = DataAnalysisOrchestrator(engine=engine, llm=get_llm_client())
        return await orchestrator.run(request)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external services
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


def _build_query_engine(*, authorization: str | None, session: Session) -> Engine:
    """为 AI 查数选择业务数据库连接。

    登录态下，AI 查数必须和系统设置里的默认数据源保持一致；未登录访问时，
    继续使用 `.env` 中的 `DATABASE_URL`，方便本地调试和接口文档演示。
    """

    if not authorization:
        return get_engine()
    auth_context = require_auth_context(authorization=authorization, session=session)
    return get_default_data_source_engine(
        session=session,
        auth_context=auth_context,
        fallback_engine_factory=get_engine,
    )


def _conversation_store(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> DatabaseConversationStore:
    """为当前登录用户创建数据库会话仓库。"""

    return DatabaseConversationStore(session=session, auth_context=auth_context)


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    store: DatabaseConversationStore = Depends(_conversation_store),
) -> ConversationList:
    """读取 AI 查数会话列表。

    前端启动时会调用这个接口，把服务端保存的历史会话恢复出来。
    如果没有任何历史记录，前端会再创建一个“新对话”作为默认入口。
    """

    conversations = store.list_conversations()
    active_id = conversations[0].id if conversations else None
    return ConversationList(conversations=conversations, activeConversationId=active_id)


@router.post("/conversations", response_model=Conversation)
def create_conversation(
    payload: ConversationCreate | None = None,
    store: DatabaseConversationStore = Depends(_conversation_store),
) -> Conversation:
    """创建一个新的 AI 查数会话。"""

    return store.create(payload)


@router.patch("/conversations/{conversation_id}", response_model=Conversation)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    store: DatabaseConversationStore = Depends(_conversation_store),
) -> Conversation:
    """更新会话标题、摘要或历史轮次。"""

    conversation = store.update(conversation_id, payload)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return conversation


@router.post("/conversations/{conversation_id}/turns", response_model=Conversation)
def append_conversation_turn(
    conversation_id: str,
    turn: ConversationTurn,
    store: DatabaseConversationStore = Depends(_conversation_store),
) -> Conversation:
    """给指定会话追加一轮问答摘要。"""

    conversation = store.append_turn(conversation_id, turn)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return conversation


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    store: DatabaseConversationStore = Depends(_conversation_store),
) -> dict[str, bool]:
    """删除指定 AI 查数会话。"""

    deleted = store.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"deleted": True}
