import pytest

from app.core.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, PromptTemplateError


def test_prompt_registry_renders_sql_generation_messages() -> None:
    registry = PromptRegistry()

    rendered = registry.render_messages(
        "sql_generation",
        variables={
            "schema_prompt": "Table orders(order_id, order_date)",
            "metric_context": "订单数 = COUNT(DISTINCT orders.order_id)",
            "question": "查询订单数量",
        },
    )

    assert rendered.prompt_id == "sql_generation"
    assert rendered.version == DEFAULT_PROMPT_VERSION
    assert rendered.variables == ("metric_context", "question", "schema_prompt")
    assert [message["role"] for message in rendered.messages] == ["system", "user"]
    assert "Table orders(order_id, order_date)" in rendered.messages[1]["content"]
    assert "订单数 = COUNT(DISTINCT orders.order_id)" in rendered.messages[1]["content"]
    assert "查询订单数量" in rendered.messages[1]["content"]


def test_prompt_registry_rejects_missing_variables() -> None:
    registry = PromptRegistry()

    with pytest.raises(PromptTemplateError, match="missing variables"):
        registry.render_messages(
            "sql_generation",
            variables={"question": "查询订单数量"},
        )


def test_v2_prompt_templates_exist() -> None:
    registry = PromptRegistry()

    for prompt_id in [
        "sql_generation",
        "sql_repair",
        "insight_summary",
        "chart_recommendation",
    ]:
        for role in ["system", "user"]:
            template = registry.load_template(prompt_id, DEFAULT_PROMPT_VERSION, role)
            assert template.content
            assert template.path.exists()
