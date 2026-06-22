from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import AnalysisRunRepository  # noqa: E402


@pytest.fixture
def conversation_client() -> Iterator[tuple[TestClient, sessionmaker[Session], dict[str, str]]]:
    """创建带产品库和登录 token 的测试客户端。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def override_product_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    with TestClient(app) as client:
        register_response = client.post(
            "/api/auth/register",
            json={
                "tenant_name": "测试租户",
                "tenant_key": "chat-test",
                "display_name": "tester",
                "email": "tester@example.com",
                "password": "12345678",
            },
        )
        assert register_response.status_code == 200
        token = register_response.json()["access_token"]
        yield client, session_factory, {"Authorization": f"Bearer {token}"}
    app.dependency_overrides.clear()


def test_chat_conversation_lifecycle(
    conversation_client: tuple[TestClient, sessionmaker[Session], dict[str, str]],
) -> None:
    """验证 AI 查数会话和分析结果可以落到产品管理库。"""

    client, session_factory, headers = conversation_client

    create_response = client.post(
        "/api/chat/conversations",
        headers=headers,
        json={"title": "新对话", "subtitle": "等待数据问题", "preview": "等待数据问题"},
    )
    assert create_response.status_code == 200
    conversation = create_response.json()
    conversation_id = conversation["id"]

    list_response = client.get("/api/chat/conversations", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == conversation_id for item in list_response.json()["conversations"])

    update_response = client.patch(
        f"/api/chat/conversations/{conversation_id}",
        headers=headers,
        json={"title": "月度销售分析", "customTitle": True},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "月度销售分析"
    assert update_response.json()["customTitle"] is True

    turn_response = client.post(
        f"/api/chat/conversations/{conversation_id}/turns",
        headers=headers,
        json={
            "traceId": "trace-test-001",
            "question": "查询最近 6 个月每月销售额趋势",
            "insight": "最近 6 个月销售额整体上升。",
            "rowCount": 6,
            "columnCount": 2,
            "chartType": "折线图",
            "createdAt": "10:24",
            "generatedSql": "SELECT month, sales_amount FROM monthly_sales LIMIT 100",
            "sqlExplanation": "按月份查询销售额趋势。",
            "columns": ["month", "sales_amount"],
            "rows": [{"month": "2026-01", "sales_amount": 136700}],
            "chart": {
                "type": "line",
                "title": {"text": "按月份统计销售额"},
                "xAxis": {"data": ["2026-01"]},
                "series": [{"type": "line", "data": [136700]}],
            },
            "warnings": [],
            "traceSteps": [{"name": "execute_sql", "status": "ok", "detail": "1 row"}],
            "followups": ["按地区拆分一下"],
            "assistantHtml": '<article class="chat-message assistant">snapshot</article>',
        },
    )
    assert turn_response.status_code == 200
    saved_turn = turn_response.json()["turns"][0]
    assert saved_turn["generatedSql"].startswith("SELECT")
    assert saved_turn["rows"][0]["sales_amount"] == 136700
    assert saved_turn["chart"]["type"] == "line"
    assert saved_turn["followups"] == ["按地区拆分一下"]
    assert "chat-message assistant" in saved_turn["assistantHtml"]

    reload_response = client.get("/api/chat/conversations", headers=headers)
    assert reload_response.status_code == 200
    reloaded_turn = reload_response.json()["conversations"][0]["turns"][0]
    assert reloaded_turn["assistantHtml"] == saved_turn["assistantHtml"]

    patch_turn_response = client.patch(
        f"/api/chat/conversations/{conversation_id}",
        headers=headers,
        json={
            "turns": [
                {
                    "traceId": "trace-test-002",
                    "question": "patch persistence smoke",
                    "insight": "PATCH can persist a full turn snapshot.",
                    "rowCount": 1,
                    "columnCount": 1,
                    "chartType": "table",
                    "createdAt": "10:25",
                    "generatedSql": "SELECT 1 AS ok LIMIT 1",
                    "sqlExplanation": "Patch route compatibility check.",
                    "columns": ["ok"],
                    "rows": [{"ok": 1}],
                    "chart": {"type": "table", "title": "patch smoke"},
                    "warnings": [],
                    "traceSteps": [],
                    "followups": ["next question"],
                    "assistantHtml": "<article>patch snapshot</article>",
                }
            ]
        },
    )
    assert patch_turn_response.status_code == 200
    assert any(turn["traceId"] == "trace-test-002" for turn in patch_turn_response.json()["turns"])

    with session_factory() as session:
        run = AnalysisRunRepository(session).get_by_trace_id("trace-test-001")
        assert run is not None
        assert run.result_columns == ["month", "sales_amount"]
        assert run.result_rows_preview[0]["sales_amount"] == 136700
        patch_run = AnalysisRunRepository(session).get_by_trace_id("trace-test-002")
        assert patch_run is not None
        assert patch_run.result_rows_preview == [{"ok": 1}]

    delete_response = client.delete(f"/api/chat/conversations/{conversation_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    after_delete_response = client.get("/api/chat/conversations", headers=headers)
    assert after_delete_response.status_code == 200
    assert after_delete_response.json()["conversations"] == []
