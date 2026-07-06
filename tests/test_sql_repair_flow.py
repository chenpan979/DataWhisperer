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




class RetryingRepairLLM:
    def __init__(self) -> None:
        self.repair_index = 0
        self.correction_prompts: list[str] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        prompt_text = "\n".join(message["content"] for message in messages)
        if "Error taxonomy" in prompt_text:
            self.correction_prompts.append(prompt_text)
            return {
                "error_category": "SCHEMA_LINKING",
                "error_subtype": "unknown_column",
                "evidence": "The generated SQL still references a wrong column.",
                "repair_strategy": "Rewrite the select list with a valid literal so the retry flow can continue.",
                "must_keep": ["read-only SQL"],
                "avoid": ["invented columns"],
                "confidence": 0.8,
            }
        self.repair_index += 1
        return {
            "sql": f"SELECT {self.repair_index} AS value",
            "explanation": f"Repair attempt {self.repair_index}.",
        }

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

@pytest.mark.asyncio
async def test_orchestrator_retries_until_third_repair_attempt(
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
        if len(calls) < 4:
            raise ValueError(f"retry failure {len(calls)}")
        return f"{sql}\nLIMIT {max_rows}", ["value"], [{"value": 3}]

    monkeypatch.setattr(validation_execution, "execute_safe_query", fake_execute_safe_query)

    llm = RetryingRepairLLM()
    orchestrator = DataAnalysisOrchestrator(engine=object(), llm=llm)  # type: ignore[arg-type]
    trace: list[TraceStep] = []
    warnings: list[str] = []

    safe_sql, columns, rows, final_sql_result, repair_count = (
        await orchestrator._execute_with_optional_repair(
            question="count orders",
            schema_prompt="Table orders(order_id)",
            metric_context="order_count = COUNT(DISTINCT orders.order_id)",
            generated=GeneratedSQL(sql="SELECT broken FROM orders", explanation="broken"),
            max_rows=20,
            trace=trace,
            warnings=warnings,
            prompt_versions={},
        )
    )

    assert repair_count == 3
    assert calls == [
        "SELECT broken FROM orders",
        "SELECT 1 AS value",
        "SELECT 2 AS value",
        "SELECT 3 AS value",
    ]
    assert safe_sql == "SELECT 3 AS value\nLIMIT 20"
    assert columns == ["value"]
    assert rows == [{"value": 3}]
    assert final_sql_result.sql == "SELECT 3 AS value"
    assert any("历史修复失败" in prompt for prompt in llm.correction_prompts[1:])
    assert any("自动修复 3 次" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_orchestrator_stops_after_three_failed_repair_attempts(
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
        raise ValueError(f"always failing {len(calls)}")

    monkeypatch.setattr(validation_execution, "execute_safe_query", fake_execute_safe_query)

    llm = RetryingRepairLLM()
    orchestrator = DataAnalysisOrchestrator(engine=object(), llm=llm)  # type: ignore[arg-type]
    trace: list[TraceStep] = []
    warnings: list[str] = []

    with pytest.raises(ValueError, match="always failing 4"):
        await orchestrator._execute_with_optional_repair(
            question="count orders",
            schema_prompt="Table orders(order_id)",
            metric_context="order_count = COUNT(DISTINCT orders.order_id)",
            generated=GeneratedSQL(sql="SELECT broken FROM orders", explanation="broken"),
            max_rows=20,
            trace=trace,
            warnings=warnings,
            prompt_versions={},
        )

    assert calls == [
        "SELECT broken FROM orders",
        "SELECT 1 AS value",
        "SELECT 2 AS value",
        "SELECT 3 AS value",
    ]
    assert any("尝试 3 次仍失败" in warning for warning in warnings)
    assert any(step.name == "sql_repair" and step.status == "error" for step in trace)
