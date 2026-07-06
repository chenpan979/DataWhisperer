from app.evals.text_to_sql import load_eval_cases, run_text_to_sql_evals


def test_load_text_to_sql_eval_cases() -> None:
    cases = load_eval_cases()

    assert len(cases) >= 60
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.question for case in cases)
    assert all(case.expected_sql_contains for case in cases)
    assert all(case.expected_chart_type for case in cases)
    assert {case.difficulty for case in cases} == {"simple", "medium", "complex"}
    assert any(case.requires_rag for case in cases)
    assert all(case.ablation_tags for case in cases)


def test_text_to_sql_eval_report_passes_current_baseline() -> None:
    report = run_text_to_sql_evals()

    assert report.total >= 60
    assert report.failed == 0
    assert report.pass_rate == 1.0
    assert all(result.passed for result in report.results)
    assert [item.name for item in report.difficulty_breakdown] == [
        "simple",
        "medium",
        "complex",
    ]
    assert sum(item.total for item in report.difficulty_breakdown) == report.total


def test_text_to_sql_eval_report_is_serializable() -> None:
    report = run_text_to_sql_evals()
    payload = report.to_dict()

    assert payload["total"] == report.total
    assert payload["passed"] == report.passed
    assert payload["failed"] == 0
    assert payload["pass_rate"] == 1.0
    assert len(payload["results"]) == report.total
    assert payload["difficulty_breakdown"]
    assert payload["rag_breakdown"]
    assert payload["ablation_breakdown"]


def test_agent_text_to_sql_eval_uses_orchestrator_response() -> None:
    """真实 Agent 评测应以 Orchestrator 响应为准，而不是本地 fallback SQL。"""

    import asyncio

    from app.evals.agent_text_to_sql import evaluate_agent_case
    from app.evals.text_to_sql import TextToSqlEvalCase
    from app.models.query import QueryResponse

    class FakeOrchestrator:
        async def run(self, request):
            return QueryResponse(
                question=request.question,
                generated_sql=(
                    "SELECT r.region_name, COUNT(DISTINCT o.order_id) AS order_count "
                    "FROM orders o JOIN regions r ON o.region_id = r.region_id "
                    "GROUP BY r.region_name LIMIT 100"
                ),
                sql_explanation="按地区统计订单数量。",
                columns=["region_name", "order_count"],
                rows=[{"region_name": "华东", "order_count": 12}],
                chart={"type": "bar"},
                insight="华东订单数量最高。",
            )

    case = TextToSqlEvalCase(
        id="agent_region_orders",
        question="查询各地区订单数量",
        tags=("agent",),
        expected_sql_contains=("COUNT(DISTINCT o.order_id)", "JOIN regions"),
        forbidden_sql_contains=("DELETE", "DROP"),
        expected_columns=("region_name", "order_count"),
        expected_chart_type="bar",
        difficulty="medium",
        ablation_tags=("multi_agent",),
    )

    result = asyncio.run(evaluate_agent_case(case, orchestrator=FakeOrchestrator()))

    assert result.passed
    assert result.generated_sql.startswith("SELECT r.region_name")
    assert result.chart_type == "bar"

def test_product_eval_datasets_cover_current_business_schema() -> None:
    """产品级评测集必须覆盖当前 18 张业务表，避免大样本退化成旧版 7 表场景。"""

    expected_tables = {
        "regions",
        "customer_segments",
        "customers",
        "categories",
        "suppliers",
        "warehouses",
        "products",
        "sales_channels",
        "campaigns",
        "coupons",
        "orders",
        "order_items",
        "inventory_snapshots",
        "payments",
        "shipments",
        "returns",
        "product_reviews",
        "support_tickets",
    }

    agent_cases = load_eval_cases("evals/text_to_sql_18_table_cases.jsonl")
    product_cases = load_eval_cases("evals/text_to_sql_product_360_cases.jsonl")

    agent_tags = {tag for case in agent_cases for tag in case.tags}
    product_tags = {tag for case in product_cases for tag in case.tags}

    assert len(agent_cases) == 18
    assert len(product_cases) == 360
    assert expected_tables <= agent_tags
    assert expected_tables <= product_tags
    assert {case.difficulty for case in product_cases} == {"simple", "medium", "complex"}
    assert any(case.requires_rag for case in product_cases)


def test_eval_dataset_files_are_clean_utf8() -> None:
    """评测集要保持可读中文，防止 Windows 编码导致 CSDN/前端预览出现乱码。"""

    from pathlib import Path

    dataset_paths = [
        Path("evals/text_to_sql_cases.json"),
        Path("evals/text_to_sql_18_table_cases.jsonl"),
        Path("evals/text_to_sql_upload_100_cases.jsonl"),
        Path("evals/text_to_sql_product_240_cases.jsonl"),
        Path("evals/text_to_sql_product_360_cases.jsonl"),
    ]
    mojibake_markers = ("鏌", "鍚", "绋", "�")

    for dataset_path in dataset_paths:
        text = dataset_path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in mojibake_markers), dataset_path