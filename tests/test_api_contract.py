from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")

from sqlalchemy.schema import CreateTable  # noqa: E402
from sqlalchemy.dialects import mysql  # noqa: E402

from app.db.product_models import ChatMessage  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_app_routes_exist() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/health" in paths
    assert "/api/auth/login" in paths
    assert "/api/auth/register" in paths
    assert "/api/auth/me" in paths
    assert "/api/examples" in paths
    assert "/api/schema/overview" in paths
    assert "/api/schema/graph" in paths
    assert "/api/schema/sync" in paths
    assert "/api/schema/tables" in paths
    assert "/api/schema/tables/{table_id}" in paths
    assert "/api/chat/query" in paths
    assert "/api/chat/conversations" in paths
    assert "/api/chat/conversations/{conversation_id}" in paths
    assert "/api/chat/conversations/{conversation_id}/turns" in paths
    assert "/api/files/schema" in paths
    assert "/api/files/schema/{file_id}/preview" in paths
    assert "/api/files/rag" in paths
    assert "/api/files/rag/{file_id}/preview" in paths
    assert "/api/evaluations/run" in paths
    assert "/api/evaluations/datasets" in paths
    assert "/api/evaluations/datasets/{file_id}/preview" in paths


def test_console_static_fragments_are_served() -> None:
    client = TestClient(create_app())

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "/static/assets/bootstrap.js" in index_response.text
    assert "/static/partials/icon-sprite.html" in index_response.text
    assert "/static/partials/auth-shell.html" in index_response.text
    assert "/static/partials/app-shell.html" in index_response.text

    for path in [
        "/static/partials/icon-sprite.html",
        "/static/partials/auth-shell.html",
        "/static/partials/app-shell.html",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.text.strip()


def test_product_schema_migration_script_contains_core_tables() -> None:
    script_path = Path("scripts/init_product_schema.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    assert "create database if not exists datawhisperer_product" in sql
    for table_name in [
        "tenants",
        "users",
        "tenant_memberships",
        "workspaces",
        "data_sources",
        "data_source_credentials",
        "schema_tables",
        "schema_columns",
        "schema_relationships",
        "conversations",
        "chat_messages",
        "analysis_runs",
        "audit_logs",
    ]:
        assert f"create table if not exists {table_name}" in sql
    assert "content longtext not null" in sql


def test_chat_message_content_uses_mysql_longtext() -> None:
    """回答快照可能包含图表 dataURL，MySQL TEXT 的 64KB 不够用。"""

    ddl = str(CreateTable(ChatMessage.__table__).compile(dialect=mysql.dialect())).lower()
    assert "content longtext not null" in ddl


def test_v31352_upgrade_script_expands_chat_message_content() -> None:
    script_path = Path("scripts/upgrade_product_schema_v3_13_5_2.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    assert "alter table chat_messages" in sql
    assert "modify column content longtext not null" in sql
