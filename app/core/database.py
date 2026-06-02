from collections.abc import Sequence
from decimal import Decimal
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """创建并缓存 SQLAlchemy Engine。

    Engine 可以理解成数据库连接管理器。用 lru_cache 缓存后，
    整个进程只创建一次连接池，避免每次请求都重新初始化数据库连接。
    """

    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def _to_jsonable(value: Any) -> Any:
    """把数据库返回值转换成 JSON 友好的 Python 类型。"""

    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def fetch_all(engine: Engine, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    """执行 SQL，并返回列名和行数据。

    行数据会被转换成 list[dict]，这样前端表格、图表和大模型总结都能复用。
    """

    with engine.connect() as connection:
        result = connection.execute(text(sql))
        columns = list(result.keys())
        rows = [
            {column: _to_jsonable(row._mapping[column]) for column in columns}
            for row in result.fetchall()
        ]
    return columns, rows


def rows_to_preview(rows: Sequence[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """截取少量结果行用于 prompt 或日志。

    不把所有结果都塞给模型，是为了控制 token、降低成本、减少噪声。
    """

    return list(rows[:limit])
