from fastapi import APIRouter, HTTPException

from app.agent.orchestrator import DataAnalysisOrchestrator
from app.core.database import get_engine
from app.core.llm import get_llm_client
from app.models.query import QueryRequest, QueryResponse

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
