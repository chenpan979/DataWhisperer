import pytest

fastapi = pytest.importorskip("fastapi")

from app.main import create_app  # noqa: E402


def test_app_routes_exist() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/health" in paths
    assert "/api/examples" in paths
    assert "/api/schema/overview" in paths
    assert "/api/chat/query" in paths
    assert "/api/files/schema" in paths
    assert "/api/files/schema/{file_id}/preview" in paths
    assert "/api/files/rag" in paths
    assert "/api/files/rag/{file_id}/preview" in paths
    assert "/api/evaluations/run" in paths
    assert "/api/evaluations/datasets" in paths
    assert "/api/evaluations/datasets/{file_id}/preview" in paths
