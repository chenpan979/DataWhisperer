from __future__ import annotations

from typing import Any

from app.agents.sql_correction_plan import SQLCorrectionPlan
from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, get_prompt_registry
from app.agents.sql_generation import GeneratedSQL


async def repair_sql(
    question: str,
    schema_prompt: str,
    failed_sql: str,
    error_message: str,
    llm: Any,
    metric_context: str = "No matched business metric context.",
    correction_plan: SQLCorrectionPlan | None = None,
    prompt_registry: PromptRegistry | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> GeneratedSQL | None:
    """Ask SQLRepairAgent to rewrite a failed SQL query under a correction plan.

    This is intentionally placed under ``app.agents`` because it is an LLM-driven
    decision step. Deterministic work such as SQL safety validation and execution
    remains in ``app.tools.sql_tool`` / ``app.tools.query_tool``.
    """

    correction_plan_text = (
        correction_plan.to_prompt_text()
        if correction_plan
        else "No structured correction plan was generated. Apply the smallest safe fix based on the failure reason."
    )
    registry = prompt_registry or get_prompt_registry()
    rendered_prompt = registry.render_messages(
        "sql_repair",
        version=prompt_version,
        variables={
            "schema_prompt": schema_prompt,
            "metric_context": metric_context,
            "question": question,
            "failed_sql": failed_sql,
            "error_message": error_message,
            "correction_plan": correction_plan_text,
        },
    )
    try:
        payload = await llm.complete_json(rendered_prompt.messages)
    except Exception:
        payload = None
    if not payload or not payload.get("sql"):
        return None
    return GeneratedSQL(
        sql=str(payload["sql"]),
        explanation=str(payload.get("explanation", "")),
        prompt_id=rendered_prompt.prompt_id,
        prompt_version=rendered_prompt.version,
    )
