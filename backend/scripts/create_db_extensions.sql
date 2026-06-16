-- Enable extensions required by docs/database/schema.sql
--
-- Run as a privileged role (postgres) BEFORE applying schema.sql or running
-- Alembic migrations. Idempotent.
--
-- Atlas Goro

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto;       -- gen_random_bytes, gen_random_uuid
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";    -- legacy uuid generators (kept for compat)
CREATE EXTENSION IF NOT EXISTS citext;         -- case-insensitive email column

-- Note: schema.sql defines uuidv7() in PL/pgSQL — no separate extension required.

-- Sanity check.
DO $$
BEGIN
    RAISE NOTICE 'extensions installed: pgcrypto, uuid-ossp, citext';
END $$;
