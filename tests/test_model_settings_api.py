from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app.api.model_settings as model_settings_api  # noqa: E402
from app.core.product_database import ProductBase, get_product_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.product import (  # noqa: E402
    ModelSettingsRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)


@pytest.fixture
def model_settings_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """创建只依赖产品库的模型配置测试客户端。"""

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


def test_model_settings_can_be_loaded_saved_tested_and_bound(
    model_settings_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """验证系统设置里的模型配置已经从静态草稿升级为后端 API。"""

    client, session_factory = model_settings_client
    headers = _seed_product_workspace_and_login(client, session_factory)

    get_response = client.get("/api/model-settings/default", headers=headers)
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["provider"]["name"] == "DashScope"
    assert payload["profile"]["chat_model"] == "qwen-plus"
    assert len(payload["agent_bindings"]) == 4

    update_response = client.patch(
        "/api/model-settings/default",
        headers=headers,
        json={
            "provider_name": "DashScope 主账号",
            "provider_type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-test-model-key",
            "profile_name": "默认生产配置",
            "chat_model": "qwen-max",
            "embedding_model": "text-embedding-v4",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["provider"]["name"] == "DashScope 主账号"
    assert updated["provider"]["api_key_saved"] is True
    assert updated["provider"]["api_key_mask"] == "sk-****-key"
    assert updated["profile"]["chat_model"] == "qwen-max"
    assert updated["profile"]["max_tokens"] == 4096

    test_response = client.post(
        "/api/model-settings/default/test",
        headers=headers,
        json={
            "provider_name": "DashScope 主账号",
            "provider_type": "dashscope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "******",
            "profile_name": "默认生产配置",
            "chat_model": "qwen-max",
            "embedding_model": "text-embedding-v4",
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    )
    assert test_response.status_code == 200
    assert test_response.json()["ok"] is True

    bindings_response = client.get("/api/model-settings/agent-bindings", headers=headers)
    assert bindings_response.status_code == 200
    bindings = bindings_response.json()
    assert {binding["agent_key"] for binding in bindings} == {
        "sql_agent",
        "insight_agent",
        "chart_agent",
        "rag_agent",
    }

    first_binding = bindings[0]
    patch_response = client.patch(
        "/api/model-settings/agent-bindings",
        headers=headers,
        json={
            "bindings": [
                {
                    "agent_key": first_binding["agent_key"],
                    "capability": first_binding["capability"],
                    "model_profile_id": first_binding["model_profile_id"],
                    "enabled": False,
                    "params": {"temperature": 0.05},
                }
            ]
        },
    )
    assert patch_response.status_code == 200
    changed = next(
        binding
        for binding in patch_response.json()
        if binding["agent_key"] == first_binding["agent_key"]
        and binding["capability"] == first_binding["capability"]
    )
    assert changed["enabled"] is False
    assert changed["params"] == {"temperature": 0.05}

    with session_factory() as session:
        repository = ModelSettingsRepository(session)
        provider = repository.get_default_provider(workspace_id=1)
        assert provider is not None
        assert provider.credential.encrypted_api_key.startswith("local-demo:")
        assert repository.get_default_profile(workspace_id=1).chat_model == "qwen-max"
        assert len(repository.list_bindings(workspace_id=1)) == 4


def test_model_settings_backfills_env_api_key_for_existing_provider(
    model_settings_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """升级脚本先建 provider 时，接口应从运行配置补齐密钥。"""

    client, session_factory = model_settings_client
    headers = _seed_product_workspace_and_login(client, session_factory)
    with session_factory() as session:
        repository = ModelSettingsRepository(session)
        repository.create_provider(
            tenant_id=1,
            workspace_id=1,
            name="DashScope",
            provider_type="dashscope",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            created_by=1,
        )
        session.commit()

    monkeypatch.setattr(
        model_settings_api,
        "get_settings",
        lambda: SimpleNamespace(
            effective_llm_api_key="sk-env-demo-key",
            effective_llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            effective_llm_model="qwen-plus",
            dashscope_embedding_model="text-embedding-v4",
            llm_temperature=0.1,
        ),
    )

    response = client.get("/api/model-settings/default", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"]["api_key_saved"] is True
    assert payload["provider"]["api_key_mask"] == "sk-****-key"

    with session_factory() as session:
        provider = ModelSettingsRepository(session).get_default_provider(workspace_id=1)
        assert provider.credential.encrypted_api_key.startswith("local-demo:")


def _seed_product_workspace_and_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> dict[str, str]:
    """准备 demo 租户、管理员和工作空间。"""

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
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
