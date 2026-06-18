-- PostgreSQL bootstrap for LegalEase SQLAlchemy enterprise tables.
-- Core chat/auth/memory tables remain on SQLite (LEGALEASE_DB_PATH) unless fully migrated.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tables are created by SQLAlchemy init_db() on API startup.
-- This script ensures the database exists and is ready.
