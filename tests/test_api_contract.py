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
    assert "/api/account/preferences" in paths
    assert "/api/account/password" in paths
    assert "/api/examples" in paths
    assert "/api/data-sources/default" in paths
    assert "/api/data-sources/default/test" in paths
    assert "/api/data-sources/default/sync" in paths
    assert "/api/model-settings/default" in paths
    assert "/api/model-settings/default/test" in paths
    assert "/api/model-settings/agent-bindings" in paths
    assert "/api/security-policies/default" in paths
    assert "/api/security-policies/default/test" in paths
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
    assert "/api/files/rag/{file_id}/sync" in paths
    assert "/api/evaluations/run" in paths
    assert "/api/evaluations/datasets" in paths
    assert "/api/evaluations/datasets/{file_id}/preview" in paths


def test_console_static_fragments_are_served() -> None:
    client = TestClient(create_app())

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "/static/assets/bootstrap.js" in index_response.text
    assert "v=4.0.0" in index_response.text
    assert "/static/partials/icon-sprite.html" in index_response.text
    assert "/static/partials/auth-shell.html" in index_response.text
    assert "/static/partials/app-shell.html" in index_response.text

    bootstrap_js = Path("static/assets/bootstrap.js").read_text(encoding="utf-8")
    assert 'const appVersion = "4.0.0"' in bootstrap_js

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
        "user_preferences",
        "tenant_memberships",
        "workspaces",
        "workspace_security_policies",
        "data_sources",
        "data_source_credentials",
        "model_providers",
        "model_credentials",
        "model_profiles",
        "agent_model_bindings",
        "schema_tables",
        "schema_columns",
        "schema_relationships",
        "knowledge_bases",
        "knowledge_documents",
        "knowledge_chunks",
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


def test_v3138_upgrade_script_adds_model_settings_tables() -> None:
    script_path = Path("scripts/upgrade_product_schema_v3_13_8.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    for table_name in [
        "model_providers",
        "model_credentials",
        "model_profiles",
        "agent_model_bindings",
    ]:
        assert f"create table if not exists {table_name}" in sql
    assert "sql_agent" in sql
    assert "rag_agent" in sql


def test_v3139_upgrade_script_adds_account_preferences() -> None:
    script_path = Path("scripts/upgrade_product_schema_v3_13_9.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    assert "create table if not exists user_preferences" in sql
    assert "modify column avatar_url longtext null" in sql
    assert "uk_user_preferences_tenant_user" in sql


def test_v31310_upgrade_script_adds_security_policy_table() -> None:
    script_path = Path("scripts/upgrade_product_schema_v3_13_10.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    assert "create table if not exists workspace_security_policies" in sql
    assert "readonly_sql_enabled" in sql
    assert "auto_limit_enabled" in sql
    assert "default_limit" in sql
    assert "max_limit" in sql
    assert "audit_trace_enabled" in sql



def test_v31312_upgrade_script_adds_knowledge_base_tables() -> None:
    script_path = Path("scripts/upgrade_product_schema_v3_13_12.sql")
    sql = script_path.read_text(encoding="utf-8").lower()

    for table_name in ["knowledge_bases", "knowledge_documents", "knowledge_chunks"]:
        assert f"create table if not exists {table_name}" in sql
    assert "workspace_id" in sql
    assert "knowledge_base_id" in sql
    assert "默认知识库" in sql
