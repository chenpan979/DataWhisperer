from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.config import get_settings
from app.core.product_database import get_product_session
from app.db.product_models import WorkspaceSecurityPolicy
from app.models.security_policies import (
    SecurityPolicyPayload,
    SecurityPolicyTestRequest,
    SecurityPolicyTestResponse,
    SecurityPolicyUpdateRequest,
)
from app.repositories.product import AuditLogRepository, SecurityPolicyRepository
from app.tools.security_policy import QuerySecurityPolicy
from app.tools.sql_tool import ensure_limit

router = APIRouter(prefix="/security-policies", tags=["security_policies"])


@router.get("/default", response_model=SecurityPolicyPayload)
def get_default_security_policy(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> SecurityPolicyPayload:
    """Read the current workspace security policy."""

    policy = ensure_default_security_policy(session=session, auth_context=auth_context)
    session.commit()
    return _build_policy_payload(policy)


@router.patch("/default", response_model=SecurityPolicyPayload)
def update_default_security_policy(
    payload: SecurityPolicyUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> SecurityPolicyPayload:
    """Persist SQL safety and audit policy for the current workspace."""

    _validate_policy_update(payload)
    repository = SecurityPolicyRepository(session)
    policy = ensure_default_security_policy(session=session, auth_context=auth_context)
    repository.update(
        policy,
        readonly_sql_enabled=True,
        auto_limit_enabled=payload.auto_limit_enabled,
        default_limit=payload.default_limit,
        max_limit=payload.max_limit,
        query_timeout_seconds=payload.query_timeout_seconds,
        audit_trace_enabled=payload.audit_trace_enabled,
        sensitive_config_managed=payload.sensitive_config_managed,
    )
    AuditLogRepository(session).record(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        user_id=auth_context.user.id,
        action="security_policy.updated",
        target_type="workspace",
        target_id=str(auth_context.workspace.id),
        detail={
            "auto_limit_enabled": payload.auto_limit_enabled,
            "default_limit": payload.default_limit,
            "max_limit": payload.max_limit,
            "audit_trace_enabled": payload.audit_trace_enabled,
        },
    )
    session.commit()
    return _build_policy_payload(policy)


@router.post("/default/test", response_model=SecurityPolicyTestResponse)
def test_default_security_policy(
    payload: SecurityPolicyTestRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> SecurityPolicyTestResponse:
    """Dry-run one SQL snippet against the persisted security policy."""

    policy = ensure_default_security_policy(session=session, auth_context=auth_context)
    runtime_policy = build_query_security_policy(policy)
    effective_limit = runtime_policy.effective_limit(
        requested_max_rows=policy.default_limit,
        system_max_rows=get_settings().max_query_rows,
    )
    try:
        normalized_sql = ensure_limit(
            payload.sql,
            effective_limit,
            auto_limit_enabled=runtime_policy.auto_limit_enabled,
        )
    except ValueError as exc:
        return SecurityPolicyTestResponse(
            ok=False,
            status="blocked",
            message=f"已拦截：{exc}",
            blocked_reason=str(exc),
        )
    return SecurityPolicyTestResponse(
        ok=True,
        status="passed",
        message="安全策略通过，SQL 可以进入执行阶段。",
        normalized_sql=normalized_sql,
        applied_limit=_extract_limit(normalized_sql),
    )


def ensure_default_security_policy(
    *,
    session: Session,
    auth_context: AuthContext,
) -> WorkspaceSecurityPolicy:
    """Ensure the current workspace has one persisted policy."""

    settings = get_settings()
    return SecurityPolicyRepository(session).ensure_for_workspace(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        default_limit=settings.max_query_rows,
        max_limit=max(settings.max_query_rows, 1000),
        query_timeout_seconds=settings.query_timeout_seconds,
    )


def build_query_security_policy(policy: WorkspaceSecurityPolicy) -> QuerySecurityPolicy:
    """Convert ORM policy into the runtime object used by query execution."""

    return QuerySecurityPolicy(
        readonly_sql_enabled=True,
        auto_limit_enabled=policy.auto_limit_enabled,
        default_limit=policy.default_limit,
        max_limit=policy.max_limit,
        query_timeout_seconds=policy.query_timeout_seconds,
        audit_trace_enabled=policy.audit_trace_enabled,
        sensitive_config_managed=policy.sensitive_config_managed,
    )


def _build_policy_payload(policy: WorkspaceSecurityPolicy) -> SecurityPolicyPayload:
    return SecurityPolicyPayload(
        id=policy.id,
        readonly_sql_enabled=True,
        auto_limit_enabled=policy.auto_limit_enabled,
        default_limit=policy.default_limit,
        max_limit=policy.max_limit,
        query_timeout_seconds=policy.query_timeout_seconds,
        audit_trace_enabled=policy.audit_trace_enabled,
        sensitive_config_managed=policy.sensitive_config_managed,
        updated_at=policy.updated_at,
    )


def _validate_policy_update(payload: SecurityPolicyUpdateRequest) -> None:
    if not payload.readonly_sql_enabled:
        raise HTTPException(
            422,
            detail="只读 SQL 是系统强制安全基线，不允许关闭。",
        )
    if payload.default_limit > payload.max_limit:
        raise HTTPException(
            422,
            detail="默认 LIMIT 不能大于最大 LIMIT。",
        )


def _extract_limit(sql: str) -> int | None:
    match = re.search(r"\blimit\s+(\d+)\s*$", sql, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None
