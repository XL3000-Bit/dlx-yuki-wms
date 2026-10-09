"""Pre-migration identity probe. Import performs no I/O; execution is opt-in."""
import ipaddress
import json
import os
import re


class Refused(RuntimeError):
    """Contains only a fixed, non-sensitive reason code."""


def connection_options(dsn):
    # Same parameter policy as guard.Target.connect; deliberately no manifest,
    # migration or fixture dependency. Keep this policy aligned with guard.py.
    from psycopg.conninfo import conninfo_to_dict

    options = conninfo_to_dict(dsn)
    if any(key in options for key in ("hostaddr", "service", "servicefile", "options")):
        raise Refused("target_overrides_not_allowed")
    ambient = ("PGOPTIONS", "PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR",
               "PGHOST", "PGPORT", "PGDATABASE", "PGUSER")
    if any(os.environ.get(key) for key in ambient):
        raise Refused("ambient_target_overrides_not_allowed")
    if not all(options.get(key) for key in ("host", "port", "dbname", "user")):
        raise Refused("explicit_host_port_database_role_required")
    if any("," in options[key] for key in ("host", "port")):
        raise Refused("multiple_targets_not_allowed")
    try:
        address = str(ipaddress.ip_address(options["host"]))
        port = int(options["port"])
    except ValueError:
        raise Refused("literal_ip_and_numeric_port_required") from None
    if not 1 <= port <= 65535:
        raise Refused("invalid_port")
    options["host"] = address
    options["connect_timeout"] = "5"
    options["application_name"] = "phase113_preflight"
    return options


def safe_failure(stage, exc):
    state = getattr(exc, "sqlstate", None)
    if not isinstance(state, str) or not re.fullmatch(r"[0-9A-Z]{5}", state):
        state = None
    categories = {"28P01": "authentication_failed", "28000": "authorization_failed",
                  "3D000": "target_database_missing", "42501": "permission_denied",
                  "57014": "query_cancelled", "55P03": "lock_unavailable"}
    return {"status": "failed", "stage": stage,
            "exception_type": type(exc).__name__, "sqlstate": state,
            "reason": str(exc) if isinstance(exc, Refused)
            else categories.get(state, "unclassified_details_withheld"),
            "isolation_status": "NOT_VERIFIED"}


def main():
    conn = None
    stage = "configuration"
    result = None
    exit_code = 2
    try:
        dsn = os.environ.get("PHASE113_PG_DSN")
        if not dsn or not dsn.strip():
            raise Refused("PHASE113_PG_DSN_required")
        options = connection_options(dsn)
        import psycopg

        stage = "connection"
        conn = psycopg.connect(**options)
        stage = "readonly_query"
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '5s'")
        conn.execute("SET LOCAL lock_timeout = '5s'")
        row = conn.execute("""SELECT current_database(), current_user,
            inet_server_addr()::text, inet_server_port(),
            (SELECT oid::bigint FROM pg_database WHERE datname=current_database()),
            current_setting('server_version_num')::integer,
            current_setting('server_version')""").fetchone()
        if row is None:
            raise Refused("identity_result_missing")
        if (row[0] != options["dbname"] or row[1] != options["user"]
                or str(ipaddress.ip_address(row[2])) != options["host"]
                or row[3] != int(options["port"])):
            raise Refused("actual_identity_differs_from_explicit_target")
        permissions = conn.execute("""SELECT pg_get_userbyid(d.datdba),
            r.rolcreatedb, r.rolsuper,
            has_database_privilege(current_user, d.oid, 'CONNECT'),
            has_database_privilege(current_user, d.oid, 'CREATE'),
            has_database_privilege(current_user, d.oid, 'TEMP'),
            (SELECT has_schema_privilege(current_user, n.oid, 'CREATE')
             FROM pg_namespace n WHERE n.nspname = 'public')
            FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
            WHERE d.datname = current_database()""").fetchone()
        if permissions is None:
            raise Refused("permission_result_missing")
        keys = ("database", "role", "address", "port", "database_oid", "server_version_num")
        result = {"status": "identity_verified", "identity": dict(zip(keys, row[:6])),
                  "server_version": row[6],
                  "permissions": dict(zip(("database_owner", "role_createdb", "role_superuser",
                                           "database_connect", "database_create", "database_temp",
                                           "public_schema_create"), permissions)),
                  "isolation_status": "NOT_VERIFIED",
                  "notice": "Identity and privileges do not establish ownership authorization or isolation"}
        exit_code = 0
    except Exception as exc:
        result = safe_failure(stage, exc)
    finally:
        if conn is not None:
            try:
                # Closing rolls back the read-only transaction; never commit.
                conn.close()
            except Exception as exc:
                result = safe_failure("connection_close", exc)
                exit_code = 2
    print(json.dumps(result, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
