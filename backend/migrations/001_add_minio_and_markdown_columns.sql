-- Migration: Add MinIO paths and markdown content columns
-- Description: Add storage paths for MinIO and markdown content to MySQL
-- Date: 2025-10-30
--
-- Run this migration with:
-- mysql -u root -p ingestify < backend/migrations/001_add_minio_and_markdown_columns.sql

USE ingestify;

-- Add MinIO columns to jobs table
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS minio_upload_path VARCHAR(500) COMMENT 'Path to uploaded file in MinIO',
ADD COLUMN IF NOT EXISTS minio_result_path VARCHAR(500) COMMENT 'Path to result markdown in MinIO';

-- Add MinIO and markdown columns to pages table
ALTER TABLE pages
ADD COLUMN IF NOT EXISTS minio_page_path VARCHAR(500) COMMENT 'Path to split page PDF in MinIO',
ADD COLUMN IF NOT EXISTS markdown_content LONGTEXT COMMENT 'Full markdown content for this page';

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_jobs_minio_upload_path ON jobs(minio_upload_path(255));
CREATE INDEX IF NOT EXISTS idx_pages_minio_page_path ON pages(minio_page_path(255));

-- Verify changes
SHOW COLUMNS FROM jobs LIKE 'minio%';
SHOW COLUMNS FROM pages LIKE 'minio%';
SHOW COLUMNS FROM pages LIKE 'markdown_content';

SELECT 'Migration completed successfully!' AS status;
