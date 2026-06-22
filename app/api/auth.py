from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.product_database import get_product_session
from app.core.security import (
    create_signed_token,
    hash_password,
    parse_signed_token,
    password_hash_needs_upgrade,
    verify_password,
)
from app.db.product_models import Tenant, TenantMembership, User, Workspace, WorkspaceMembership
from app.models.auth import (
    AuthLoginRequest,
    AuthMeResponse,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthTenant,
    AuthUser,
    AuthWorkspace,
    PasswordResetRequest,
    PasswordResetResponse,
)
from app.repositories.product import (
    AuditLogRepository,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: AuthLoginRequest, session: Session = Depends(get_product_session)):
    """登录数据工作空间。

    V3.13.3 开始，登录不再由前端 localStorage 模拟，而是读取
    `datawhisperer_product` 里的租户、用户和工作空间。
    """

    tenant_key = _normalize_tenant_key(payload.tenant_key)
    account = payload.account.strip()
    user_repo = UserRepository(session)
    workspace_repo = WorkspaceRepository(session)

    auth_record = user_repo.get_by_account_in_tenant(tenant_key=tenant_key, account=account)
    if auth_record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确。")

    user, tenant, membership = auth_record
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确。")

    workspace = workspace_repo.get_default_for_user(tenant_id=tenant.id, user_id=user.id)
    if workspace is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="当前账号还没有可用工作空间。")

    if password_hash_needs_upgrade(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user_repo.mark_login(user)
    AuditLogRepository(session).record(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        user_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=str(user.id),
    )
    session.commit()
    return _build_session_response(user=user, tenant=tenant, membership=membership, workspace=workspace)


@router.post("/register", response_model=AuthSessionResponse)
def register(payload: AuthRegisterRequest, session: Session = Depends(get_product_session)):
    """注册租户空间并创建管理员账号。"""

    tenant_key = _normalize_tenant_key(payload.tenant_key)
    email = payload.email.strip().lower()
    display_name = payload.display_name.strip()
    tenant_name = payload.tenant_name.strip()

    _validate_tenant_key(tenant_key)
    _validate_email(email)

    tenant_repo = TenantRepository(session)
    user_repo = UserRepository(session)
    workspace_repo = WorkspaceRepository(session)

    if tenant_repo.get_by_key(tenant_key) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="租户标识已存在，请换一个。")
    if user_repo.get_by_email(email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该邮箱已经注册。")

    tenant = tenant_repo.create(tenant_key=tenant_key, name=tenant_name, plan="team")
    user = user_repo.create(
        email=email,
        display_name=display_name,
        password_hash=hash_password(payload.password),
    )
    membership = tenant_repo.add_member(
        tenant_id=tenant.id,
        user_id=user.id,
        role="owner",
    )
    workspace = workspace_repo.create(
        tenant_id=tenant.id,
        workspace_key="default",
        name="默认工作空间",
        description=f"{tenant_name} 的默认数据分析空间",
        created_by=user.id,
    )
    workspace_repo.add_member(workspace_id=workspace.id, user_id=user.id, role="admin")
    AuditLogRepository(session).record(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        user_id=user.id,
        action="auth.register",
        target_type="tenant",
        target_id=str(tenant.id),
    )
    session.commit()
    return _build_session_response(user=user, tenant=tenant, membership=membership, workspace=workspace)


@router.post("/logout")
def logout() -> dict[str, bool]:
    """退出登录。

    当前 token 是无状态签名令牌，服务端不需要删除 session。
    后续如果增加 session 表或 refresh token，这里可以改成服务端吊销。
    """

    return {"ok": True}


@router.post("/password-reset", response_model=PasswordResetResponse)
def request_password_reset(
    payload: PasswordResetRequest,
    session: Session = Depends(get_product_session),
) -> PasswordResetResponse:
    """提交找回密码请求。

    V3.13.3 先落一个前后端闭环，不真正发送邮件，避免引入邮件服务配置。
    """

    tenant_key = _normalize_tenant_key(payload.tenant_key)
    email = payload.email.strip().lower()
    _validate_email(email)

    tenant = TenantRepository(session).get_by_key(tenant_key)
    if tenant is not None:
        AuditLogRepository(session).record(
            tenant_id=tenant.id,
            action="auth.password_reset.requested",
            target_type="email",
            target_id=email,
        )
        session.commit()

    return PasswordResetResponse(
        accepted=True,
        message="如果该账号存在，系统会发送重置指引。当前演示版本先记录请求，不发送邮件。",
    )


class AuthContext:
    """当前认证上下文。"""

    def __init__(
        self,
        *,
        user: User,
        tenant: Tenant,
        membership: TenantMembership,
        workspace: Workspace,
    ):
        self.user = user
        self.tenant = tenant
        self.membership = membership
        self.workspace = workspace


def _require_auth_context(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> AuthContext:
    """解析 Authorization 头并回查数据库。"""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = parse_signed_token(token, secret=settings.auth_token_secret)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = session.get(User, int(payload.get("sub", 0)))
    tenant = session.get(Tenant, int(payload.get("tenant_id", 0)))
    workspace = session.get(Workspace, int(payload.get("workspace_id", 0)))
    if user is None or tenant is None or workspace is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录。")

    membership = (
        session.query(TenantMembership)
        .filter(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
            TenantMembership.status == "active",
        )
        .first()
    )
    workspace_membership = (
        session.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
        .first()
    )
    if membership is None or workspace_membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="当前账号没有访问该工作空间的权限。")
    return AuthContext(user=user, tenant=tenant, membership=membership, workspace=workspace)


@router.get("/me", response_model=AuthMeResponse)
def get_current_user(
    auth_context: Annotated[AuthContext, Depends(_require_auth_context)],
):
    """返回当前登录用户、租户和工作空间。"""

    return AuthMeResponse(
        user=_build_auth_user(auth_context.user, auth_context.membership.role),
        tenant=_build_auth_tenant(auth_context.tenant),
        workspace=_build_auth_workspace(auth_context.workspace),
    )


def _build_session_response(
    *,
    user: User,
    tenant: Tenant,
    membership: TenantMembership,
    workspace: Workspace,
) -> AuthSessionResponse:
    settings = get_settings()
    access_token = create_signed_token(
        {
            "sub": user.id,
            "tenant_id": tenant.id,
            "workspace_id": workspace.id,
        },
        secret=settings.auth_token_secret,
        expires_in=settings.auth_token_ttl_seconds,
    )
    return AuthSessionResponse(
        access_token=access_token,
        expires_in=settings.auth_token_ttl_seconds,
        user=_build_auth_user(user, membership.role),
        tenant=_build_auth_tenant(tenant),
        workspace=_build_auth_workspace(workspace),
    )


def _build_auth_user(user: User, role: str) -> AuthUser:
    return AuthUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=_role_label(role),
        avatar_url=user.avatar_url,
    )


def _build_auth_tenant(tenant: Tenant) -> AuthTenant:
    return AuthTenant(id=tenant.id, tenant_key=tenant.tenant_key, name=tenant.name, plan=tenant.plan)


def _build_auth_workspace(workspace: Workspace) -> AuthWorkspace:
    return AuthWorkspace(id=workspace.id, workspace_key=workspace.workspace_key, name=workspace.name)


def _normalize_tenant_key(value: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", value.strip().lower().replace("_", "-"))


def _validate_tenant_key(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9-]{3,64}", value):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="租户标识只支持 3-64 位小写字母、数字和短横线。",
        )


def _validate_email(value: str) -> None:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确。")


def _role_label(role: str) -> str:
    return {
        "owner": "租户管理员",
        "admin": "数据工作台管理员",
        "viewer": "数据分析成员",
    }.get(role, role)
