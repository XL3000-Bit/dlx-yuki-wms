"""Add future allocation facts and immutable final dispatch plans; no backfill.

Existing business writers do not maintain these tables. An operation_id identifies
one future allocation fact, not a stock reservation or a completed dispatch.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260925_0037"
down_revision = "20260917_0036"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.create_table(
        "load_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outbound_id", sa.Integer(), sa.ForeignKey("outbound_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_allocation_id", sa.Integer(), sa.ForeignKey("outbound_inventory_allocations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("carton_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("pallet_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("operation_id", sa.String(64), nullable=False),
        *timestamps(),
        sa.CheckConstraint("carton_qty BETWEEN 0 AND 9999999999.99", name="cartons_valid"),
        sa.CheckConstraint("pallet_qty BETWEEN 0 AND 9999999999.99", name="pallets_valid"),
        sa.UniqueConstraint("operation_id", name="uq_load_allocation_operation"),
    )
    op.create_index("ix_load_allocations_load_id", "load_allocations", ["load_id"])
    op.create_index("ix_load_allocations_outbound_id", "load_allocations", ["outbound_id"])
    op.create_table(
        "load_dispatch_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("content_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("load_id", "version", name="uq_load_dispatch_plan_version"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'FINAL')", name="valid_status"),
        sa.CheckConstraint("content_revision >= 0", name="content_revision_nonnegative"),
    )
    op.create_index("ix_load_dispatch_plans_load_id", "load_dispatch_plans", ["load_id"])
    op.create_table(
        "load_dispatch_plan_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("load_dispatch_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("allocation_id", sa.Integer(), sa.ForeignKey("load_allocations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("carton_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("pallet_qty", sa.Numeric(12, 2), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("plan_id", "allocation_id", name="uq_load_dispatch_plan_allocation"),
        sa.CheckConstraint("carton_qty BETWEEN 0 AND 9999999999.99", name="cartons_valid"),
        sa.CheckConstraint("pallet_qty BETWEEN 0 AND 9999999999.99", name="pallets_valid"),
    )
    op.create_index("ix_load_dispatch_plan_lines_plan_id", "load_dispatch_plan_lines", ["plan_id"])
    op.execute("""
    CREATE FUNCTION guard_load_allocation_fact() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE linked_order integer;
    BEGIN
        IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'load allocation facts are immutable' USING ERRCODE = '23514';
        END IF;
        SELECT outbound_order_id INTO linked_order FROM outbound_inventory_allocations
          WHERE id = NEW.inventory_allocation_id FOR SHARE;
        IF NOT FOUND OR linked_order IS DISTINCT FROM NEW.outbound_id THEN
            RAISE EXCEPTION 'inventory allocation order mismatch' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER load_allocation_fact_guard BEFORE INSERT OR UPDATE OR DELETE
      ON load_allocations FOR EACH ROW EXECUTE FUNCTION guard_load_allocation_fact();
    """)
    op.execute("""
    CREATE FUNCTION guard_load_dispatch_plan() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION 'plans must start as drafts' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END IF;
        IF OLD.status = 'FINAL' THEN
            RAISE EXCEPTION 'final plans are immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF NEW.id IS DISTINCT FROM OLD.id OR NEW.load_id IS DISTINCT FROM OLD.load_id
           OR NEW.version IS DISTINCT FROM OLD.version THEN
            RAISE EXCEPTION 'plan identity is immutable' USING ERRCODE = '23514';
        END IF;
        IF NEW.status = 'FINAL' THEN
            IF NOT EXISTS (SELECT 1 FROM load_dispatch_plan_lines WHERE plan_id = OLD.id) THEN
                RAISE EXCEPTION 'final plan requires lines' USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                SELECT 1 FROM load_dispatch_plan_lines l
                JOIN load_allocations a ON a.id = l.allocation_id
                WHERE l.plan_id = OLD.id AND (a.load_id <> NEW.load_id
                  OR l.carton_qty > a.carton_qty OR l.pallet_qty > a.pallet_qty)
            ) THEN
                RAISE EXCEPTION 'plan line exceeds allocation or belongs to another load'
                  USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER load_dispatch_plan_guard BEFORE INSERT OR UPDATE OR DELETE
      ON load_dispatch_plans FOR EACH ROW EXECUTE FUNCTION guard_load_dispatch_plan();
    """)
    op.execute("""
    CREATE FUNCTION guard_load_dispatch_line() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_id integer; parent_load integer; fact load_allocations%ROWTYPE;
    BEGIN
        IF TG_OP = 'UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id
           OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
           OR NEW.allocation_id IS DISTINCT FROM OLD.allocation_id) THEN
            RAISE EXCEPTION 'plan line identity is immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN parent_id := OLD.plan_id;
        ELSE parent_id := NEW.plan_id; END IF;
        -- A real parent write serializes line changes with finalization, including
        -- repeatable-read transactions (which must abort on concurrent changes).
        UPDATE load_dispatch_plans SET content_revision = content_revision + 1
          WHERE id = parent_id AND status = 'DRAFT' RETURNING load_id INTO parent_load;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'line changes require a draft plan' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        SELECT * INTO fact FROM load_allocations WHERE id = NEW.allocation_id;
        IF NOT FOUND OR fact.load_id IS DISTINCT FROM parent_load
           OR NEW.carton_qty > fact.carton_qty OR NEW.pallet_qty > fact.pallet_qty THEN
            RAISE EXCEPTION 'plan line exceeds allocation or belongs to another load'
              USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER load_dispatch_line_guard BEFORE INSERT OR UPDATE OR DELETE
      ON load_dispatch_plan_lines FOR EACH ROW EXECUTE FUNCTION guard_load_dispatch_line();
    """)
    op.execute("""
    CREATE FUNCTION reject_load_dispatch_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'dispatch history cannot be truncated' USING ERRCODE = '23514';
    END $$;
    CREATE TRIGGER load_allocations_no_truncate BEFORE TRUNCATE ON load_allocations
      FOR EACH STATEMENT EXECUTE FUNCTION reject_load_dispatch_truncate();
    CREATE TRIGGER load_dispatch_plans_no_truncate BEFORE TRUNCATE ON load_dispatch_plans
      FOR EACH STATEMENT EXECUTE FUNCTION reject_load_dispatch_truncate();
    CREATE TRIGGER load_dispatch_lines_no_truncate BEFORE TRUNCATE ON load_dispatch_plan_lines
      FOR EACH STATEMENT EXECUTE FUNCTION reject_load_dispatch_truncate();
    """)


def downgrade():
    # Explicit structural rollback destroys future data; never run automatically.
    op.drop_table("load_dispatch_plan_lines")
    op.drop_table("load_dispatch_plans")
    op.drop_table("load_allocations")
    op.execute("DROP FUNCTION guard_load_dispatch_line()")
    op.execute("DROP FUNCTION guard_load_dispatch_plan()")
    op.execute("DROP FUNCTION guard_load_allocation_fact()")
    op.execute("DROP FUNCTION reject_load_dispatch_truncate()")
