USE datawhisperer_product;

-- DataWhisperer V3.13.12
-- 将 RAG 知识库从本地文件清单升级为租户/工作空间级产品表。


CREATE TABLE IF NOT EXISTS knowledge_bases (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(512) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_default TINYINT(1) NOT NULL DEFAULT 1,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_knowledge_bases_workspace_name (workspace_id, name),
    KEY idx_knowledge_bases_tenant_workspace (tenant_id, workspace_id),
    KEY idx_knowledge_bases_workspace_default (workspace_id, is_default),
    CONSTRAINT fk_knowledge_bases_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_bases_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_bases_created_by
      FOREIGN KEY (created_by) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工作空间级 RAG 知识库。';

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    knowledge_base_id BIGINT UNSIGNED NOT NULL,
    file_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL,
    extension VARCHAR(32) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    previewable TINYINT(1) NOT NULL DEFAULT 1,
    sync_status VARCHAR(32) NULL,
    sync_message VARCHAR(1024) NULL,
    sync_collection VARCHAR(128) NULL,
    sync_chunk_count INT NULL,
    synced_at DATETIME NULL,
    uploaded_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_knowledge_documents_workspace_file (workspace_id, file_id),
    KEY idx_knowledge_documents_base (knowledge_base_id, created_at),
    KEY idx_knowledge_documents_sync (workspace_id, sync_status),
    CONSTRAINT fk_knowledge_documents_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_documents_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_documents_base
      FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_documents_uploaded_by
      FOREIGN KEY (uploaded_by) REFERENCES users(id)
      ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库上传文档。';

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workspace_id BIGINT UNSIGNED NOT NULL,
    knowledge_base_id BIGINT UNSIGNED NOT NULL,
    document_id BIGINT UNSIGNED NOT NULL,
    chunk_id VARCHAR(128) NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    vector_collection VARCHAR(128) NOT NULL,
    synced_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_knowledge_chunks_document_index (document_id, chunk_index),
    UNIQUE KEY uk_knowledge_chunks_chunk_id (chunk_id),
    KEY idx_knowledge_chunks_base (knowledge_base_id, chunk_index),
    KEY idx_knowledge_chunks_workspace (tenant_id, workspace_id),
    CONSTRAINT fk_knowledge_chunks_tenant
      FOREIGN KEY (tenant_id) REFERENCES tenants(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_chunks_workspace
      FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_chunks_base
      FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_chunks_document
      FOREIGN KEY (document_id) REFERENCES knowledge_documents(id)
      ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库文档切片元数据，向量本体保存在 Milvus。';


INSERT INTO knowledge_bases (
    tenant_id,
    workspace_id,
    name,
    description,
    status,
    is_default,
    created_by
)
SELECT
    w.tenant_id,
    w.id,
    '默认知识库',
    '当前工作空间默认的 RAG 业务知识库。',
    'active',
    1,
    w.created_by
FROM workspaces w
LEFT JOIN knowledge_bases kb
  ON kb.workspace_id = w.id
 AND kb.is_default = 1
WHERE kb.id IS NULL;
