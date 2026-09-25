-- Migration: 003_add_crawled_files_table.sql
-- Description: Create crawled_files table for tracking individual downloaded files
-- Date: 2025-01-13
-- Sprint: 3 - Application Layer & Use Cases

USE ingestify;

-- Create crawled_files table
CREATE TABLE IF NOT EXISTS crawled_files (
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID do arquivo',
    execution_id VARCHAR(36) NOT NULL COMMENT 'FK para jobs table (execução do crawler)',
    url TEXT NOT NULL COMMENT 'URL original do arquivo',
    filename VARCHAR(512) COMMENT 'Nome do arquivo',

    -- File metadata
    file_type VARCHAR(50) COMMENT 'Tipo do arquivo (pdf, jpg, css, js, etc.)',
    mime_type VARCHAR(255) COMMENT 'MIME type (application/pdf, image/jpeg, etc.)',
    size_bytes BIGINT DEFAULT 0 COMMENT 'Tamanho do arquivo em bytes',

    -- MinIO storage
    minio_path VARCHAR(1024) COMMENT 'Caminho no MinIO (crawled/{execution_id}/files/...)',
    minio_bucket VARCHAR(255) DEFAULT 'ingestify-crawled' COMMENT 'Bucket do MinIO',
    public_url TEXT COMMENT 'URL pública do arquivo (pre-signed ou público)',

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending' COMMENT 'Status: pending, downloading, completed, failed, skipped',
    error_message TEXT COMMENT 'Mensagem de erro (se failed)',

    -- Timestamps
    downloaded_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Quando o download foi concluído',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Data de criação do registro',

    -- Foreign key constraint
    CONSTRAINT fk_crawled_files_execution
        FOREIGN KEY (execution_id)
        REFERENCES jobs(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Indexes for performance
    INDEX idx_execution_id (execution_id),
    INDEX idx_file_type (file_type),
    INDEX idx_status (status),
    INDEX idx_downloaded_at (downloaded_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual files downloaded by crawler executions';

-- Verify table creation
SELECT 'Checking crawled_files table...' AS status;
DESCRIBE crawled_files;

SELECT 'Checking crawled_files indexes...' AS status;
SHOW INDEX FROM crawled_files;

SELECT 'Checking foreign key constraint...' AS status;
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'ingestify'
  AND TABLE_NAME = 'crawled_files'
  AND REFERENCED_TABLE_NAME IS NOT NULL;

SELECT '✅ Migration 003 completed successfully!' AS status;
SELECT 'Created: crawled_files table with 5 indexes and FK to jobs table' AS changes;
