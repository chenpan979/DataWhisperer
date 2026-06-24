from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.product_database import ProductBase


# MySQL 使用 BIGINT UNSIGNED，SQLite 测试环境使用 INTEGER 才能稳定自增。
ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
MESSAGE_CONTENT_TYPE = Text().with_variant(mysql.LONGTEXT, "mysql")
AVATAR_CONTENT_TYPE = Text().with_variant(mysql.LONGTEXT, "mysql")


class TimestampMixin:
    """通用创建/更新时间字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Tenant(ProductBase, TimestampMixin):
    """租户/组织。

    多租户产品里，租户代表一个公司、团队或独立数据空间。
    之后所有工作空间、数据源、会话和审计记录都要挂在租户下面。
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("tenant_key", name="uk_tenants_tenant_key"),
        Index("idx_tenants_status", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class User(ProductBase, TimestampMixin):
    """平台用户账号。

    注意这里只存 `password_hash`，真实产品不能保存明文密码。
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uk_users_email"),
        Index("idx_users_status", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(AVATAR_CONTENT_TYPE, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant_memberships: Mapped[list[TenantMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    workspace_memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")
    preferences: Mapped[list[UserPreference]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserPreference(ProductBase, TimestampMixin):
    """用户在某个租户下的工作台偏好。

    这张表按 `tenant_id + user_id` 做唯一约束，是为了给后续多租户预留空间：
    同一个账号加入不同公司时，可以拥有不同的默认页面、语言和展示角色。
    """

    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uk_user_preferences_tenant_user"),
        Index("idx_user_preferences_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_title: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    default_view: Mapped[str] = mapped_column(String(64), nullable=False, default="analysisView")

    user: Mapped[User] = relationship(back_populates="preferences")


class TenantMembership(ProductBase):
    """用户和租户之间的成员关系。"""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uk_tenant_memberships_member"),
        Index("idx_tenant_memberships_user", "user_id"),
        Index("idx_tenant_memberships_role", "tenant_id", "role"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="tenant_memberships")


class Workspace(ProductBase, TimestampMixin):
    """工作空间。

    一个租户可以有多个工作空间。后续数据源、AI 查数会话、RAG 知识库和评测任务
    都会按工作空间隔离。
    """

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_key", name="uk_workspaces_tenant_key"),
        Index("idx_workspaces_tenant_status", "tenant_id", "status"),
        Index("idx_workspaces_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    default_data_source_id: Mapped[int | None] = mapped_column(ID_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="workspaces")
    memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    data_sources: Mapped[list[DataSource]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    model_providers: Mapped[list[ModelProvider]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    security_policy: Mapped[WorkspaceSecurityPolicy | None] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )
    knowledge_bases: Mapped[list[KnowledgeBase]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list[Conversation]] = relationship(back_populates="workspace")


class WorkspaceSecurityPolicy(ProductBase, TimestampMixin):
    """Workspace-level SQL safety and audit policy."""

    __tablename__ = "workspace_security_policies"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uk_workspace_security_policies_workspace"),
        Index("idx_workspace_security_policies_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    readonly_sql_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_limit_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    query_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    audit_trace_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sensitive_config_managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workspace: Mapped[Workspace] = relationship(back_populates="security_policy")


class WorkspaceMembership(ProductBase):
    """用户和工作空间之间的成员关系。"""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uk_workspace_memberships_member"),
        Index("idx_workspace_memberships_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="workspace_memberships")


class DataSource(ProductBase, TimestampMixin):
    """业务数据源连接信息。

    这里保存主机、端口、库名和用户名。密码等敏感字段放在
    `data_source_credentials`，后续接真实系统时要做服务端加密。
    """

    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uk_data_sources_workspace_name"),
        Index("idx_data_sources_tenant", "tenant_id"),
        Index("idx_data_sources_workspace_status", "workspace_id", "status"),
        Index("idx_data_sources_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mysql")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="data_sources")
    credential: Mapped[DataSourceCredential | None] = relationship(
        back_populates="data_source",
        cascade="all, delete-orphan",
        uselist=False,
    )
    schema_tables: Mapped[list[SchemaTable]] = relationship(back_populates="data_source")
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(back_populates="data_source")


class DataSourceCredential(ProductBase, TimestampMixin):
    """数据源密钥。"""

    __tablename__ = "data_source_credentials"
    __table_args__ = (
        UniqueConstraint("data_source_id", name="uk_data_source_credentials_source"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="local-demo",
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    data_source: Mapped[DataSource] = relationship(back_populates="credential")


class ModelProvider(ProductBase, TimestampMixin):
    """模型供应商配置。

    供应商负责描述一个 OpenAI-compatible 网关，例如 DashScope、OpenAI、
    DeepSeek 或公司内部模型服务。API Key 单独放在 `model_credentials`，
    便于后续接入 KMS、Vault 或租户级密钥托管。
    """

    __tablename__ = "model_providers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uk_model_providers_workspace_name"),
        Index("idx_model_providers_tenant", "tenant_id"),
        Index("idx_model_providers_workspace_status", "workspace_id", "status"),
        Index("idx_model_providers_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dashscope")
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="configured")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="model_providers")
    credential: Mapped[ModelCredential | None] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
        uselist=False,
    )
    profiles: Mapped[list[ModelProfile]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
    )


class ModelCredential(ProductBase, TimestampMixin):
    """模型供应商密钥。"""

    __tablename__ = "model_credentials"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uk_model_credentials_provider"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("model_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_mask: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encryption_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="local-demo",
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    provider: Mapped[ModelProvider] = relationship(back_populates="credential")


class ModelProfile(ProductBase, TimestampMixin):
    """模型调用 Profile。

    Profile 描述一次模型调用需要的模型名、温度、最大 token 等参数。
    后续多 Agent 不直接绑供应商，而是绑 Profile，这样可以做到多个 Agent
    共用一个模型，也可以让每个 Agent 独立使用不同模型。
    """

    __tablename__ = "model_profiles"
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uk_model_profiles_provider_name"),
        Index("idx_model_profiles_workspace_default", "workspace_id", "is_default"),
        Index("idx_model_profiles_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("model_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    chat_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.100"))
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    provider: Mapped[ModelProvider] = relationship(back_populates="profiles")
    agent_bindings: Mapped[list[AgentModelBinding]] = relationship(back_populates="profile")


class AgentModelBinding(ProductBase, TimestampMixin):
    """Agent 与模型 Profile 的绑定关系。

    首版先记录 SQL 生成、分析总结、图表推荐、RAG Embedding 等能力使用哪个
    Profile。后面如果升级成多智能体编排，这张表可以直接扩展为每个 Agent
    独立配置模型、参数和开关。
    """

    __tablename__ = "agent_model_bindings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "agent_key",
            "capability",
            name="uk_agent_model_bindings_workspace_agent_capability",
        ),
        Index("idx_agent_model_bindings_profile", "model_profile_id"),
        Index("idx_agent_model_bindings_tenant_workspace", "tenant_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    model_profile_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("model_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    profile: Mapped[ModelProfile] = relationship(back_populates="agent_bindings")


class SchemaTable(ProductBase, TimestampMixin):
    """同步后的数据库表元信息。"""

    __tablename__ = "schema_tables"
    __table_args__ = (
        UniqueConstraint("data_source_id", "table_name", name="uk_schema_tables_source_name"),
        Index("idx_schema_tables_tenant_workspace", "tenant_id", "workspace_id"),
        Index("idx_schema_tables_type", "data_source_id", "table_type"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_source_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_comment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    table_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    row_count_estimate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sync_version: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    data_source: Mapped[DataSource] = relationship(back_populates="schema_tables")
    columns: Mapped[list[SchemaColumn]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
    )


class SchemaColumn(ProductBase, TimestampMixin):
    """同步后的字段元信息。"""

    __tablename__ = "schema_columns"
    __table_args__ = (
        UniqueConstraint("table_id", "column_name", name="uk_schema_columns_table_name"),
        Index("idx_schema_columns_source", "data_source_id"),
        Index("idx_schema_columns_semantic", "data_source_id", "semantic_type"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_source_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("schema_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    column_comment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    table: Mapped[SchemaTable] = relationship(back_populates="columns")


class SchemaRelationship(ProductBase):
    """表关系元信息。

    3D 关系图谱连线、SQL JOIN 推荐和后续 RAG schema 检索都可以复用这里。
    """

    __tablename__ = "schema_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_column_id",
            "target_column_id",
            name="uk_schema_relationships_columns",
        ),
        Index("idx_schema_relationships_source_table", "source_table_id"),
        Index("idx_schema_relationships_target_table", "target_table_id"),
        Index("idx_schema_relationships_workspace", "tenant_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_source_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_table_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("schema_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_column_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("schema_columns.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_table_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("schema_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_column_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("schema_columns.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="many_to_one")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="database_fk")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )


class KnowledgeBase(ProductBase, TimestampMixin):
    """租户/工作空间级知识库。"""

    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uk_knowledge_bases_workspace_name"),
        Index("idx_knowledge_bases_tenant_workspace", "tenant_id", "workspace_id"),
        Index("idx_knowledge_bases_workspace_default", "workspace_id", "is_default"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="knowledge_bases")
    documents: Mapped[list[KnowledgeDocument]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )


class KnowledgeDocument(ProductBase, TimestampMixin):
    """知识库中的一个上传文档。"""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "file_id", name="uk_knowledge_documents_workspace_file"),
        Index("idx_knowledge_documents_base", "knowledge_base_id", "created_at"),
        Index("idx_knowledge_documents_sync", "workspace_id", "sync_status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previewable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sync_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sync_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(ProductBase):
    """知识文档切片元数据。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uk_knowledge_chunks_document_index"),
        UniqueConstraint("chunk_id", name="uk_knowledge_chunks_chunk_id"),
        Index("idx_knowledge_chunks_base", "knowledge_base_id", "chunk_index"),
        Index("idx_knowledge_chunks_workspace", "tenant_id", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_collection: Mapped[str] = mapped_column(String(128), nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class Conversation(ProductBase, TimestampMixin):
    """AI 查数会话。"""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conversations_workspace_updated", "workspace_id", "updated_at"),
        Index("idx_conversations_user_updated", "user_id", "updated_at"),
        Index("idx_conversations_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    workspace: Mapped[Workspace] = relationship(back_populates="conversations")
    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ChatMessage(ProductBase):
    """会话消息。"""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_conversation", "conversation_id", "id"),
        Index("idx_chat_messages_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(MESSAGE_CONTENT_TYPE, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AnalysisRun(ProductBase):
    """一次自然语言查数运行快照。"""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uk_analysis_runs_trace_id"),
        Index("idx_analysis_runs_conversation", "conversation_id", "created_at"),
        Index("idx_analysis_runs_workspace", "workspace_id", "created_at"),
        Index("idx_analysis_runs_data_source", "data_source_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_columns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    result_rows_preview: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    chart_option: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    insight: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    prompt_versions: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="analysis_runs")
    data_source: Mapped[DataSource | None] = relationship(back_populates="analysis_runs")


class AuditLog(ProductBase):
    """审计日志。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_logs_tenant_time", "tenant_id", "created_at"),
        Index("idx_audit_logs_workspace_time", "workspace_id", "created_at"),
        Index("idx_audit_logs_user_time", "user_id", "created_at"),
        Index("idx_audit_logs_action", "action"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
