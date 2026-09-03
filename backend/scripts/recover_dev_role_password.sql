\set ON_ERROR_STOP on

-- The connection has already been authenticated. Remove the temporary local
-- rule immediately; this established session remains usable afterward.
\! powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File C:/Users/XL/dlx-yuki-wms/backend/scripts/restore_pg_hba_after_dev_recovery.ps1
\if :SHELL_ERROR
  \echo 'REFUSED: temporary authentication cleanup failed.'
  \quit 3
\endif

SELECT (
  current_database() = 'postgres'
  AND current_user = 'postgres'
) AS approved_admin_session \gset
\if :approved_admin_session
\else
  \echo 'REFUSED: unexpected administrative session.'
  \quit 3
\endif

SELECT EXISTS (
  SELECT 1
  FROM pg_roles
  WHERE rolname = 'dlx_yuki_wms_dev_user'
    AND rolcanlogin
    AND NOT rolsuper
    AND NOT rolcreatedb
    AND NOT rolcreaterole
    AND NOT rolinherit
    AND NOT rolreplication
    AND NOT rolbypassrls
) AS approved_dev_role \gset
\if :approved_dev_role
\else
  \echo 'REFUSED: DEV role is missing or does not match the low-privilege profile.'
  \quit 3
\endif

\echo 'Enter the NEW password for dlx_yuki_wms_dev_user twice (input is hidden):'
\password dlx_yuki_wms_dev_user

\echo 'CONTROLLED_DEV_PASSWORD_RECOVERY=PASS'
