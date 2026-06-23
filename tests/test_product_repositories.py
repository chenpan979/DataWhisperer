from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.product_database import ProductBase
from app.db import product_models
from app.repositories.product import (
    AnalysisRunRepository,
    AuditLogRepository,
    ConversationRepository,
    DataSourceRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def session() -> Iterator[Session]:
    """使用 SQLite 内存库验证 Repository 行为。

    这里测试的是 ORM 映射和仓储逻辑，不依赖开发者本机是否启动 MySQL。
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with session_factory() as current_session:
        yield current_session


def test_product_models_cover_core_tables() -> None:
    """确认产品管理库核心表都有 ORM 映射。"""

    # 显式引用模块，避免静态检查误判这个导入没有作用。
    assert product_models.Tenant.__tablename__ == "tenants"

    expected_tables = {
        "tenants",
        "users",
        "tenant_memberships",
        "workspaces",
        "workspace_memberships",
        "data_sources",
        "data_source_credentials",
        "model_providers",
        "model_credentials",
        "model_profiles",
        "agent_model_bindings",
        "schema_tables",
        "schema_columns",
        "schema_relationships",
        "conversations",
        "chat_messages",
        "analysis_runs",
        "audit_logs",
    }
    assert expected_tables.issubset(ProductBase.metadata.tables.keys())


def test_product_repositories_create_workspace_and_analysis_flow(session: Session) -> None:
    """验证产品库主链路：租户 -> 用户 -> 工作空间 -> 数据源 -> 会话 -> 分析结果。"""

    tenants = TenantRepository(session)
    users = UserRepository(session)
    workspaces = WorkspaceRepository(session)
    data_sources = DataSourceRepository(session)
    conversations = ConversationRepository(session)
    analysis_runs = AnalysisRunRepository(session)
    audit_logs = AuditLogRepository(session)

    tenant = tenants.create(tenant_key="demo", name="示例数据空间", plan="team")
    user = users.create(
        email="admin@datawhisperer.local",
        display_name="admin",
        password_hash="hash-placeholder",
    )
    tenants.add_member(tenant_id=tenant.id, user_id=user.id, role="owner")

    workspace = workspaces.create(
        tenant_id=tenant.id,
        workspace_key="default",
        name="默认工作空间",
        created_by=user.id,
    )
    workspaces.add_member(workspace_id=workspace.id, user_id=user.id, role="admin")

    data_source = data_sources.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        name="示例 MySQL 库",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="datawhisperer_demo",
        username="root",
        created_by=user.id,
    )
    data_sources.save_credential(
        data_source_id=data_source.id,
        encrypted_password="encrypted-placeholder",
    )
    workspaces.set_default_data_source(workspace, data_source.id)

    conversation = conversations.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        user_id=user.id,
        title="月度销售分析",
        summary="最近 6 个月销售额趋势",
    )
    question_message = conversations.append_message(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        role="user",
        content="查询最近 6 个月每月销售额趋势",
    )
    assistant_message = conversations.append_message(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        role="assistant",
        content="最近 6 个月销售额整体上升。",
    )

    run = analysis_runs.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        data_source_id=data_source.id,
        trace_id="trace-v3132-001",
        question=question_message.content,
        generated_sql="SELECT month, sales_amount FROM monthly_sales LIMIT 100",
        result_columns=["month", "sales_amount"],
        result_rows_preview=[{"month": "2026-01", "sales_amount": 136700}],
        chart_option={"type": "line"},
        insight="最近 6 个月销售额整体上升。",
        trace_steps=[{"name": "execute_sql", "status": "success"}],
        warnings=[],
        prompt_versions={"sql_generation": "v1"},
        duration_ms=18,
    )
    audit_logs.record(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        user_id=user.id,
        action="analysis.run.created",
        target_type="analysis_run",
        target_id=str(run.id),
    )
    session.commit()

    assert tenants.get_by_key("demo") is not None
    assert users.get_by_email("admin@datawhisperer.local") is not None
    assert workspaces.list_for_user(user_id=user.id)[0].name == "默认工作空间"
    assert data_sources.get_default_for_workspace(workspace).database_name == "datawhisperer_demo"
    assert conversations.list_recent(workspace_id=workspace.id)[0].title == "月度销售分析"
    assert [message.role for message in conversations.list_messages(conversation_id=conversation.id)] == [
        "user",
        "assistant",
    ]
    assert analysis_runs.get_by_trace_id("trace-v3132-001").duration_ms == 18
