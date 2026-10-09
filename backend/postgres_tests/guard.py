"""Explicit, fail-closed PostgreSQL test target. Import has no I/O."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path


class Refused(RuntimeError):
    pass


class Target:
    def __init__(self, dsn, manifest):
        self._dsn = dsn
        self.manifest = manifest

    @classmethod
    def from_environment(cls):
        dsn = os.environ.get("PHASE113_PG_DSN")
        path = os.environ.get("PHASE113_PG_MANIFEST")
        if not dsn or not path:
            raise Refused("Explicit target and isolation manifest required")
        try:
            if not Path(path).is_absolute():
                raise ValueError()
            manifest = json.loads(Path(path).read_text(encoding="utf-8"))
            expected = manifest["identity"]
            if set(expected) != {"database", "role", "address", "port", "database_oid", "server_version_num"}:
                raise ValueError()
            for key in ("port", "database_oid", "server_version_num"):
                if type(expected[key]) is not int or expected[key] <= 0:
                    raise ValueError()
            for key in ("database", "role", "address"):
                if not isinstance(expected[key], str) or not expected[key].strip():
                    raise ValueError()
            ipaddress.ip_address(expected["address"])
            for key in ("database", "role", "address", "port", "database_oid", "server_version_num"):
                if expected.get(key) is None:
                    raise ValueError()
            if manifest["migration_revision"] != "20260925_0037":
                raise ValueError()
            if manifest["exclusive_database"] is not True:
                raise ValueError()
            if not manifest["reviewer"] or not manifest["reviewed_at"]:
                raise ValueError()
            # Evidence is external, reviewed documentation; a flag or DB name alone
            # is insufficient. These hashes bind this run to the reviewed artifacts.
            for key in ("database_ownership", "synthetic_fixtures", "storage_isolation", "external_effects_disabled"):
                evidence = manifest["evidence"][key]
                digest = evidence["sha256"]
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError()
                if not Path(evidence["path"]).is_absolute():
                    raise ValueError()
                content = Path(evidence["path"]).read_bytes()
                if not content or hashlib.sha256(content).hexdigest() != evidence["sha256"]:
                    raise ValueError()
            fixtures = manifest["fixtures"]
            for key in ("load_id", "no_plan_load_id", "legacy_ready_load_id", "outbound_id", "inventory_allocation_id", "allowed_user_id", "warehouse_denied_user_id", "customer_denied_user_id"):
                if type(fixtures[key]) is not int or fixtures[key] <= 0:
                    raise ValueError()
            if len({fixtures[key] for key in ("load_id", "no_plan_load_id", "legacy_ready_load_id")}) != 3:
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise Refused("Invalid or incomplete reviewed isolation manifest") from None
        return cls(dsn, manifest)

    def connect(self):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict

        conn = None
        try:
            options = conninfo_to_dict(self._dsn)
            if any(key in options for key in ("hostaddr", "service", "servicefile", "options")):
                raise Refused("Connection target overrides are not allowed")
            if any(os.environ.get(key) for key in ("PGOPTIONS", "PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER")):
                raise Refused("Ambient connection overrides are not allowed")
            # One explicit TCP target, no service files, implicit hosts or retries.
            if not all(options.get(k) for k in ("host", "port", "dbname", "user")):
                raise Refused("Explicit host, port, database and role required")
            if any("," in options[k] for k in ("host", "port")) or "service" in options:
                raise Refused("Multi-target and service-file connections are not allowed")
            expected = self.manifest["identity"]
            if (str(ipaddress.ip_address(options["host"])) != str(ipaddress.ip_address(expected["address"]))
                    or int(options["port"]) != expected["port"]
                    or options["dbname"] != expected["database"]
                    or options["user"] != expected["role"]):
                raise Refused("Explicit target differs from reviewed identity")
            options["connect_timeout"] = "5"
            options["application_name"] = "phase113_integration"
            conn = psycopg.connect(**options)
            # This transaction is read-only; no fixture access or writes precede it.
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '5s'")
            row = conn.execute("""SELECT current_database(), current_user,
                inet_server_addr()::text, inet_server_port(),
                (SELECT oid::bigint FROM pg_database WHERE datname=current_database()),
                current_setting('server_version_num')::integer""").fetchone()
            keys = ("database", "role", "address", "port", "database_oid", "server_version_num")
            if dict(zip(keys, row)) != self.manifest["identity"]:
                raise Refused("Actual PostgreSQL identity does not match reviewed target")
            revisions = conn.execute("SELECT version_num FROM public.alembic_version").fetchall()
            if revisions != [(self.manifest["migration_revision"],)]:
                raise Refused("Required project migration is not installed")
            conn.rollback()
            conn.execute("SET statement_timeout = '8s'")
            conn.execute("SET lock_timeout = '5s'")
            conn.execute("SET search_path = public, pg_catalog")
            conn.commit()
            return conn
        except Exception as exc:
            if conn is not None:
                conn.close()
            if isinstance(exc, Refused):
                raise
            # Driver/SQL exception text can contain credentials or parameter values.
            raise Refused("Target verification failed; exception_type=" + type(exc).__name__) from None
