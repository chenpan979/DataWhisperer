from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.config import get_settings
from app.core.product_database import get_product_session
from app.db.product_models import DataSource
from app.models.data_sources import (
    DataSourceConnectionTestResponse,
    DataSourcePayload,
    DataSourceSyncResponse,
    DataSourceUpdateRequest,
)
from app.models.schema import SchemaSyncResponse
from app.repositories.product import (
    DataSourceRepository,
    SchemaRepository,
    WorkspaceRepository,
)
from app.tools.data_source_engine import (
    build_engine_for_data_source,
    encode_demo_password,
    is_password_placeholder,
    resolve_data_source_password,
)
from app.tools.schema_sync import SchemaSyncService

router = APIRouter(prefix="/data-sources", tags=["data_sources"])


@router.get("/default", response_model=DataSourcePayload)
def get_default_data_source(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> DataSourcePayload:
    """读取当前工作空间默认数据源。

    系统设置页会用这个接口回填表单，避免刷新后又退回前端假数据。
    """

    data_source = _ensure_default_data_source(session=session, auth_context=auth_context)
    return _build_data_source_payload(session=session, data_source=data_source)


@router.patch("/default", response_model=DataSourcePayload)
def update_default_data_source(
    payload: DataSourceUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> DataSourcePayload:
    """保存默认数据源配置。

    当前版本只正式支持 MySQL。密码为空或为占位符时，不覆盖后端已保存的凭据。
    """

    data_source = _ensure_default_data_source(session=session, auth_context=auth_context)
    db_type = _normalize_db_type(payload.db_type)
    repository = DataSourceRepository(session)
    repository.update(
        data_source,
        name=payload.name.strip(),
        db_type=db_type,
        host=payload.host.strip(),
        port=payload.port,
        database_name=payload.database_name.strip(),
        username=payload.username.strip(),
    )
    if not is_password_placeholder(payload.password):
        repository.save_credential(
            data_source_id=data_source.id,
            encrypted_password=encode_demo_password(payload.password or ""),
        )
    session.commit()
    return _build_data_source_payload(session=session, data_source=data_source)


@router.post("/default/test", response_model=DataSourceConnectionTestResponse)
def test_default_data_source_connection(
    payload: DataSourceUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> DataSourceConnectionTestResponse:
    """测试默认数据源连接。

    前端会先把表单内容传过来，因此用户即使还没点击保存，也能先验证配置是否正确。
    """

    persisted = _ensure_default_data_source(session=session, auth_context=auth_context)
    data_source = _transient_data_source_from_payload(payload, auth_context=auth_context)
    password = (
        resolve_data_source_password(persisted)
        if is_password_placeholder(payload.password)
        else payload.password
    )
    checked_at = datetime.now()
    started_at = time.perf_counter()
    status_value = "connected"
    try:
        table_count = _probe_database(build_engine_for_data_source(data_source, password=password), data_source)
        message = f"连接正常，读取到 {table_count} 张表。"
        ok = True
    except Exception as exc:
        table_count = 0
        message = f"连接失败：{exc}"
        ok = False
        status_value = "failed"

    latency_ms = max(1, round((time.perf_counter() - started_at) * 1000))
    DataSourceRepository(session).update(
        persisted,
        status=status_value,
        last_checked_at=checked_at,
    )
    session.commit()
    return DataSourceConnectionTestResponse(
        ok=ok,
        message=message,
        status=status_value,
        table_count=table_count,
        latency_ms=latency_ms,
        checked_at=checked_at,
    )


@router.post("/default/sync", response_model=DataSourceSyncResponse)
def sync_default_data_source_schema(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> DataSourceSyncResponse:
    """同步默认数据源 schema，并返回系统设置页需要展示的同步状态。"""

    data_source = _ensure_default_data_source(session=session, auth_context=auth_context)
    try:
        sync_result: SchemaSyncResponse = SchemaSyncService(
            session=session,
            auth_context=auth_context,
            engine=build_engine_for_data_source(data_source),
        ).sync()
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Schema 同步失败：{exc}") from exc

    return DataSourceSyncResponse(
        data_source=_build_data_source_payload(session=session, data_source=data_source),
        message=(
            f"已同步 {sync_result.table_count} 张表、{sync_result.column_count} 个字段、"
            f"{sync_result.relationship_count} 条关系。"
        ),
    )


def _ensure_default_data_source(*, session: Session, auth_context: AuthContext) -> DataSource:
    """确保当前工作空间至少有一个默认数据源。

    新注册租户初始没有 data_sources 记录；这里会从 DATABASE_URL 创建一条默认配置。
    """

    repository = DataSourceRepository(session)
    data_source = repository.get_default_for_workspace(auth_context.workspace)
    if data_source is not None:
        return data_source

    settings = get_settings()
    url = make_url(settings.database_url)
    data_source = repository.create(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        name="示例 MySQL 库",
        db_type=url.get_backend_name() or "mysql",
        host=url.host or "127.0.0.1",
        port=int(url.port or 3306),
        database_name=url.database or "datawhisperer_demo",
        username=url.username or "root",
        status="unknown",
        created_by=auth_context.user.id,
    )
    if url.password:
        repository.save_credential(
            data_source_id=data_source.id,
            encrypted_password=encode_demo_password(url.password),
        )
    WorkspaceRepository(session).set_default_data_source(auth_context.workspace, data_source.id)
    session.commit()
    return data_source


def _build_data_source_payload(*, session: Session, data_source: DataSource) -> DataSourcePayload:
    tables = SchemaRepository(session).list_tables(data_source_id=data_source.id)
    latest_synced_at = max(
        (table.synced_at for table in tables if table.synced_at is not None),
        default=None,
    )
    return DataSourcePayload(
        id=data_source.id,
        name=data_source.name,
        db_type=_display_db_type(data_source.db_type),
        host=data_source.host,
        port=data_source.port,
        database_name=data_source.database_name,
        username=data_source.username,
        status=data_source.status,
        password_saved=resolve_data_source_password(data_source) is not None,
        last_checked_at=data_source.last_checked_at,
        schema_synced_at=latest_synced_at,
        schema_table_count=len(tables),
    )


def _transient_data_source_from_payload(
    payload: DataSourceUpdateRequest,
    *,
    auth_context: AuthContext,
) -> DataSource:
    """用表单内容构造一个不入库的临时数据源对象，用于连接测试。"""

    return DataSource(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        name=payload.name.strip(),
        db_type=_normalize_db_type(payload.db_type),
        host=payload.host.strip(),
        port=payload.port,
        database_name=payload.database_name.strip(),
        username=payload.username.strip(),
        status="testing",
        created_by=auth_context.user.id,
    )


def _probe_database(engine: Engine, data_source: DataSource) -> int:
    """执行轻量连接检测，并统计当前库下的数据表数量。"""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if data_source.db_type.lower() == "mysql":
            result = connection.execute(
                text(
                    """
                    SELECT COUNT(*) AS table_count
                    FROM information_schema.tables
                    WHERE table_schema = :database_name
                    """
                ),
                {"database_name": data_source.database_name},
            )
            return int(result.scalar_one())
        return 0


def _normalize_db_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"mysql", "mysql+pymysql"}:
        return "mysql"
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前版本暂只支持 MySQL 数据源。")


def _display_db_type(value: str) -> str:
    return "MySQL" if value.lower().startswith("mysql") else value
