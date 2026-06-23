-- DataWhisperer V3.13.8 产品库升级脚本
-- 作用：为系统设置的模型配置新增后端持久化表，并预置 demo 工作空间默认配置。
-- 说明：脚本使用 IF NOT EXISTS / ON DUPLICATE KEY UPDATE，可重复执行。

USE datawhisperer_product;

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
    JSON_OBJECT('source', 'upgrade_product_schema_v3_13_8')
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
