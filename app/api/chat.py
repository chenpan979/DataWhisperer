from fastapi import APIRouter, HTTPException

from app.agent.orchestrator import DataAnalysisOrchestrator
from app.core.database import get_engine
from app.core.llm import get_llm_client
from app.models.conversations import (
    Conversation,
    ConversationCreate,
    ConversationList,
    ConversationTurn,
    ConversationUpdate,
)
from app.models.query import QueryRequest, QueryResponse
from app.tools.conversation_store import get_conversation_store

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=QueryResponse)
async def query_data(request: QueryRequest) -> QueryResponse:
    """执行一次自然语言数据分析请求。

    API 层保持薄层设计：只负责接收请求、组装依赖、调用 Orchestrator、
    把异常转换成 HTTP 响应。具体业务流程放在 agent/tools 层。
    """

    orchestrator = DataAnalysisOrchestrator(engine=get_engine(), llm=get_llm_client())
    try:
        return await orchestrator.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external services
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


@router.get("/conversations", response_model=ConversationList)
def list_conversations() -> ConversationList:
    """读取 AI 查数会话列表。

    前端启动时会调用这个接口，把服务端保存的历史会话恢复出来。
    如果没有任何历史记录，前端会再创建一个“新对话”作为默认入口。
    """

    conversations = get_conversation_store().list_conversations()
    active_id = conversations[0].id if conversations else None
    return ConversationList(conversations=conversations, activeConversationId=active_id)


@router.post("/conversations", response_model=Conversation)
def create_conversation(payload: ConversationCreate | None = None) -> Conversation:
    """创建一个新的 AI 查数会话。"""

    return get_conversation_store().create(payload)


@router.patch("/conversations/{conversation_id}", response_model=Conversation)
def update_conversation(conversation_id: str, payload: ConversationUpdate) -> Conversation:
    """更新会话标题、摘要或历史轮次。"""

    conversation = get_conversation_store().update(conversation_id, payload)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return conversation


@router.post("/conversations/{conversation_id}/turns", response_model=Conversation)
def append_conversation_turn(conversation_id: str, turn: ConversationTurn) -> Conversation:
    """给指定会话追加一轮问答摘要。"""

    conversation = get_conversation_store().append_turn(conversation_id, turn)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return conversation


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    """删除指定 AI 查数会话。"""

    deleted = get_conversation_store().delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"deleted": True}
