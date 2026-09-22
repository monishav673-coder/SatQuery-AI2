-- SATQUERY AI — PostgreSQL initialisation script
-- This runs once when the PostgreSQL container starts for the first time.
-- Tables are created by SQLAlchemy/Alembic on first backend startup.

-- Ensure the database exists (handled by POSTGRES_DB env var)
-- Grant standard permissions
GRANT ALL PRIVILEGES ON DATABASE satquery_db TO satquery;
