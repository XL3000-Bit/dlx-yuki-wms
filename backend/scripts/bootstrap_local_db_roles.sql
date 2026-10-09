\set ON_ERROR_STOP on

\if :{?DBNAME}
\else
  \echo 'DBNAME is unavailable; refusing to continue.'
  \quit 3
\endif

SELECT current_database() = 'postgres' AS connected_to_admin_db \gset
\if :connected_to_admin_db
\else
  \echo 'Connect to the postgres maintenance database first; refusing to continue.'
  \quit 3
\endif

DO $bootstrap$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dlx_yuki_wms_dev_user') THEN
    CREATE ROLE dlx_yuki_wms_dev_user
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dlx_yuki_wms_test_user') THEN
    CREATE ROLE dlx_yuki_wms_test_user
      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
END
$bootstrap$;

ALTER ROLE dlx_yuki_wms_dev_user
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE dlx_yuki_wms_test_user
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

\echo 'Set the DEV role password (input is hidden):'
\password dlx_yuki_wms_dev_user
\echo 'Set the TEST role password (input is hidden):'
\password dlx_yuki_wms_test_user

ALTER DATABASE dlx_yuki_wms_dev OWNER TO dlx_yuki_wms_dev_user;
ALTER DATABASE dlx_yuki_wms_test OWNER TO dlx_yuki_wms_test_user;

\connect dlx_yuki_wms_dev
BEGIN;
ALTER SCHEMA public OWNER TO dlx_yuki_wms_dev_user;
SELECT format(
  'ALTER %s %I.%I OWNER TO dlx_yuki_wms_dev_user',
  CASE c.relkind
    WHEN 'S' THEN 'SEQUENCE'
    WHEN 'v' THEN 'VIEW'
    WHEN 'm' THEN 'MATERIALIZED VIEW'
    WHEN 'f' THEN 'FOREIGN TABLE'
    ELSE 'TABLE'
  END,
  n.nspname,
  c.relname
)
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
  AND NOT EXISTS (
    SELECT 1 FROM pg_depend AS d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
  )
  AND NOT (
    c.relkind = 'S'
    AND EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass
        AND d.objid = c.oid
        AND d.refclassid = 'pg_class'::regclass
        AND d.deptype IN ('a', 'i')
    )
  )
\gexec
GRANT ALL PRIVILEGES ON SCHEMA public TO dlx_yuki_wms_dev_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dlx_yuki_wms_dev_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dlx_yuki_wms_dev_user;
GRANT ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA public TO dlx_yuki_wms_dev_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_dev_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO dlx_yuki_wms_dev_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_dev_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO dlx_yuki_wms_dev_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_dev_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON ROUTINES TO dlx_yuki_wms_dev_user;
COMMIT;

\connect dlx_yuki_wms_test
BEGIN;
ALTER SCHEMA public OWNER TO dlx_yuki_wms_test_user;
SELECT format(
  'ALTER %s %I.%I OWNER TO dlx_yuki_wms_test_user',
  CASE c.relkind
    WHEN 'S' THEN 'SEQUENCE'
    WHEN 'v' THEN 'VIEW'
    WHEN 'm' THEN 'MATERIALIZED VIEW'
    WHEN 'f' THEN 'FOREIGN TABLE'
    ELSE 'TABLE'
  END,
  n.nspname,
  c.relname
)
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
  AND NOT EXISTS (
    SELECT 1 FROM pg_depend AS d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
  )
  AND NOT (
    c.relkind = 'S'
    AND EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass
        AND d.objid = c.oid
        AND d.refclassid = 'pg_class'::regclass
        AND d.deptype IN ('a', 'i')
    )
  )
\gexec
GRANT ALL PRIVILEGES ON SCHEMA public TO dlx_yuki_wms_test_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dlx_yuki_wms_test_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dlx_yuki_wms_test_user;
GRANT ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA public TO dlx_yuki_wms_test_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_test_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO dlx_yuki_wms_test_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_test_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO dlx_yuki_wms_test_user;
ALTER DEFAULT PRIVILEGES FOR ROLE dlx_yuki_wms_test_user IN SCHEMA public
  GRANT ALL PRIVILEGES ON ROUTINES TO dlx_yuki_wms_test_user;
COMMIT;

\connect postgres
\o C:/Users/XL/AppData/Local/Temp/dlx-yuki-wms-phase-a-result.txt
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname IN ('dlx_yuki_wms_dev_user', 'dlx_yuki_wms_test_user')
ORDER BY rolname;
SELECT datname, pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE datname IN ('dlx_yuki_wms_dev', 'dlx_yuki_wms_test')
ORDER BY datname;
\o
\echo 'PHASE_A_ROLE_BOOTSTRAP_COMPLETE'
