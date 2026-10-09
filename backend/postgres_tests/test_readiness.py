"""Real PostgreSQL reads and actual service calls; no project imports at import time."""
import unittest


class ReadinessTests(unittest.TestCase):
    target = None

    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import NullPool
        from app.models import User
        from app.services.load_dispatch_readiness import dispatch_readiness

        self.engine = create_engine("postgresql+psycopg://", creator=self.target.connect,
                                    poolclass=NullPool)
        self.addCleanup(self.engine.dispose)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.db.close)
        self.f = self.target.manifest["fixtures"]
        self.service = dispatch_readiness
        self.users = {}
        for key in ("allowed_user_id", "warehouse_denied_user_id", "customer_denied_user_id"):
            user = self.db.get(User, self.f[key])
            self.assertIsNotNone(user, "Reviewed fixture user is missing")
            list(user.warehouses)
            list(user.customers)
            self.users[key] = user
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.loads import router
        from app.api.deps import get_current_user, get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        self.active_user = self.users["allowed_user_id"]

        def session_dependency():
            yield self.db

        app.dependency_overrides[get_db] = session_dependency
        app.dependency_overrides[get_current_user] = lambda: self.active_user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def get_readiness(self, load_id=None, user_key="allowed_user_id"):
        self.active_user = self.users[user_key]
        target_id = self.f["load_id"] if load_id is None else load_id
        return self.client.get(f"/api/v1/loads/{target_id}/dispatch-readiness")

    def check(self, load_id=None, user_key="allowed_user_id"):
        return self.service(self.db, self.users[user_key],
                            load_id if load_id is not None else self.f["load_id"])

    def test_no_plan_and_missing_evidence_are_not_ready(self):
        response = self.get_readiness(self.f["no_plan_load_id"])
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIsNone(result["plan_id"])
        self.assertFalse(result["ready"])
        reasons = {item["reason_code"] for item in result["checks"]}
        self.assertIn("FINAL_PLAN_MISSING", reasons)
        self.assertIn("LEGACY_WRITERS_NOT_INTEGRATED", reasons)
        self.assertIn("DOCUMENT_RULES_NOT_CONFIGURED", reasons)
        self.assertIn("DISPATCH_APPROVAL_MISSING", reasons)

    def test_actual_scope_denials_are_generic(self):
        from app.models import Load
        # Positive control prevents a nonexistent fixture masking scope failures.
        self.assertIsNotNone(self.db.get(Load, self.f["load_id"]))
        self.assertEqual(self.get_readiness().status_code, 200)
        for key in ("warehouse_denied_user_id", "customer_denied_user_id"):
            with self.subTest(scope=key):
                response = self.get_readiness(user_key=key)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Load not found"})
        response = self.get_readiness(-1)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Load not found"})

    def test_missing_structure_is_technical_error(self):
        from sqlalchemy import text
        # Transaction-local namespace exclusion; no table is dropped or altered.
        self.db.execute(text("SET LOCAL search_path = pg_catalog"))
        try:
            response = self.get_readiness()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail":
                             "Dispatch readiness is temporarily unavailable"})
        finally:
            self.db.rollback()

    def snapshot(self):
        from sqlalchemy import text
        names = self.db.execute(text("SELECT tablename FROM pg_tables "
                                     "WHERE schemaname='public' ORDER BY tablename")).scalars()
        quote = self.engine.dialect.identifier_preparer.quote
        result = {}
        for name in list(names):
            result[name] = self.db.execute(text(
                "SELECT count(*), md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' "
                "ORDER BY md5(row_to_json(t)::text)), '')) FROM public."
                + quote(name) + " AS t")).one()
        return result

    def test_readiness_preserves_all_public_table_contents(self):
        before = self.snapshot()
        self.assertEqual(self.get_readiness().status_code, 200)
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.dirty)
        self.assertFalse(self.db.deleted)
        self.assertEqual(before, self.snapshot())

    def test_existing_dispatch_is_not_gated_by_readiness(self):
        from app.models import Load

        load_id = self.f["legacy_ready_load_id"]
        load = self.db.get(Load, load_id)
        self.assertIsNotNone(load)
        self.assertEqual(load.status, "READY")
        response = self.get_readiness(load_id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])
        response = self.client.post(f"/api/v1/loads/{load_id}/status",
                                    json={"status": "DISPATCHED"})
        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.get(Load, load_id).status, "DISPATCHED")

    def test_quantities_cannot_offset_other_lines_or_units(self):
        from decimal import Decimal
        from types import SimpleNamespace
        from app.models import Load
        from app.services.load_dispatch_readiness import evaluate
        load = self.db.get(Load, self.f["load_id"])
        self.assertIsNotNone(load)
        # Actual evaluator, explicit synthetic inputs; this part is not a DB constraint claim.
        plan = SimpleNamespace(id=1, version=1, content_revision=1, status="FINAL")
        allocations = [SimpleNamespace(id=i, carton_qty=Decimal(100), pallet_qty=Decimal(10))
                       for i in (1, 2)]
        for quantities in (((101, 1), (99, 9)), ((60, 11), (40, 9))):
            lines = [SimpleNamespace(id=i, allocation_id=i, carton_qty=Decimal(c), pallet_qty=Decimal(p))
                     for i, (c, p) in enumerate(quantities, 1)]
            result = evaluate(load, plan, lines, allocations)
            self.assertFalse(result.ready)
            self.assertTrue(any(item.status == "BLOCKED" and
                                item.reason_code == "QUANTITY_OUTSIDE_ALLOCATION"
                                for item in result.checks))
