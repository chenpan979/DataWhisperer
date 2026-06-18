from fastapi import APIRouter, HTTPException

from app.core.database import get_engine
from app.tools.schema_tool import build_schema_graph, build_schema_overview

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/overview")
def schema_overview() -> dict[str, object]:
    try:
        return build_schema_overview(get_engine())
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status_code=503, detail=f"Database schema read failed: {exc}") from exc


@router.get("/graph")
def schema_graph() -> dict[str, object]:
    try:
        return build_schema_graph(get_engine())
    except Exception as exc:  # pragma: no cover - depends on external database
        raise HTTPException(status_code=503, detail=f"Database schema graph read failed: {exc}") from exc
