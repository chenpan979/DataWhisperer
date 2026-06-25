from app.agents.context import DataAnalysisAgentState
from app.agents.retrieval_context import combine_retrieval_contexts
from app.rag.document_retriever import empty_rag_document_result, get_rag_document_retriever
from app.rag.metric_retriever import get_metric_retriever


class KnowledgeRetrievalAgent:
    """检索内置指标口径和当前工作空间知识库资料。"""

    async def run(self, state: DataAnalysisAgentState) -> None:
        state.metric_retrieval = get_metric_retriever().retrieve(state.request.question)
        metric_detail = (
            ", ".join(state.metric_retrieval.names)
            if state.metric_retrieval.names
            else "未命中业务指标口径"
        )
        state.add_trace("metric_retrieval", "ok", f"KnowledgeAgent 指标口径：{metric_detail}")

        if state.knowledge_scope is None:
            state.knowledge_retrieval = empty_rag_document_result()
        else:
            retriever = state.rag_retriever or get_rag_document_retriever()
            state.knowledge_retrieval = retriever.retrieve(
                state.request.question,
                scope=state.knowledge_scope,
            )
            knowledge_detail = (
                ", ".join(state.knowledge_retrieval.sources)
                if state.knowledge_retrieval.sources
                else "未命中工作空间知识库"
            )
            state.add_trace(
                "knowledge_retrieval",
                "ok",
                f"KnowledgeAgent 工作空间知识库：{knowledge_detail}（{state.knowledge_retrieval.retrieval_mode}）",
            )

        state.retrieval_context = combine_retrieval_contexts(
            metric_context=state.metric_retrieval.prompt_context,
            knowledge_context=state.knowledge_retrieval.prompt_context,
        )