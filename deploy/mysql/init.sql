-- RAGIMS metadata database initialization.
-- Executed once by the mysql:8.0 entrypoint on first run
-- (mounted at /docker-entrypoint-initdb.d/init.sql).

CREATE DATABASE IF NOT EXISTS ragims
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Enforce the expected charset/collation even if the image already pre-created
-- the database via MYSQL_DATABASE (which may default to utf8mb4_0900_ai_ci).
ALTER DATABASE ragims
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
