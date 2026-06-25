from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.api.model_settings import _ensure_default_model_settings
from app.api.security_policies import build_query_security_policy, ensure_default_security_policy
from app.agents.orchestrator import DataAnalysisOrchestrator
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.llm import LLMClient, get_llm_client
from app.core.product_database import get_product_session
from app.models.conversations import (
    Conversation,
    ConversationCreate,
    ConversationList,
    ConversationTurn,
    ConversationUpdate,
)
from app.models.query import QueryRequest, QueryResponse
from app.rag.document_retriever import RagKnowledgeScope
from app.repositories.product import KnowledgeRepository
from app.tools.agent_model_router import AgentModelRouter, build_agent_model_router
from app.tools.data_source_engine import get_default_data_source_engine
from app.tools.database_conversation_store import DatabaseConversationStore
from app.tools.security_policy import QuerySecurityPolicy, default_query_security_policy

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
        auth_context = _resolve_auth_context(authorization=authorization, session=session)
        engine = _build_query_engine(auth_context=auth_context, session=session)
        security_policy = _build_query_security_policy(auth_context=auth_context, session=session)
        knowledge_scope = _build_knowledge_scope(auth_context=auth_context, session=session)
        llm = get_llm_client()
        agent_model_router = _build_agent_model_router(
            auth_context=auth_context,
            session=session,
            fallback_llm=llm,
        )
        orchestrator = DataAnalysisOrchestrator(
            engine=engine,
            llm=llm,
            security_policy=security_policy,
            knowledge_scope=knowledge_scope,
            agent_model_router=agent_model_router,
        )
        return await orchestrator.run(request)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external services
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


def _resolve_auth_context(*, authorization: str | None, session: Session) -> AuthContext | None:
    """Resolve optional auth context for endpoints that still support local demo access."""

    if not authorization:
        return None
    return require_auth_context(authorization=authorization, session=session)


def _build_query_engine(*, auth_context: AuthContext | None, session: Session) -> Engine:
    """根据登录态选择 AI 查数使用的数据源。

    登录用户会优先使用系统设置里的默认数据源；
    未登录或本地演示场景继续使用 `.env` 中的 `DATABASE_URL`。
    """

    if auth_context is None:
        return get_engine()
    return get_default_data_source_engine(
        session=session,
        auth_context=auth_context,
        fallback_engine_factory=get_engine,
    )


def _build_query_security_policy(
    *,
    auth_context: AuthContext | None,
    session: Session,
) -> QuerySecurityPolicy:
    """Read the current workspace security policy for query execution."""

    if auth_context is None:
        settings = get_settings()
        return default_query_security_policy(
            system_max_rows=settings.max_query_rows,
            query_timeout_seconds=settings.query_timeout_seconds,
        )
    policy = ensure_default_security_policy(session=session, auth_context=auth_context)
    session.commit()
    return build_query_security_policy(policy)



def _build_knowledge_scope(
    *,
    auth_context: AuthContext | None,
    session: Session,
) -> RagKnowledgeScope | None:
    """为登录用户构建工作空间知识库检索范围。"""

    if auth_context is None:
        return None
    knowledge_base = KnowledgeRepository(session).ensure_default_base(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        created_by=auth_context.user.id,
    )
    session.commit()
    return RagKnowledgeScope(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        knowledge_base_id=knowledge_base.id,
    )


def _build_agent_model_router(
    *,
    auth_context: AuthContext | None,
    session: Session,
    fallback_llm: LLMClient,
) -> AgentModelRouter:
    """Resolve workspace model bindings for the SQL-of-Thought agent pipeline."""

    if auth_context is None:
        return AgentModelRouter(default_llm=fallback_llm)
    _ensure_default_model_settings(session=session, auth_context=auth_context)
    session.commit()
    return build_agent_model_router(
        session=session,
        auth_context=auth_context,
        fallback_llm=fallback_llm,
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
