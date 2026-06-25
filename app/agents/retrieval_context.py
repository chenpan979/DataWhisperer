from app.rag.document_retriever import NO_KNOWLEDGE_CONTEXT


def combine_retrieval_contexts(*, metric_context: str, knowledge_context: str) -> str:
    """合并内置指标口径和工作空间知识库上下文。"""

    sections = []
    if metric_context:
        sections.append("## 内置业务指标口径\n" + metric_context)
    if knowledge_context and knowledge_context != NO_KNOWLEDGE_CONTEXT:
        sections.append("## 工作空间知识库资料\n" + knowledge_context)
    return "\n\n".join(sections)


def append_plan_context(context: str, plan_context: str) -> str:
    """把查询计划追加到检索上下文后面，统一交给 SQL Agent 使用。"""

    if not context:
        return plan_context
    return context + "\n\n" + plan_context