from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.product_database import get_product_session
from app.core.security import hash_password, verify_password
from app.models.account import (
    AccountPreferencePayload,
    AccountPreferenceUpdateRequest,
    PasswordChangeRequest,
    PasswordChangeResponse,
)
from app.repositories.product import AccountPreferenceRepository, AuditLogRepository, UserRepository

router = APIRouter(prefix="/account", tags=["account"])

ALLOWED_LANGUAGES = {"zh-CN", "en-US"}
ALLOWED_DEFAULT_VIEWS = {
    "analysisView",
    "schemaView",
    "ragView",
    "datasetView",
    "evaluationView",
    "settingsView",
}


@router.get("/preferences", response_model=AccountPreferencePayload)
def get_account_preferences(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> AccountPreferencePayload:
    """读取当前登录用户的账号偏好。

    前端左下角用户卡片和系统设置的账号页都会使用这个接口，避免只靠浏览器草稿。
    """

    preference = AccountPreferenceRepository(session).ensure_for_user(
        tenant_id=auth_context.tenant.id,
        user_id=auth_context.user.id,
        role_title=_role_label(auth_context.membership.role),
    )
    session.commit()
    return _build_account_preference_payload(auth_context=auth_context, preference=preference)


@router.patch("/preferences", response_model=AccountPreferencePayload)
def update_account_preferences(
    payload: AccountPreferenceUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> AccountPreferencePayload:
    """保存账号资料和当前租户下的工作台偏好。"""

    _validate_language(payload.language)
    _validate_default_view(payload.default_view)
    preference_repo = AccountPreferenceRepository(session)
    preference = preference_repo.ensure_for_user(
        tenant_id=auth_context.tenant.id,
        user_id=auth_context.user.id,
        role_title=_role_label(auth_context.membership.role),
    )
    user = UserRepository(session).update_profile(
        auth_context.user,
        display_name=payload.display_name.strip(),
        avatar_url=payload.avatar_url or "",
    )
    auth_context.user = user
    preference_repo.update(
        preference,
        role_title=payload.role_title.strip(),
        language=payload.language,
        default_view=payload.default_view,
    )
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="account.preferences.updated",
        target_type="user",
        target_id=str(auth_context.user.id),
        detail={
            "language": payload.language,
            "default_view": payload.default_view,
        },
    )
    session.commit()
    return _build_account_preference_payload(auth_context=auth_context, preference=preference)


@router.patch("/password", response_model=PasswordChangeResponse)
def change_account_password(
    payload: PasswordChangeRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> PasswordChangeResponse:
    """修改当前登录账号密码。"""

    if not verify_password(payload.current_password, auth_context.user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前密码不正确。")
    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="新密码不能和当前密码相同。")
    auth_context.user.password_hash = hash_password(payload.new_password)
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="account.password.changed",
        target_type="user",
        target_id=str(auth_context.user.id),
    )
    session.commit()
    return PasswordChangeResponse(ok=True, message="密码已更新，下次登录请使用新密码。")


def _build_account_preference_payload(*, auth_context: AuthContext, preference) -> AccountPreferencePayload:
    role = _role_label(auth_context.membership.role)
    return AccountPreferencePayload(
        user_id=auth_context.user.id,
        email=auth_context.user.email,
        display_name=auth_context.user.display_name,
        role=role,
        role_title=preference.role_title or role,
        avatar_url=auth_context.user.avatar_url,
        language=preference.language,
        default_view=preference.default_view,
    )


def _validate_language(language: str) -> None:
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="暂不支持该界面语言。")


def _validate_default_view(default_view: str) -> None:
    if default_view not in ALLOWED_DEFAULT_VIEWS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="默认打开页不在允许范围内。")


def _role_label(role: str) -> str:
    return {
        "owner": "租户管理员",
        "admin": "数据工作台管理员",
        "viewer": "数据分析成员",
    }.get(role, role)