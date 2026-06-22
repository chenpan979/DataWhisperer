from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.db.product_models import DataSource, SchemaColumn, SchemaRelationship, SchemaTable
from app.models.schema import SchemaSyncResponse
from app.repositories.product import (
    AuditLogRepository,
    DataSourceRepository,
    SchemaRepository,
)
from app.tools.schema_tool import build_schema_overview, schema_overview_to_graph

SYNC_VERSION = "v3.13.5"


class SchemaSyncService:
    """Schema 同步服务。

    这个服务是 V3.13.5 的核心：把业务数据库的实时结构同步到产品管理库。
    同步后的快照会被 3D 关系图谱、表详情和后续 RAG schema 检索复用。
    """

    def __init__(self, *, session: Session, auth_context: AuthContext, engine: Engine):
        self.session = session
        self.auth = auth_context
        self.engine = engine
        self.data_sources = DataSourceRepository(session)
        self.schemas = SchemaRepository(session)
        self.audit_logs = AuditLogRepository(session)

    def get_default_data_source(self) -> DataSource:
        """读取当前工作空间默认数据源。"""

        data_source = self.data_sources.get_default_for_workspace(self.auth.workspace)
        if data_source is None:
            raise ValueError("当前工作空间还没有默认数据源，请先在系统设置中配置数据源。")
        return data_source

    def has_snapshot(self) -> bool:
        """判断默认数据源是否已经同步过 schema。"""

        data_source = self.get_default_data_source()
        return bool(self.schemas.list_tables(data_source_id=data_source.id))

    def sync(self) -> SchemaSyncResponse:
        """从业务库读取 schema，并覆盖写入产品管理库快照表。"""

        data_source = self.get_default_data_source()
        overview = build_schema_overview(self.engine)
        graph = schema_overview_to_graph(overview)
        kind_by_table = {node["id"]: node.get("kind", "unknown") for node in graph.get("nodes", [])}
        synced_at = datetime.now()

        self.schemas.clear_for_data_source(data_source.id)
        table_records: dict[str, SchemaTable] = {}
        column_records: dict[tuple[str, str], SchemaColumn] = {}
        column_count = 0
        relationship_count = 0

        for table in overview.get("tables", []):
            table_name = table["name"]
            table_record = self.schemas.create_table(
                tenant_id=self.auth.tenant.id,
                workspace_id=self.auth.workspace.id,
                data_source_id=data_source.id,
                table_name=table_name,
                table_comment=table.get("comment"),
                table_type=kind_by_table.get(table_name, "unknown"),
                sync_version=SYNC_VERSION,
                synced_at=synced_at,
            )
            table_records[table_name] = table_record

            for index, column in enumerate(table.get("columns", []), start=1):
                column_record = self.schemas.create_column(
                    tenant_id=self.auth.tenant.id,
                    workspace_id=self.auth.workspace.id,
                    data_source_id=data_source.id,
                    table_id=table_record.id,
                    column_name=column["name"],
                    data_type=column["type"],
                    column_comment=column.get("comment"),
                    is_primary_key=bool(column.get("primary_key")),
                    is_nullable=bool(column.get("nullable", True)),
                    ordinal_position=index,
                    semantic_type=_infer_semantic_type(column["name"], column["type"]),
                )
                column_records[(table_name, column["name"])] = column_record
                column_count += 1

        for table in overview.get("tables", []):
            source_table = table_records.get(table["name"])
            if source_table is None:
                continue
            for foreign_key in table.get("foreign_keys", []):
                target_table = table_records.get(foreign_key.get("referred_table"))
                if target_table is None:
                    continue
                for source_column_name, target_column_name in zip(
                    foreign_key.get("columns", []),
                    foreign_key.get("referred_columns", []),
                    strict=False,
                ):
                    source_column = column_records.get((table["name"], source_column_name))
                    target_column = column_records.get((target_table.table_name, target_column_name))
                    if source_column is None or target_column is None:
                        continue
                    self.schemas.create_relationship(
                        tenant_id=self.auth.tenant.id,
                        workspace_id=self.auth.workspace.id,
                        data_source_id=data_source.id,
                        source_table_id=source_table.id,
                        source_column_id=source_column.id,
                        target_table_id=target_table.id,
                        target_column_id=target_column.id,
                    )
                    relationship_count += 1

        self.audit_logs.record(
            tenant_id=self.auth.tenant.id,
            workspace_id=self.auth.workspace.id,
            user_id=self.auth.user.id,
            action="schema.synced",
            target_type="data_source",
            target_id=str(data_source.id),
            detail={
                "table_count": len(table_records),
                "column_count": column_count,
                "relationship_count": relationship_count,
                "sync_version": SYNC_VERSION,
            },
        )
        self.session.commit()
        return SchemaSyncResponse(
            data_source_id=data_source.id,
            data_source_name=data_source.name,
            table_count=len(table_records),
            column_count=column_count,
            relationship_count=relationship_count,
            synced_at=synced_at.isoformat(),
        )

    def ensure_snapshot(self) -> None:
        """如果还没有 schema 快照，就自动同步一次。"""

        if not self.has_snapshot():
            self.sync()

    def build_overview(self) -> dict[str, Any]:
        """把产品库 schema 快照组装成 `/api/schema/overview` 兼容结构。"""

        data_source = self.get_default_data_source()
        tables = self.schemas.list_tables(data_source_id=data_source.id)
        columns = self.schemas.list_columns(data_source_id=data_source.id)
        relationships = self.schemas.list_relationships(data_source_id=data_source.id)
        return _snapshot_to_overview(tables=tables, columns=columns, relationships=relationships)

    def build_graph(self) -> dict[str, Any]:
        """把产品库 schema 快照组装成前端 3D 图谱结构。"""

        return schema_overview_to_graph(self.build_overview())

    def list_tables(self) -> dict[str, Any]:
        """返回数据结构页面可消费的表清单。"""

        data_source = self.get_default_data_source()
        tables = self.schemas.list_tables(data_source_id=data_source.id)
        overview = self.build_overview()
        graph = schema_overview_to_graph(overview)
        node_by_name = {node["id"]: node for node in graph.get("nodes", [])}
        return {
            "data_source": _data_source_payload(data_source),
            "table_count": len(tables),
            "tables": [
                {
                    "id": table.id,
                    "name": table.table_name,
                    "comment": table.table_comment,
                    "type": table.table_type,
                    "synced_at": table.synced_at.isoformat() if table.synced_at else None,
                    "column_count": node_by_name.get(table.table_name, {}).get("column_count", 0),
                    "primary_keys": node_by_name.get(table.table_name, {}).get("primary_keys", []),
                    "core_fields": node_by_name.get(table.table_name, {}).get("core_fields", []),
                    "incoming_count": node_by_name.get(table.table_name, {}).get("incoming_count", 0),
                    "outgoing_count": node_by_name.get(table.table_name, {}).get("outgoing_count", 0),
                }
                for table in tables
            ],
        }

    def get_table_detail(self, table_id: int) -> dict[str, Any] | None:
        """返回单表详情。"""

        table = self.schemas.get_table(table_id=table_id, workspace_id=self.auth.workspace.id)
        if table is None:
            return None
        overview = self.build_overview()
        graph = schema_overview_to_graph(overview)
        node = next((item for item in graph.get("nodes", []) if item["id"] == table.table_name), None)
        if node is None:
            return None
        return {
            "id": table.id,
            "name": table.table_name,
            "comment": table.table_comment,
            "type": table.table_type,
            "synced_at": table.synced_at.isoformat() if table.synced_at else None,
            "primary_keys": node.get("primary_keys", []),
            "core_fields": node.get("core_fields", []),
            "columns": node.get("columns", []),
            "foreign_keys": node.get("foreign_keys", []),
            "incoming_relations": node.get("incoming_relations", []),
            "incoming_count": node.get("incoming_count", 0),
            "outgoing_count": node.get("outgoing_count", 0),
        }


def _snapshot_to_overview(
    *,
    tables: list[SchemaTable],
    columns: list[SchemaColumn],
    relationships: list[SchemaRelationship],
) -> dict[str, Any]:
    """把产品库三张 schema 表还原成 schema overview。"""

    table_by_id = {table.id: table for table in tables}
    column_by_id = {column.id: column for column in columns}
    columns_by_table_id: dict[int, list[SchemaColumn]] = defaultdict(list)
    relationships_by_source_table_id: dict[int, list[SchemaRelationship]] = defaultdict(list)

    for column in columns:
        columns_by_table_id[column.table_id].append(column)
    for relationship in relationships:
        relationships_by_source_table_id[relationship.source_table_id].append(relationship)

    table_payloads = []
    for table in tables:
        table_columns = sorted(
            columns_by_table_id.get(table.id, []),
            key=lambda item: item.ordinal_position,
        )
        foreign_keys = []
        for relationship in relationships_by_source_table_id.get(table.id, []):
            target_table = table_by_id.get(relationship.target_table_id)
            source_column = column_by_id.get(relationship.source_column_id)
            target_column = column_by_id.get(relationship.target_column_id)
            if target_table is None or source_column is None or target_column is None:
                continue
            foreign_keys.append(
                {
                    "columns": [source_column.column_name],
                    "referred_table": target_table.table_name,
                    "referred_columns": [target_column.column_name],
                }
            )
        table_payloads.append(
            {
                "id": table.id,
                "name": table.table_name,
                "comment": table.table_comment,
                "columns": [
                    {
                        "name": column.column_name,
                        "type": column.data_type,
                        "comment": column.column_comment,
                        "nullable": column.is_nullable,
                        "primary_key": column.is_primary_key,
                        "semantic_type": column.semantic_type,
                    }
                    for column in table_columns
                ],
                "foreign_keys": foreign_keys,
                "synced_at": table.synced_at.isoformat() if table.synced_at else None,
                "sync_version": table.sync_version,
            }
        )
    return {"tables": table_payloads, "table_count": len(table_payloads)}


def _data_source_payload(data_source: DataSource) -> dict[str, Any]:
    return {
        "id": data_source.id,
        "name": data_source.name,
        "db_type": data_source.db_type,
        "host": data_source.host,
        "port": data_source.port,
        "database_name": data_source.database_name,
        "status": data_source.status,
    }


def _infer_semantic_type(column_name: str, data_type: str) -> str | None:
    """给字段打一个轻量语义标签，方便后续搜索和推荐。"""

    name = column_name.lower()
    normalized_type = data_type.lower()
    if name.endswith("_id") or name == "id":
        return "identifier"
    if "date" in name or "time" in name:
        return "time"
    if any(keyword in name for keyword in ("amount", "price", "cost", "gmv", "sales")):
        return "measure"
    if any(keyword in name for keyword in ("quantity", "count", "num")):
        return "measure"
    if any(keyword in name for keyword in ("name", "category", "region", "status", "type")):
        return "dimension"
    if any(keyword in normalized_type for keyword in ("int", "decimal", "float", "double")):
        return "numeric"
    return None
