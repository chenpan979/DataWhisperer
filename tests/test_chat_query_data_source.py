from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app.api.chat as chat_api  # noqa: E402
from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.query import QueryResponse  # noqa: E402
from app.repositories.product import (  # noqa: E402
    DataSourceRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def chat_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, sessionmaker[Session], list[object]]]:
    """创建 AI 查数测试客户端，并把真实 Orchestrator 替换成轻量假对象。"""

    product_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    ProductBase.metadata.create_all(product_engine)
    product_session_factory = sessionmaker(bind=product_engine, expire_on_commit=False, future=True)

    captured_engines: list[object] = []

    class DummyOrchestrator:
        """只记录传入的业务库 Engine，不真的调用 LLM 或执行 SQL。"""

        def __init__(self, engine: object, llm: object):
            captured_engines.append(engine)

        async def run(self, request) -> QueryResponse:
            return QueryResponse(
                question=request.question,
                generated_sql="SELECT 1",
                sql_explanation="用于测试的只读查询。",
                columns=["value"],
                rows=[{"value": 1}],
                chart={"type": "table"},
                insight="测试通过。",
            )

    monkeypatch.setattr(chat_api, "DataAnalysisOrchestrator", DummyOrchestrator)
    monkeypatch.setattr(chat_api, "get_llm_client", lambda: object())

    def override_product_session() -> Iterator[Session]:
        with product_session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_product_session] = override_product_session
    with TestClient(app) as client:
        yield client, product_session_factory, captured_engines
    app.dependency_overrides.clear()


def test_chat_query_uses_default_data_source_when_logged_in(
    chat_client: tuple[TestClient, sessionmaker[Session], list[object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录态 AI 查数应该和系统设置中的默认数据源保持一致。"""

    client, session_factory, captured_engines = chat_client
    headers = _seed_product_workspace_and_login(client, session_factory)
    authenticated_engine = object()
    fallback_engine = object()

    monkeypatch.setattr(chat_api, "get_engine", lambda: fallback_engine)
    monkeypatch.setattr(
        chat_api,
        "get_default_data_source_engine",
        lambda **kwargs: authenticated_engine,
    )

    response = client.post(
        "/api/chat/query",
        headers=headers,
        json={"question": "查询各地区订单数量", "max_rows": 20},
    )

    assert response.status_code == 200
    assert response.json()["generated_sql"] == "SELECT 1"
    assert captured_engines[-1] is authenticated_engine


def test_chat_query_keeps_env_database_fallback_without_login(
    chat_client: tuple[TestClient, sessionmaker[Session], list[object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未登录调试接口时继续使用 `.env` 中的 DATABASE_URL。"""

    client, _session_factory, captured_engines = chat_client
    fallback_engine = object()

    monkeypatch.setattr(chat_api, "get_engine", lambda: fallback_engine)

    response = client.post(
        "/api/chat/query",
        json={"question": "查询各地区订单数量", "max_rows": 20},
    )

    assert response.status_code == 200
    assert captured_engines[-1] is fallback_engine


def _seed_product_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    """准备 demo 租户、管理员、工作空间和默认数据源，并返回登录头。"""

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
            name="系统设置默认库",
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
