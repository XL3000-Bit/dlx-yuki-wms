"""Migration-backed PostgreSQL constraints; imported without application setup."""
import threading
import time
import unittest
import uuid


class StructureTests(unittest.TestCase):
    target = None

    def setUp(self):
        self.db = self.target.connect()
        self.addCleanup(self.db.close)
        self.f = self.target.manifest["fixtures"]

    def allocation(self, db):
        return db.execute("""INSERT INTO load_allocations
            (load_id,outbound_id,inventory_allocation_id,carton_qty,pallet_qty,operation_id)
            VALUES (%s,%s,%s,100,10,%s) RETURNING id""",
            (self.f["load_id"], self.f["outbound_id"],
             self.f["inventory_allocation_id"], uuid.uuid4().hex)).fetchone()[0]

    def draft(self, db):
        return db.execute("""INSERT INTO load_dispatch_plans
            (load_id,version,status,content_revision)
            SELECT %s,COALESCE(MAX(version),0)+1,'DRAFT',0
            FROM load_dispatch_plans WHERE load_id=%s RETURNING id""",
            (self.f["load_id"], self.f["load_id"])).fetchone()[0]

    def line(self, db, plan, allocation, cartons=60, pallets=6):
        return db.execute("""INSERT INTO load_dispatch_plan_lines
            (plan_id,allocation_id,carton_qty,pallet_qty)
            VALUES (%s,%s,%s,%s) RETURNING id""",
            (plan, allocation, cartons, pallets)).fetchone()[0]

    def rejected(self, sql, params, states=("23514",)):
        self.db.execute("SAVEPOINT expected_rejection")
        try:
            self.db.execute(sql, params)
        except Exception as exc:
            self.assertIn(getattr(exc, "sqlstate", None), states)
        else:
            self.fail("Database accepted a forbidden mutation")
        finally:
            self.db.execute("ROLLBACK TO SAVEPOINT expected_rejection")

    def test_quantities_independent(self):
        allocation = self.allocation(self.db)
        plan = self.draft(self.db)
        for cartons, pallets in ((-1, 6), (60, -1), (101, 1), (1, 11)):
            with self.subTest(cartons=cartons, pallets=pallets):
                self.rejected("""INSERT INTO load_dispatch_plan_lines
                    (plan_id,allocation_id,carton_qty,pallet_qty)
                    VALUES (%s,%s,%s,%s)""", (plan, allocation, cartons, pallets))
        self.line(self.db, plan, allocation)

    def test_allocation_immutable(self):
        allocation = self.allocation(self.db)
        self.rejected("UPDATE load_allocations SET carton_qty=99 WHERE id=%s", (allocation,))
        self.rejected("DELETE FROM load_allocations WHERE id=%s", (allocation,))

    def test_spare_quantity_on_another_line_cannot_offset_excess(self):
        first = self.allocation(self.db)
        second = self.allocation(self.db)
        plan = self.draft(self.db)
        self.line(self.db, plan, second, 1, 1)
        for cartons, pallets in ((101, 1), (1, 11)):
            with self.subTest(cartons=cartons, pallets=pallets):
                self.rejected("""INSERT INTO load_dispatch_plan_lines
                    (plan_id,allocation_id,carton_qty,pallet_qty)
                    VALUES (%s,%s,%s,%s)""", (plan, first, cartons, pallets))

    def test_line_change_before_finalization_is_in_final_snapshot(self):
        allocation = self.allocation(self.db)
        plan = self.draft(self.db)
        line = self.line(self.db, plan, allocation)
        self.db.commit()
        self.db.execute("UPDATE load_dispatch_plan_lines SET carton_qty=59 WHERE id=%s", (line,))
        started = threading.Event()
        outcome = {}

        def finalize():
            conn = None
            try:
                conn = self.target.connect()
                outcome["pid"] = conn.info.backend_pid
                started.set()
                conn.execute("UPDATE load_dispatch_plans SET status='FINAL' WHERE id=%s", (plan,))
                conn.commit()
                outcome["state"] = "COMMITTED"
            except Exception as exc:
                outcome["state"] = getattr(exc, "sqlstate", None)
            finally:
                started.set()
                if conn is not None:
                    conn.close()

        worker = threading.Thread(target=finalize, daemon=True)
        worker.start()
        try:
            self.assertTrue(started.wait(7), "Worker did not reach connection boundary")
            self.assertIn("pid", outcome, "Worker target verification failed")
            deadline = time.monotonic() + 3
            blocked = False
            while time.monotonic() < deadline:
                blocked = self.db.execute("SELECT %s = ANY(pg_blocking_pids(%s))",
                    (self.db.info.backend_pid, outcome["pid"])).fetchone()[0]
                if blocked:
                    break
                started.wait(0.02) if not started.is_set() else threading.Event().wait(0.02)
            self.assertTrue(blocked, "Finalizer did not wait for the line transaction")
            self.db.commit()
        finally:
            self.db.rollback()
            worker.join(10)
        self.assertFalse(worker.is_alive(), "Worker exceeded bounded completion time")
        self.assertEqual(outcome.get("state"), "COMMITTED")
        self.assertEqual(self.db.execute("SELECT status FROM load_dispatch_plans WHERE id=%s",
            (plan,)).fetchone()[0], "FINAL")
        self.assertEqual(self.db.execute("SELECT carton_qty,pallet_qty FROM load_dispatch_plan_lines WHERE id=%s",
            (line,)).fetchone(), (59, 6))
        self.rejected("UPDATE load_dispatch_plan_lines SET carton_qty=58 WHERE id=%s", (line,))

    def test_final_plan_and_lines_immutable(self):
        allocation = self.allocation(self.db)
        self.rejected("""INSERT INTO load_dispatch_plans
            (load_id,version,status,content_revision) VALUES (%s,2147483647,'FINAL',0)""",
            (self.f["load_id"],))
        plan = self.draft(self.db)
        line = self.line(self.db, plan, allocation)
        second = self.allocation(self.db)
        self.db.execute("UPDATE load_dispatch_plans SET status='FINAL' WHERE id=%s", (plan,))
        for sql, params in (
            ("UPDATE load_dispatch_plans SET content_revision=999 WHERE id=%s", (plan,)),
            ("UPDATE load_dispatch_plans SET status='DRAFT' WHERE id=%s", (plan,)),
            ("DELETE FROM load_dispatch_plans WHERE id=%s", (plan,)),
            ("UPDATE load_dispatch_plan_lines SET carton_qty=59 WHERE id=%s", (line,)),
            ("DELETE FROM load_dispatch_plan_lines WHERE id=%s", (line,)),
            ("""INSERT INTO load_dispatch_plan_lines
                (plan_id,allocation_id,carton_qty,pallet_qty) VALUES (%s,%s,1,1)""", (plan, second)),
        ):
            with self.subTest(operation=sql.split()[0]):
                self.rejected(sql, params)

    def test_finalization_blocks_late_line_change(self):
        # This test deliberately retains committed synthetic rows for inspection.
        allocation = self.allocation(self.db)
        plan = self.draft(self.db)
        line = self.line(self.db, plan, allocation)
        self.db.commit()
        self.db.execute("UPDATE load_dispatch_plans SET status='FINAL' WHERE id=%s", (plan,))
        started = threading.Event()
        outcome = {}

        def change():
            conn = None
            try:
                conn = self.target.connect()
                outcome["pid"] = conn.info.backend_pid
                started.set()
                conn.execute("UPDATE load_dispatch_plan_lines SET carton_qty=59 WHERE id=%s", (line,))
                conn.commit()
                outcome["state"] = "COMMITTED"
            except Exception as exc:
                outcome["state"] = getattr(exc, "sqlstate", None)
            finally:
                started.set()
                if conn is not None:
                    conn.close()

        worker = threading.Thread(target=change, daemon=True)
        worker.start()
        try:
            self.assertTrue(started.wait(7), "Worker did not reach connection boundary")
            self.assertIn("pid", outcome, "Worker target verification failed")
            deadline = time.monotonic() + 3
            blocked = False
            while time.monotonic() < deadline:
                blocked = self.db.execute("SELECT %s = ANY(pg_blocking_pids(%s))",
                    (self.db.info.backend_pid, outcome["pid"])).fetchone()[0]
                if blocked:
                    break
                threading.Event().wait(0.02)
            self.assertTrue(blocked, "Expected parent-row lock was not observed")
            self.db.commit()
        finally:
            self.db.rollback()
            worker.join(10)
        self.assertFalse(worker.is_alive(), "Worker exceeded bounded completion time")
        self.assertEqual(outcome.get("state"), "23514")
        self.assertEqual(self.db.execute(
            "SELECT carton_qty,pallet_qty FROM load_dispatch_plan_lines WHERE id=%s", (line,)
        ).fetchone(), (60, 6))
