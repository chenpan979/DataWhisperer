from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import (  # noqa: E402
    AccountPreferenceRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def account_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
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


def test_account_preferences_are_persisted_and_password_can_change(
    account_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = account_client
    headers = _seed_workspace_and_login(client, session_factory)

    get_response = client.get("/api/account/preferences", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "admin"
    assert get_response.json()["default_view"] == "analysisView"

    avatar = "data:image/png;base64,QUJDRA=="
    update_response = client.patch(
        "/api/account/preferences",
        headers=headers,
        json={
            "display_name": "Chen",
            "role_title": "Data Product Owner",
            "avatar_url": avatar,
            "language": "en-US",
            "default_view": "schemaView",
        },
    )
    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["display_name"] == "Chen"
    assert payload["role_title"] == "Data Product Owner"
    assert payload["avatar_url"] == avatar
    assert payload["language"] == "en-US"

    me_response = client.get("/api/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["user"]["display_name"] == "Chen"

    with session_factory() as session:
        user = UserRepository(session).get_by_email("admin@datawhisperer.local")
        preference = AccountPreferenceRepository(session).get_for_user(tenant_id=1, user_id=user.id)
        assert preference.default_view == "schemaView"
        assert user.avatar_url == avatar

    wrong_password_response = client.patch(
        "/api/account/password",
        headers=headers,
        json={"current_password": "bad-password", "new_password": "87654321"},
    )
    assert wrong_password_response.status_code == 400

    password_response = client.patch(
        "/api/account/password",
        headers=headers,
        json={"current_password": "12345678", "new_password": "87654321"},
    )
    assert password_response.status_code == 200

    with session_factory() as session:
        user = UserRepository(session).get_by_email("admin@datawhisperer.local")
        assert verify_password("87654321", user.password_hash)

    old_login = client.post(
        "/api/auth/login",
        json={"tenant_key": "demo", "account": "admin@datawhisperer.local", "password": "12345678"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"tenant_key": "demo", "account": "admin@datawhisperer.local", "password": "87654321"},
    )
    assert new_login.status_code == 200


def _seed_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    with session_factory() as session:
        tenants = TenantRepository(session)
        users = UserRepository(session)
        workspaces = WorkspaceRepository(session)
        tenant = tenants.create(tenant_key="demo", name="Demo", plan="team")
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
