import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def test_chat_conversation_lifecycle() -> None:
    """验证 AI 查数会话可以被服务端持久化管理。"""

    client = TestClient(create_app())

    create_response = client.post(
        "/api/chat/conversations",
        json={"title": "新对话", "subtitle": "等待数据问题", "preview": "等待数据问题"},
    )
    assert create_response.status_code == 200
    conversation = create_response.json()
    conversation_id = conversation["id"]

    list_response = client.get("/api/chat/conversations")
    assert list_response.status_code == 200
    assert any(item["id"] == conversation_id for item in list_response.json()["conversations"])

    update_response = client.patch(
        f"/api/chat/conversations/{conversation_id}",
        json={"title": "月度销售分析", "customTitle": True},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "月度销售分析"
    assert update_response.json()["customTitle"] is True

    turn_response = client.post(
        f"/api/chat/conversations/{conversation_id}/turns",
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
        },
    )
    assert turn_response.status_code == 200
    saved_turn = turn_response.json()["turns"][0]
    assert saved_turn["generatedSql"].startswith("SELECT")
    assert saved_turn["rows"][0]["sales_amount"] == 136700
    assert saved_turn["chart"]["type"] == "line"
    assert saved_turn["followups"] == ["按地区拆分一下"]

    delete_response = client.delete(f"/api/chat/conversations/{conversation_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
