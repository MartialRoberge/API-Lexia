-- =============================================================================
-- Lexia API - Database Initialization
-- =============================================================================
-- This script runs on first container startup to initialize the database
-- =============================================================================

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE lexia TO lexia;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS lexia;

-- Set default schema
ALTER DATABASE lexia SET search_path TO lexia, public;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Lexia database initialized successfully';
END $$;
