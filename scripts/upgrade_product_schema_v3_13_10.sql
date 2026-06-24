-- DataWhisperer V3.13.10 product schema upgrade
-- Adds persisted workspace security policy for SQL safety settings.

USE datawhisperer_product;

CREATE TABLE IF NOT EXISTS workspace_security_policies (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    readonly_sql_enabled TINYINT(1) NOT NULL DEFAULT 1,
    auto_limit_enabled TINYINT(1) NOT NULL DEFAULT 1,
    default_limit INT NOT NULL DEFAULT 100,
    max_limit INT NOT NULL DEFAULT 1000,
    query_timeout_seconds INT NOT NULL DEFAULT 20,
    audit_trace_enabled TINYINT(1) NOT NULL DEFAULT 1,
    sensitive_config_managed TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_workspace_security_policies_workspace (workspace_id),
    KEY idx_workspace_security_policies_tenant (tenant_id),
    CONSTRAINT fk_workspace_security_policies_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_workspace_security_policies_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Workspace SQL safety policy.';

INSERT INTO workspace_security_policies (
    tenant_id,
    workspace_id,
    readonly_sql_enabled,
    auto_limit_enabled,
    default_limit,
    max_limit,
    query_timeout_seconds,
    audit_trace_enabled,
    sensitive_config_managed
)
SELECT t.id, w.id, 1, 1, 100, 1000, 20, 1, 1
FROM workspaces w
JOIN tenants t ON t.id = w.tenant_id
WHERE t.tenant_key = 'demo'
  AND w.workspace_key = 'default'
ON DUPLICATE KEY UPDATE
    updated_at = CURRENT_TIMESTAMP;
