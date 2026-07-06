from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def test_run_evaluations_api_returns_quality_report() -> None:
    client = TestClient(create_app())
    response = client.post("/api/evaluations/run", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("eval-")
    assert payload["duration_ms"] >= 1
    assert len(payload["kpis"]) >= 4
    assert {suite["id"] for suite in payload["suites"]} == {
        "text_to_sql",
        "sql_safety",
        "metric_retrieval",
    }
    assert payload["cases"]
    assert payload["version_snapshots"][-1]["version"] == "v4.1.2"
    assert len(payload["trend_points"]) >= 4
    assert payload["issue_distribution"]
    assert len(payload["recent_runs"]) == 3
    assert len(payload["model_comparisons"]) >= 3


def test_evaluation_dataset_file_management_api() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/evaluations/datasets",
        files={
            "file": (
                "custom_text_to_sql_cases.jsonl",
                b'{"question":"query monthly sales","expected_sql_contains":["SUM"]}\n',
                "application/jsonl",
            )
        },
    )

    assert response.status_code == 200
    uploaded = response.json()
    file_id = uploaded["id"]

    list_response = client.get("/api/evaluations/datasets")
    assert list_response.status_code == 200
    assert any(file["id"] == file_id for file in list_response.json()["files"])

    preview_response = client.get(f"/api/evaluations/datasets/{file_id}/preview")
    assert preview_response.status_code == 200
    assert "expected_sql_contains" in preview_response.json()["preview"]

    delete_response = client.delete(f"/api/evaluations/datasets/{file_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}


def test_run_evaluations_with_uploaded_dataset() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/evaluations/datasets",
        files={
            "file": (
                "custom_text_to_sql_cases.jsonl",
                (
                    b'\xef\xbb\xbf{"id":"custom_region_orders","question":"query orders by region",'
                    b'"expected_sql_contains":["orders"],"tags":["custom"]}\n'
                ),
                "application/jsonl",
            )
        },
    )
    assert response.status_code == 200
    file_id = response.json()["id"]

    run_response = client.post("/api/evaluations/run", json={"dataset_file_id": file_id})
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["dataset_file_id"] == file_id
    assert payload["dataset_name"] == "custom_text_to_sql_cases.jsonl"
    text_suite = next(suite for suite in payload["suites"] if suite["id"] == "text_to_sql")
    assert text_suite["total"] == 1
    assert "上传测试集" in text_suite["name"]
    assert any(case["case_id"] == "custom_region_orders" for case in payload["cases"])

    delete_response = client.delete(f"/api/evaluations/datasets/{file_id}")
    assert delete_response.status_code == 200


def test_run_evaluations_with_sample_100_case_dataset() -> None:
    """验证项目内置的 100 条上传样例可以完整接入评测中心。

    这个测试覆盖真实产品链路：测试集管理上传文件，评测中心选择该文件，
    然后运行 Text-to-SQL 自定义回归评测。
    """

    client = TestClient(create_app())
    dataset_path = Path("evals/text_to_sql_upload_100_cases.jsonl")
    response = client.post(
        "/api/evaluations/datasets",
        files={
            "file": (
                dataset_path.name,
                dataset_path.read_bytes(),
                "application/jsonl",
            )
        },
    )
    assert response.status_code == 200
    file_id = response.json()["id"]

    run_response = client.post("/api/evaluations/run", json={"dataset_file_id": file_id})
    assert run_response.status_code == 200
    payload = run_response.json()
    text_suite = next(suite for suite in payload["suites"] if suite["id"] == "text_to_sql")
    assert text_suite["total"] == 100
    assert 0 <= text_suite["failed"] <= text_suite["total"]
    assert payload["dataset_name"] == dataset_path.name

    delete_response = client.delete(f"/api/evaluations/datasets/{file_id}")
    assert delete_response.status_code == 200


def test_run_evaluations_with_product_360_case_dataset() -> None:
    """????? 360 ? benchmark ???????????"""

    client = TestClient(create_app())
    dataset_path = Path("evals/text_to_sql_product_360_cases.jsonl")
    response = client.post(
        "/api/evaluations/datasets",
        files={
            "file": (
                dataset_path.name,
                dataset_path.read_bytes(),
                "application/jsonl",
            )
        },
    )
    assert response.status_code == 200
    file_id = response.json()["id"]

    run_response = client.post("/api/evaluations/run", json={"dataset_file_id": file_id})
    assert run_response.status_code == 200
    payload = run_response.json()
    text_suite = next(suite for suite in payload["suites"] if suite["id"] == "text_to_sql")
    assert text_suite["total"] == 360
    assert 0 <= text_suite["failed"] <= text_suite["total"]
    assert {item["name"] for item in text_suite["difficulty_breakdown"]} == {
        "simple",
        "medium",
        "complex",
    }
    assert text_suite["rag_breakdown"]
    assert text_suite["ablation_breakdown"]
    assert any(case["difficulty"] == "complex" for case in payload["cases"])
    assert any(case["requires_rag"] for case in payload["cases"])

    delete_response = client.delete(f"/api/evaluations/datasets/{file_id}")
    assert delete_response.status_code == 200


def test_run_evaluations_agent_mode_uses_agent_runner(monkeypatch) -> None:
    """runner_mode=agent 时，API 应调用真实 Agent Runner 入口。"""

    import app.api.evaluations as evaluations_api
    from app.evals.text_to_sql import TextToSqlEvalResult, build_text_to_sql_report

    called = {"value": False}

    async def fake_agent_runner(cases, **kwargs):
        called["value"] = True
        case = cases[0]
        result = TextToSqlEvalResult(
            case_id=case.id,
            passed=True,
            errors=(),
            generated_sql="SELECT 1 AS value LIMIT 100",
            chart_type=case.expected_chart_type,
            difficulty=case.difficulty,
            requires_rag=case.requires_rag,
            tags=case.tags,
            ablation_tags=case.ablation_tags,
        )
        return build_text_to_sql_report((result,))

    monkeypatch.setattr(evaluations_api, "run_agent_text_to_sql_evals", fake_agent_runner)
    monkeypatch.setattr(evaluations_api, "get_engine", lambda: object())
    monkeypatch.setattr(evaluations_api, "get_llm_client", lambda: object())

    client = TestClient(create_app())
    response = client.post(
        "/api/evaluations/run",
        json={"suites": ["text_to_sql"], "runner_mode": "agent"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert called["value"]
    assert payload["runner_mode"] == "agent"
    assert payload["suites"][0]["id"] == "text_to_sql"
    assert payload["cases"][0]["actual"].startswith("runner=agent")

def test_sync_builtin_evaluation_datasets_replaces_stale_files(tmp_path, monkeypatch) -> None:
    """同步内置 benchmark 时，应替换旧同名文件，同时保留用户自定义测试集。"""

    import app.api.evaluations as evaluations_api
    from app.tools.file_store import FileStoreConfig, ManagedFileStore

    store = ManagedFileStore(
        FileStoreConfig(
            category="evaluation_dataset",
            directory=tmp_path,
            allowed_extensions=frozenset({".json", ".jsonl"}),
        )
    )
    stale = store.save(
        original_name="text_to_sql_upload_100_cases.jsonl",
        content=b'{"id":"old_case","question":"old"}\n',
    )
    custom = store.save(
        original_name="custom_text_to_sql_cases.jsonl",
        content=b'{"id":"custom_case","question":"custom"}\n',
    )
    monkeypatch.setattr(evaluations_api, "get_evaluation_dataset_store", lambda: store)

    client = TestClient(create_app())
    response = client.post("/api/evaluations/datasets/sync-builtins")

    assert response.status_code == 200
    files = response.json()["files"]
    names = {file["name"] for file in files}
    assert {
        "text_to_sql_cases.json",
        "text_to_sql_18_table_cases.jsonl",
        "text_to_sql_upload_100_cases.jsonl",
        "text_to_sql_product_240_cases.jsonl",
        "text_to_sql_product_360_cases.jsonl",
    } <= names
    assert custom.id in {file["id"] for file in files}
    assert stale.id not in {file["id"] for file in files}

    synced_100 = next(file for file in files if file["name"] == "text_to_sql_upload_100_cases.jsonl")
    preview = client.get(f"/api/evaluations/datasets/{synced_100['id']}/preview")
    assert preview.status_code == 200
    assert "product_region_gmv" in preview.json()["preview"]