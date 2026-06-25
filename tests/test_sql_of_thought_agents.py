import pytest

from app.agents import sql_of_thought
from app.models.query import QueryRequest


class CapturingLLM:
    """Capture prompts so the test does not call a real model."""

    def __init__(self) -> None:
        self.json_messages: list[list[dict[str, str]]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, str]:
        self.json_messages.append(messages)
        return {
            "sql": "SELECT product_name, stock_status FROM products",
            "explanation": "Summarize product inventory status.",
        }

    async def complete_text(self, messages: list[dict[str, str]]) -> str:
        return "Inventory status has been summarized from the query result."


@pytest.mark.asyncio
async def test_sql_of_thought_plan_is_injected_into_sql_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The V4 pipeline should plan first, then pass that plan to SQL generation."""

    def fake_schema_overview(engine: object) -> dict:
        return {
            "table_count": 2,
            "tables": [
                {
                    "name": "products",
                    "comment": None,
                    "columns": [
                        {
                            "name": "product_id",
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        {
                            "name": "product_name",
                            "type": "VARCHAR(128)",
                            "nullable": False,
                            "primary_key": False,
                        },
                        {
                            "name": "stock_status",
                            "type": "VARCHAR(32)",
                            "nullable": True,
                            "primary_key": False,
                        },
                    ],
                    "foreign_keys": [],
                },
                {
                    "name": "orders",
                    "comment": None,
                    "columns": [
                        {
                            "name": "order_id",
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                    ],
                    "foreign_keys": [],
                },
            ],
        }

    def fake_execute_safe_query(
        engine: object,
        sql: str,
        max_rows: int,
        *,
        auto_limit_enabled: bool = True,
    ) -> tuple[str, list[str], list[dict]]:
        return (
            f"{sql}\nLIMIT {max_rows}",
            ["product_name", "stock_status"],
            [{"product_name": "Aurora Laptop", "stock_status": "normal"}],
        )

    monkeypatch.setattr(sql_of_thought, "build_schema_overview", fake_schema_overview)
    monkeypatch.setattr(sql_of_thought, "execute_safe_query", fake_execute_safe_query)

    llm = CapturingLLM()
    orchestrator = sql_of_thought.DataAnalysisOrchestrator(engine=object(), llm=llm)  # type: ignore[arg-type]
    response = await orchestrator.run(QueryRequest(question="Show products inventory status", max_rows=20))

    prompt_text = "\n".join(message["content"] for message in llm.json_messages[0])
    trace_names = [step.name for step in response.trace_steps]

    assert "SQL-of-Thought" in prompt_text
    assert "products" in prompt_text
    assert response.generated_sql == "SELECT product_name, stock_status FROM products\nLIMIT 20"
    assert response.rows == [{"product_name": "Aurora Laptop", "stock_status": "normal"}]
    assert "query_planning" in trace_names
    assert "generate_sql" in trace_names
    assert "execute_sql" in trace_names
    assert "chart" in trace_names
    assert "insight" in trace_names
