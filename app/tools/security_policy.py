from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuerySecurityPolicy:
    """Runtime SQL safety policy consumed by the query execution flow."""

    readonly_sql_enabled: bool = True
    auto_limit_enabled: bool = True
    default_limit: int = 100
    max_limit: int = 1000
    query_timeout_seconds: int = 20
    audit_trace_enabled: bool = True
    sensitive_config_managed: bool = True

    def effective_limit(self, *, requested_max_rows: int, system_max_rows: int) -> int:
        """Return the effective row limit after product and system constraints."""

        requested = requested_max_rows if requested_max_rows != 100 else self.default_limit
        candidates = [requested, self.max_limit, system_max_rows]
        return max(1, min(int(value) for value in candidates if value and int(value) > 0))


def default_query_security_policy(*, system_max_rows: int, query_timeout_seconds: int) -> QuerySecurityPolicy:
    """Build a fallback policy for unauthenticated API examples."""

    return QuerySecurityPolicy(
        default_limit=system_max_rows,
        max_limit=system_max_rows,
        query_timeout_seconds=query_timeout_seconds,
    )
