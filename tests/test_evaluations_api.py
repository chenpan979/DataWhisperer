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
    assert payload["version_snapshots"][-1]["version"] == "v3.7.0"
