from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app.api.data_sources as data_sources_api  # noqa: E402
from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import (  # noqa: E402
    DataSourceRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def data_source_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """创建只依赖产品库的测试客户端。"""

    product_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(product_engine)
    product_session_factory = sessionmaker(bind=product_engine, expire_on_commit=False, future=True)

    # 连接测试只关心 API 编排，不在单测里真的连 MySQL。
    monkeypatch.setattr(data_sources_api, "build_engine_for_data_source", lambda *args, **kwargs: object())
    monkeypatch.setattr(data_sources_api, "_probe_database", lambda engine, data_source: 5)

    def override_product_session() -> Iterator[Session]:
        with product_session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    with TestClient(app) as client:
        yield client, product_session_factory
    app.dependency_overrides.clear()


def test_default_data_source_can_be_loaded_saved_and_tested(
    data_source_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = data_source_client
    headers = _seed_product_workspace_and_login(client, session_factory)

    get_response = client.get("/api/data-sources/default", headers=headers)
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["name"] == "Demo MySQL"
    assert payload["database_name"] == "datawhisperer_demo"
    assert "password" not in payload

    update_response = client.patch(
        "/api/data-sources/default",
        headers=headers,
        json={
            "name": "Sales Demo",
            "db_type": "MySQL",
            "host": "127.0.0.1",
            "port": 3306,
            "database_name": "datawhisperer_demo",
            "username": "root",
            "password": "secret123",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Sales Demo"
    assert updated["password_saved"] is True
    assert "password" not in updated

    test_response = client.post(
        "/api/data-sources/default/test",
        headers=headers,
        json={
            "name": "Sales Demo",
            "db_type": "MySQL",
            "host": "127.0.0.1",
            "port": 3306,
            "database_name": "datawhisperer_demo",
            "username": "root",
            "password": "******",
        },
    )
    assert test_response.status_code == 200
    result = test_response.json()
    assert result["ok"] is True
    assert result["table_count"] == 5

    with session_factory() as session:
        data_source = DataSourceRepository(session).list_by_workspace(workspace_id=1)[0]
        assert data_source.name == "Sales Demo"
        assert data_source.status == "connected"
        assert data_source.last_checked_at is not None
        assert data_source.credential.encrypted_password.startswith("local-demo:")


def _seed_product_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    with session_factory() as session:
        tenants = TenantRepository(session)
        users = UserRepository(session)
        workspaces = WorkspaceRepository(session)
        data_sources = DataSourceRepository(session)

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
        data_source = data_sources.create(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            name="Demo MySQL",
            db_type="mysql",
            host="127.0.0.1",
            port=3306,
            database_name="datawhisperer_demo",
            username="root",
            created_by=user.id,
        )
        workspaces.set_default_data_source(workspace, data_source.id)
        session.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"tenant_key": "demo", "account": "admin", "password": "12345678"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
