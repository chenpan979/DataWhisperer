from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.product_models import (
    AnalysisRun,
    AuditLog,
    ChatMessage,
    Conversation,
    DataSource,
    DataSourceCredential,
    Tenant,
    TenantMembership,
    User,
    Workspace,
    WorkspaceMembership,
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
