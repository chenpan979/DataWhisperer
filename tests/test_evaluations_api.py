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
    assert payload["version_snapshots"][-1]["version"] == "v3.8.8"
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
    assert text_suite["failed"] == 0
    assert payload["dataset_name"] == dataset_path.name

    delete_response = client.delete(f"/api/evaluations/datasets/{file_id}")
    assert delete_response.status_code == 200
