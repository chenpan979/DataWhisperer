from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app.api.schema as schema_api  # noqa: E402
from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.db.product_models import SchemaColumn, SchemaRelationship, SchemaTable  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import (  # noqa: E402
    DataSourceRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def schema_sync_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """创建带产品库和业务库的 schema 同步测试客户端。"""

    product_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(product_engine)
    product_session_factory = sessionmaker(bind=product_engine, expire_on_commit=False, future=True)

    business_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    with business_engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                """
                CREATE TABLE regions (
                    region_id INTEGER PRIMARY KEY,
                    region_name VARCHAR(64) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE orders (
                    order_id INTEGER PRIMARY KEY,
                    region_id INTEGER NOT NULL,
                    order_date DATE NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    FOREIGN KEY(region_id) REFERENCES regions(region_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE order_items (
                    item_id INTEGER PRIMARY KEY,
                    order_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price DECIMAL(12, 2) NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES orders(order_id)
                )
                """
            )
        )

    monkeypatch.setattr(schema_api, "get_engine", lambda: business_engine)

    def override_product_session() -> Iterator[Session]:
        with product_session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    with TestClient(app) as client:
        yield client, product_session_factory
    app.dependency_overrides.clear()


def test_schema_sync_writes_snapshot_and_serves_graph(
    schema_sync_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """验证 schema 可以从业务库同步到产品管理库，并服务给图谱接口。"""

    client, session_factory = schema_sync_client
    headers = _seed_product_workspace_and_login(client, session_factory)

    sync_response = client.post("/api/schema/sync", headers=headers)
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert sync_payload["table_count"] == 3
    assert sync_payload["column_count"] == 10
    assert sync_payload["relationship_count"] == 2

    overview_response = client.get("/api/schema/overview", headers=headers)
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["table_count"] == 3
    orders = next(table for table in overview["tables"] if table["name"] == "orders")
    assert orders["foreign_keys"][0]["referred_table"] == "regions"

    graph_response = client.get("/api/schema/graph", headers=headers)
    assert graph_response.status_code == 200
    graph = graph_response.json()
    assert graph["node_count"] == 3
    assert graph["edge_count"] == 2
    assert {node["id"] for node in graph["nodes"]} == {"regions", "orders", "order_items"}

    tables_response = client.get("/api/schema/tables", headers=headers)
    assert tables_response.status_code == 200
    table_payload = tables_response.json()
    assert table_payload["data_source"]["database_name"] == "business_demo"
    orders_table = next(table for table in table_payload["tables"] if table["name"] == "orders")
    assert orders_table["outgoing_count"] == 1

    detail_response = client.get(f"/api/schema/tables/{orders_table['id']}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["name"] == "orders"
    assert "order_id" in detail["primary_keys"]
    assert detail["foreign_keys"][0]["referred_table"] == "regions"

    with session_factory() as session:
        assert session.query(SchemaTable).count() == 3
        assert session.query(SchemaColumn).count() == 10
        assert session.query(SchemaRelationship).count() == 2


def _seed_product_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    """准备 demo 租户、管理员、工作空间和默认数据源。"""

    with session_factory() as session:
        tenants = TenantRepository(session)
        users = UserRepository(session)
        workspaces = WorkspaceRepository(session)
        data_sources = DataSourceRepository(session)

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
        data_source = data_sources.create(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            name="测试业务库",
            db_type="sqlite",
            host="local",
            port=0,
            database_name="business_demo",
            username="tester",
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
