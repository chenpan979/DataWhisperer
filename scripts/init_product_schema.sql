CREATE DATABASE IF NOT EXISTS datawhisperer_product
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE datawhisperer_product;

-- DataWhisperer V3.13.1
-- 产品级管理库初始化脚本。
--
-- 说明：
-- 1. datawhisperer_product 存平台自身数据：租户、用户、工作空间、数据源、会话和分析结果。
-- 2. datawhisperer_demo 仍然作为被分析的示例业务库，不和产品管理库混在一起。
-- 3. 本脚本使用 CREATE TABLE IF NOT EXISTS 与幂等种子数据，方便本地反复执行。

CREATE TABLE IF NOT EXISTS tenants (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_key VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    plan VARCHAR(32) NOT NULL DEFAULT 'free',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenants_tenant_key (tenant_key),
    KEY idx_tenants_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='租户/组织。一个租户代表一个公司或团队。';

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(128) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    avatar_url LONGTEXT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_users_email (email),
    KEY idx_users_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户账号。密码只保存哈希，不保存明文。';

CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    role_title VARCHAR(64) NULL,
    language VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
    default_view VARCHAR(64) NOT NULL DEFAULT 'analysisView',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_preferences_tenant_user (tenant_id, user_id),
    KEY idx_user_preferences_user (user_id),
    CONSTRAINT fk_user_preferences_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_user_preferences_user
      FOREIGN KEY (user_id) REFERENCES users(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户在租户下的工作台偏好。';
CREATE TABLE IF NOT EXISTS tenant_memberships (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'viewer',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tenant_memberships_member (tenant_id, user_id),
    KEY idx_tenant_memberships_user (user_id),
    KEY idx_tenant_memberships_role (tenant_id, role),
    CONSTRAINT fk_tenant_memberships_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_tenant_memberships_user
      FOREIGN KEY (user_id) REFERENCES users(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='租户成员关系。控制用户在租户内的角色。';

CREATE TABLE IF NOT EXISTS workspaces (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_key VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(512) NULL,
    default_data_source_id BIGINT UNSIGNED NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_workspaces_tenant_key (tenant_id, workspace_key),
    KEY idx_workspaces_tenant_status (tenant_id, status),
    KEY idx_workspaces_created_by (created_by),
    CONSTRAINT fk_workspaces_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_workspaces_created_by
      FOREIGN KEY (created_by) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工作空间。AI 查数、数据源、Schema 和评测都挂在工作空间下。';

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
  COMMENT='工作空间级 SQL 安全策略';

CREATE TABLE IF NOT EXISTS workspace_memberships (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    workspace_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'viewer',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_workspace_memberships_member (workspace_id, user_id),
    KEY idx_workspace_memberships_user (user_id),
    CONSTRAINT fk_workspace_memberships_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_workspace_memberships_user
      FOREIGN KEY (user_id) REFERENCES users(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工作空间成员关系。后续用于更细粒度的空间级权限。';

CREATE TABLE IF NOT EXISTS data_sources (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(128) NOT NULL,
    db_type VARCHAR(32) NOT NULL DEFAULT 'mysql',
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    database_name VARCHAR(128) NOT NULL,
    username VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'connected',
    last_checked_at DATETIME NULL,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_data_sources_workspace_name (workspace_id, name),
    KEY idx_data_sources_tenant (tenant_id),
    KEY idx_data_sources_workspace_status (workspace_id, status),
    KEY idx_data_sources_created_by (created_by),
    CONSTRAINT fk_data_sources_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_data_sources_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_data_sources_created_by
      FOREIGN KEY (created_by) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='业务数据源连接信息。密码等敏感信息放在 data_source_credentials。';

CREATE TABLE IF NOT EXISTS data_source_credentials (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    data_source_id BIGINT UNSIGNED NOT NULL,
    encrypted_password TEXT NOT NULL,
    encryption_version VARCHAR(32) NOT NULL DEFAULT 'local-demo',
    rotated_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_data_source_credentials_source (data_source_id),
    CONSTRAINT fk_data_source_credentials_source
      FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='数据源密钥。当前脚本只放演示占位值，生产环境必须服务端加密。';

CREATE TABLE IF NOT EXISTS model_providers (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(128) NOT NULL,
    provider_type VARCHAR(32) NOT NULL DEFAULT 'dashscope',
    base_url VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'configured',
    last_checked_at DATETIME NULL,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_providers_workspace_name (workspace_id, name),
    KEY idx_model_providers_tenant (tenant_id),
    KEY idx_model_providers_workspace_status (workspace_id, status),
    KEY idx_model_providers_created_by (created_by),
    CONSTRAINT fk_model_providers_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_model_providers_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_model_providers_created_by
      FOREIGN KEY (created_by) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模型供应商配置。';

CREATE TABLE IF NOT EXISTS model_credentials (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    provider_id BIGINT UNSIGNED NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_mask VARCHAR(64) NULL,
    encryption_version VARCHAR(32) NOT NULL DEFAULT 'local-demo',
    rotated_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_credentials_provider (provider_id),
    CONSTRAINT fk_model_credentials_provider
      FOREIGN KEY (provider_id) REFERENCES model_providers(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模型供应商密钥。生产环境应接入 KMS 或 Vault。';

CREATE TABLE IF NOT EXISTS model_profiles (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    provider_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(128) NOT NULL,
    chat_model VARCHAR(128) NOT NULL,
    embedding_model VARCHAR(128) NULL,
    temperature DECIMAL(4,3) NOT NULL DEFAULT 0.100,
    max_tokens INT NOT NULL DEFAULT 2048,
    is_default TINYINT(1) NOT NULL DEFAULT 1,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    config_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_profiles_provider_name (provider_id, name),
    KEY idx_model_profiles_workspace_default (workspace_id, is_default),
    KEY idx_model_profiles_tenant (tenant_id),
    CONSTRAINT fk_model_profiles_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_model_profiles_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_model_profiles_provider
      FOREIGN KEY (provider_id) REFERENCES model_providers(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模型调用 Profile。Agent 绑定时引用这里。';

CREATE TABLE IF NOT EXISTS agent_model_bindings (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    agent_key VARCHAR(64) NOT NULL,
    capability VARCHAR(64) NOT NULL,
    model_profile_id BIGINT UNSIGNED NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    params_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_agent_model_bindings_workspace_agent_capability (workspace_id, agent_key, capability),
    KEY idx_agent_model_bindings_profile (model_profile_id),
    KEY idx_agent_model_bindings_tenant_workspace (tenant_id, workspace_id),
    CONSTRAINT fk_agent_model_bindings_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_agent_model_bindings_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_agent_model_bindings_profile
      FOREIGN KEY (model_profile_id) REFERENCES model_profiles(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Agent 与模型 Profile 的绑定关系。';

CREATE TABLE IF NOT EXISTS schema_tables (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    table_comment VARCHAR(512) NULL,
    table_type VARCHAR(32) NOT NULL DEFAULT 'unknown',
    row_count_estimate BIGINT UNSIGNED NULL,
    sync_version VARCHAR(64) NOT NULL DEFAULT 'manual',
    synced_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_schema_tables_source_name (data_source_id, table_name),
    KEY idx_schema_tables_tenant_workspace (tenant_id, workspace_id),
    KEY idx_schema_tables_type (data_source_id, table_type),
    CONSTRAINT fk_schema_tables_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_tables_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_tables_source
      FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='同步后的数据表元信息。3D 图谱节点来自这里。';

CREATE TABLE IF NOT EXISTS schema_columns (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NOT NULL,
    table_id BIGINT UNSIGNED NOT NULL,
    column_name VARCHAR(128) NOT NULL,
    data_type VARCHAR(128) NOT NULL,
    column_comment VARCHAR(512) NULL,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    ordinal_position INT NOT NULL,
    semantic_type VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_schema_columns_table_name (table_id, column_name),
    KEY idx_schema_columns_source (data_source_id),
    KEY idx_schema_columns_semantic (data_source_id, semantic_type),
    CONSTRAINT fk_schema_columns_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_columns_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_columns_source
      FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_columns_table
      FOREIGN KEY (table_id) REFERENCES schema_tables(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='同步后的字段元信息。Text-to-SQL prompt 与表详情抽屉使用。';

CREATE TABLE IF NOT EXISTS schema_relationships (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NOT NULL,
    source_table_id BIGINT UNSIGNED NOT NULL,
    source_column_id BIGINT UNSIGNED NOT NULL,
    target_table_id BIGINT UNSIGNED NOT NULL,
    target_column_id BIGINT UNSIGNED NOT NULL,
    relation_type VARCHAR(32) NOT NULL DEFAULT 'many_to_one',
    confidence DECIMAL(5, 4) NOT NULL DEFAULT 1.0000,
    source VARCHAR(32) NOT NULL DEFAULT 'database_fk',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_schema_relationships_columns (source_column_id, target_column_id),
    KEY idx_schema_relationships_source_table (source_table_id),
    KEY idx_schema_relationships_target_table (target_table_id),
    KEY idx_schema_relationships_workspace (tenant_id, workspace_id),
    CONSTRAINT fk_schema_relationships_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_source
      FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_source_table
      FOREIGN KEY (source_table_id) REFERENCES schema_tables(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_source_column
      FOREIGN KEY (source_column_id) REFERENCES schema_columns(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_target_table
      FOREIGN KEY (target_table_id) REFERENCES schema_tables(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_schema_relationships_target_column
      FOREIGN KEY (target_column_id) REFERENCES schema_columns(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='表关系元信息。3D 图谱连线和 SQL join 推荐使用。';

CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(128) NOT NULL,
    summary VARCHAR(512) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_conversations_workspace_updated (workspace_id, updated_at),
    KEY idx_conversations_user_updated (user_id, updated_at),
    KEY idx_conversations_tenant_status (tenant_id, status),
    CONSTRAINT fk_conversations_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_conversations_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_conversations_user
      FOREIGN KEY (user_id) REFERENCES users(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 查数会话。左侧最近对话列表来自这里。';

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    conversation_id BIGINT UNSIGNED NOT NULL,
    role VARCHAR(32) NOT NULL,
    content LONGTEXT NOT NULL,
    content_type VARCHAR(32) NOT NULL DEFAULT 'text',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_chat_messages_conversation (conversation_id, id),
    KEY idx_chat_messages_workspace (workspace_id, created_at),
    CONSTRAINT fk_chat_messages_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_chat_messages_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_chat_messages_conversation
      FOREIGN KEY (conversation_id) REFERENCES conversations(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='会话消息。保存用户问题、助手回答和系统消息。';

CREATE TABLE IF NOT EXISTS analysis_runs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    conversation_id BIGINT UNSIGNED NOT NULL,
    message_id BIGINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    trace_id VARCHAR(128) NOT NULL,
    question TEXT NOT NULL,
    generated_sql TEXT NULL,
    sql_explanation TEXT NULL,
    result_columns JSON NULL,
    result_rows_preview JSON NULL,
    chart_option JSON NULL,
    insight TEXT NULL,
    trace_steps JSON NULL,
    warnings JSON NULL,
    prompt_versions JSON NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    duration_ms INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_analysis_runs_trace_id (trace_id),
    KEY idx_analysis_runs_conversation (conversation_id, created_at),
    KEY idx_analysis_runs_workspace (workspace_id, created_at),
    KEY idx_analysis_runs_data_source (data_source_id),
    CONSTRAINT fk_analysis_runs_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_analysis_runs_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_analysis_runs_conversation
      FOREIGN KEY (conversation_id) REFERENCES conversations(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_analysis_runs_message
      FOREIGN KEY (message_id) REFERENCES chat_messages(id)
      ON DELETE SET NULL,
    CONSTRAINT fk_analysis_runs_data_source
      FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='一次自然语言查数的完整运行快照。';

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NULL,
    user_id BIGINT UNSIGNED NULL,
    action VARCHAR(128) NOT NULL,
    target_type VARCHAR(64) NULL,
    target_id VARCHAR(64) NULL,
    ip_address VARCHAR(64) NULL,
    user_agent VARCHAR(512) NULL,
    detail JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_logs_tenant_time (tenant_id, created_at),
    KEY idx_audit_logs_workspace_time (workspace_id, created_at),
    KEY idx_audit_logs_user_time (user_id, created_at),
    KEY idx_audit_logs_action (action),
    CONSTRAINT fk_audit_logs_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_audit_logs_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE SET NULL,
    CONSTRAINT fk_audit_logs_user
      FOREIGN KEY (user_id) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='审计日志。记录关键数据操作和安全事件。';

-- 幂等初始化 demo 租户、管理员、工作空间和示例业务数据源。
INSERT INTO tenants (tenant_key, name, plan, status)
VALUES ('demo', '示例数据空间', 'team', 'active')
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    plan = VALUES(plan),
    status = VALUES(status);

INSERT INTO users (email, display_name, password_hash, status)
VALUES ('admin@datawhisperer.local', 'admin', 'demo-password-hash-placeholder', 'active')
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    status = VALUES(status);

INSERT INTO user_preferences (tenant_id, user_id, role_title, language, default_view)
SELECT t.id, u.id, '数据工作台管理员', 'zh-CN', 'analysisView'
FROM tenants t
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    updated_at = CURRENT_TIMESTAMP;
INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
SELECT t.id, u.id, 'owner', 'active'
FROM tenants t
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    role = VALUES(role),
    status = VALUES(status);

INSERT INTO workspaces (tenant_id, workspace_key, name, description, created_by, status)
SELECT t.id, 'default', '默认工作空间', 'DataWhisperer 示例工作空间', u.id, 'active'
FROM tenants t
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    status = VALUES(status);

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

INSERT INTO workspace_memberships (workspace_id, user_id, role)
SELECT w.id, u.id, 'admin'
FROM workspaces w
JOIN tenants t ON t.id = w.tenant_id
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
  AND w.workspace_key = 'default'
ON DUPLICATE KEY UPDATE
    role = VALUES(role);

INSERT INTO data_sources (
    tenant_id,
    workspace_id,
    name,
    db_type,
    host,
    port,
    database_name,
    username,
    status,
    created_by,
    last_checked_at
)
SELECT
    t.id,
    w.id,
    '示例 MySQL 库',
    'mysql',
    '127.0.0.1',
    3306,
    'datawhisperer_demo',
    'root',
    'connected',
    u.id,
    CURRENT_TIMESTAMP
FROM tenants t
JOIN workspaces w ON w.tenant_id = t.id AND w.workspace_key = 'default'
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    db_type = VALUES(db_type),
    host = VALUES(host),
    port = VALUES(port),
    database_name = VALUES(database_name),
    username = VALUES(username),
    status = VALUES(status),
    last_checked_at = VALUES(last_checked_at);

INSERT INTO data_source_credentials (data_source_id, encrypted_password, encryption_version, rotated_at)
SELECT ds.id, 'demo-encrypted-password-placeholder', 'local-demo', CURRENT_TIMESTAMP
FROM data_sources ds
JOIN workspaces w ON w.id = ds.workspace_id
JOIN tenants t ON t.id = ds.tenant_id
WHERE t.tenant_key = 'demo'
  AND w.workspace_key = 'default'
  AND ds.name = '示例 MySQL 库'
ON DUPLICATE KEY UPDATE
    encryption_version = VALUES(encryption_version),
    rotated_at = VALUES(rotated_at);

UPDATE workspaces w
JOIN tenants t ON t.id = w.tenant_id
JOIN data_sources ds ON ds.workspace_id = w.id AND ds.name = '示例 MySQL 库'
SET w.default_data_source_id = ds.id
WHERE t.tenant_key = 'demo'
  AND w.workspace_key = 'default';

INSERT INTO model_providers (
    tenant_id,
    workspace_id,
    name,
    provider_type,
    base_url,
    status,
    created_by,
    last_checked_at
)
SELECT
    t.id,
    w.id,
    'DashScope',
    'dashscope',
    'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'configured',
    u.id,
    CURRENT_TIMESTAMP
FROM tenants t
JOIN workspaces w ON w.tenant_id = t.id AND w.workspace_key = 'default'
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    provider_type = VALUES(provider_type),
    base_url = VALUES(base_url),
    status = VALUES(status),
    last_checked_at = VALUES(last_checked_at);

INSERT INTO model_credentials (provider_id, encrypted_api_key, key_mask, encryption_version, rotated_at)
SELECT mp.id, 'demo-encrypted-api-key-placeholder', 'sk-****demo', 'local-demo', CURRENT_TIMESTAMP
FROM model_providers mp
JOIN workspaces w ON w.id = mp.workspace_id
JOIN tenants t ON t.id = mp.tenant_id
WHERE t.tenant_key = 'demo'
  AND w.workspace_key = 'default'
  AND mp.name = 'DashScope'
ON DUPLICATE KEY UPDATE
    key_mask = VALUES(key_mask),
    encryption_version = VALUES(encryption_version),
    rotated_at = VALUES(rotated_at);

INSERT INTO model_profiles (
    tenant_id,
    workspace_id,
    provider_id,
    name,
    chat_model,
    embedding_model,
    temperature,
    max_tokens,
    is_default,
    status,
    config_json
)
SELECT
    t.id,
    w.id,
    mp.id,
    '默认模型配置',
    'qwen-plus',
    'text-embedding-v4',
    0.100,
    2048,
    1,
    'active',
    JSON_OBJECT('source', 'init_product_schema')
FROM tenants t
JOIN workspaces w ON w.tenant_id = t.id AND w.workspace_key = 'default'
JOIN model_providers mp ON mp.workspace_id = w.id AND mp.name = 'DashScope'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    chat_model = VALUES(chat_model),
    embedding_model = VALUES(embedding_model),
    temperature = VALUES(temperature),
    max_tokens = VALUES(max_tokens),
    is_default = VALUES(is_default),
    status = VALUES(status);

INSERT INTO agent_model_bindings (
    tenant_id,
    workspace_id,
    agent_key,
    capability,
    model_profile_id,
    enabled,
    params_json
)
SELECT t.id, w.id, binding.agent_key, binding.capability, mpf.id, 1, JSON_OBJECT()
FROM tenants t
JOIN workspaces w ON w.tenant_id = t.id AND w.workspace_key = 'default'
JOIN model_providers mp ON mp.workspace_id = w.id AND mp.name = 'DashScope'
JOIN model_profiles mpf ON mpf.provider_id = mp.id AND mpf.name = '默认模型配置'
JOIN (
    SELECT 'sql_agent' AS agent_key, 'sql_generation' AS capability
    UNION ALL SELECT 'insight_agent', 'insight_summary'
    UNION ALL SELECT 'chart_agent', 'chart_recommendation'
    UNION ALL SELECT 'rag_agent', 'embedding'
) binding
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    model_profile_id = VALUES(model_profile_id),
    enabled = VALUES(enabled);
