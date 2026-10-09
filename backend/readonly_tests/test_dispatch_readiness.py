"""Run directly with Python, never through the database-backed pytest suite."""
import importlib.abc
import socket
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class NoDatabaseImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ("app.db.session", "app.core.config", "app.api.deps", "app.main",
                   "conftest", "psycopg", "psycopg2", "sqlite3")
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("Database initialization import forbidden: " + fullname)
        return None


sys.meta_path.insert(0, NoDatabaseImports())
import sqlalchemy
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList, False_, Grouping


def forbidden(*args, **kwargs):
    raise AssertionError("Database connection or schema initialization forbidden")


guards = [patch.object(socket.socket, "connect", forbidden),
          patch.object(Engine, "connect", forbidden),
          patch.object(sqlalchemy.MetaData, "create_all", forbidden)]
for guard in guards:
    guard.start()

from fastapi import HTTPException
from app.services.load_dispatch_readiness import dispatch_readiness, evaluate, overall_ready
from app.schemas.load_dispatch import ReadinessCheck, ReadinessStatus
from app.models import Load, OutboundOrder
from app.models.load_dispatch import LoadAllocation, LoadDispatchPlan, LoadDispatchPlanLine
from app.models.outbound import OutboundInventoryAllocation
from app.models.user import ScopeMode, UserRole


def matches(expression, row):
    if isinstance(expression, False_):
        return False
    if isinstance(expression, Grouping):
        return matches(expression.element, row)
    if isinstance(expression, BooleanClauseList):
        if expression.operator is not operators.and_:
            raise AssertionError("Unsupported predicate")
        return all(matches(clause, row) for clause in expression.clauses)
    actual = getattr(row, expression.left.key)
    expected = expression.right.value
    if expression.operator is operators.eq:
        return actual == expected
    if expression.operator is operators.in_op:
        return actual in expected
    raise AssertionError("Unsupported predicate")


class ReadOnlySession:
    """Evaluate the actual generated scope predicates; reject every other operation."""
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail
        self.reads = 0
        self.inside_no_autoflush = False

    @property
    @contextmanager
    def no_autoflush(self):
        self.inside_no_autoflush = True
        try:
            yield
        finally:
            self.inside_no_autoflush = False

    def query(self, statement):
        assert self.inside_no_autoflush
        self.reads += 1
        if self.fail:
            raise SQLAlchemyError("synthetic confidential query detail")
        description = statement.column_descriptions[0]
        entity = description["entity"]
        rows = [row for row in self.rows.get(entity, [])
                if all(matches(condition, row) for condition in statement._where_criteria)]
        if entity is LoadDispatchPlan:
            rows.sort(key=lambda row: row.version, reverse=True)
        if statement._limit_clause is not None:
            rows = rows[:statement._limit_clause.value]
        if description["expr"] is not entity:
            rows = [getattr(row, description["name"]) for row in rows]
        return rows

    def scalar(self, statement):
        rows = self.query(statement)
        return rows[0] if rows else None

    def scalars(self, statement):
        rows = self.query(statement)
        return NS(all=lambda: rows)

    def __getattr__(self, name):
        raise AssertionError("Unexpected session operation: " + name)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.user = NS(role=UserRole.VIEWER, warehouse_scope_mode=ScopeMode.SELECTED,
                       customer_scope_mode=ScopeMode.SELECTED,
                       warehouses=[NS(id=1)], customers=[NS(id=2)])
        self.load = NS(id=1, warehouse_id=1, status="READY")
        self.order = NS(id=10, load_id=1, warehouse_id=1, customer_id=2)
        self.allocation = NS(id=20, load_id=1, outbound_id=10,
                             inventory_allocation_id=30, carton_qty=100, pallet_qty=10)
        self.inventory = NS(id=30, outbound_order_id=10)
        self.plan = NS(id=40, load_id=1, version=1, content_revision=1, status="FINAL")
        self.line = NS(id=50, plan_id=40, allocation_id=20, carton_qty=60, pallet_qty=6)
        self.rows = {Load: [self.load], OutboundOrder: [self.order],
                     LoadAllocation: [self.allocation], OutboundInventoryAllocation: [self.inventory],
                     LoadDispatchPlan: [self.plan], LoadDispatchPlanLine: [self.line]}

    def result(self):
        return dispatch_readiness(ReadOnlySession(self.rows), self.user, 1)

    def check(self, result, key):
        return next(item for item in result.checks if item.key == key)

    def denied(self):
        with self.assertRaises(HTTPException) as raised:
            self.result()
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (404, "Load not found"))

    def test_four_statuses_and_evidence(self):
        for status in ReadinessStatus:
            item = ReadinessCheck(key="x", status=status, reason_code="RULE", reason="rule", evidence=["rule:1"])
            self.assertEqual(overall_ready([item]), status in (ReadinessStatus.PASS, ReadinessStatus.NOT_APPLICABLE))
            item.evidence = []
            self.assertFalse(overall_ready([item]))
        self.assertFalse(overall_ready([]))

    def test_missing_information_prevents_ready(self):
        item = ReadinessCheck(key="x", status="PASS", reason_code="RULE", reason="rule",
                              evidence=["rule:1"], missing_information=["approval"])
        self.assertFalse(overall_ready([item]))

    def test_contract_and_unintegrated_rules(self):
        result = self.result()
        self.assertEqual((result.plan_id, result.plan_version, result.content_revision), (40, 1, 1))
        self.assertIsNotNone(result.checked_at.tzinfo)
        self.assertFalse(result.ready)
        for key in ("allocation_trust", "writer_integration", "documents", "dispatch_approval", "exceptions"):
            self.assertEqual(self.check(result, key).status, ReadinessStatus.UNKNOWN)
            self.assertTrue(self.check(result, key).missing_information)

    def test_no_plan_is_unknown(self):
        self.rows[LoadDispatchPlan] = []
        result = self.result()
        self.assertIsNone(result.plan_id)
        self.assertEqual(self.check(result, "final_plan").reason_code, "FINAL_PLAN_MISSING")
        self.assertFalse(result.ready)

    def test_draft_is_blocked(self):
        self.plan.status = "DRAFT"
        self.assertEqual(self.check(self.result(), "final_plan").status, ReadinessStatus.BLOCKED)

    def test_empty_final_is_blocked(self):
        self.rows[LoadDispatchPlanLine] = []
        self.assertEqual(self.check(self.result(), "final_plan").reason_code, "FINAL_PLAN_EMPTY")

    def test_non_ready_load_is_blocked(self):
        self.load.status = "DISPATCHED"
        self.assertEqual(self.check(self.result(), "load_state").status, ReadinessStatus.BLOCKED)

    def test_units_independent(self):
        self.line.pallet_qty = 11
        result = self.result()
        self.assertEqual(self.check(result, "quantity:50:carton_qty").status, ReadinessStatus.PASS)
        self.assertEqual(self.check(result, "quantity:50:pallet_qty").status, ReadinessStatus.BLOCKED)

    def test_lines_do_not_offset(self):
        other = NS(id=21, carton_qty=100, pallet_qty=10)
        lines = [NS(id=50, allocation_id=20, carton_qty=101, pallet_qty=6),
                 NS(id=51, allocation_id=21, carton_qty=1, pallet_qty=6)]
        result = evaluate(self.load, self.plan, lines, [self.allocation, other])
        self.assertEqual(self.check(result, "quantity:50:carton_qty").status, ReadinessStatus.BLOCKED)
        self.assertEqual(self.check(result, "quantity:51:carton_qty").status, ReadinessStatus.PASS)

    def test_negative_quantity_is_blocked(self):
        self.line.carton_qty = -1
        self.assertEqual(self.check(self.result(), "quantity:50:carton_qty").status, ReadinessStatus.BLOCKED)

    def test_warehouse_denied(self):
        self.user.warehouses = [NS(id=9)]
        self.denied()

    def test_customer_denied(self):
        self.user.customers = [NS(id=9)]
        self.denied()

    def test_partial_visibility_denied(self):
        self.rows[OutboundOrder].append(NS(id=11, load_id=1, warehouse_id=1, customer_id=9))
        self.denied()

    def test_order_warehouse_denied(self):
        self.order.warehouse_id = 9
        self.denied()

    def test_visible_other_warehouse_is_still_denied(self):
        self.user.warehouses.append(NS(id=9))
        self.order.warehouse_id = 9
        self.denied()

    def test_visible_inventory_for_other_order_is_denied(self):
        self.rows[OutboundOrder].append(NS(id=11, load_id=None, warehouse_id=1, customer_id=2))
        self.inventory.outbound_order_id = 11
        self.denied()

    def test_admin_cannot_bypass_relationship_checks(self):
        self.user.role = UserRole.ADMIN
        self.inventory.outbound_order_id = 11
        self.denied()

    def test_foreign_allocation_denied(self):
        self.line.allocation_id = 99
        self.denied()

    def test_missing_inventory_object_denied(self):
        self.rows[OutboundInventoryAllocation] = []
        self.denied()

    def test_query_failure_is_safe_technical_error(self):
        with self.assertRaises(HTTPException) as raised:
            dispatch_readiness(ReadOnlySession(self.rows, fail=True), self.user, 1)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Dispatch readiness is temporarily unavailable")

    def test_only_reads_without_autoflush(self):
        db = ReadOnlySession(self.rows)
        dispatch_readiness(db, self.user, 1)
        self.assertGreater(db.reads, 0)
        self.assertFalse(db.inside_no_autoflush)


if __name__ == "__main__":
    unittest.main()
