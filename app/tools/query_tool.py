from sqlalchemy.engine import Engine

from app.core.database import fetch_all
from app.tools.sql_tool import ensure_limit


def execute_safe_query(
    engine: Engine,
    sql: str,
    max_rows: int,
    *,
    auto_limit_enabled: bool = True,
) -> tuple[str, list[str], list[dict]]:
    """执行经过安全处理的 SQL。

    这里不直接执行模型生成的原始 SQL，而是先调用 ensure_limit：
    1. 校验只允许 SELECT / WITH；
    2. 拦截危险关键字和多语句；
    3. 自动补 LIMIT，避免返回过多数据。
    """

    safe_sql = ensure_limit(sql, max_rows, auto_limit_enabled=auto_limit_enabled)
    columns, rows = fetch_all(engine, safe_sql)
    return safe_sql, columns, rows
