import pytest

from app.agents import validation_execution
from app.agents.orchestrator import DataAnalysisOrchestrator
from app.models.query import TraceStep
from app.agents.sql_generation import GeneratedSQL


class RepairLLM:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        self.messages.append(messages)
        if len(self.messages) == 1:
            assert "Error taxonomy" in messages[1]["content"]
            return {
                "error_category": "SCHEMA_LINKING",
                "error_subtype": "unknown_column",
                "evidence": "missing_column is not present in schema.",
                "repair_strategy": "Replace the missing column with a valid aggregate.",
                "must_keep": ["order count intent"],
                "avoid": ["invented columns"],
                "confidence": 0.9,
            }
        assert "Structured correction plan" in messages[1]["content"]
        assert "SCHEMA_LINKING" in messages[1]["content"]
        return {"sql": "SELECT 1 AS value", "explanation": "Repaired missing column."}


@pytest.mark.asyncio
async def test_orchestrator_repairs_failed_sql_with_guided_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_execute_safe_query(
        engine: object,
        sql: str,
        max_rows: int,
        *,
        auto_limit_enabled: bool = True,
    ) -> tuple[str, list[str], list[dict]]:
        calls.append(sql)
        if len(calls) == 1:
            raise ValueError("Unknown column 'missing_column'")
        return f"{sql}\nLIMIT {max_rows}", ["value"], [{"value": 1}]

    monkeypatch.setattr(validation_execution, "execute_safe_query", fake_execute_safe_query)

    llm = RepairLLM()
    orchestrator = DataAnalysisOrchestrator(engine=object(), llm=llm)  # type: ignore[arg-type]
    trace: list[TraceStep] = []
    warnings: list[str] = []
    prompt_versions = {"sql_generation": "v1"}

    safe_sql, columns, rows, final_sql_result, repair_count = (
        await orchestrator._execute_with_optional_repair(
            question="count orders",
            schema_prompt="Table orders(order_id)",
            metric_context="order_count = COUNT(DISTINCT orders.order_id)",
            generated=GeneratedSQL(
                sql="SELECT missing_column FROM orders",
                explanation="count orders",
                prompt_id="sql_generation",
                prompt_version="v1",
            ),
            max_rows=50,
            trace=trace,
            warnings=warnings,
            prompt_versions=prompt_versions,
        )
    )

    assert repair_count == 1
    assert calls == ["SELECT missing_column FROM orders", "SELECT 1 AS value"]
    assert safe_sql == "SELECT 1 AS value\nLIMIT 50"
    assert columns == ["value"]
    assert rows == [{"value": 1}]
    assert final_sql_result.prompt_id == "sql_repair"
    assert final_sql_result.prompt_version == "v1"
    assert prompt_versions["sql_correction_plan"] == "v1"
    assert prompt_versions["sql_repair"] == "v1"
    assert any(step.name == "sql_correction_plan" and step.status == "ok" for step in trace)
    assert any(step.name == "sql_repair" and step.status == "ok" for step in trace)
    assert warnings
