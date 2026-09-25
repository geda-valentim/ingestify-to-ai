-- Migration: 002_add_crawler_fields.sql
-- Description: Add crawler-specific fields to jobs table (STI pattern)
-- Date: 2025-01-13
-- Sprint: 1 - Foundation & Data Models

USE ingestify;

-- Add JSON columns for crawler configuration
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS crawler_config JSON DEFAULT NULL COMMENT 'Crawler configuration (mode, engine, retry strategy, assets, proxy, etc.)',
ADD COLUMN IF NOT EXISTS crawler_schedule JSON DEFAULT NULL COMMENT 'Crawler schedule configuration (cron, timezone, next_runs)';

-- Add composite index for crawler job queries (job_type + status)
-- This optimizes queries like: SELECT * FROM jobs WHERE job_type = 'crawler' AND status = 'active'
CREATE INDEX IF NOT EXISTS idx_job_type_status ON jobs(job_type, status);

-- Verify changes
SELECT 'Checking crawler_config column...' AS status;
SHOW COLUMNS FROM jobs LIKE 'crawler_config';

SELECT 'Checking crawler_schedule column...' AS status;
SHOW COLUMNS FROM jobs LIKE 'crawler_schedule';

SELECT 'Checking idx_job_type_status index...' AS status;
SHOW INDEX FROM jobs WHERE Key_name = 'idx_job_type_status';

SELECT '✅ Migration 002 completed successfully!' AS status;
SELECT 'Added: crawler_config (JSON), crawler_schedule (JSON), idx_job_type_status (INDEX)' AS changes;
