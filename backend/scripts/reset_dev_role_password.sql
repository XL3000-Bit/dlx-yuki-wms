\set ON_ERROR_STOP on

SELECT current_database() = 'postgres' AS connected_to_admin_db \gset
\if :connected_to_admin_db
\else
  \echo 'REFUSED: connect to the postgres maintenance database.'
  \quit 3
\endif

SELECT EXISTS (
  SELECT 1
  FROM pg_roles
  WHERE rolname = 'dlx_yuki_wms_dev_user'
) AS dev_role_exists \gset
\if :dev_role_exists
\else
  \echo 'REFUSED: DEV role does not exist.'
  \quit 3
\endif

SELECT (
  rolcanlogin
  AND NOT rolsuper
  AND NOT rolcreatedb
  AND NOT rolcreaterole
  AND NOT rolinherit
  AND NOT rolreplication
  AND NOT rolbypassrls
) AS dev_role_is_low_privilege
FROM pg_roles
WHERE rolname = 'dlx_yuki_wms_dev_user'
\gset

\if :dev_role_is_low_privilege
\else
  \echo 'REFUSED: DEV role attributes do not match the approved low-privilege profile.'
  \quit 3
\endif

\echo 'Enter the NEW password for dlx_yuki_wms_dev_user twice (input is hidden):'
\password dlx_yuki_wms_dev_user

SELECT (
  rolcanlogin
  AND NOT rolsuper
  AND NOT rolcreatedb
  AND NOT rolcreaterole
  AND NOT rolinherit
  AND NOT rolreplication
  AND NOT rolbypassrls
) AS dev_role_still_low_privilege
FROM pg_roles
WHERE rolname = 'dlx_yuki_wms_dev_user'
\gset

\if :dev_role_still_low_privilege
  \echo 'DEV_ROLE_PASSWORD_RESET=PASS'
\else
  \echo 'REFUSED: DEV role attributes changed unexpectedly.'
  \quit 3
\endif
