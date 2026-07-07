-- DataWhisperer V3.13.14 product schema upgrade
-- Adds public/tenant knowledge-base scoping for multi-tenant RAG.

USE datawhisperer_product;

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS scope VARCHAR(32) NOT NULL DEFAULT 'tenant' AFTER description;

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS readonly TINYINT(1) NOT NULL DEFAULT 0 AFTER is_default;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS source_scope VARCHAR(32) NOT NULL DEFAULT 'tenant' AFTER previewable;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS readonly TINYINT(1) NOT NULL DEFAULT 0 AFTER source_scope;

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS source_scope VARCHAR(32) NOT NULL DEFAULT 'tenant' AFTER document_id;

UPDATE knowledge_bases
SET scope = 'tenant', readonly = 0
WHERE scope IS NULL OR scope = '';

UPDATE knowledge_documents
SET source_scope = 'tenant', readonly = 0
WHERE source_scope IS NULL OR source_scope = '';

UPDATE knowledge_chunks
SET source_scope = 'tenant'
WHERE source_scope IS NULL OR source_scope = '';

DROP PROCEDURE IF EXISTS add_index_if_missing;
DELIMITER $$
CREATE PROCEDURE add_index_if_missing(
    IN table_name_value VARCHAR(64),
    IN index_name_value VARCHAR(64),
    IN ddl_value TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND INDEX_NAME = index_name_value
    ) THEN
        SET @ddl = ddl_value;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_index_if_missing(
    'knowledge_bases',
    'idx_knowledge_bases_scope',
    'ALTER TABLE knowledge_bases ADD INDEX idx_knowledge_bases_scope (scope, status)'
);

CALL add_index_if_missing(
    'knowledge_documents',
    'idx_knowledge_documents_scope',
    'ALTER TABLE knowledge_documents ADD INDEX idx_knowledge_documents_scope (source_scope, sync_status)'
);

CALL add_index_if_missing(
    'knowledge_chunks',
    'idx_knowledge_chunks_scope',
    'ALTER TABLE knowledge_chunks ADD INDEX idx_knowledge_chunks_scope (source_scope, tenant_id, workspace_id)'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
