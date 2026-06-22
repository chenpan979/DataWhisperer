from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.database import get_engine
from app.core.product_database import get_product_session
from app.models.schema import SchemaSyncResponse
from app.tools.schema_sync import SchemaSyncService
from app.tools.schema_tool import build_schema_graph, build_schema_overview

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/overview")
def schema_overview(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> dict[str, object]:
    """读取数据库结构摘要。

    登录后优先读取产品库中的 schema 快照；如果快照不存在，会自动同步一次。
    未登录访问时仍保留 V1 的实时读取能力，方便本地调试和接口文档演示。
    """

    try:
        auth_context = _optional_auth_context(authorization, session)
        if auth_context is not None:
            service = _build_schema_service(session=session, auth_context=auth_context)
            service.ensure_snapshot()
            return service.build_overview()
        return build_schema_overview(get_engine())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status_code=503, detail=f"Database schema read failed: {exc}") from exc


@router.get("/graph")
def schema_graph(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> dict[str, object]:
    """读取 3D 关系图谱数据。

    这里返回前端 3D 图谱可以直接消费的 `nodes` 和 `edges`。
    登录态下读产品库快照，未登录时兜底实时扫描业务库。
    """

    try:
        auth_context = _optional_auth_context(authorization, session)
        if auth_context is not None:
            service = _build_schema_service(session=session, auth_context=auth_context)
            service.ensure_snapshot()
            return service.build_graph()
        return build_schema_graph(get_engine())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status_code=503, detail=f"Database schema graph read failed: {exc}") from exc


@router.post("/sync", response_model=SchemaSyncResponse)
def sync_schema(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> SchemaSyncResponse:
    """把当前默认数据源的表结构同步到产品管理库。"""

    try:
        return _build_schema_service(session=session, auth_context=auth_context).sync()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status_code=503, detail=f"Database schema sync failed: {exc}") from exc


@router.get("/tables")
def list_schema_tables(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> dict[str, object]:
    """读取已同步的数据表清单。"""

    try:
        service = _build_schema_service(session=session, auth_context=auth_context)
        service.ensure_snapshot()
        return service.list_tables()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tables/{table_id}")
def get_schema_table_detail(
    table_id: int,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> dict[str, object]:
    """读取单张表详情。"""

    try:
        service = _build_schema_service(session=session, auth_context=auth_context)
        service.ensure_snapshot()
        detail = service.get_table_detail(table_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="表结构不存在或无权访问。")
    return detail


def _optional_auth_context(authorization: str | None, session: Session) -> AuthContext | None:
    """尝试解析登录态；没有 token 时返回 None，非法 token 仍然抛出 401。"""

    if not authorization:
        return None
    return require_auth_context(authorization=authorization, session=session)


def _build_schema_service(*, session: Session, auth_context: AuthContext) -> SchemaSyncService:
    return SchemaSyncService(session=session, auth_context=auth_context, engine=get_engine())
