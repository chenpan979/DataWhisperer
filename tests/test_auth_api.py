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
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def auth_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """创建带 SQLite 产品库的测试客户端。"""

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
        yield client, session_factory
    app.dependency_overrides.clear()


def test_auth_login_me_and_password_hash_upgrade(
    auth_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """验证 demo 管理员可以从真实产品库登录，并升级历史占位密码。"""

    client, session_factory = auth_client
    with session_factory() as session:
        tenants = TenantRepository(session)
        users = UserRepository(session)
        workspaces = WorkspaceRepository(session)
        tenant = tenants.create(tenant_key="demo", name="示例数据空间", plan="team")
        user = users.create(
            email="admin@datawhisperer.local",
            display_name="admin",
            password_hash="demo-password-hash-placeholder",
        )
        tenants.add_member(tenant_id=tenant.id, user_id=user.id, role="owner")
        workspace = workspaces.create(
            tenant_id=tenant.id,
            workspace_key="default",
            name="默认工作空间",
            created_by=user.id,
        )
        workspaces.add_member(workspace_id=workspace.id, user_id=user.id, role="admin")
        session.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"tenant_key": "demo", "account": "admin", "password": "12345678"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert login_payload["tenant"]["tenant_key"] == "demo"
    assert login_payload["workspace"]["workspace_key"] == "default"

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["user"]["display_name"] == "admin"

    with session_factory() as session:
        user = UserRepository(session).get_by_email("admin@datawhisperer.local")
        assert user is not None
        assert user.password_hash != "demo-password-hash-placeholder"


def test_auth_register_creates_tenant_user_and_workspace(
    auth_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """验证注册接口会真实创建租户、管理员和默认工作空间。"""

    client, session_factory = auth_client
    response = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "星河零售数据团队",
            "tenant_key": "galaxy-retail",
            "display_name": "Chen",
            "email": "chen@example.com",
            "password": "12345678",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant"]["tenant_key"] == "galaxy-retail"
    assert payload["user"]["role"] == "租户管理员"
    assert payload["workspace"]["name"] == "默认工作空间"

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["tenant"]["name"] == "星河零售数据团队"

    duplicate_response = client.post(
        "/api/auth/register",
        json={
            "tenant_name": "星河零售数据团队",
            "tenant_key": "galaxy-retail",
            "display_name": "Chen",
            "email": "another@example.com",
            "password": "12345678",
        },
    )
    assert duplicate_response.status_code == 409

    with session_factory() as session:
        tenant = TenantRepository(session).get_by_key("galaxy-retail")
        assert tenant is not None
        workspace = WorkspaceRepository(session).get_by_key(
            tenant_id=tenant.id,
            workspace_key="default",
        )
        assert workspace is not None
