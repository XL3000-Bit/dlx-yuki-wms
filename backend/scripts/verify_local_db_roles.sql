\set ON_ERROR_STOP on

\o C:/Users/XL/AppData/Local/Temp/dlx-yuki-wms-phase-a-result.txt
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname IN ('dlx_yuki_wms_dev_user', 'dlx_yuki_wms_test_user')
ORDER BY rolname;

SELECT datname, pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE datname IN ('dlx_yuki_wms_dev', 'dlx_yuki_wms_test')
ORDER BY datname;
\o

\echo 'PHASE_A_VERIFICATION_COMPLETE'
