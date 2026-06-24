from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SecurityPolicyPayload(BaseModel):
    """Workspace security policy returned to the settings page."""

    id: int
    readonly_sql_enabled: bool
    auto_limit_enabled: bool
    default_limit: int
    max_limit: int
    query_timeout_seconds: int
    audit_trace_enabled: bool
    sensitive_config_managed: bool
    updated_at: datetime | None = None


class SecurityPolicyUpdateRequest(BaseModel):
    """Update workspace SQL safety and audit policy."""

    readonly_sql_enabled: bool = True
    auto_limit_enabled: bool = True
    default_limit: int = Field(default=100, ge=1, le=5000)
    max_limit: int = Field(default=1000, ge=1, le=10000)
    query_timeout_seconds: int = Field(default=20, ge=1, le=300)
    audit_trace_enabled: bool = True
    sensitive_config_managed: bool = True


class SecurityPolicyTestRequest(BaseModel):
    """SQL snippet used to test the current security policy."""

    sql: str = Field(min_length=1, max_length=20000)


class SecurityPolicyTestResponse(BaseModel):
    """Security policy dry-run result."""

    ok: bool
    status: str
    message: str
    normalized_sql: str | None = None
    applied_limit: int | None = None
    blocked_reason: str | None = None
