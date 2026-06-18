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


def build_schema_graph(engine: Engine) -> dict[str, Any]:
    """把数据库 schema 转成前端 3D 图谱可以直接消费的节点和边。

    overview 接口偏“表结构清单”，graph 接口偏“关系可视化”。
    后端在这里统一判断表类型、主键、核心字段和外键关系，避免前端为了画图
    重复理解数据库元信息。后续如果要接入业务知识、RAG 文档或指标口径，
    也可以继续在这个结构上扩展节点类型。
    """

    schema = build_schema_overview(engine)
    tables = schema.get("tables", [])
    incoming_counts = {table["name"]: 0 for table in tables}
    outgoing_counts = {table["name"]: len(table.get("foreign_keys", [])) for table in tables}
    incoming_relations: dict[str, list[dict[str, Any]]] = {table["name"]: [] for table in tables}

    for table in tables:
        for foreign_key in table.get("foreign_keys", []):
            referred_table = foreign_key.get("referred_table")
            if referred_table in incoming_counts:
                incoming_counts[referred_table] += 1
                incoming_relations[referred_table].append(
                    {
                        "source_table": table["name"],
                        "columns": foreign_key.get("columns", []),
                        "referred_columns": foreign_key.get("referred_columns", []),
                    }
                )

    nodes = []
    edges = []
    for table in tables:
        table_name = table["name"]
        columns = table.get("columns", [])
        primary_keys = [column["name"] for column in columns if column.get("primary_key")]
        foreign_keys = table.get("foreign_keys", [])
        core_fields = _pick_core_fields(columns, foreign_keys)
        table_kind = _classify_table(table_name, incoming_counts[table_name], outgoing_counts[table_name])

        nodes.append(
            {
                "id": table_name,
                "label": table_name,
                "kind": table_kind,
                "primary_keys": primary_keys,
                "core_fields": core_fields,
                "columns": columns,
                "column_count": len(columns),
                "foreign_keys": foreign_keys,
                "incoming_relations": incoming_relations[table_name],
                "incoming_count": incoming_counts[table_name],
                "outgoing_count": outgoing_counts[table_name],
            }
        )

        for foreign_key in foreign_keys:
            referred_table = foreign_key.get("referred_table")
            if not referred_table:
                continue
            columns_text = ", ".join(foreign_key.get("columns", []))
            referred_text = ", ".join(foreign_key.get("referred_columns", []))
            edges.append(
                {
                    "source": table_name,
                    "target": referred_table,
                    "label": f"{columns_text} -> {referred_text}",
                    "columns": foreign_key.get("columns", []),
                    "referred_columns": foreign_key.get("referred_columns", []),
                    "type": "foreign_key",
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _pick_core_fields(columns: list[dict[str, Any]], foreign_keys: list[dict[str, Any]]) -> list[str]:
    """挑选适合在详情面板首屏展示的关键字段。

    规则优先展示主键、外键和常见业务字段，避免把几十个字段一次性塞给用户。
    完整字段仍保留在 columns 中，详情表格会展示全部内容。
    """

    foreign_key_columns = {
        column_name
        for foreign_key in foreign_keys
        for column_name in foreign_key.get("columns", [])
    }
    business_keywords = ("name", "date", "time", "amount", "price", "quantity", "status", "category", "region")
    scored: list[tuple[int, str]] = []
    for index, column in enumerate(columns):
        name = column["name"]
        score = index
        if column.get("primary_key"):
            score -= 100
        if name in foreign_key_columns:
            score -= 60
        if any(keyword in name.lower() for keyword in business_keywords):
            score -= 20
        scored.append((score, name))
    return [name for _, name in sorted(scored)[:6]]


def _classify_table(table_name: str, incoming_count: int, outgoing_count: int) -> str:
    """按关系数量和命名约定给表一个轻量类型，便于前端区分颜色和大小。"""

    lowered = table_name.lower()
    if "item" in lowered or (incoming_count and outgoing_count):
        return "bridge"
    if outgoing_count >= 2 or any(keyword in lowered for keyword in ("order", "fact", "sale")):
        return "fact"
    return "dimension"


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
