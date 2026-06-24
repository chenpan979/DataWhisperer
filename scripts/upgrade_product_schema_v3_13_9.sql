-- DataWhisperer V3.13.9 产品库升级脚本
-- 作用：为系统设置的账号偏好新增后端持久化表，并扩展头像字段容量。
-- 说明：脚本使用 CREATE TABLE IF NOT EXISTS / ON DUPLICATE KEY UPDATE，可重复执行。

USE datawhisperer_product;

ALTER TABLE users
  MODIFY COLUMN avatar_url LONGTEXT NULL;

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

INSERT INTO user_preferences (tenant_id, user_id, role_title, language, default_view)
SELECT t.id, u.id, '数据工作台管理员', 'zh-CN', 'analysisView'
FROM tenants t
JOIN users u ON u.email = 'admin@datawhisperer.local'
WHERE t.tenant_key = 'demo'
ON DUPLICATE KEY UPDATE
    updated_at = CURRENT_TIMESTAMP;