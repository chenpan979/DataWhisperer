import base64
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.product_database import ProductBase
from app.repositories.product import (
    ModelSettingsRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)
from app.tools.agent_model_router import build_agent_model_router


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_agent_model_router_resolves_workspace_bindings() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        auth_context = _seed_workspace(session)
        repository = ModelSettingsRepository(session)
        provider = repository.create_provider(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            name="DashScope",
            provider_type="dashscope",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            status="configured",
            created_by=auth_context.user.id,
        )
        repository.save_credential(
            provider_id=provider.id,
            encrypted_api_key=_encode_demo_secret("sk-router-test"),
            key_mask="sk-****test",
        )
        profile = repository.create_profile(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            provider_id=provider.id,
            name="SQL Profile",
            chat_model="qwen-max",
            embedding_model="text-embedding-v4",
            temperature=0.2,
            max_tokens=4096,
            is_default=True,
        )
        repository.upsert_binding(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            agent_key="sql_agent",
            capability="sql_generation",
            model_profile_id=profile.id,
            enabled=True,
            params_json={"temperature": 0.05, "max_tokens": 2048},
        )
        repository.upsert_binding(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            agent_key="insight_agent",
            capability="insight_summary",
            model_profile_id=profile.id,
            enabled=False,
            params_json={},
        )
        session.commit()

        fallback = object()
        router = build_agent_model_router(
            session=session,
            auth_context=auth_context,
            fallback_llm=fallback,
            client_factory=FakeClient,
        )

    sql_client = router.client_for("sql_agent")
    assert isinstance(sql_client, FakeClient)
    assert sql_client.kwargs["model"] == "qwen-max"
    assert sql_client.kwargs["api_key"] == "sk-router-test"
    assert sql_client.kwargs["temperature"] == 0.05
    assert sql_client.kwargs["max_tokens"] == 2048
    assert router.client_for("insight_agent") is fallback
    assert "DashScope/qwen-max" in router.trace_detail("sql_agent")
    assert "disabled" in router.trace_detail("insight_agent")


def _seed_workspace(session: Session) -> SimpleNamespace:
    tenants = TenantRepository(session)
    users = UserRepository(session)
    workspaces = WorkspaceRepository(session)
    tenant = tenants.create(tenant_key="demo", name="Demo Tenant", plan="team")
    user = users.create(
        email="admin@datawhisperer.local",
        display_name="admin",
        password_hash="demo-password-hash-placeholder",
    )
    tenants.add_member(tenant_id=tenant.id, user_id=user.id, role="owner")
    workspace = workspaces.create(
        tenant_id=tenant.id,
        workspace_key="default",
        name="Default Workspace",
        created_by=user.id,
    )
    workspaces.add_member(workspace_id=workspace.id, user_id=user.id, role="admin")
    session.flush()
    return SimpleNamespace(tenant=tenant, user=user, workspace=workspace)


def _encode_demo_secret(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return f"local-demo:{encoded}"
