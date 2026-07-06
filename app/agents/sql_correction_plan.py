from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, get_prompt_registry


ERROR_TAXONOMY: dict[str, tuple[str, ...]] = {
    "SQL_SYNTAX": (
        "malformed_select",
        "invalid_function",
        "invalid_grouping_syntax",
        "dialect_mismatch",
    ),
    "SCHEMA_LINKING": (
        "unknown_table",
        "unknown_column",
        "ambiguous_column",
        "wrong_table_for_column",
    ),
    "JOIN_PATH": (
        "missing_join",
        "wrong_join_key",
        "wrong_join_type",
        "duplicated_join",
    ),
    "FILTER_CONDITION": (
        "missing_filter",
        "wrong_filter_column",
        "wrong_operator",
        "wrong_boolean_logic",
    ),
    "AGGREGATION": (
        "missing_aggregation",
        "wrong_aggregation_function",
        "missing_group_by",
        "wrong_having_clause",
    ),
    "VALUE_GROUNDING": (
        "wrong_date_range",
        "wrong_literal_value",
        "wrong_unit_or_scale",
        "unsupported_enum_value",
    ),
    "NESTED_QUERY": (
        "missing_subquery",
        "wrong_subquery_scope",
        "wrong_cte_dependency",
    ),
    "SET_OPERATION": (
        "wrong_set_operator",
        "incompatible_set_columns",
    ),
    "RESULT_SHAPING": (
        "wrong_order_by",
        "wrong_limit_or_distinct",
    ),
}


@dataclass(slots=True)
class SQLCorrectionPlan:
    """Structured repair plan inspired by SQL-of-Thought guided correction."""

    error_category: str
    error_subtype: str
    evidence: str
    repair_strategy: str
    must_keep: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    confidence: float = 0.5
    prompt_id: str | None = None
    prompt_version: str | None = None

    def to_prompt_text(self) -> str:
        return json.dumps(
            {
                "error_category": self.error_category,
                "error_subtype": self.error_subtype,
                "evidence": self.evidence,
                "repair_strategy": self.repair_strategy,
                "must_keep": self.must_keep,
                "avoid": self.avoid,
                "confidence": self.confidence,
            },
            ensure_ascii=False,
            indent=2,
        )

    def to_trace_detail(self) -> str:
        return (
            f"{self.error_category}/{self.error_subtype}: {self.repair_strategy} "
            f"(confidence={self.confidence:.2f})"
        )


def taxonomy_subtype_count() -> int:
    return sum(len(subtypes) for subtypes in ERROR_TAXONOMY.values())


def taxonomy_prompt_text() -> str:
    lines = []
    for category, subtypes in ERROR_TAXONOMY.items():
        lines.append(f"- {category}: {', '.join(subtypes)}")
    return "\n".join(lines)


async def generate_sql_correction_plan(
    *,
    question: str,
    schema_prompt: str,
    failed_sql: str,
    error_message: str,
    llm: Any,
    metric_context: str = "No matched business metric context.",
    prompt_registry: PromptRegistry | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> SQLCorrectionPlan:
    """Diagnose the SQL failure before asking the repair model to rewrite SQL."""

    registry = prompt_registry or get_prompt_registry()
    rendered_prompt = registry.render_messages(
        "sql_correction_plan",
        version=prompt_version,
        variables={
            "taxonomy": taxonomy_prompt_text(),
            "schema_prompt": schema_prompt,
            "metric_context": metric_context,
            "question": question,
            "failed_sql": failed_sql,
            "error_message": error_message,
        },
    )
    try:
        payload = await llm.complete_json(rendered_prompt.messages)
    except Exception:
        payload = None

    plan = plan_from_payload(payload, error_message=error_message)
    if plan is None:
        plan = classify_sql_error_locally(error_message=error_message, failed_sql=failed_sql)
    else:
        plan.prompt_id = rendered_prompt.prompt_id
        plan.prompt_version = rendered_prompt.version
    return plan


def plan_from_payload(payload: Any, *, error_message: str) -> SQLCorrectionPlan | None:
    if not isinstance(payload, dict):
        return None

    category = str(payload.get("error_category") or "").strip().upper()
    subtype = str(payload.get("error_subtype") or "").strip().lower()
    if category not in ERROR_TAXONOMY or subtype not in ERROR_TAXONOMY[category]:
        return None

    evidence = str(payload.get("evidence") or error_message or "No explicit evidence.").strip()
    strategy = str(payload.get("repair_strategy") or "Apply a minimal SQL correction.").strip()
    return SQLCorrectionPlan(
        error_category=category,
        error_subtype=subtype,
        evidence=evidence,
        repair_strategy=strategy,
        must_keep=_coerce_string_list(payload.get("must_keep")),
        avoid=_coerce_string_list(payload.get("avoid")),
        confidence=_coerce_confidence(payload.get("confidence")),
    )


def classify_sql_error_locally(*, error_message: str, failed_sql: str) -> SQLCorrectionPlan:
    """Deterministic fallback when the LLM diagnosis is unavailable or malformed."""

    text = f"{error_message}\n{failed_sql}".lower()
    if "unknown column" in text or "no such column" in text:
        return _local_plan(
            "SCHEMA_LINKING",
            "unknown_column",
            error_message,
            "Replace the missing column with a column that exists in the provided schema.",
        )
    if "unknown table" in text or "doesn't exist" in text or "no such table" in text:
        return _local_plan(
            "SCHEMA_LINKING",
            "unknown_table",
            error_message,
            "Replace or remove the table that is not present in the provided schema.",
        )
    if "ambiguous" in text:
        return _local_plan(
            "SCHEMA_LINKING",
            "ambiguous_column",
            error_message,
            "Qualify ambiguous columns with the correct table alias.",
        )
    if "group by" in text or "not functionally dependent" in text:
        return _local_plan(
            "AGGREGATION",
            "missing_group_by",
            error_message,
            "Align selected non-aggregated columns with GROUP BY or aggregate them.",
        )
    if "join" in text or "foreign key" in text:
        return _local_plan(
            "JOIN_PATH",
            "wrong_join_key",
            error_message,
            "Rebuild the join path using the primary-key and foreign-key relationships in schema.",
        )
    if "syntax" in text or "parse" in text:
        return _local_plan(
            "SQL_SYNTAX",
            "malformed_select",
            error_message,
            "Fix SQL syntax while preserving the original question intent.",
        )
    return _local_plan(
        "SQL_SYNTAX",
        "malformed_select",
        error_message,
        "Make the smallest safe change that lets the query run and still answer the question.",
    )


def _local_plan(category: str, subtype: str, evidence: str, strategy: str) -> SQLCorrectionPlan:
    return SQLCorrectionPlan(
        error_category=category,
        error_subtype=subtype,
        evidence=evidence or "Local deterministic diagnosis.",
        repair_strategy=strategy,
        must_keep=["original business question", "read-only SELECT/WITH boundary"],
        avoid=["inventing tables or columns", "changing the metric definition without evidence"],
        confidence=0.65,
    )


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(number, 1.0))
