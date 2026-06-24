from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import (  # noqa: E402
    SecurityPolicyRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def security_policy_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """Create an isolated product database for security policy API tests."""

    product_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(product_engine)
    product_session_factory = sessionmaker(bind=product_engine, expire_on_commit=False, future=True)

    def override_product_session() -> Iterator[Session]:
        with product_session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    with TestClient(app) as client:
        yield client, product_session_factory
    app.dependency_overrides.clear()


def test_security_policy_can_be_loaded_saved_and_tested(
    security_policy_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Settings security policy is backed by a real API and product table."""

    client, session_factory = security_policy_client
    headers = _seed_product_workspace_and_login(client, session_factory)

    get_response = client.get("/api/security-policies/default", headers=headers)
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["readonly_sql_enabled"] is True
    assert payload["auto_limit_enabled"] is True
    assert payload["default_limit"] == 100

    blocked_update = client.patch(
        "/api/security-policies/default",
        headers=headers,
        json={
            "readonly_sql_enabled": False,
            "auto_limit_enabled": True,
            "default_limit": 80,
            "max_limit": 120,
            "query_timeout_seconds": 15,
            "audit_trace_enabled": True,
            "sensitive_config_managed": True,
        },
    )
    assert blocked_update.status_code == 422

    update_response = client.patch(
        "/api/security-policies/default",
        headers=headers,
        json={
            "readonly_sql_enabled": True,
            "auto_limit_enabled": True,
            "default_limit": 80,
            "max_limit": 120,
            "query_timeout_seconds": 15,
            "audit_trace_enabled": False,
            "sensitive_config_managed": True,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["default_limit"] == 80
    assert updated["max_limit"] == 120
    assert updated["audit_trace_enabled"] is False

    unsafe_test = client.post(
        "/api/security-policies/default/test",
        headers=headers,
        json={"sql": "DELETE FROM orders"},
    )
    assert unsafe_test.status_code == 200
    assert unsafe_test.json()["ok"] is False
    assert unsafe_test.json()["status"] == "blocked"

    safe_test = client.post(
        "/api/security-policies/default/test",
        headers=headers,
        json={"sql": "SELECT * FROM orders"},
    )
    assert safe_test.status_code == 200
    safe_payload = safe_test.json()
    assert safe_payload["ok"] is True
    assert safe_payload["applied_limit"] == 80
    assert safe_payload["normalized_sql"].endswith("LIMIT 80")

    with session_factory() as session:
        policy = SecurityPolicyRepository(session).get_for_workspace(workspace_id=1)
        assert policy is not None
        assert policy.default_limit == 80
        assert policy.audit_trace_enabled is False


def test_security_policy_rejects_default_limit_above_max(
    security_policy_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = security_policy_client
    headers = _seed_product_workspace_and_login(client, session_factory)

    response = client.patch(
        "/api/security-policies/default",
        headers=headers,
        json={
            "readonly_sql_enabled": True,
            "auto_limit_enabled": True,
            "default_limit": 500,
            "max_limit": 100,
            "query_timeout_seconds": 15,
            "audit_trace_enabled": True,
            "sensitive_config_managed": True,
        },
    )

    assert response.status_code == 422


def _seed_product_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    """Seed demo tenant, user and workspace, then return auth headers."""

    with session_factory() as session:
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
        session.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"tenant_key": "demo", "account": "admin", "password": "12345678"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
