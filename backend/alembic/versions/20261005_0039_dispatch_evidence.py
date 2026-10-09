"""Append-only evidence and dispatch source serialization. No business-rule seed/backfill."""
from alembic import op
import sqlalchemy as sa
revision = "20261005_0039"
down_revision = "20261005_0038"
branch_labels = None
depends_on = None
LOCK = 748320610050039
TABLES = ("users", "user_warehouse_scopes", "user_customer_scopes", "loads", "outbound_orders", "outbound_inventory_allocations", "fba_shipments", "fba_inventory_allocations", "inventory_lots", "inventory_lot_locations", "inventory_transactions", "load_allocations", "load_dispatch_plans", "load_dispatch_plan_lines", "stage_transactions", "load_verification_transactions", "picking_lists", "picking_list_items", "bols", "bol_items", "operational_documents", "document_events", "operational_exceptions", "operational_exception_events", "container_trackings", "work_orders", "work_order_events", "warehouse_locations", "warehouses", "customers", "inbound_records", "dispatch_evidence_policies", "dispatch_evidence_reviews")

def upgrade():
    op.add_column("operational_documents", sa.Column("dispatch_business_type", sa.String(10), nullable=True))
    op.create_index("ix_operational_documents_dispatch_business_type", "operational_documents", ["dispatch_business_type"])
    op.create_check_constraint("document_dispatch_business", "operational_documents", "dispatch_business_type IS NULL OR dispatch_business_type IN ('FBA','PRIVATE')")
    from app.models.dispatch_evidence import DispatchEvidencePolicy, DispatchEvidenceReview
    for model in (DispatchEvidencePolicy, DispatchEvidenceReview): model.__table__.create(op.get_bind())
    if op.get_bind().dialect.name != "postgresql": return
    op.execute(f"CREATE FUNCTION dispatch_evidence_source_lock() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock({LOCK}); RETURN NULL; END $$")
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in TABLES:
        if table not in existing:
            raise RuntimeError(f'Missing dispatch evidence source table: {table}')
        op.execute(f'CREATE TRIGGER dispatch_evidence_source_lock BEFORE INSERT OR UPDATE OR DELETE ON "{table}" FOR EACH STATEMENT EXECUTE FUNCTION dispatch_evidence_source_lock()')
    op.execute("CREATE FUNCTION dispatch_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Dispatch evidence is append-only'; END $$")
    for table in ("dispatch_evidence_policies", "dispatch_evidence_reviews"):
        op.execute(f'CREATE TRIGGER dispatch_evidence_immutable BEFORE UPDATE OR DELETE ON "{table}" FOR EACH ROW EXECUTE FUNCTION dispatch_evidence_immutable()')

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            if table in sa.inspect(op.get_bind()).get_table_names(): op.execute(f'DROP TRIGGER IF EXISTS dispatch_evidence_source_lock ON "{table}"')
        op.execute("DROP FUNCTION dispatch_evidence_source_lock()")
        for table in ("dispatch_evidence_policies", "dispatch_evidence_reviews"): op.execute(f'DROP TRIGGER dispatch_evidence_immutable ON "{table}"')
        op.execute("DROP FUNCTION dispatch_evidence_immutable()")
    op.drop_table("dispatch_evidence_reviews"); op.drop_table("dispatch_evidence_policies")
    op.drop_constraint("document_dispatch_business", "operational_documents", type_="check")
    op.drop_index("ix_operational_documents_dispatch_business_type", table_name="operational_documents")
    op.drop_column("operational_documents", "dispatch_business_type")
