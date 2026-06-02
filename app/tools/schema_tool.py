from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def build_schema_overview(engine: Engine) -> dict[str, Any]:
    """读取数据库元信息，并整理成 JSON 可序列化的 schema 概览。

    Text-to-SQL 很依赖 schema context。这里用 SQLAlchemy inspection 自动反射
    表、字段、主键和外键，而不是把表结构硬编码进 prompt。
    数据库结构变化时，Agent 可以自动读取最新结构。
    """

    inspector = inspect(engine)
    tables = []
    for table_name in inspector.get_table_names():
        pk_columns = set(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or []
        )
        columns = []
        for column in inspector.get_columns(table_name):
            columns.append(
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column.get("nullable", True),
                    "primary_key": column["name"] in pk_columns or bool(column.get("primary_key")),
                }
            )
        foreign_keys = [
            {
                "columns": fk.get("constrained_columns", []),
                "referred_table": fk.get("referred_table"),
                "referred_columns": fk.get("referred_columns", []),
            }
            for fk in inspector.get_foreign_keys(table_name)
        ]
        tables.append({"name": table_name, "columns": columns, "foreign_keys": foreign_keys})
    return {"tables": tables, "table_count": len(tables)}


def schema_to_prompt(schema: dict[str, Any]) -> str:
    """把 schema JSON 压缩成适合放进 prompt 的文本。

    完整 JSON 对程序友好，但对模型来说偏啰嗦，会浪费 token。
    这里只保留 V1 生成 SQL 必需的信息：表名、字段、主键、非空和外键关系。
    """

    lines: list[str] = []
    for table in schema.get("tables", []):
        column_parts = []
        for column in table.get("columns", []):
            flags = []
            if column.get("primary_key"):
                flags.append("PK")
            if not column.get("nullable", True):
                flags.append("NOT NULL")
            flag_text = f" [{' '.join(flags)}]" if flags else ""
            column_parts.append(f"{column['name']} {column['type']}{flag_text}")
        lines.append(f"Table {table['name']}: " + ", ".join(column_parts))
        for fk in table.get("foreign_keys", []):
            lines.append(
                "  FK "
                + ", ".join(fk.get("columns", []))
                + f" -> {fk.get('referred_table')}("
                + ", ".join(fk.get("referred_columns", []))
                + ")"
            )
    return "\n".join(lines)
