import pytest

from app.agents.sql_correction_plan import (
    ERROR_TAXONOMY,
    classify_sql_error_locally,
    generate_sql_correction_plan,
    taxonomy_subtype_count,
)


class PlanLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        self.messages = messages
        return {
            "error_category": "SCHEMA_LINKING",
            "error_subtype": "unknown_column",
            "evidence": "missing_column is not in the provided schema.",
            "repair_strategy": "Use orders.order_id and COUNT(DISTINCT orders.order_id).",
            "must_keep": ["original question", "read-only SQL"],
            "avoid": ["invented columns"],
            "confidence": 0.88,
        }


def test_sql_error_taxonomy_has_9_categories_and_31_subtypes() -> None:
    assert len(ERROR_TAXONOMY) == 9
    assert taxonomy_subtype_count() == 31


def test_local_sql_error_classifier_handles_unknown_column() -> None:
    plan = classify_sql_error_locally(
        error_message="Unknown column 'missing_column' in 'field list'",
        failed_sql="SELECT missing_column FROM orders",
    )

    assert plan.error_category == "SCHEMA_LINKING"
    assert plan.error_subtype == "unknown_column"
    assert "missing column" in plan.repair_strategy.lower()


@pytest.mark.asyncio
async def test_generate_sql_correction_plan_uses_versioned_prompt() -> None:
    llm = PlanLLM()

    plan = await generate_sql_correction_plan(
        question="count orders",
        schema_prompt="Table orders(order_id)",
        failed_sql="SELECT missing_column FROM orders",
        error_message="Unknown column 'missing_column'",
        metric_context="order_count = COUNT(DISTINCT orders.order_id)",
        llm=llm,
    )

    assert plan.error_category == "SCHEMA_LINKING"
    assert plan.error_subtype == "unknown_column"
    assert plan.prompt_id == "sql_correction_plan"
    assert plan.prompt_version == "v1"
    assert "Error taxonomy" in llm.messages[1]["content"]
    assert "Table orders(order_id)" in llm.messages[1]["content"]
