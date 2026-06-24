from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db.product_models import (
    AgentModelBinding,
    AnalysisRun,
    AuditLog,
    ChatMessage,
    Conversation,
    DataSource,
    DataSourceCredential,
    ModelCredential,
    ModelProfile,
    ModelProvider,
    SchemaColumn,
    SchemaRelationship,
    SchemaTable,
    Tenant,
    TenantMembership,
    User,
    UserPreference,
    Workspace,
    WorkspaceMembership,
    WorkspaceSecurityPolicy,
)


class TenantRepository:
    """租户仓储。

    后续注册流程会先创建租户，再创建用户和默认工作空间。
    """

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, tenant_id: int) -> Tenant | None:
        """按主键读取租户。"""

        return self.session.get(Tenant, tenant_id)

    def get_by_key(self, tenant_key: str) -> Tenant | None:
        """按租户标识读取租户。"""

        statement = select(Tenant).where(Tenant.tenant_key == tenant_key)
        return self.session.scalar(statement)

    def create(
        self,
        *,
        tenant_key: str,
        name: str,
        plan: str = "free",
        status: str = "active",
    ) -> Tenant:
        """创建租户，并 flush 出数据库主键。"""

        tenant = Tenant(tenant_key=tenant_key, name=name, plan=plan, status=status)
        self.session.add(tenant)
        self.session.flush()
        return tenant

    def add_member(
        self,
        *,
        tenant_id: int,
        user_id: int,
        role: str = "viewer",
        status: str = "active",
    ) -> TenantMembership:
        """把用户加入租户；如果已存在则更新角色。"""

        statement = select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
        membership = self.session.scalar(statement)
        if membership is None:
            membership = TenantMembership(
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                status=status,
            )
            self.session.add(membership)
        else:
            membership.role = role
            membership.status = status
        self.session.flush()
        return membership


class UserRepository:
    """用户仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        """按主键读取用户。"""

        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """按邮箱读取用户。"""

        statement = select(User).where(User.email == email)
        return self.session.scalar(statement)

    def get_by_account_in_tenant(
        self,
        *,
        tenant_key: str,
        account: str,
    ) -> tuple[User, Tenant, TenantMembership] | None:
        """在指定租户下按账号查找用户。

        登录页允许用户输入邮箱，也允许 demo 环境输入 `admin` 这类显示名。
        查询时必须带租户条件，避免未来多租户场景下跨租户误登录。
        """

        normalized_account = account.strip()
        statement = (
            select(User, Tenant, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(
                Tenant.tenant_key == tenant_key,
                Tenant.status == "active",
                TenantMembership.status == "active",
                User.status == "active",
                or_(
                    User.email == normalized_account,
                    User.display_name == normalized_account,
                ),
            )
        )
        row = self.session.execute(statement).first()
        if row is None:
            return None
        user, tenant, membership = row
        return user, tenant, membership

    def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        avatar_url: str | None = None,
        status: str = "active",
    ) -> User:
        """创建用户账号。"""

        user = User(
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            password_hash=password_hash,
            status=status,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def update_profile(
        self,
        user: User,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """更新用户展示信息。"""

        if display_name is not None:
            user.display_name = display_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        self.session.flush()
        return user

    def mark_login(self, user: User, *, login_at: datetime | None = None) -> User:
        """记录最近登录时间。"""

        user.last_login_at = login_at or datetime.now()
        self.session.flush()
        return user


class AccountPreferenceRepository:
    """账号偏好仓储。

    偏好按租户保存，方便同一个用户未来加入多个租户时拥有不同工作台体验。
    """

    def __init__(self, session: Session):
        self.session = session

    def get_for_user(self, *, tenant_id: int, user_id: int) -> UserPreference | None:
        """读取用户在指定租户下的偏好。"""

        statement = select(UserPreference).where(
            UserPreference.tenant_id == tenant_id,
            UserPreference.user_id == user_id,
        )
        return self.session.scalar(statement)

    def ensure_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        role_title: str | None = None,
        language: str = "zh-CN",
        default_view: str = "analysisView",
    ) -> UserPreference:
        """确保用户至少有一条偏好记录。"""

        preference = self.get_for_user(tenant_id=tenant_id, user_id=user_id)
        if preference is not None:
            return preference
        preference = UserPreference(
            tenant_id=tenant_id,
            user_id=user_id,
            role_title=role_title,
            language=language,
            default_view=default_view,
        )
        self.session.add(preference)
        self.session.flush()
        return preference

    def update(
        self,
        preference: UserPreference,
        *,
        role_title: str | None = None,
        language: str | None = None,
        default_view: str | None = None,
    ) -> UserPreference:
        """更新账号偏好。"""

        if role_title is not None:
            preference.role_title = role_title
        if language is not None:
            preference.language = language
        if default_view is not None:
            preference.default_view = default_view
        self.session.flush()
        return preference


class WorkspaceRepository:
    """工作空间仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, workspace_id: int) -> Workspace | None:
        """按主键读取工作空间。"""

        return self.session.get(Workspace, workspace_id)

    def get_by_key(self, *, tenant_id: int, workspace_key: str) -> Workspace | None:
        """按租户和工作空间标识读取工作空间。"""

        statement = select(Workspace).where(
            Workspace.tenant_id == tenant_id,
            Workspace.workspace_key == workspace_key,
        )
        return self.session.scalar(statement)

    def create(
        self,
        *,
        tenant_id: int,
        workspace_key: str,
        name: str,
        description: str | None = None,
        created_by: int | None = None,
        status: str = "active",
    ) -> Workspace:
        """创建工作空间。"""

        workspace = Workspace(
            tenant_id=tenant_id,
            workspace_key=workspace_key,
            name=name,
            description=description,
            created_by=created_by,
            status=status,
        )
        self.session.add(workspace)
        self.session.flush()
        return workspace

    def add_member(
        self,
        *,
        workspace_id: int,
        user_id: int,
        role: str = "viewer",
    ) -> WorkspaceMembership:
        """把用户加入工作空间；如果已存在则更新角色。"""

        statement = select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        membership = self.session.scalar(statement)
        if membership is None:
            membership = WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
            self.session.add(membership)
        else:
            membership.role = role
        self.session.flush()
        return membership

    def list_for_user(self, *, user_id: int, tenant_id: int | None = None) -> list[Workspace]:
        """列出用户可访问的工作空间。"""

        statement = (
            select(Workspace)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                WorkspaceMembership.user_id == user_id,
                Workspace.status == "active",
            )
            .order_by(Workspace.updated_at.desc())
        )
        if tenant_id is not None:
            statement = statement.where(Workspace.tenant_id == tenant_id)
        return list(self.session.scalars(statement).all())

    def get_default_for_user(self, *, tenant_id: int, user_id: int) -> Workspace | None:
        """读取用户在租户下的默认工作空间。

        目前注册流程会创建 `default` 工作空间；如果后续一个用户有多个工作空间，
        可以在这里接用户偏好或最近访问记录。
        """

        default_statement = (
            select(Workspace)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                Workspace.tenant_id == tenant_id,
                Workspace.workspace_key == "default",
                Workspace.status == "active",
                WorkspaceMembership.user_id == user_id,
            )
        )
        workspace = self.session.scalar(default_statement)
        if workspace is not None:
            return workspace
        workspaces = self.list_for_user(user_id=user_id, tenant_id=tenant_id)
        return workspaces[0] if workspaces else None

    def set_default_data_source(self, workspace: Workspace, data_source_id: int) -> Workspace:
        """设置工作空间默认数据源。"""

        workspace.default_data_source_id = data_source_id
        self.session.flush()
        return workspace


class DataSourceRepository:
    """数据源仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, data_source_id: int) -> DataSource | None:
        """按主键读取数据源。"""

        return self.session.get(DataSource, data_source_id)

    def get_credential(self, *, data_source_id: int) -> DataSourceCredential | None:
        """读取数据源凭据，后续可以在这里替换成 KMS 或 Vault。"""

        statement = select(DataSourceCredential).where(
            DataSourceCredential.data_source_id == data_source_id
        )
        return self.session.scalar(statement)

    def list_by_workspace(self, *, workspace_id: int) -> list[DataSource]:
        """列出工作空间下的可用数据源。"""

        statement = (
            select(DataSource)
            .where(DataSource.workspace_id == workspace_id)
            .order_by(DataSource.created_at.desc())
        )
        return list(self.session.scalars(statement).all())

    def get_default_for_workspace(self, workspace: Workspace) -> DataSource | None:
        """读取工作空间默认数据源。

        如果默认数据源字段还没有设置，则退回到第一个 connected 数据源。
        """

        if workspace.default_data_source_id:
            data_source = self.session.get(DataSource, workspace.default_data_source_id)
            if data_source is not None:
                return data_source
        statement = (
            select(DataSource)
            .where(
                DataSource.workspace_id == workspace.id,
                DataSource.status == "connected",
            )
            .order_by(DataSource.created_at.asc())
        )
        return self.session.scalar(statement)

    def create(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        name: str,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        status: str = "connected",
        created_by: int | None = None,
        last_checked_at: datetime | None = None,
    ) -> DataSource:
        """创建业务数据源连接信息。"""

        data_source = DataSource(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            db_type=db_type,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            status=status,
            created_by=created_by,
            last_checked_at=last_checked_at,
        )
        self.session.add(data_source)
        self.session.flush()
        return data_source

    def update(
        self,
        data_source: DataSource,
        *,
        name: str | None = None,
        db_type: str | None = None,
        host: str | None = None,
        port: int | None = None,
        database_name: str | None = None,
        username: str | None = None,
        status: str | None = None,
        last_checked_at: datetime | None = None,
    ) -> DataSource:
        """更新数据源基础连接信息。"""

        if name is not None:
            data_source.name = name
        if db_type is not None:
            data_source.db_type = db_type
        if host is not None:
            data_source.host = host
        if port is not None:
            data_source.port = port
        if database_name is not None:
            data_source.database_name = database_name
        if username is not None:
            data_source.username = username
        if status is not None:
            data_source.status = status
        if last_checked_at is not None:
            data_source.last_checked_at = last_checked_at
        self.session.flush()
        return data_source

    def save_credential(
        self,
        *,
        data_source_id: int,
        encrypted_password: str,
        encryption_version: str = "local-demo",
    ) -> DataSourceCredential:
        """保存或更新数据源密钥。"""

        statement = select(DataSourceCredential).where(
            DataSourceCredential.data_source_id == data_source_id
        )
        credential = self.session.scalar(statement)
        if credential is None:
            credential = DataSourceCredential(
                data_source_id=data_source_id,
                encrypted_password=encrypted_password,
                encryption_version=encryption_version,
                rotated_at=datetime.now(),
            )
            self.session.add(credential)
        else:
            credential.encrypted_password = encrypted_password
            credential.encryption_version = encryption_version
            credential.rotated_at = datetime.now()
        self.session.flush()
        return credential


class ModelSettingsRepository:
    """模型配置仓储。

    这里按“供应商 -> Profile -> Agent 绑定”三层组织，避免后续多 Agent
    改造时把模型配置写死在某一个单体服务里。
    """

    def __init__(self, session: Session):
        self.session = session

    def list_providers(self, *, workspace_id: int) -> list[ModelProvider]:
        """列出工作空间下的模型供应商。"""

        statement = (
            select(ModelProvider)
            .where(ModelProvider.workspace_id == workspace_id)
            .order_by(ModelProvider.created_at.asc())
        )
        return list(self.session.scalars(statement).all())

    def get_default_provider(self, *, workspace_id: int) -> ModelProvider | None:
        """读取默认模型供应商。

        当前版本一个工作空间先只暴露一个默认供应商；后续多模型路由时可以增加
        `is_default` 或按 Agent 绑定反查。
        """

        statement = (
            select(ModelProvider)
            .where(ModelProvider.workspace_id == workspace_id)
            .order_by(ModelProvider.created_at.asc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def create_provider(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        name: str,
        provider_type: str,
        base_url: str,
        status: str = "configured",
        created_by: int | None = None,
        last_checked_at: datetime | None = None,
    ) -> ModelProvider:
        """创建模型供应商。"""

        provider = ModelProvider(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            provider_type=provider_type,
            base_url=base_url,
            status=status,
            created_by=created_by,
            last_checked_at=last_checked_at,
        )
        self.session.add(provider)
        self.session.flush()
        return provider

    def update_provider(
        self,
        provider: ModelProvider,
        *,
        name: str | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        status: str | None = None,
        last_checked_at: datetime | None = None,
    ) -> ModelProvider:
        """更新模型供应商基础信息。"""

        if name is not None:
            provider.name = name
        if provider_type is not None:
            provider.provider_type = provider_type
        if base_url is not None:
            provider.base_url = base_url
        if status is not None:
            provider.status = status
        if last_checked_at is not None:
            provider.last_checked_at = last_checked_at
        self.session.flush()
        return provider

    def save_credential(
        self,
        *,
        provider_id: int,
        encrypted_api_key: str,
        key_mask: str | None,
        encryption_version: str = "local-demo",
    ) -> ModelCredential:
        """保存或更新模型 API Key。

        当前演示版仍用本地可逆占位编码；真实产品应替换为 KMS/Vault。
        """

        statement = select(ModelCredential).where(ModelCredential.provider_id == provider_id)
        credential = self.session.scalar(statement)
        if credential is None:
            credential = ModelCredential(
                provider_id=provider_id,
                encrypted_api_key=encrypted_api_key,
                key_mask=key_mask,
                encryption_version=encryption_version,
                rotated_at=datetime.now(),
            )
            self.session.add(credential)
        else:
            credential.encrypted_api_key = encrypted_api_key
            credential.key_mask = key_mask
            credential.encryption_version = encryption_version
            credential.rotated_at = datetime.now()
        self.session.flush()
        return credential

    def get_default_profile(self, *, workspace_id: int) -> ModelProfile | None:
        """读取工作空间默认模型 Profile。"""

        default_statement = (
            select(ModelProfile)
            .where(
                ModelProfile.workspace_id == workspace_id,
                ModelProfile.is_default.is_(True),
            )
            .order_by(ModelProfile.created_at.asc())
            .limit(1)
        )
        profile = self.session.scalar(default_statement)
        if profile is not None:
            return profile
        fallback_statement = (
            select(ModelProfile)
            .where(ModelProfile.workspace_id == workspace_id)
            .order_by(ModelProfile.created_at.asc())
            .limit(1)
        )
        return self.session.scalar(fallback_statement)

    def create_profile(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        provider_id: int,
        name: str,
        chat_model: str,
        embedding_model: str | None,
        temperature: float,
        max_tokens: int,
        is_default: bool = True,
        status: str = "active",
        config_json: dict[str, Any] | None = None,
    ) -> ModelProfile:
        """创建模型调用 Profile。"""

        profile = ModelProfile(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            provider_id=provider_id,
            name=name,
            chat_model=chat_model,
            embedding_model=embedding_model,
            temperature=temperature,
            max_tokens=max_tokens,
            is_default=is_default,
            status=status,
            config_json=config_json or {},
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def update_profile(
        self,
        profile: ModelProfile,
        *,
        name: str | None = None,
        chat_model: str | None = None,
        embedding_model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        is_default: bool | None = None,
        status: str | None = None,
        config_json: dict[str, Any] | None = None,
    ) -> ModelProfile:
        """更新模型调用 Profile。"""

        if name is not None:
            profile.name = name
        if chat_model is not None:
            profile.chat_model = chat_model
        if embedding_model is not None:
            profile.embedding_model = embedding_model
        if temperature is not None:
            profile.temperature = temperature
        if max_tokens is not None:
            profile.max_tokens = max_tokens
        if is_default is not None:
            profile.is_default = is_default
        if status is not None:
            profile.status = status
        if config_json is not None:
            profile.config_json = config_json
        self.session.flush()
        return profile

    def list_bindings(self, *, workspace_id: int) -> list[AgentModelBinding]:
        """列出工作空间下的 Agent 模型绑定。"""

        statement = (
            select(AgentModelBinding)
            .where(AgentModelBinding.workspace_id == workspace_id)
            .order_by(AgentModelBinding.agent_key.asc(), AgentModelBinding.capability.asc())
        )
        return list(self.session.scalars(statement).all())

    def upsert_binding(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        agent_key: str,
        capability: str,
        model_profile_id: int,
        enabled: bool = True,
        params_json: dict[str, Any] | None = None,
    ) -> AgentModelBinding:
        """创建或更新 Agent 模型绑定。"""

        statement = select(AgentModelBinding).where(
            AgentModelBinding.workspace_id == workspace_id,
            AgentModelBinding.agent_key == agent_key,
            AgentModelBinding.capability == capability,
        )
        binding = self.session.scalar(statement)
        if binding is None:
            binding = AgentModelBinding(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                agent_key=agent_key,
                capability=capability,
                model_profile_id=model_profile_id,
                enabled=enabled,
                params_json=params_json or {},
            )
            self.session.add(binding)
        else:
            binding.model_profile_id = model_profile_id
            binding.enabled = enabled
            binding.params_json = params_json or {}
        self.session.flush()
        return binding


class SecurityPolicyRepository:
    """Repository for workspace-level security policy."""

    def __init__(self, session: Session):
        self.session = session

    def get_for_workspace(self, *, workspace_id: int) -> WorkspaceSecurityPolicy | None:
        """Read one workspace security policy."""

        statement = select(WorkspaceSecurityPolicy).where(
            WorkspaceSecurityPolicy.workspace_id == workspace_id
        )
        return self.session.scalar(statement)

    def create_default(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        default_limit: int = 100,
        max_limit: int = 1000,
        query_timeout_seconds: int = 20,
    ) -> WorkspaceSecurityPolicy:
        """Create the default policy for a workspace."""

        policy = WorkspaceSecurityPolicy(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            readonly_sql_enabled=True,
            auto_limit_enabled=True,
            default_limit=default_limit,
            max_limit=max_limit,
            query_timeout_seconds=query_timeout_seconds,
            audit_trace_enabled=True,
            sensitive_config_managed=True,
        )
        self.session.add(policy)
        self.session.flush()
        return policy

    def ensure_for_workspace(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        default_limit: int = 100,
        max_limit: int = 1000,
        query_timeout_seconds: int = 20,
    ) -> WorkspaceSecurityPolicy:
        """Ensure the workspace has a persisted security policy."""

        policy = self.get_for_workspace(workspace_id=workspace_id)
        if policy is not None:
            return policy
        return self.create_default(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            default_limit=default_limit,
            max_limit=max_limit,
            query_timeout_seconds=query_timeout_seconds,
        )

    def update(
        self,
        policy: WorkspaceSecurityPolicy,
        *,
        readonly_sql_enabled: bool | None = None,
        auto_limit_enabled: bool | None = None,
        default_limit: int | None = None,
        max_limit: int | None = None,
        query_timeout_seconds: int | None = None,
        audit_trace_enabled: bool | None = None,
        sensitive_config_managed: bool | None = None,
    ) -> WorkspaceSecurityPolicy:
        """Update security policy settings."""

        if readonly_sql_enabled is not None:
            policy.readonly_sql_enabled = readonly_sql_enabled
        if auto_limit_enabled is not None:
            policy.auto_limit_enabled = auto_limit_enabled
        if default_limit is not None:
            policy.default_limit = default_limit
        if max_limit is not None:
            policy.max_limit = max_limit
        if query_timeout_seconds is not None:
            policy.query_timeout_seconds = query_timeout_seconds
        if audit_trace_enabled is not None:
            policy.audit_trace_enabled = audit_trace_enabled
        if sensitive_config_managed is not None:
            policy.sensitive_config_managed = sensitive_config_managed
        self.session.flush()
        return policy


class SchemaRepository:
    """数据源 Schema 快照仓储。

    这里保存的是“某个时间点同步到产品库里的表结构快照”。
    后续 3D 图谱、SQL 生成上下文、RAG schema 检索都应该优先读这里，
    而不是每次都实时扫描业务数据库。
    """

    def __init__(self, session: Session):
        self.session = session

    def clear_for_data_source(self, data_source_id: int) -> None:
        """清空某个数据源旧的 schema 快照。"""

        self.session.execute(
            delete(SchemaRelationship).where(SchemaRelationship.data_source_id == data_source_id)
        )
        self.session.execute(delete(SchemaColumn).where(SchemaColumn.data_source_id == data_source_id))
        self.session.execute(delete(SchemaTable).where(SchemaTable.data_source_id == data_source_id))
        self.session.flush()

    def create_table(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        data_source_id: int,
        table_name: str,
        table_comment: str | None,
        table_type: str,
        sync_version: str,
        synced_at: datetime,
    ) -> SchemaTable:
        """写入一张同步后的数据表。"""

        table = SchemaTable(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            data_source_id=data_source_id,
            table_name=table_name,
            table_comment=table_comment,
            table_type=table_type,
            sync_version=sync_version,
            synced_at=synced_at,
        )
        self.session.add(table)
        self.session.flush()
        return table

    def create_column(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        data_source_id: int,
        table_id: int,
        column_name: str,
        data_type: str,
        column_comment: str | None,
        is_primary_key: bool,
        is_nullable: bool,
        ordinal_position: int,
        semantic_type: str | None,
    ) -> SchemaColumn:
        """写入一列字段元信息。"""

        column = SchemaColumn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            data_source_id=data_source_id,
            table_id=table_id,
            column_name=column_name,
            data_type=data_type,
            column_comment=column_comment,
            is_primary_key=is_primary_key,
            is_nullable=is_nullable,
            ordinal_position=ordinal_position,
            semantic_type=semantic_type,
        )
        self.session.add(column)
        self.session.flush()
        return column

    def create_relationship(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        data_source_id: int,
        source_table_id: int,
        source_column_id: int,
        target_table_id: int,
        target_column_id: int,
        relation_type: str = "many_to_one",
        confidence: float = 1.0,
        source: str = "database_fk",
    ) -> SchemaRelationship:
        """写入一条表关系。"""

        relationship = SchemaRelationship(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            data_source_id=data_source_id,
            source_table_id=source_table_id,
            source_column_id=source_column_id,
            target_table_id=target_table_id,
            target_column_id=target_column_id,
            relation_type=relation_type,
            confidence=confidence,
            source=source,
        )
        self.session.add(relationship)
        self.session.flush()
        return relationship

    def list_tables(self, *, data_source_id: int) -> list[SchemaTable]:
        """读取某个数据源已同步的表。"""

        statement = (
            select(SchemaTable)
            .where(SchemaTable.data_source_id == data_source_id)
            .order_by(SchemaTable.table_name.asc())
        )
        return list(self.session.scalars(statement).all())

    def get_table(self, *, table_id: int, workspace_id: int) -> SchemaTable | None:
        """按表 id 读取，并校验工作空间归属。"""

        statement = select(SchemaTable).where(
            SchemaTable.id == table_id,
            SchemaTable.workspace_id == workspace_id,
        )
        return self.session.scalar(statement)

    def list_columns(self, *, data_source_id: int) -> list[SchemaColumn]:
        """读取某个数据源的全部字段。"""

        statement = (
            select(SchemaColumn)
            .where(SchemaColumn.data_source_id == data_source_id)
            .order_by(SchemaColumn.table_id.asc(), SchemaColumn.ordinal_position.asc())
        )
        return list(self.session.scalars(statement).all())

    def list_relationships(self, *, data_source_id: int) -> list[SchemaRelationship]:
        """读取某个数据源的全部表关系。"""

        statement = select(SchemaRelationship).where(
            SchemaRelationship.data_source_id == data_source_id
        )
        return list(self.session.scalars(statement).all())


class ConversationRepository:
    """AI 查数会话仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        """按主键读取会话。"""

        return self.session.get(Conversation, conversation_id)

    def list_recent(self, *, workspace_id: int, limit: int = 20) -> list[Conversation]:
        """按更新时间倒序列出最近会话。"""

        statement = (
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.status == "active",
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def create(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        user_id: int,
        title: str = "新对话",
        summary: str | None = None,
    ) -> Conversation:
        """创建 AI 查数会话。"""

        conversation = Conversation(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            summary=summary,
            status="active",
        )
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def rename(self, conversation: Conversation, *, title: str) -> Conversation:
        """重命名会话。"""

        conversation.title = title
        self.session.flush()
        return conversation

    def update_metadata(
        self,
        conversation: Conversation,
        *,
        title: str | None = None,
        summary: str | None = None,
    ) -> Conversation:
        """更新会话标题和摘要。"""

        if title is not None:
            conversation.title = title
        if summary is not None:
            conversation.summary = summary
        self.session.flush()
        return conversation

    def archive(self, conversation: Conversation) -> Conversation:
        """软删除会话，保留审计和恢复空间。"""

        conversation.status = "deleted"
        self.session.flush()
        return conversation

    def append_message(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        conversation_id: int,
        role: str,
        content: str,
        content_type: str = "text",
    ) -> ChatMessage:
        """追加一条会话消息。"""

        message = ChatMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            content_type=content_type,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def list_messages(self, *, conversation_id: int) -> list[ChatMessage]:
        """按发送顺序列出会话消息。"""

        statement = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.asc())
        )
        return list(self.session.scalars(statement).all())


class AnalysisRunRepository:
    """AI 查数运行记录仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_trace_id(self, trace_id: str) -> AnalysisRun | None:
        """按 trace_id 查询运行记录。"""

        statement = select(AnalysisRun).where(AnalysisRun.trace_id == trace_id)
        return self.session.scalar(statement)

    def create(
        self,
        *,
        tenant_id: int,
        workspace_id: int,
        conversation_id: int,
        trace_id: str,
        question: str,
        message_id: int | None = None,
        data_source_id: int | None = None,
        generated_sql: str | None = None,
        sql_explanation: str | None = None,
        result_columns: Sequence[str] | None = None,
        result_rows_preview: Sequence[dict[str, Any]] | None = None,
        chart_option: dict[str, Any] | None = None,
        insight: str | None = None,
        trace_steps: Sequence[dict[str, Any]] | None = None,
        warnings: Sequence[str] | None = None,
        prompt_versions: dict[str, str] | None = None,
        status: str = "success",
        duration_ms: int | None = None,
    ) -> AnalysisRun:
        """保存一次完整查数运行快照。"""

        run = AnalysisRun(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            data_source_id=data_source_id,
            trace_id=trace_id,
            question=question,
            generated_sql=generated_sql,
            sql_explanation=sql_explanation,
            result_columns=list(result_columns or []),
            result_rows_preview=list(result_rows_preview or []),
            chart_option=chart_option or {},
            insight=insight,
            trace_steps=list(trace_steps or []),
            warnings=list(warnings or []),
            prompt_versions=prompt_versions or {},
            status=status,
            duration_ms=duration_ms,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def list_for_conversation(self, *, conversation_id: int) -> list[AnalysisRun]:
        """列出一个会话内的所有查数运行记录。"""

        statement = (
            select(AnalysisRun)
            .where(AnalysisRun.conversation_id == conversation_id)
            .order_by(AnalysisRun.created_at.asc())
        )
        return list(self.session.scalars(statement).all())


class AuditLogRepository:
    """审计日志仓储。"""

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        tenant_id: int,
        action: str,
        workspace_id: int | None = None,
        user_id: int | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        """写入一条审计日志。"""

        log = AuditLog(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail or {},
        )
        self.session.add(log)
        self.session.flush()
        return log

    def exists(
        self,
        *,
        tenant_id: int,
        action: str,
        user_id: int | None = None,
    ) -> bool:
        """检查某类审计事件是否已经发生。"""

        statement = select(AuditLog.id).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == action,
        )
        if user_id is not None:
            statement = statement.where(AuditLog.user_id == user_id)
        return self.session.scalar(statement.limit(1)) is not None
